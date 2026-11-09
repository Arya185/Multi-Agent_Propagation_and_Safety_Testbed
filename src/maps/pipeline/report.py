"""Structured report of one mock pipeline run (plain data; no analysis code).

The report keeps five things apart on purpose:
  * ``pipeline_execution_status``  - did every software stage run to the end;
  * ``structural_validation_passed`` - did the run directory, records and adapter pass integrity checks;
  * ``descriptive_analysis_completed`` - did the generic descriptive functions run;
  * ``integrity_overall_status`` / ``analysis_eligible`` - the run executor's lifecycle verdict
    (``run_integrity.json``); a reference, not a statistical claim;
  * ``statistical_protocol_complete`` - ALWAYS False here: the statistical protocol (decisions D1-D22)
    is unresolved, and descriptive output is never a protocol result.
The report holds counts, statuses and safe error descriptions only. It never holds credentials, raw
record content, or any hidden label field.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STAGES = (
    "inputs", "run_directory", "mock_execution", "provenance", "loader_validation",
    "adapter", "descriptive_analysis", "report",
)
STATISTICAL_PROTOCOL_STATUS = "NOT COMPLETE - decisions D1-D22 unresolved; descriptive output only"
MOCK_NOTICE = (
    "SYNTHETIC MOCK RUN. Mock responses are arbitrary; this run says nothing about model behaviour, "
    "experimental results or real-data readiness."
)
REPORT_FILENAME = "pipeline_report.json"


@dataclass(frozen=True)
class StageRecord:
    stage: str
    status: str  # "ok" | "failed" | "skipped"
    detail: str = ""


@dataclass(frozen=True)
class PipelineReport:
    run_id: str
    pipeline_execution_status: str  # "success" | "failed"
    failed_stage: str | None
    stages: tuple[StageRecord, ...]
    output_dir: str
    report_path: str | None
    client_name: str | None
    mock_only: bool
    provenance_status: str  # "not_run" | "complete" | "partial" | "failed"
    provenance_path: str | None
    unavailable_provenance_fields: tuple[str, ...]
    loader_status: str  # "not_run" | "passed" | "failed"
    inventory_supplied: bool
    records_written: int | None
    records_loaded: int | None
    invalid_records: int | None
    invalid_json_records: int | None
    schema_invalid_records: int | None
    duplicate_identifier_count: int | None
    missing_expected_count: int | None
    unexpected_count: int | None
    structural_validation_passed: bool
    adapter_status: str  # "not_run" | "ok" | "failed"
    descriptive_analysis_status: str  # "not_run" | "blocked" | "completed" | "failed"
    descriptive_analysis_completed: bool
    descriptive_analysis: dict | None
    statistical_protocol_complete: bool = False
    statistical_protocol_status: str = STATISTICAL_PROTOCOL_STATUS
    warnings: tuple[str, ...] = ()
    integrity_report_path: str | None = None      # run_integrity.json written by the executor (None: not written)
    integrity_overall_status: str | None = None   # "complete" | "failed" (lifecycle and structure only)
    analysis_eligible: bool = False               # the executor's verdict; not statistical validity
    notes: tuple[str, ...] = field(default_factory=lambda: (MOCK_NOTICE,))

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"

    def raise_for_failure(self) -> None:
        if self.pipeline_execution_status != "success":
            raise PipelineFailed(f"pipeline failed at stage {self.failed_stage!r}")


class PipelineFailed(RuntimeError):
    """Raised by ``PipelineReport.raise_for_failure`` for a failed run."""


def write_report(run_dir: str | Path, report: PipelineReport, filename: str = REPORT_FILENAME) -> Path:
    """Write the report beside the run with exclusive creation (an existing file is never overwritten)."""
    target = Path(run_dir) / filename
    with open(target, "x", encoding="utf-8") as handle:
        handle.write(report.to_json())
    return target
