"""Shared run lifecycle (extracted from the mock executor in v2.3.48; behavior unchanged).

``run_lifecycle`` is the integrity sequence that follows an executor's own input checks. It receives
ALREADY-VALIDATED inputs and a zero-argument ``invoke_runner`` callable, and performs, in this fixed
order (nothing is retried, resumed, appended to, cleaned up or overwritten; partial output is always left
in place for inspection):

  1. claim the run directory with the existing guard (``initialize_run_dir``);
  2. append ``run_claimed`` to ``run_events.jsonl``;
  3. record PRE-RUN provenance (``run_provenance.json``); if this fails the runner is NOT started;
  4. append ``provenance_recorded`` and ``runner_started``;
  5. call ``invoke_runner`` exactly once;
  6. collect POST-RUN provenance in memory and compare source files, the lock file and installed
     packages with the pre-run record (drift);
  7. load ``episodes.jsonl`` with the existing loader (read-only), compare the loaded order with the order
     the runner returned, check structure and, only if the caller supplied one, the inventory;
  8. append ``post_run_validation_finished`` and write ``run_integrity.json`` (exclusive creation).

FILE HASHES (v2.3.53). The report is schema version 2 and carries an ``artifacts`` block: byte length and SHA-256 of the
allow-listed run files (``maps.runs.artifact_hashes``), taken in ``finish`` after the runner has returned, failed or
been interrupted, so every hashed file is final. ``episodes.jsonl`` is read ONCE during validation; the bytes that
are parsed are the bytes that are hashed, and the file is not read again for the report. A file that exists but
cannot be hashed makes the run ineligible (stage ``artifact_hashing``) instead of being skipped. The event log,
the report, the legacy summaries and the pipeline report are not hashed.

A run is eligible for downstream analysis only if every condition in
``integrity_report.ELIGIBILITY_CONDITIONS`` holds AND the final report was written. A run directory
without ``run_integrity.json`` is incomplete. There is no override and no recovery path in this module.

What this module does NOT do: it performs no policy check of any kind. It never constructs, inspects or
names a model client, never reads configuration, credentials or the environment, and has no network or
subprocess code. ``execution_mode`` is a label copied into the report, not a permission. Each executor
owns its input policy (for example the mock executor refuses non-mock clients) and must apply it BEFORE
calling ``run_lifecycle``. Passing these checks says the software lifecycle behaved; it does not say the
data are truthful, statistically valid or ready for any real run.

The collaborators (provenance collection/writing and the event-log class) default to this module's own
imports but can be passed in, so a caller (and its tests) can substitute them at call time.

OPTIONAL HOOKS (v2.3.49). ``LifecycleHooks`` lets an executor add live-run behavior without changing the
sequence above. With ``hooks=None`` (the mock executor) nothing below applies and behavior is exactly as
described. With hooks: ``prepare`` runs after ``provenance_recorded`` and before ``runner_started`` (a failure is
stage ``client_construction``, and the runner is not started); ``classify_runner_exception`` can turn a runner
exception into a distinct stage and event (for example ``policy_stop``) and then still validates the partial
output for evidence; ``post_runner_check`` can flag a run whose runner returned normally; ``record_interruption``
records a ``KeyboardInterrupt`` raised by the runner (best effort), writes the report, and RE-RAISES the original
interrupt; ``live_block`` / ``extra_eligibility`` / ``report_event`` add report content. A hook that fails never
masks the original failure. Any recorded failure stage makes the run ineligible for analysis.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from maps.adapters.run_loader import LoadResult, load_episode_results, parse_episode_results
from maps.runs.artifact_hashes import EPISODES_NAME, ArtifactError, build_artifact_block, read_artifact
from maps.runs.guard import UnsafeRunDirectoryError, initialize_run_dir
from maps.runs.integrity_report import (
    ELIGIBILITY_CONDITIONS, EVENTS_FILENAME, REPORT_VERSION_HASHED, EventLog, IntegrityReport, write_integrity_report,
)
from maps.runs.provenance import collect_provenance, write_provenance

ALLOWED_PROVENANCE_OPTIONS = frozenset({"lock_file", "source_files", "package_provider", "include_git", "created_utc"})
_MAX_CHANGES_LISTED = 20


CLIENT_CONSTRUCTION_STAGE = "client_construction"
INTERRUPTED_STAGE = "interrupted"
ARTIFACT_HASHING_STAGE = "artifact_hashing"


class RunNotEligibleError(RuntimeError):
    """The run is not eligible for downstream analysis."""


@dataclass(frozen=True)
class RunnerFailure:
    """A hook's classification of a runner outcome: the failure stage to record, the lifecycle event to append
    (``event`` plus safe ``event_fields``) and a safe ``detail``. ``validate_partial`` asks the lifecycle to
    still read back and validate whatever the runner wrote, as evidence (the stage given here stays primary)."""

    stage: str
    event: str
    detail: str
    event_fields: Mapping = field(default_factory=dict)
    validate_partial: bool = True


@dataclass(frozen=True)
class LifecycleHooks:
    """Optional extension points for an executor (all default to None = not used; see the module docstring)."""

    prepare: Callable[[], None] | None = None
    classify_runner_exception: Callable[[Exception], RunnerFailure | None] | None = None
    post_runner_check: Callable[[], RunnerFailure | None] | None = None
    record_interruption: bool = False
    live_block: Callable[[], dict] | None = None
    extra_eligibility: Callable[[], Mapping] | None = None
    report_event: str | None = None


@dataclass(frozen=True)
class ExecutionOutcome:
    """Result of an executor (see ``run_lifecycle``).

    ``status``: ``"refused"`` (nothing was written: invalid inputs or an unsafe directory), ``"failed"``
    (the directory was claimed and a lifecycle step failed; its files are preserved) or ``"complete"``
    (every lifecycle and validation step passed; this is not statistical validity).
    ``failed_stage``: ``"inputs"``, ``"run_directory"`` or one of ``integrity_report.FAILURE_STAGES``.
    ``detail`` is a safe description (never a raw exception message, except the guard's own message,
    which lists file names only). ``results`` is what the runner returned (None if it did not return);
    ``loaded`` is the read-only loader result (None if the loader did not run or raised).
    """

    run_id: str
    run_dir: Path
    status: str
    failed_stage: str | None
    detail: str
    claimed: bool
    report: IntegrityReport | None
    report_path: Path | None
    events_path: Path | None
    provenance_record: dict | None
    provenance_path: Path | None
    results: tuple | None
    loaded: LoadResult | None
    warnings: tuple[str, ...] = ()

    @property
    def analysis_eligible(self) -> bool:
        """True only when the final report exists on disk and every eligibility condition held."""
        return self.report is not None and self.report_path is not None and self.report.analysis_eligible

    def require_eligible(self) -> tuple:
        if not self.analysis_eligible:
            raise RunNotEligibleError(f"run is not eligible for analysis (stage: {self.failed_stage or 'report'})")
        return self.loaded.require_safe()  # type: ignore[union-attr]


def provenance_drift(pre: Mapping, post: Mapping) -> list[str]:
    """Names of what differs between two provenance records: source files (by path), the lock file and
    the installed packages. Metadata such as timestamps is deliberately not compared."""
    changed: list[str] = []
    pre_files = {e["path"]: (e["sha256"], e["status"]) for e in pre["source_files"]["files"]}
    post_files = {e["path"]: (e["sha256"], e["status"]) for e in post["source_files"]["files"]}
    for path in sorted(set(pre_files) | set(post_files)):
        if pre_files.get(path) != post_files.get(path):
            changed.append(f"source_files:{path}")
    if pre["lock_file"] != post["lock_file"]:
        changed.append("lock_file")
    if pre["packages"]["items"] != post["packages"]["items"]:
        changed.append("packages")
    return changed


def validate_inventory(inventory) -> None:
    """An explicitly supplied inventory must hold non-empty strings (``None`` means none supplied)."""
    if inventory is not None and not all(isinstance(i, str) and i for i in inventory):
        raise ValueError("expected_episode_ids must be non-empty strings")


def validate_provenance_options(provenance_options: Mapping | None) -> dict:
    """The provenance options as a plain dict; unknown option names are refused."""
    options = dict(provenance_options or {})
    if set(options) - ALLOWED_PROVENANCE_OPTIONS:
        raise ValueError("unsupported provenance option")
    return options


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _withheld(exc: BaseException) -> str:
    return f"{type(exc).__name__} (message withheld)"


def refused(run_id, out: Path, stage: str, detail: str) -> ExecutionOutcome:
    """An outcome for a run refused before anything was written."""
    return ExecutionOutcome(
        run_id=str(run_id), run_dir=out, status="refused", failed_stage=stage, detail=detail, claimed=False, report=None,
        report_path=None, events_path=None, provenance_record=None, provenance_path=None, results=None, loaded=None,
    )


def _eligibility(state: dict) -> dict:
    inventory_ok = state["inventory"]["status"] in ("matched", "not_performed")
    values = {
        "runner_completed": state["runner"]["status"] == "completed",
        "pre_run_provenance_recorded": state["pre"]["status"] == "recorded",
        "post_run_provenance_collected": state["post"]["status"] == "collected",
        "no_provenance_drift": state["drift"]["status"] == "none_detected",
        "loader_safe": state["loader"]["status"] == "passed" and state["structural"]["status"] == "passed",
        "inventory_matches_if_supplied": inventory_ok and state["loader"]["status"] != "not_run",
    }
    assert tuple(values) == ELIGIBILITY_CONDITIONS
    return values


def _artifact_block(out: Path, episodes_read) -> tuple[dict, list[dict]]:
    """The report's hash block. The episode bytes read during validation are reused, never re-read."""
    precomputed = {EPISODES_NAME: episodes_read} if episodes_read is not None else {}
    try:
        return build_artifact_block(out, precomputed=precomputed)
    except Exception:  # hashing must never prevent the report; the run is then ineligible
        errors = [{"name": "*", "reason": "artifact_unreadable"}]
        from maps.runs.artifact_hashes import ALGORITHM, DIGEST_FORMAT, NOT_HASHED, artifact_set_digest

        return ({"hash_algorithm": ALGORITHM, "files": [], "artifact_digest": artifact_set_digest([]), "digest_format": DIGEST_FORMAT,
                 "not_hashed": list(NOT_HASHED), "errors": errors}, errors)


