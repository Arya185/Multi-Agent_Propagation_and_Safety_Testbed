"""AnalysisRow input contract, F1 structural validation and the shared validity definition (generic; no I/O).

``AnalysisRow`` is a plain frozen record, one per episode. It does not depend on the experiment
schemas; a separate adapter (not implemented) is responsible for producing rows from experiment
results. The contract is provisional until it is approved with the adapter.

One definition of a valid observation is used everywhere (``is_complete``): the status is ``ok`` AND
all three outcomes are present. A status-ok row with a missing outcome is therefore an invalid
observation in every function (reported by validate_rows as ``missing_outcome``, counted as
incomplete by the quality reports) rather than a reason to stop.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from maps.analysis.tiers import DESCRIPTIVE, check_tier

STATUSES = ("ok", "parse_error", "call_error")
OUTCOMES = ("accepts_claim", "confidence", "estimated_roots")
UNLABELLED = "unlabelled"
RowKey = tuple[str, str, str, str, int]


@dataclass(frozen=True)
class AnalysisRow:
    """One episode. ``status != "ok"`` rows carry no outcome values.

    ``n_roots`` is the number of independent roots actually presented: 0 for a no-message
    control, ``None`` when it is unknown. ``truth_label`` is optional and label-based."""

    model_alias: str
    prompt_variant: str
    scenario_id: str
    pair_id: str
    condition_id: str
    repetition: int
    status: str
    accepts_claim: bool | None = None
    confidence: int | None = None
    estimated_roots: int | None = None
    n_messages: int = 0
    n_roots: int | None = 0
    truth_label: str | None = None

    @property
    def key(self) -> RowKey:
        return (self.model_alias, self.prompt_variant, self.scenario_id, self.condition_id, self.repetition)


def is_complete(row: AnalysisRow) -> bool:
    """The single definition of a valid observation: status ok and every outcome present."""
    return (
        row.status == "ok"
        and row.accepts_claim is not None
        and row.confidence is not None
        and row.estimated_roots is not None
    )


def truth_stratum(row: AnalysisRow) -> str:
    return row.truth_label if row.truth_label else UNLABELLED


class DuplicateRowError(ValueError):
    """Two rows share the same (model, variant, scenario, condition, repetition) key."""


class InvalidRowsError(ValueError):
    """Structural problems that make the rows unusable; ``issues`` lists them."""

    def __init__(self, issues: "tuple[Issue, ...]") -> None:
        self.issues = issues
        shown = "; ".join(f"{i.code}: {i.message}" for i in issues[:5])
        super().__init__(f"{len(issues)} structural problem(s): {shown}")


@dataclass(frozen=True)
class Issue:
    code: str
    key: RowKey | None
    message: str


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    n_rows: int
    issues: tuple[Issue, ...]
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)

    def codes(self) -> tuple[str, ...]:
        return tuple(i.code for i in self.issues)


def assert_unique_keys(rows: Iterable[AnalysisRow]) -> None:
    seen: set[RowKey] = set()
    duplicates: list[RowKey] = []
    for r in rows:
        if r.key in seen:
            duplicates.append(r.key)
        seen.add(r.key)
    if duplicates:
        raise DuplicateRowError(f"duplicate row keys: {duplicates[:5]}")


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_rows(rows: Iterable[AnalysisRow], *, check_truth_labels: bool = False) -> ValidationReport:
    """F1. Raises DuplicateRowError on duplicate keys; otherwise reports structural issues.

    With ``check_truth_labels`` a scenario whose rows carry different truth labels (unlabelled counts
    as a label) is reported as ``truth_label_inconsistent``."""
    rows = list(rows)
    assert_unique_keys(rows)
    issues: list[Issue] = []

    def add(code: str, row: AnalysisRow | None, message: str) -> None:
        issues.append(Issue(code, row.key if row is not None else None, message))

    pair_ids: dict[str, set[str]] = {}
    labels: dict[str, set[str]] = {}
    for r in rows:
        pair_ids.setdefault(r.scenario_id, set()).add(r.pair_id)
        labels.setdefault(r.scenario_id, set()).add(truth_stratum(r))
        for name in ("model_alias", "prompt_variant", "scenario_id", "pair_id", "condition_id"):
            if not isinstance(getattr(r, name), str) or not getattr(r, name):
                add("empty_identifier", r, f"{name} must be a non-empty string")
        if not _is_int(r.repetition) or r.repetition < 0:
            add("repetition_invalid", r, "repetition must be a non-negative integer")
        if not _is_int(r.n_messages) or r.n_messages < 0:
            add("n_messages_invalid", r, "n_messages must be a non-negative integer")
        if r.n_roots is not None and (not _is_int(r.n_roots) or r.n_roots < 0):
            add("n_roots_invalid", r, "n_roots must be a non-negative integer or None (unknown)")
        if r.status not in STATUSES:
            add("unknown_status", r, f"status {r.status!r} is not one of {STATUSES}")
        elif r.status == "ok":
            if r.accepts_claim is None or r.confidence is None or r.estimated_roots is None:
                add("missing_outcome", r, "an ok row needs accepts_claim, confidence and estimated_roots")
            if r.accepts_claim is not None and not isinstance(r.accepts_claim, bool):
                add("accepts_invalid", r, "accepts_claim must be a bool")
            if r.confidence is not None and (not _is_int(r.confidence) or not 0 <= r.confidence <= 100):
                add("confidence_invalid", r, "confidence must be an integer in 0..100")
            if r.estimated_roots is not None and (not _is_int(r.estimated_roots) or r.estimated_roots < 0):
                add("estimated_roots_invalid", r, "estimated_roots must be a non-negative integer")
        elif any(v is not None for v in (r.accepts_claim, r.confidence, r.estimated_roots)):
            add("outcome_on_failed_row", r, "a failed row must not carry outcome values")
    for scenario, ids in sorted(pair_ids.items()):
        if len(ids) > 1:
            add("pair_id_inconsistent", None, f"scenario {scenario} appears with pair ids {sorted(ids)}")
    if check_truth_labels:
        for scenario, found in sorted(labels.items()):
            if len(found) > 1:
                add("truth_label_inconsistent", None, f"scenario {scenario} appears with truth labels {sorted(found)}")
    return ValidationReport(ok=not issues, n_rows=len(rows), issues=tuple(issues))


def require_wellformed(
    rows: Iterable[AnalysisRow],
    *,
    tolerate: tuple[str, ...] = ("missing_outcome",),
    check_truth_labels: bool = False,
) -> list[AnalysisRow]:
    """Structural validation shared by the public functions. Returns the rows as a list.

    Raises DuplicateRowError for duplicate keys and InvalidRowsError for any structural issue whose
    code is not in ``tolerate``. By default only ``missing_outcome`` is tolerated, because such a row is
    simply an invalid observation (see ``is_complete``); the invalid-response report also tolerates
    ``unknown_status`` because reporting failures is its job."""
    rows = list(rows)
    report = validate_rows(rows, check_truth_labels=check_truth_labels)
    blocking = tuple(i for i in report.issues if i.code not in tolerate)
    if blocking:
        raise InvalidRowsError(blocking)
    return rows
