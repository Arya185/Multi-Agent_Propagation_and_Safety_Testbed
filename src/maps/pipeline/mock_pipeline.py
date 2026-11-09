"""Mock end-to-end pipeline: executor (guard, provenance, mock run, drift check, loader, integrity report) -> adapter -> descriptive analysis -> report.

ENGINEERING INTEGRATION ONLY. It uses the existing mock execution path (``run_experiment`` with the
mock client or a test double named ``"mock"``) and nothing else: no live client, no network, no model
calls. It demonstrates that synthetic records can travel through the software pipeline; it says
nothing about model behaviour, experimental results or readiness for live data collection.

Directory claiming, provenance, the single runner call, the drift check, loading and the integrity
report are delegated to ``maps.runs.executor.execute_mock_run``; this module does not repeat them.
Stages are reported in this fixed order, each stopping the pipeline on failure (nothing is retried,
resumed, appended to, cleaned up or overwritten; partial outputs are left in place for inspection):
  inputs -> run_directory -> mock_execution -> provenance -> loader_validation -> adapter ->
  descriptive_analysis -> report
The executor actually records provenance BEFORE the runner starts and checks drift after it; the
``provenance`` stage reports that whole provenance lifecycle and is presented in the fixed order above.
Analysis starts only for a run the executor reports as eligible (see ``maps.runs.integrity_report``).
The report file is written only when this pipeline claimed the run directory, so an unsafe directory
is never touched.

Analysis boundary: only structural validation, the invalid-response report, per-outcome stratified
descriptive summaries (no intervals), and, when the caller explicitly supplies condition pairs,
plain per-stratum mean differences. Everything that depends on unresolved decisions D1-D22 is
omitted and listed under ``omitted`` (hypothesis tests, multiplicity, intervals, effect sizes,
minimum-valid rules, bounds, root metrics, variant or label interactions). The adapter is called with
labels disabled, and no label field appears in the report.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from maps.adapters.episode_results import episode_results_to_rows
from maps.adapters.run_loader import load_episode_results
from maps.analysis import (
    aggregate_to_scenario,
    invalid_response_report,
    paired_scenario_diffs,
    stratified_summary,
    validate_rows,
)
from maps.config import ExperimentConfig
from maps.experiments.receiver import run_experiment
from maps.mock_client import MockClient
from maps.pipeline.report import STAGES, PipelineReport, StageRecord, write_report
from maps.runs.executor import ALLOWED_PROVENANCE_OPTIONS, execute_mock_run
from maps.runs.guard import UnsafeRunDirectoryError
from maps.scenarios import REPO_ROOT
from maps.schemas import Scenario

OUTCOMES = ("accepts_claim", "confidence", "estimated_roots")
OMITTED = (
    "hypothesis tests, significance decisions and multiplicity correction: protocol decisions unresolved",
    "confidence intervals and effect sizes: interval and effect-size decisions unresolved",
    "minimum-valid-repetition rule and missing-data sensitivity bounds: decisions unresolved",
    "root-count comparison (nominal baseline) and coverage report: depend on unresolved decisions or on a caller-supplied inventory of keys",
    "variant, scenario-population and label-stratified analyses: decisions unresolved",
)


STAGE_OF_FAILURE = {
    "pre_run_provenance": "provenance", "post_run_provenance": "provenance", "provenance_drift": "provenance",
    "runner": "mock_execution", "loader": "loader_validation", "structural_validation": "loader_validation",
    "inventory": "loader_validation", "report": "report",
}


def _safe_error(exc: BaseException) -> str:
    """A description that cannot carry record or scenario content."""
    if isinstance(exc, UnsafeRunDirectoryError):
        return str(exc)  # lists file names only
    return f"{type(exc).__name__} (message withheld)"


def _plain_summary(item, fields: Sequence[str]) -> dict:
    return {name: getattr(item, name) for name in fields}


_SUMMARY_FIELDS = (
    "model_alias", "prompt_variant", "condition_id", "outcome", "n_scenarios_total", "n_scenarios_with_value",
    "n_scenarios_missing", "n_episodes_total", "n_episodes_valid", "n_episodes_invalid", "mean", "sd",
)
_INVALID_FIELDS = (
    "model_alias", "prompt_variant", "condition_id", "n_total", "n_ok", "n_incomplete", "n_parse_error",
    "n_call_error", "n_other", "n_invalid", "invalid_rate", "n_scenarios", "n_scenarios_no_valid", "unit",
)


def _descriptive_analysis(rows, contrast_pairs) -> dict:
    validation = validate_rows(rows)
    results: dict = {
        "row_validation": {"ok": validation.ok, "n_rows": validation.n_rows},
        "invalid_response_report": [_plain_summary(r, _INVALID_FIELDS) for r in invalid_response_report(rows).rows],
        "stratified_summaries": {
            outcome: [_plain_summary(s, _SUMMARY_FIELDS) for s in stratified_summary(rows, outcome, interval_method=None)]
            for outcome in OUTCOMES
        },
        "contrasts": [],
        "omitted": list(OMITTED),
        "interpretation": "Descriptive counts and means of arbitrary mock outputs; not a statistical result.",
    }
    for condition_a, condition_b in contrast_pairs:
        for outcome in OUTCOMES:
            table = aggregate_to_scenario(rows, outcome)
            for paired in paired_scenario_diffs(table, condition_a, condition_b):
                values = paired.values
                results["contrasts"].append(
                    {
                        "model_alias": paired.model_alias,
                        "prompt_variant": paired.prompt_variant,
                        "outcome": outcome,
                        "condition_a": condition_a,
                        "condition_b": condition_b,
                        "n_scenarios_total": paired.n_scenarios_total,
                        "n_scenarios_used": paired.n_scenarios_used,
                        "n_dropped": len(paired.dropped),
                        "mean_diff": math.fsum(values) / len(values) if values else None,
                    }
                )
    return results


def run_mock_pipeline(
    cfg: ExperimentConfig,
    scenarios: Sequence[Scenario],
    out_dir: str | Path,
    run_id: str,
    *,
    expected_episode_ids: Iterable[str] | None = None,
    contrast_pairs: Sequence[tuple[str, str]] | None = None,
    client=None,
    repo_root: str | Path = REPO_ROOT,
    provenance_options: Mapping | None = None,
) -> PipelineReport:
    """Run the mock pipeline once and return its report (see the module docstring)."""
    out = Path(out_dir)
    stages: list[StageRecord] = []
    warnings: list[str] = []
    state: dict = dict(
        client_name=None, provenance_status="not_run", provenance_path=None, unavailable=(), loader_status="not_run",
        records_written=None, records_loaded=None, invalid_records=None, invalid_json=None, schema_invalid=None,
        duplicates=None, missing=None, unexpected=None, structural=False, adapter_status="not_run",
        analysis_status="not_run", analysis=None, claimed=False,
        integrity_report_path=None, integrity_status=None, analysis_eligible=False,
    )
    inventory = list(expected_episode_ids) if expected_episode_ids is not None else None

    def build(failed_stage: str | None, report_path: str | None) -> PipelineReport:
        if failed_stage is not None:
            done = {s.stage for s in stages}
            stages.extend(StageRecord(name, "skipped", "not run because an earlier stage failed") for name in STAGES if name not in done)
        return PipelineReport(
            run_id=str(run_id), pipeline_execution_status="failed" if failed_stage else "success", failed_stage=failed_stage,
            stages=tuple(sorted(stages, key=lambda st: STAGES.index(st.stage))), output_dir=str(out), report_path=report_path, client_name=state["client_name"], mock_only=True,
            provenance_status=state["provenance_status"], provenance_path=state["provenance_path"],
            unavailable_provenance_fields=tuple(state["unavailable"]), loader_status=state["loader_status"],
            inventory_supplied=inventory is not None, records_written=state["records_written"],
            records_loaded=state["records_loaded"], invalid_records=state["invalid_records"],
            invalid_json_records=state["invalid_json"], schema_invalid_records=state["schema_invalid"],
            duplicate_identifier_count=state["duplicates"], missing_expected_count=state["missing"],
            unexpected_count=state["unexpected"], structural_validation_passed=state["structural"],
            adapter_status=state["adapter_status"], descriptive_analysis_status=state["analysis_status"],
            descriptive_analysis_completed=state["analysis_status"] == "completed", descriptive_analysis=state["analysis"],
            warnings=tuple(warnings), integrity_report_path=state["integrity_report_path"],
            integrity_overall_status=state["integrity_status"], analysis_eligible=state["analysis_eligible"],
        )

    def fail(stage: str, detail: str) -> PipelineReport:
        stages.append(StageRecord(stage, "failed", detail))
        if state["claimed"]:
            planned = out / "pipeline_report.json"
            report = build(stage, str(planned))
            try:
                write_report(out, report)
                return report
            except OSError as exc:
                warnings.append(f"report file could not be written ({type(exc).__name__})")
                return build(stage, None)
        return build(stage, None)

    # 1. inputs (the executor validates the run id, client, configuration, inventory and provenance options)
    try:
        client = client if client is not None else MockClient()
        state["client_name"] = getattr(client, "name", None)
        pairs = [tuple(p) for p in (contrast_pairs or [])]
        if not all(len(p) == 2 and all(isinstance(c, str) for c in p) and p[0] != p[1] for p in pairs):
            raise ValueError("contrast_pairs must be pairs of two different condition ids")
        if set(provenance_options or {}) - ALLOWED_PROVENANCE_OPTIONS:
            raise ValueError("unsupported provenance option")
    except Exception as exc:
        return fail("inputs", _safe_error(exc) if not isinstance(exc, ValueError) else str(exc))

    # 2-5. claim, pre-run provenance, the runner (exactly once), drift check, loader, integrity report
    outcome = execute_mock_run(
        run_fn=run_experiment, cfg=cfg, scenarios=list(scenarios), client=client, run_dir=out, run_id=str(run_id),
        repo_root=repo_root, expected_episode_ids=inventory, provenance_options=provenance_options,
    )
    if outcome.status == "refused":
        if outcome.failed_stage == "run_directory":
            stages.append(StageRecord("inputs", "ok"))
        return fail(outcome.failed_stage, outcome.detail)
    state["claimed"] = True
    stages.append(StageRecord("inputs", "ok"))
    if outcome.failed_stage == "event_log":   # claimed, but the lifecycle log was unwritable: the runner never started
        return fail("run_directory", outcome.detail)
    stages.append(StageRecord("run_directory", "ok"))
    state.update(
        integrity_report_path=str(outcome.report_path) if outcome.report_path else None,
        integrity_status=outcome.report.overall_status if outcome.report else None,
        analysis_eligible=outcome.analysis_eligible,
    )
    record = outcome.provenance_record
    if record is not None:
        state["provenance_path"] = str(outcome.provenance_path)
        state["unavailable"] = tuple(record["unavailable_fields"])
        state["provenance_status"] = "partial" if record["unavailable_fields"] else "complete"
        if record["unavailable_fields"]:
            warnings.append("provenance is partial: " + ", ".join(record["unavailable_fields"]))
    warnings.extend(w for w in outcome.warnings if w not in warnings)
    ran = outcome.results is not None
    if ran:
        state["records_written"] = len(outcome.results)
    loaded = outcome.loaded
    if loaded is not None:
        rep = loaded.report
        state.update(
            records_loaded=rep.valid_records, invalid_json=len(rep.invalid_json), schema_invalid=len(rep.schema_invalid),
            invalid_records=len(rep.invalid_json) + len(rep.schema_invalid), duplicates=len(rep.duplicate_ids),
            missing=len(rep.missing_expected) if rep.expected_supplied else None,
            unexpected=len(rep.unexpected) if rep.expected_supplied else None,
        )
    loader_state = outcome.report.loader["status"] if outcome.report else "not_run"
    state["loader_status"] = loader_state
    failed = STAGE_OF_FAILURE.get(outcome.failed_stage) if outcome.failed_stage else None
    if failed == "provenance":
        state["provenance_status"] = "failed"
    if failed in ("loader_validation", "report") or (failed == "provenance" and ran):
        state["analysis_status"] = "blocked"
    # stages that completed before the failure (the failed stage itself is recorded by ``fail``)
    if record is not None and failed != "provenance":
        stages.append(StageRecord("provenance", "ok", state["provenance_status"]))
    if ran and failed != "mock_execution":
        stages.append(StageRecord("mock_execution", "ok", f"{len(outcome.results)} episode results returned by the mock run"))
    if loader_state == "passed" and failed != "loader_validation":
        stages.append(StageRecord("loader_validation", "ok", f"{loaded.report.valid_records} records loaded in written order"))
    if failed is not None:
        return fail(failed, outcome.detail)

    # 6. adapter (labels disabled)
    try:
        rows = episode_results_to_rows(loaded.require_safe(), include_truth_labels=False)
    except Exception as exc:
        state["adapter_status"] = "failed"
        state["analysis_status"] = "blocked"
        return fail("adapter", _safe_error(exc))
    state["adapter_status"] = "ok"
    state["structural"] = True
    stages.append(StageRecord("adapter", "ok", f"{len(rows)} rows"))

    # 7. descriptive analysis (generic functions only)
    try:
        state["analysis"] = _descriptive_analysis(rows, pairs)
    except Exception as exc:
        state["analysis_status"] = "failed"
        return fail("descriptive_analysis", _safe_error(exc))
    state["analysis_status"] = "completed"
    stages.append(StageRecord("descriptive_analysis", "ok"))

    # 8. report
    planned = out / "pipeline_report.json"
    stages.append(StageRecord("report", "ok"))
    final = build(None, str(planned))
    try:
        write_report(out, final)
    except OSError as exc:
        stages.pop()
        warnings.append(f"report file could not be written ({type(exc).__name__})")
        stages.append(StageRecord("report", "failed", type(exc).__name__))
        return build("report", None)
    return final

