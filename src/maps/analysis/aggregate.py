"""F2: scenario-level aggregation over valid repetitions (generic; no I/O).

Unit of analysis: the scenario x condition cell within one (model, prompt variant) stratum.
Repetitions of one scenario are averaged inside its cell and are never counted as separate scenarios.
Models and prompt variants are never pooled. A repetition is valid only if ``is_complete`` (status ok
and all outcomes present); the same definition is used by the quality reports.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from maps.analysis.rows import OUTCOMES, AnalysisRow, is_complete, require_wellformed, truth_stratum
from maps.analysis.tiers import DESCRIPTIVE, check_tier

WEIGHTINGS = ("valid_rep_mean",)
INCONSISTENT = "inconsistent"


def check_outcome(outcome: str) -> None:
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; expected one of {OUTCOMES}")


def outcome_value(row: AnalysisRow, outcome: str) -> float | None:
    """Numeric value of ``outcome`` for a valid row, or None when the row is not a valid observation."""
    check_outcome(outcome)
    if not is_complete(row):
        return None
    return float(getattr(row, outcome))  # bool -> 0.0 / 1.0


@dataclass(frozen=True)
class Cell:
    model_alias: str
    prompt_variant: str
    scenario_id: str
    pair_id: str
    condition_id: str
    outcome: str
    n_total: int
    n_valid: int
    n_invalid: int
    value: float | None
    truth_stratum: str = "unlabelled"
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


@dataclass(frozen=True)
class CellTable:
    outcome: str
    cells: tuple[Cell, ...]
    n_rows: int
    n_cells: int
    n_cells_without_value: int
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)

    def lookup(self) -> dict[tuple[str, str, str, str], Cell]:
        return {(c.model_alias, c.prompt_variant, c.scenario_id, c.condition_id): c for c in self.cells}


def aggregate_to_scenario(rows: Iterable[AnalysisRow], outcome: str, *, weighting: str = "valid_rep_mean") -> CellTable:
    """Mean of the outcome over the valid repetitions of each scenario x condition cell.

    cell value = (1 / n_valid) * sum of the valid repetition values; ``None`` when n_valid is 0
    (never imputed). The outcome name and weighting are validated before any row is touched. Raises
    DuplicateRowError on duplicate keys and InvalidRowsError on structural problems (including a
    scenario that appears with different pair ids across conditions, models or variants)."""
    check_outcome(outcome)
    if weighting not in WEIGHTINGS:
        raise ValueError(f"unsupported weighting {weighting!r}; supported: {WEIGHTINGS}")
    rows = require_wellformed(rows)
    groups: dict[tuple[str, str, str, str], list[AnalysisRow]] = {}
    for r in rows:
        groups.setdefault((r.model_alias, r.prompt_variant, r.scenario_id, r.condition_id), []).append(r)

    cells: list[Cell] = []
    for key in sorted(groups):
        rs = groups[key]
        values = [v for v in (outcome_value(r, outcome) for r in rs) if v is not None]
        strata = {truth_stratum(r) for r in rs}
        cells.append(
            Cell(
                model_alias=key[0],
                prompt_variant=key[1],
                scenario_id=key[2],
                pair_id=rs[0].pair_id,
                condition_id=key[3],
                outcome=outcome,
                n_total=len(rs),
                n_valid=len(values),
                n_invalid=len(rs) - len(values),
                value=math.fsum(values) / len(values) if values else None,
                truth_stratum=strata.pop() if len(strata) == 1 else INCONSISTENT,
            )
        )
    return CellTable(
        outcome=outcome,
        cells=tuple(cells),
        n_rows=len(rows),
        n_cells=len(cells),
        n_cells_without_value=sum(1 for c in cells if c.value is None),
    )
