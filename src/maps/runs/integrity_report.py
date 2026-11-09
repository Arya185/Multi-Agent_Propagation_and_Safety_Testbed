"""Run-integrity report and lifecycle event log (plain data; no execution logic).

``run_integrity.json`` is the FINAL artifact of an executed run. A run directory that has no such file
must be treated as INCOMPLETE by every reader (the process may have been terminated, or the report
could not be written), and is never eligible for downstream analysis.

The report keeps lifecycle status apart from provenance metadata: provenance lives in
``run_provenance.json``; this file only says whether each lifecycle step happened and what it found.

What the report does and does not establish:
  * a directory claim does not prove the run completed;
  * provenance describes the environment and source files; it is a local snapshot, not proof that the
    data are truthful and not an independent trust anchor;
  * a passing loader check is structural validity only, not statistical validity or experimental
    correctness;
  * ``analysis_eligible`` means "no integrity check failed", nothing more.

The report and the event log hold statuses, counts, file names and exception CLASS NAMES only. They
never hold credentials, environment values, raw record content, scenario content, hidden labels or raw
exception messages.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from maps.logging_utils import JsonlWriter

REPORT_SCHEMA = "maps-run-integrity"
REPORT_VERSION = 1          # legacy: no artifact hashes (still readable; never admitted to primary analysis)
REPORT_VERSION_HASHED = 2   # v2.3.53: carries the ``artifacts`` hash block (see maps.runs.artifact_hashes)
REPORT_FILENAME = "run_integrity.json"
EVENTS_FILENAME = "run_events.jsonl"

EVENT_TYPES = (
    "run_claimed", "provenance_recorded", "provenance_failed", "runner_started", "runner_finished",
    "runner_failed", "post_run_validation_finished",
    # added for the live executor (v2.3.49); the mock executor never emits them
    "client_construction_failed", "policy_stop", "runner_interrupted", "integrity_report_written",
)
FAILURE_STAGES = (
    "event_log", "pre_run_provenance", "runner", "post_run_provenance", "provenance_drift", "loader",
    "structural_validation", "inventory",
)
# Failure stages used only by the live executor. Kept apart from FAILURE_STAGES so the mock report vocabulary
# is unchanged.
LIVE_FAILURE_STAGES = ("client_construction", "policy_stop", "interrupted")
# Failure stage used when an otherwise successful run's files could not all be hashed (v2.3.53). Kept apart from
# FAILURE_STAGES for the same reason.
ARTIFACT_FAILURE_STAGES = ("artifact_hashing",)
ELIGIBILITY_CONDITIONS = (
    "runner_completed", "pre_run_provenance_recorded", "post_run_provenance_collected", "no_provenance_drift",
    "loader_safe", "inventory_matches_if_supplied",
)
NOTES = (
    "A directory claim does not prove completion.",
    "Provenance is a local snapshot; it does not prove the data are truthful and is not an independent trust anchor.",
    "A passing loader check is structural validity only; it is not statistical validity.",
    "A run without this file is incomplete and not eligible for analysis.",
)


@dataclass(frozen=True)
class IntegrityReport:
    run_id: str
    execution_mode: str                       # "mock" (mock executor) or the live executor's label
    directory_initialization: str             # "claimed"
    event_log: dict                           # {"status": "complete" | "incomplete", "file": str}
    pre_run_provenance: dict                  # {"status": "recorded" | "failed" | "not_run", "file", "partial", "unavailable_fields"}
    runner: dict                              # {"status": "not_started" | "completed" | "failed" | "interrupted", "results_returned", "exception_class"}
    post_run_provenance: dict                 # {"status": "collected" | "failed" | "not_run", "partial"}
    provenance_drift: dict                    # {"status": "none_detected" | "detected" | "not_checked", "changed": [...]}
    loader: dict                              # {"status": "passed" | "failed" | "not_run", counts..., "order_matches_runner"}
    structural_validation: dict               # {"status": "passed" | "failed" | "not_run"}
    inventory_validation: dict                # {"performed": bool, "status": "matched" | "mismatch" | "not_performed" | "not_run", counts}
    analysis_eligible: bool
    eligibility: dict                         # condition name -> bool
    overall_status: str                       # "complete" | "failed"
    failure_stage: str | None
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = NOTES
    schema: str = REPORT_SCHEMA
    version: int = REPORT_VERSION
    statistical_validity_claimed: bool = field(default=False)
    # Live executor only: policy summary and budget summary. ADDITIVE: when it is None the key is omitted from
    # ``to_dict`` / ``to_json``, so a mock report is byte-for-byte what it was before this field existed.
    live: dict | None = None
    # Version 2: the artifact hash block (names, byte lengths, SHA-256, set digest). Omitted from ``to_dict`` when None,
    # so a report built without it is exactly a legacy version-1 report. SHA-256 here is integrity checking, not
    # authentication; see maps.runs.artifact_hashes for what it does and does not establish.
    artifacts: dict | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        for optional in ("live", "artifacts"):
            if data.get(optional) is None:
                data.pop(optional, None)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_integrity_report(run_dir: str | Path, report: IntegrityReport, filename: str = REPORT_FILENAME) -> Path:
    """Write the report beside the run with exclusive creation (an existing file is never overwritten)."""
    if Path(filename).name != filename:
        raise ValueError("filename must not contain path separators")
    target = Path(run_dir) / filename
    with open(target, "x", encoding="utf-8") as handle:
        handle.write(report.to_json())
    return target


class EventLog:
    """Append-only lifecycle events. Each call appends one line and never rewrites an earlier one.

    ``emit`` returns False (and remembers it) when an event could not be written, so the caller can
    decide what that means; it never raises. Event fields are fixed and safe: sequence number, event
    type, UTC time, run id and, for failures, an exception class name.
    """

    def __init__(self, run_dir: str | Path, run_id: str, now, filename: str = EVENTS_FILENAME):
        self.path = Path(run_dir) / filename
        self.filename = filename
        self._run_id = run_id
        self._now = now
        self._writer = JsonlWriter(self.path)
        self._seq = 0
        self.complete = True

    def emit(self, event: str, **fields) -> bool:
        if event not in EVENT_TYPES:
            raise ValueError("unknown lifecycle event type")
        self._seq += 1
        record = {"seq": self._seq, "event": event, "utc": self._now(), "run_id": self._run_id, **fields}
        try:
            self._writer.write(record)
        except Exception:  # an unwritable log is reported through ``complete``, never hidden
            self.complete = False
            return False
        return True
