"""Downstream integrity gate: persisted runs enter primary analysis only through this module.

A finished run directory holds a final ``run_integrity.json`` written by an executor. This gate reads it
(read-only; it never writes, deletes or rewrites run data) and returns ONE of five verdicts:

  ELIGIBLE    the report is well formed, belongs to this run, says the run is eligible, is internally
              consistent, and the data still match the facts it records;
  INELIGIBLE  the report is well formed and says the run is NOT eligible (failed, stopped, interrupted,
              incomplete inventory, a false eligibility condition ...);
  MISSING     there is no run directory or no report: the run is incomplete by rule;
  MALFORMED   the report or the claim record is unreadable, has missing or wrongly typed fields, or has an
              unsupported schema or version;
  MISMATCH    the report and the run disagree: a different run id than the claim record, a record count that
              differs from what is loaded now, data that no longer validate, a different expected inventory,
              or a report that contradicts itself.

Nothing is silently turned into eligibility: only ``ELIGIBLE`` admits a run, and every other verdict carries a
bounded reason code (no content, no provider text).

FILE HASH BINDING (schema version 2, v2.3.53). A version 2 report carries an ``artifacts`` block (see
``maps.runs.artifact_hashes``): byte length and raw-file SHA-256 of the allow-listed run files, plus one set digest. For
a report that claims eligibility this gate re-reads every listed file, checks its length and SHA-256 and refuses on any
difference. ``episodes.jsonl`` and the claim record are read ONCE: the bytes whose hash was checked are the bytes that are
parsed, and the file is not reopened. A version 1 (legacy) report has no hashes: it stays readable for diagnostics but is
never admitted (INELIGIBLE, ``legacy_report_without_hashes``).

TWO ACCESS PATHS, deliberately separate:
  * PRIMARY ANALYSIS: ``load_eligible_run`` returns the loaded records only for ``ELIGIBLE`` and otherwise raises
    ``IntegrityGateError`` (with the verdict and reason). It never falls back to the raw loader. The records it
    returns are parsed from the verified bytes, so there is no gap between checking and using.
  * DIAGNOSTICS: ``load_for_diagnostics`` reads whatever is on disk (partial, interrupted, stopped, legacy, or with a
    missing report) together with the gate's verdict. The result states ``analysis_admitted = False`` always.
    Diagnostic records are NOT valid experimental observations.

LIMITS, stated plainly:
  * SHA-256 here is INTEGRITY CHECKING against what the report recorded. It is not authentication: someone who can
    write the run directory can replace the data, the claim, the hashes and the report together, and nothing here
    detects that. (Comparing the set digest with a value the owner recorded OUTSIDE the repository would; that
    comparison is not implemented.) The hashes also do not show the data are truthful.
  * Files that are not listed are not bound: the event log, the legacy ``summary.json`` and ``contrast_gaps.json`` and the
    pipeline report. Unlisted files in the directory are only noted (``GateResult.notes``), never rejected.
  * A narrow race remains: a file replaced between the two ``lstat`` calls of one read, with exact timing, by someone with
    write access. Edits made after the gate returned are, of course, not covered.
  * Python cannot force a caller to use this gate. Analysis functions take plain records or rows and cannot know
    where they came from. This module is the single supported way to admit a PERSISTED run; a static test lists
    the source modules allowed to call the raw loaders.
  * ``INELIGIBLE`` and ``MISMATCH`` say nothing about statistical validity, and neither does ``ELIGIBLE``.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from pathlib import Path

from maps.adapters.run_loader import LoadResult, load_episode_results, parse_episode_results
from maps.runs.artifact_hashes import (
    ARTIFACT_REASONS, CLAIM_NAME, EPISODES_NAME, ArtifactError, list_unlisted, missing_required, validate_artifact_block, verify_entry,
)
from maps.runs.guard import CLAIM_FILENAME
from maps.runs.ids import InvalidRunIdError, validate_run_id
from maps.runs.integrity_report import ELIGIBILITY_CONDITIONS, REPORT_FILENAME, REPORT_SCHEMA

SUPPORTED_VERSIONS = frozenset({1, 2})      # 1 = legacy (diagnostic only), 2 = carries the artifact hash block
HASHED_VERSION = 2
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_CLAIM_BYTES = 64 * 1024

# Every report field this gate reads (documentation, and a test checks each exists in a real report).
FIELDS_USED = (
    "schema", "version", "run_id", "execution_mode", "directory_initialization", "analysis_eligible", "overall_status",
    "failure_stage", "eligibility", "runner", "loader", "structural_validation", "inventory_validation",
    "provenance_drift", "pre_run_provenance", "post_run_provenance", "statistical_validity_claimed", "live", "artifacts",
)
CLAIM_FIELDS_USED = ("run_id",)


class Verdict(enum.Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    MISSING = "missing"
    MALFORMED = "malformed"
    MISMATCH = "mismatch"


# Reason codes (bounded; each has a fixed message).
REASONS = {
    "ok": "the report is well formed, matches the run and the data, and says the run is eligible",
    "run_directory_missing": "the run directory does not exist",
    "report_missing": "the integrity report is missing, so the run is incomplete",
    "report_not_a_regular_file": "the integrity report path is not a regular file",
    "report_is_symlink": "the integrity report is a symbolic link",
    "report_too_large": "the integrity report is larger than the supported size",
    "report_unreadable": "the integrity report could not be read",
    "report_not_utf8": "the integrity report is not valid UTF-8 text",
    "report_not_json": "the integrity report is not valid JSON",
    "report_not_an_object": "the integrity report is not a JSON object",
    "unsupported_schema": "the integrity report has an unsupported schema name",
    "unsupported_version": "the integrity report has an unsupported schema version",
    "field_missing_or_invalid": "a required report field is missing or has the wrong type or value",
    "run_id_invalid": "the report run id is not a valid run id",
    "validity_claim_present": "the report claims statistical validity, which no executor does",
    "live_block_missing": "a live report has no live block, so a policy stop cannot be excluded",
    "claim_missing": "the run's claim record is missing",
    "claim_unreadable": "the run's claim record could not be read or is not valid JSON",
    "claim_malformed": "the run's claim record has no valid run id",
    "run_id_differs_from_claim": "the report run id differs from the run's claim record",
    "report_says_ineligible": "the report says the run is not eligible for analysis",
    "policy_stop_recorded": "the report records a policy stop",
    "interrupted": "the report records an interruption",
    "failure_stage_recorded": "the report records a failure stage",
    "overall_status_not_complete": "the report's overall status is not complete",
    "eligibility_condition_false": "an eligibility condition in the report is false",
    "inventory_not_matched": "the report's inventory check did not match the planned episodes",
    "inventory_required_but_not_performed": "a live run must record an inventory check, and none was performed",
    "report_internally_inconsistent": "the report says eligible but contradicts itself",
    "loader_count_differs": "the number of records now loaded differs from the count in the report",
    "runner_count_differs": "the report's runner result count differs from its loader count",
    "data_not_structurally_valid": "the run data no longer pass structural validation",
    "inventory_differs_from_expected": "the run data do not match the expected episode inventory supplied",
    "legacy_report_without_hashes": "the report is a legacy version 1 report without file hashes: diagnostic use only",
    **ARTIFACT_REASONS,
}


@dataclass(frozen=True)
class GateResult:
    """Outcome of the gate. ``reason`` is a code from ``REASONS``; ``message`` is its fixed text."""

    verdict: Verdict
    reason: str
    run_dir: Path
    run_id: str | None = None
    execution_mode: str | None = None
    report_path: Path | None = None
    notes: tuple[str, ...] = ()                 # bounded names of unlisted files in the run directory (never an error)
    artifact_digest: str | None = None          # the verified set digest, only for a verified version 2 report

    @property
    def message(self) -> str:
        return REASONS[self.reason]

    @property
    def eligible(self) -> bool:
        return self.verdict is Verdict.ELIGIBLE


class IntegrityGateError(RuntimeError):
    """Raised by ``load_eligible_run`` for every verdict except ELIGIBLE. Carries the ``GateResult``."""

    def __init__(self, result: GateResult):
        super().__init__(f"run is not admitted to primary analysis: {result.verdict.value} ({result.reason})")
        self.result = result


@dataclass(frozen=True)
class DiagnosticRun:
    """Whatever is on disk, for inspection only. Never an admission to analysis."""

    loaded: LoadResult
    gate: GateResult
    purpose: str = "diagnostic"

    @property
    def analysis_admitted(self) -> bool:
        return False


# -- helpers ------------------------------------------------------------------------------------------------------
def _is_bool(v) -> bool:
    return type(v) is bool


def _is_int(v) -> bool:
    return type(v) is int


def _is_str(v) -> bool:
    return type(v) is str


def _is_nonneg_int(v) -> bool:
    return _is_int(v) and v >= 0


def _reject_constant(name: str):
    raise ValueError(f"non-standard JSON constant: {name}")


def _read_json_object(path: Path, max_bytes: int, *, missing: str, symlink: str | None, not_file: str, unreadable: str, large: str | None,
                      not_utf8: str | None, not_json: str, not_object: str):
    """Read a small JSON object file; returns (data, None) or (None, reason_code)."""
    if path.is_symlink():
        return None, symlink or not_file
    if not path.exists():
        return None, missing
    if not path.is_file():
        return None, not_file
    try:
        if path.stat().st_size > max_bytes:
            return None, large or unreadable
        raw = path.read_bytes()
    except OSError:
        return None, unreadable
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, not_utf8 or not_json
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return None, not_json
    if not isinstance(data, dict):
        return None, not_object
    return data, None


def _section(report: dict, key: str, status_keys: tuple[str, ...] = ("status",)):
    section = report.get(key)
    if not isinstance(section, dict) or not all(_is_str(section.get(k)) for k in status_keys):
        return None
    return section


def _validate_structure(report: dict) -> str | None:
    """Reason code if the report is malformed, else None. Types are checked strictly (no truthiness)."""
    schema = report.get("schema")
    if not _is_str(schema):
        return "field_missing_or_invalid"
    if schema != REPORT_SCHEMA:
        return "unsupported_schema"
    version = report.get("version")
    if not _is_int(version):
        return "field_missing_or_invalid"
    if version not in SUPPORTED_VERSIONS:
        return "unsupported_version"
    run_id = report.get("run_id")
    if not _is_str(run_id):
        return "field_missing_or_invalid"
    try:
        validate_run_id(run_id)
    except InvalidRunIdError:
        return "run_id_invalid"
    if not _is_str(report.get("execution_mode")) or not report["execution_mode"]:
        return "field_missing_or_invalid"
    if report.get("directory_initialization") != "claimed" or not _is_str(report.get("directory_initialization")):
        return "field_missing_or_invalid"
    if not _is_bool(report.get("analysis_eligible")):
        return "field_missing_or_invalid"
    if report.get("overall_status") not in ("complete", "failed") or not _is_str(report.get("overall_status")):
        return "field_missing_or_invalid"
    if "failure_stage" not in report or not (report["failure_stage"] is None or _is_str(report["failure_stage"])):
        return "field_missing_or_invalid"
    eligibility = report.get("eligibility")
    if not isinstance(eligibility, dict) or not all(_is_bool(v) for v in eligibility.values()):
        return "field_missing_or_invalid"
    if not set(ELIGIBILITY_CONDITIONS) <= set(eligibility):
        return "field_missing_or_invalid"
    for key in ("runner", "structural_validation", "provenance_drift", "pre_run_provenance", "post_run_provenance"):
        if _section(report, key) is None:
            return "field_missing_or_invalid"
    runner = report["runner"]
    if "results_returned" not in runner or not (runner["results_returned"] is None or _is_nonneg_int(runner["results_returned"])):
        return "field_missing_or_invalid"
    # In a run that failed before the loader ran, these counts are legitimately null; they are strict integers
    # whenever the report says the check was performed (and are required to be integers for an eligible claim below).
    loader = _section(report, "loader")
    if loader is None or "records_loaded" not in loader or not (loader["records_loaded"] is None or _is_nonneg_int(loader["records_loaded"])):
        return "field_missing_or_invalid"
    inventory = report.get("inventory_validation")
    if not isinstance(inventory, dict) or not _is_bool(inventory.get("performed")) or not _is_str(inventory.get("status")):
        return "field_missing_or_invalid"
    for key in ("missing", "unexpected", "invalid_expected"):
        if key not in inventory or not (inventory[key] is None or _is_nonneg_int(inventory[key])):
            return "field_missing_or_invalid"
    if inventory["status"] in ("matched", "mismatch") and not all(_is_nonneg_int(inventory[k]) for k in ("missing", "unexpected", "invalid_expected")):
        return "field_missing_or_invalid"
    claimed = report.get("statistical_validity_claimed")
    if not _is_bool(claimed):
        return "field_missing_or_invalid"
    if claimed:
        return "validity_claim_present"
    if version == HASHED_VERSION:
        if "artifacts" not in report:
            return "artifacts_missing"
        block_problem = validate_artifact_block(report["artifacts"])
        if block_problem is not None:
            return block_problem
    elif "artifacts" in report:
        return "artifacts_malformed"                  # a legacy report must not carry a hash block
    live = report.get("live")
    if live is not None and not isinstance(live, dict):
        return "field_missing_or_invalid"
    if report["execution_mode"] == "live":
        if live is None:
            return "live_block_missing"
        if not _is_bool(live.get("policy_stop_recorded")):
            return "field_missing_or_invalid"
        if "wrapper_stop_reason" not in live or not (live["wrapper_stop_reason"] is None or _is_str(live["wrapper_stop_reason"])):
            return "field_missing_or_invalid"
    elif live is not None and "policy_stop_recorded" in live and not _is_bool(live["policy_stop_recorded"]):
        return "field_missing_or_invalid"
    return None


def _ineligible_reason(report: dict) -> str | None:
    """The first reason a well-formed report says the run is not eligible, else None."""
    live = report.get("live") or {}
    if live.get("policy_stop_recorded") is True or report.get("failure_stage") == "policy_stop":
        return "policy_stop_recorded"
    if report["runner"]["status"] == "interrupted" or report.get("failure_stage") == "interrupted":
        return "interrupted"
    if report["failure_stage"] is not None:
        return "failure_stage_recorded"
    if report["overall_status"] != "complete":
        return "overall_status_not_complete"
    if not all(report["eligibility"].values()):
        return "eligibility_condition_false"
    inventory = report["inventory_validation"]
    if inventory["performed"] and (inventory["status"] != "matched" or inventory["missing"] != 0 or inventory["unexpected"] != 0 or inventory["invalid_expected"] != 0):
        return "inventory_not_matched"
    if report["execution_mode"] == "live" and not inventory["performed"]:
        return "inventory_required_but_not_performed"
    if not report["analysis_eligible"]:
        return "report_says_ineligible"
    return None


def _inconsistency(report: dict) -> str | None:
    """Reason code if an eligible claim disagrees with a field it depends on, else None."""
    live = report.get("live") or {}
    runner = report["runner"]
    if runner["status"] != "completed":
        return "report_internally_inconsistent"
    if not _is_nonneg_int(report["loader"]["records_loaded"]) or not _is_nonneg_int(runner["results_returned"]):
        return "report_internally_inconsistent"
    if runner["results_returned"] != report["loader"]["records_loaded"]:
        return "runner_count_differs"
    if (
        report["pre_run_provenance"]["status"] != "recorded"
        or report["post_run_provenance"]["status"] != "collected"
        or report["provenance_drift"]["status"] != "none_detected"
        or report["loader"]["status"] != "passed"
        or report["structural_validation"]["status"] != "passed"
        or report["inventory_validation"]["status"] not in ("matched", "not_performed")
        or live.get("wrapper_stop_reason") is not None
    ):
        return "report_internally_inconsistent"
    return None


# -- the gate ---------------------------------------------------------------------------------------------------------
def _gate(run_dir, expected_episode_ids) -> tuple[GateResult, LoadResult | None]:
    run = Path(run_dir)
    report_path = run / REPORT_FILENAME

    def result(verdict: Verdict, reason: str, report: dict | None = None, *, notes: tuple[str, ...] = (), digest: str | None = None) -> GateResult:
        run_id = report.get("run_id") if report and _is_str(report.get("run_id")) else None
        mode = report.get("execution_mode") if report and _is_str(report.get("execution_mode")) else None
        return GateResult(verdict, reason, run, run_id, mode, report_path if report_path.is_file() else None, notes, digest)

    if not run.is_dir():
        return result(Verdict.MISSING, "run_directory_missing"), None
    report, reason = _read_json_object(
        report_path, MAX_REPORT_BYTES, missing="report_missing", symlink="report_is_symlink", not_file="report_not_a_regular_file",
        unreadable="report_unreadable", large="report_too_large", not_utf8="report_not_utf8", not_json="report_not_json",
        not_object="report_not_an_object",
    )
    if reason is not None:
        return result(Verdict.MISSING if reason == "report_missing" else Verdict.MALFORMED, reason), None
    problem = _validate_structure(report)
    if problem is not None:
        return result(Verdict.MALFORMED, problem, report), None

    claim, reason = _read_json_object(
        run / CLAIM_FILENAME, MAX_CLAIM_BYTES, missing="claim_missing", symlink="claim_unreadable", not_file="claim_unreadable",
        unreadable="claim_unreadable", large=None, not_utf8=None, not_json="claim_unreadable", not_object="claim_malformed",
    )
    if reason is not None:
        return result(Verdict.MALFORMED, reason, report), None
    claim_run_id = claim.get("run_id")
    try:
        validate_run_id(claim_run_id)
    except InvalidRunIdError:
        return result(Verdict.MALFORMED, "claim_malformed", report), None
    if claim_run_id != report["run_id"]:
        return result(Verdict.MISMATCH, "run_id_differs_from_claim", report), None

    if report["version"] != HASHED_VERSION:           # a legacy report has no file hashes: never admitted
        return result(Verdict.INELIGIBLE, "legacy_report_without_hashes", report), None

    why_not = _ineligible_reason(report)
    if why_not is not None:
        if report["analysis_eligible"]:
            return result(Verdict.MISMATCH, "report_internally_inconsistent", report), None   # claims eligible, yet a field says otherwise
        return result(Verdict.INELIGIBLE, why_not, report), None
    if not report["analysis_eligible"]:                          # defensive: _ineligible_reason covers it
        return result(Verdict.INELIGIBLE, "report_says_ineligible", report), None
    inconsistent = _inconsistency(report)
    if inconsistent is not None:
        return result(Verdict.MISMATCH, inconsistent, report), None

    # The report claims eligibility and is consistent: verify every listed file against its recorded hash, reading
    # the claim record and the episode file ONCE and keeping exactly those bytes.
    block = report["artifacts"]
    if block.get("errors"):
        return result(Verdict.MISMATCH, "report_internally_inconsistent", report), None   # eligible, yet some file could not be hashed
    if missing_required(block):
        return result(Verdict.MALFORMED, "artifacts_malformed", report), None
    verified: dict[str, bytes] = {}
    for entry in sorted(block["files"], key=lambda e: e["name"]):
        keep = entry["name"] in (EPISODES_NAME, CLAIM_NAME)
        try:
            read = verify_entry(run, entry, keep_bytes=keep)
        except ArtifactError as exc:
            return result(Verdict.MISMATCH, exc.reason, report), None
        if keep:
            verified[entry["name"]] = read.data
    notes = list_unlisted(run, block)
    try:                                                # the claim as verified now must still name this run
        verified_claim = json.loads(verified[CLAIM_NAME].decode("utf-8"), parse_constant=_reject_constant)
        verified_claim_id = verified_claim.get("run_id") if isinstance(verified_claim, dict) else None
        validate_run_id(verified_claim_id)
    except (ValueError, RecursionError, InvalidRunIdError):
        return result(Verdict.MALFORMED, "claim_malformed", report, notes=notes), None
    if verified_claim_id != report["run_id"]:
        return result(Verdict.MISMATCH, "run_id_differs_from_claim", report, notes=notes), None

    expected = list(expected_episode_ids) if expected_episode_ids is not None else None
    loaded = parse_episode_results(verified[EPISODES_NAME], expected_episode_ids=expected, source=str(run / EPISODES_NAME))
    if not loaded.report.structurally_valid:
        return result(Verdict.MISMATCH, "data_not_structurally_valid", report, notes=notes), loaded
    if loaded.report.valid_records != report["loader"]["records_loaded"]:
        return result(Verdict.MISMATCH, "loader_count_differs", report, notes=notes), loaded
    if expected is not None and not loaded.report.inventory_matches:
        return result(Verdict.MISMATCH, "inventory_differs_from_expected", report, notes=notes), loaded
    return result(Verdict.ELIGIBLE, "ok", report, notes=notes, digest=block["artifact_digest"]), loaded


def check_run_integrity(run_dir, *, expected_episode_ids=None) -> GateResult:
    """The gate's verdict for a persisted run directory (read-only). ``expected_episode_ids``, if supplied, is an
    explicit planned inventory that the data must match exactly."""
    return _gate(run_dir, expected_episode_ids)[0]


def load_eligible_run(run_dir, *, expected_episode_ids=None) -> LoadResult:
    """PRIMARY-ANALYSIS access: the records read at gate time, only for an ``ELIGIBLE`` run.

    Raises ``IntegrityGateError`` (carrying the verdict and reason) for every other verdict. There is no fallback to
    the raw loader."""
    gate, loaded = _gate(run_dir, expected_episode_ids)
    if gate.verdict is not Verdict.ELIGIBLE or loaded is None:
        raise IntegrityGateError(gate)
    loaded.require_safe()                                        # raises if the loader itself found a problem
    return loaded


def load_for_diagnostics(run_dir, *, expected_episode_ids=None) -> DiagnosticRun:
    """DIAGNOSTIC access: whatever is on disk plus the gate's verdict. Never an admission to analysis
    (``analysis_admitted`` is always False); the records are not valid experimental observations."""
    expected = list(expected_episode_ids) if expected_episode_ids is not None else None
    loaded = load_episode_results(run_dir, expected_episode_ids=expected)
    return DiagnosticRun(loaded=loaded, gate=check_run_integrity(run_dir, expected_episode_ids=expected))