def run_lifecycle(
    *,
    run_dir: str | Path,
    run_id: str,
    execution_mode: str,
    repo_root: str | Path,
    invoke_runner: Callable,
    inventory: list | None,
    options: Mapping,
    clock: Callable[[], str] | None = None,
    collect_provenance_fn: Callable | None = None,
    write_provenance_fn: Callable | None = None,
    event_log_factory: Callable | None = None,
    hooks: LifecycleHooks | None = None,
) -> ExecutionOutcome:
    """Run ``invoke_runner`` once inside the integrity lifecycle (see the module docstring).

    ``invoke_runner()`` returns the runner's sequence of episode results. ``inventory`` (a list of episode
    ids, or None) and ``options`` (provenance options) must already be validated. ``clock`` (returns a UTC
    time string) can be injected for deterministic tests."""
    out = Path(run_dir)
    now = clock or _now_utc
    collect = collect_provenance_fn or collect_provenance
    write_prov = write_provenance_fn or write_provenance
    make_log = event_log_factory or EventLog

    # 1. claim the directory (the existing guard; never touches an unsafe directory)
    try:
        initialize_run_dir(out, run_id=run_id)
    except UnsafeRunDirectoryError as exc:
        return refused(run_id, out, "run_directory", str(exc))
    except Exception as exc:
        return refused(run_id, out, "run_directory", _withheld(exc))

    log = make_log(out, run_id, now)
    state: dict = dict(
        pre=dict(status="not_run", file=None, partial=None, unavailable_fields=[]),
        runner=dict(status="not_started", results_returned=None, exception_class=None),
        post=dict(status="not_run", partial=None),
        drift=dict(status="not_checked", changed=[], n_changed=0),
        loader=dict(status="not_run", records_loaded=None, invalid_json=None, schema_invalid=None, duplicate_ids=None,
                    order_matches_runner=None),
        structural=dict(status="not_run"),
        inventory=dict(performed=inventory is not None, status="not_run", missing=None, unexpected=None, invalid_expected=None),
        warnings=[],
    )
    held: dict = dict(pre_record=None, pre_path=None, results=None, loaded=None, episodes_read=None)

    def safe_hook(hook, fallback, label):
        """Call an optional report hook; a failing hook never masks the run's own outcome."""
        if hook is None:
            return fallback
        try:
            return hook()
        except Exception as exc:
            state["warnings"].append(f"{label} unavailable ({type(exc).__name__})")
            return fallback

    def finish(failure_stage: str | None, detail: str) -> ExecutionOutcome:
        artifacts, hash_errors = _artifact_block(out, held["episodes_read"])
        held["episodes_read"] = None
        if hash_errors and failure_stage is None:
            failure_stage, detail = ARTIFACT_HASHING_STAGE, "a run file could not be hashed"
        eligibility = _eligibility(state)
        eligibility.update(safe_hook(hooks.extra_eligibility if hooks else None, {}, "extra eligibility"))
        eligible = all(eligibility.values()) and failure_stage is None
        if not log.complete:
            state["warnings"].append("lifecycle event log is incomplete")
        live = safe_hook(hooks.live_block if hooks else None, None, "live report block")
        report = IntegrityReport(
            run_id=run_id, execution_mode=execution_mode, directory_initialization="claimed",
            event_log={"status": "complete" if log.complete else "incomplete", "file": EVENTS_FILENAME},
            pre_run_provenance=state["pre"], runner=state["runner"], post_run_provenance=state["post"],
            provenance_drift=state["drift"], loader=state["loader"], structural_validation=state["structural"],
            inventory_validation=state["inventory"], analysis_eligible=eligible, eligibility=eligibility,
            overall_status="complete" if failure_stage is None else "failed", failure_stage=failure_stage,
            warnings=tuple(state["warnings"]), live=live, artifacts=artifacts, version=REPORT_VERSION_HASHED,
        )
        report_path: Path | None = None
        try:
            report_path = write_integrity_report(out, report)
            if hooks is not None and hooks.report_event:
                log.emit(hooks.report_event)
        except Exception as exc:  # no report on disk means the run stays incomplete and ineligible
            state["warnings"].append(f"integrity report could not be written ({type(exc).__name__}); the run is incomplete")
            report = IntegrityReport(**{**report.to_dict(), "analysis_eligible": False, "warnings": tuple(state["warnings"]),
                                        "notes": report.notes})
        return ExecutionOutcome(
            run_id=run_id, run_dir=out, status="complete" if failure_stage is None and report_path else "failed",
            failed_stage=failure_stage if failure_stage else (None if report_path else "report"),
            detail=detail if failure_stage else ("" if report_path else "integrity report could not be written"),
            claimed=True, report=report, report_path=report_path, events_path=log.path,
            provenance_record=held["pre_record"], provenance_path=held["pre_path"],
            results=held["results"], loaded=held["loaded"], warnings=tuple(state["warnings"]),
        )

    # 2. claimed event (fail closed: without a log the runner is not started)
    if not log.emit("run_claimed"):
        return finish("event_log", "the lifecycle event log could not be written; the runner was not started")

    # 3. pre-run provenance (fail closed: without it the runner is not started)
    try:
        record = collect(run_id=run_id, repo_root=repo_root, **options)
        path = write_prov(out, record)
    except Exception as exc:
        state["pre"] = dict(status="failed", file=None, partial=None, unavailable_fields=[])
        log.emit("provenance_failed", phase="pre_run", exception_class=type(exc).__name__)
        return finish("pre_run_provenance", _withheld(exc))
    held.update(pre_record=record, pre_path=path)
    state["pre"] = dict(status="recorded", file=path.name, partial=bool(record["unavailable_fields"]),
                        unavailable_fields=list(record["unavailable_fields"]))
    if not log.emit("provenance_recorded", phase="pre_run"):
        return finish("event_log", "the lifecycle event log could not be written; the runner was not started")

    # 3b. optional preparation (for example building the client); the runner is not started if it fails
    if hooks is not None and hooks.prepare is not None:
        try:
            hooks.prepare()
        except Exception as exc:
            log.emit("client_construction_failed", exception_class=type(exc).__name__)
            return finish(CLIENT_CONSTRUCTION_STAGE, _withheld(exc))
    if not log.emit("runner_started"):
        return finish("event_log", "the lifecycle event log could not be written; the runner was not started")

    failure: tuple[str, str] | None = None

    def note_failure(stage: str, detail: str) -> None:
        nonlocal failure
        if failure is None:
            failure = (stage, detail)

    def validate_outputs(results: tuple | None) -> None:
        """Post-run provenance and drift, then loader / structure / order / inventory. ``results`` is None when
        the runner did not return (partial-output evidence); the loader order check is then not applicable."""
        # post-run provenance and drift (read-only; the post-run record is not written)
        try:
            post = collect(run_id=run_id, repo_root=repo_root, **options)
        except Exception as exc:
            state["post"] = dict(status="failed", partial=None)
            note_failure("post_run_provenance", _withheld(exc))
        else:
            state["post"] = dict(status="collected", partial=bool(post["unavailable_fields"]))
            changed = provenance_drift(held["pre_record"], post)
            state["drift"] = dict(status="detected" if changed else "none_detected", changed=changed[:_MAX_CHANGES_LISTED],
                                  n_changed=len(changed))
            if changed:
                note_failure("provenance_drift", "provenance drift detected in: " + ", ".join(changed[:_MAX_CHANGES_LISTED]))

        # loader, structure, order and (only when supplied) inventory
        episodes_path = out / EPISODES_NAME
        try:
            read = read_artifact(episodes_path, keep_bytes=True)
        except ArtifactError:
            read = None   # absent, not a regular file, unreadable or unstable: the path loader reports exactly what is wrong
        try:
            if read is not None:
                held["episodes_read"] = read   # the SAME bytes are parsed here and hashed into the report
                loaded = parse_episode_results(read.data, expected_episode_ids=inventory, source=str(episodes_path))
            else:
                loaded = load_episode_results(out, expected_episode_ids=inventory)
        except Exception as exc:
            state["loader"]["status"] = "failed"
            note_failure("loader", _withheld(exc))
        else:
            held["loaded"] = loaded
            rep = loaded.report
            order_ok = True if results is None else [r.spec.episode_id for r in loaded.records] == [r.spec.episode_id for r in results]
            state["loader"] = dict(
                status="passed" if rep.structurally_valid and order_ok else "failed", records_loaded=rep.valid_records,
                invalid_json=len(rep.invalid_json), schema_invalid=len(rep.schema_invalid), duplicate_ids=len(rep.duplicate_ids),
                order_matches_runner=order_ok if results is not None else None,
            )
            state["structural"] = dict(status="passed" if rep.structurally_valid else "failed")
            if rep.expected_supplied:
                state["inventory"] = dict(
                    performed=True, status="matched" if rep.inventory_matches else "mismatch", missing=len(rep.missing_expected),
                    unexpected=len(rep.unexpected), invalid_expected=len(rep.invalid_expected),
                )
            else:
                state["inventory"] = dict(performed=False, status="not_performed", missing=None, unexpected=None, invalid_expected=None)
            if not rep.structurally_valid:
                note_failure("structural_validation", "; ".join(rep.problems) or "result file failed structural validation")
            elif not order_ok:
                note_failure("loader", "loaded record order differs from the order written by the run")
            if rep.inventory_matches is False:
                note_failure("inventory", "; ".join(p for p in rep.problems if "expected" in p or "unexpected" in p) or "inventory mismatch")

    def conclude() -> ExecutionOutcome:
        """The validation event and the final report."""
        log.emit(
            "post_run_validation_finished", loader_status=state["loader"]["status"], drift_status=state["drift"]["status"],
            passed=failure is None,
        )
        return finish(failure[0] if failure else None, failure[1] if failure else "")

    def conclude_after(outcome_failure: RunnerFailure | tuple[str, str]) -> ExecutionOutcome:
        """A runner outcome that did not return normally (or a flagged one): the given stage stays primary."""
        stage, detail, validate = (
            (outcome_failure.stage, outcome_failure.detail, outcome_failure.validate_partial)
            if isinstance(outcome_failure, RunnerFailure) else (*outcome_failure, True)
        )
        note_failure(stage, detail)
        if not validate:
            return finish(stage, detail)
        validate_outputs(None)
        return conclude()

    # 4. the runner, exactly once (no retry, no resume, no append, no cleanup)
    try:
        results = tuple(invoke_runner())
    except KeyboardInterrupt as interrupt:
        if hooks is None or not hooks.record_interruption:
            raise
        # Best-effort record of the interruption, then re-raise THE ORIGINAL interrupt. A failure while
        # recording is disclosed on the interrupt (a note) and never replaces it.
        state["runner"] = dict(status="interrupted", results_returned=None, exception_class=type(interrupt).__name__)
        try:
            log.emit("runner_interrupted")
            recorded = conclude_after((INTERRUPTED_STAGE, "the run was interrupted (KeyboardInterrupt); partial output is preserved"))
            interrupt.maps_outcome = recorded  # type: ignore[attr-defined]
        except Exception as secondary:
            interrupt.add_note(f"recording the interruption failed ({type(secondary).__name__}); the run has no complete integrity report")
        raise
    except Exception as exc:
        state["runner"] = dict(status="failed", results_returned=None, exception_class=type(exc).__name__)
        classified = None
        if hooks is not None and hooks.classify_runner_exception is not None:
            try:
                classified = hooks.classify_runner_exception(exc)
            except Exception:
                classified = None  # a failing classifier falls back to the ordinary runner failure
        if classified is None:
            log.emit("runner_failed", exception_class=type(exc).__name__)
            return finish("runner", _withheld(exc))
        log.emit(classified.event, **dict(classified.event_fields))
        return conclude_after(classified)
    held["results"] = results
    state["runner"] = dict(status="completed", results_returned=len(results), exception_class=None)
    log.emit("runner_finished", results_returned=len(results))

    # 4b. a run whose runner returned normally can still be flagged (for example a policy stop on the final call)
    if hooks is not None and hooks.post_runner_check is not None:
        try:
            flagged = hooks.post_runner_check()
        except Exception as exc:
            flagged = None
            state["warnings"].append(f"post-runner check unavailable ({type(exc).__name__})")
        if flagged is not None:
            log.emit(flagged.event, **dict(flagged.event_fields))
            note_failure(flagged.stage, flagged.detail)

    # 5-6. post-run provenance and drift, then loader, structure, order and (only when supplied) inventory
    validate_outputs(results)

    # 7. validation event and the final report
    return conclude()
