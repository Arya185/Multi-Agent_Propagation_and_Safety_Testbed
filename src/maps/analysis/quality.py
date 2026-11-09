"""F8-F9: invalid-response reporting and binary-outcome missingness bounds (generic).

Units are stated in every output. F8 and F9 work on episodes within a (model, prompt variant,
condition) stratum, with scenario counts alongside; ``scenario_level_bounds`` and
``contrast_bounds`` work on scenarios, the unit of the paired contrasts. All use the single validity
definition ``is_complete`` (status ok and every outcome present). Reports are descriptive (F8) or
sensitivity (F9 and the scenario-level bounds); they make no inferential claim.

``by_truth=True`` (opt-in, default off) adds the truth label to the stratum key; unlabelled rows form
an explicit ``unlabelled`` stratum and a scenario whose rows carry different labels raises.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from maps.analysis.rows import AnalysisRow, is_complete, require_wellformed, truth_stratum
from maps.analysis.tiers import DESCRIPTIVE, SENSITIVITY, check_tier

TOLERATED_FOR_REPORTS = ("missing_outcome", "unknown_status")


def _stratum_key(r: AnalysisRow, by_truth: bool) -> tuple[str, str, str, str]:
    return (r.model_alias, r.prompt_variant, truth_stratum(r) if by_truth else "", r.condition_id)


def _strata(rows: list[AnalysisRow], by_truth: bool) -> dict[tuple[str, str, str, str], list[AnalysisRow]]:
    groups: dict[tuple[str, str, str, str], list[AnalysisRow]] = {}
    for r in rows:
        groups.setdefault(_stratum_key(r, by_truth), []).append(r)
    return groups


@dataclass(frozen=True)
class InvalidRow:
    model_alias: str
    prompt_variant: str
    condition_id: str
    n_total: int
    n_ok: int  # valid observations: status ok and every outcome present
    n_parse_error: int
    n_call_error: int
    n_other: int  # unrecognized statuses
    n_invalid: int
    invalid_rate: float
    n_scenarios: int
    n_scenarios_no_valid: int
    n_incomplete: int = 0  # status ok but at least one outcome missing
    truth_stratum: str | None = None
    unit: str = "episode"
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


@dataclass(frozen=True)
class Differential:
    model_alias: str
    prompt_variant: str
    rate_by_condition: tuple[tuple[str, float], ...]
    spread: float
    condition_max: str
    condition_min: str
    truth_stratum: str | None = None
    unit: str = "episode"
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


@dataclass(frozen=True)
class InvalidReport:
    rows: tuple[InvalidRow, ...]
    differential: tuple[Differential, ...]
    n_rows_total: int
    unit: str = "episode"
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


def invalid_response_report(rows: Iterable[AnalysisRow], *, by_truth: bool = False) -> InvalidReport:
    """F8. Counts of valid / incomplete / parse_error / call_error / other rows per
    (model, variant[, truth], condition), the invalid rate (invalid = not ``is_complete``), how many
    scenarios have no valid repetition, and the spread of invalid rates across conditions inside each
    (model, variant[, truth]) (a differential-missingness diagnostic). Unit: episode."""
    rows = require_wellformed(rows, tolerate=TOLERATED_FOR_REPORTS, check_truth_labels=by_truth)
    out: list[InvalidRow] = []
    for (model, variant, truth, cond), rs in sorted(_strata(rows, by_truth).items()):
        n_ok = sum(is_complete(r) for r in rs)
        n_parse = sum(r.status == "parse_error" for r in rs)
        n_call = sum(r.status == "call_error" for r in rs)
        n_incomplete = sum(r.status == "ok" and not is_complete(r) for r in rs)
        n_other = len(rs) - n_ok - n_incomplete - n_parse - n_call
        scenarios: dict[str, int] = {}
        for r in rs:
            scenarios[r.scenario_id] = scenarios.get(r.scenario_id, 0) + is_complete(r)
        out.append(
            InvalidRow(
                model, variant, cond, len(rs), n_ok, n_parse, n_call, n_other, len(rs) - n_ok,
                (len(rs) - n_ok) / len(rs), len(scenarios), sum(1 for v in scenarios.values() if v == 0),
                n_incomplete=n_incomplete, truth_stratum=truth if by_truth else None,
            )
        )
    diffs: list[Differential] = []
    by_stratum: dict[tuple[str, str, str], list[InvalidRow]] = {}
    for row in out:
        by_stratum.setdefault((row.model_alias, row.prompt_variant, row.truth_stratum or ""), []).append(row)
    for (model, variant, truth), group in sorted(by_stratum.items()):
        rates = tuple((g.condition_id, g.invalid_rate) for g in group)
        # group is sorted by condition id, so ties resolve to the first condition in sorted order
        hi = max(group, key=lambda g: g.invalid_rate)
        lo = min(group, key=lambda g: g.invalid_rate)
        diffs.append(
            Differential(model, variant, rates, hi.invalid_rate - lo.invalid_rate, hi.condition_id, lo.condition_id,
                         truth_stratum=truth if by_truth else None)
        )
    return InvalidReport(rows=tuple(out), differential=tuple(diffs), n_rows_total=len(rows))


@dataclass(frozen=True)
class BinaryBounds:
    model_alias: str
    prompt_variant: str
    condition_id: str
    unit: str
    n_total: int
    n_valid: int
    n_invalid: int
    n_accept: int
    observed_rate: float | None
    lower: float
    upper: float
    truth_stratum: str | None = None
    tier: str = SENSITIVITY

    def __post_init__(self) -> None:
        check_tier(self.tier)


def invalid_bounds(rows: Iterable[AnalysisRow], *, by_truth: bool = False) -> tuple[BinaryBounds, ...]:
    """F9 (episode level). Worst-case bounds for the acceptance rate when invalid episodes are treated
    as all rejections (lower) or all acceptances (upper):
        lower = n_accept / n_total,   upper = (n_accept + n_invalid) / n_total,
        observed = n_accept / n_valid (None when there is no valid episode).
    Unit: episodes (repetitions are pooled; see scenario_level_bounds for the scenario unit).
    Sensitivity output only."""
    rows = require_wellformed(rows, check_truth_labels=by_truth)
    out = []
    for (model, variant, truth, cond), rs in sorted(_strata(rows, by_truth).items()):
        valid = [r for r in rs if is_complete(r)]
        n_accept = sum(1 for r in valid if r.accepts_claim)
        n_total, n_valid = len(rs), len(valid)
        out.append(
            BinaryBounds(
                model, variant, cond, "episode", n_total, n_valid, n_total - n_valid, n_accept,
                n_accept / n_valid if n_valid else None, n_accept / n_total, (n_accept + n_total - n_valid) / n_total,
                truth_stratum=truth if by_truth else None,
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# W6: scenario-level sensitivity bounds (the unit of the paired contrasts)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _CellBounds:
    scenario_id: str
    n_total: int
    n_invalid: int
    lower: float
    upper: float
    observed: float | None


def _cell_bounds(rows: list[AnalysisRow], by_truth: bool) -> dict[tuple[str, str, str, str], dict[str, _CellBounds]]:
    """(model, variant, truth, condition) -> scenario id -> bounds of that scenario's acceptance proportion."""
    groups: dict[tuple[str, str, str, str, str], list[AnalysisRow]] = {}
    for r in rows:
        model, variant, truth, cond = _stratum_key(r, by_truth)
        groups.setdefault((model, variant, truth, cond, r.scenario_id), []).append(r)
    out: dict[tuple[str, str, str, str], dict[str, _CellBounds]] = {}
    for (model, variant, truth, cond, scenario), rs in groups.items():
        valid = [r for r in rs if is_complete(r)]
        accepts = sum(1 for r in valid if r.accepts_claim)
        n_total, n_invalid = len(rs), len(rs) - len(valid)
        out.setdefault((model, variant, truth, cond), {})[scenario] = _CellBounds(
            scenario, n_total, n_invalid, accepts / n_total, (accepts + n_invalid) / n_total, accepts / len(valid) if valid else None
        )
    return out


def _mean(values: list[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


@dataclass(frozen=True)
class ScenarioBounds:
    model_alias: str
    prompt_variant: str
    condition_id: str
    n_scenarios: int
    n_scenarios_with_observed: int
    n_episodes: int
    n_invalid_episodes: int
    lower: float
    upper: float
    observed_rate: float | None
    truth_stratum: str | None = None
    unit: str = "scenario"
    tier: str = SENSITIVITY

    def __post_init__(self) -> None:
        check_tier(self.tier)


def scenario_level_bounds(rows: Iterable[AnalysisRow], *, by_truth: bool = False) -> tuple[ScenarioBounds, ...]:
    """Scenario-level sensitivity bounds for the acceptance proportion, per (model, variant[, truth], condition).

    Per scenario cell: lower = accepts / n_total, upper = (accepts + invalid) / n_total (a cell with no
    valid repetition is therefore [0, 1]); observed = accepts / n_valid (None if no valid repetition).
    Stratum values are equal-weight means over scenarios; the observed mean covers only scenarios that
    have an observed proportion. Unit: scenario. Sensitivity output only."""
    rows = require_wellformed(rows, check_truth_labels=by_truth)
    out = []
    for key, scenarios in sorted(_cell_bounds(rows, by_truth).items()):
        model, variant, truth, cond = key
        cells = [scenarios[s] for s in sorted(scenarios)]
        observed = [c.observed for c in cells if c.observed is not None]
        n_episodes = sum(c.n_total for c in cells)
        invalid = sum(c.n_invalid for c in cells)
        out.append(
            ScenarioBounds(
                model, variant, cond, len(cells), len(observed), n_episodes, invalid,
                _mean([c.lower for c in cells]), _mean([c.upper for c in cells]), _mean(observed),
                truth_stratum=truth if by_truth else None,
            )
        )
    return tuple(out)


@dataclass(frozen=True)
class ContrastBounds:
    model_alias: str
    prompt_variant: str
    condition_a: str
    condition_b: str
    n_scenarios_used: int
    n_scenarios_with_observed: int
    dropped: tuple[tuple[str, str], ...]  # (scenario id, reason)
    lower: float | None
    upper: float | None
    observed_diff: float | None
    truth_stratum: str | None = None
    unit: str = "scenario"
    tier: str = SENSITIVITY

    def __post_init__(self) -> None:
        check_tier(self.tier)


def contrast_bounds(
    rows: Iterable[AnalysisRow], condition_a: str, condition_b: str, *, by_truth: bool = False
) -> tuple[ContrastBounds, ...]:
    """Bounds on the mean scenario-level difference in acceptance proportion, a minus b.

    Per scenario with a cell in both conditions: lower = lower_a - upper_b, upper = upper_a - lower_b,
    observed = observed_a - observed_b (None if either is undefined). Strata are (model, variant[, truth]).
    A scenario missing one condition entirely is listed in ``dropped``. Unit: scenario. Sensitivity only."""
    if condition_a == condition_b:
        raise ValueError("a contrast needs two different conditions")
    rows = require_wellformed(rows, check_truth_labels=by_truth)
    cells = _cell_bounds(rows, by_truth)
    strata = sorted({(m, v, t) for (m, v, t, _c) in cells})
    out = []
    for model, variant, truth in strata:
        a = cells.get((model, variant, truth, condition_a), {})
        b = cells.get((model, variant, truth, condition_b), {})
        lowers, uppers, observed, dropped = [], [], [], []
        for scenario in sorted(set(a) | set(b)):
            if scenario not in a or scenario not in b:
                dropped.append((scenario, "a:absent" if scenario not in a else "b:absent"))
                continue
            ca, cb = a[scenario], b[scenario]
            lowers.append(ca.lower - cb.upper)
            uppers.append(ca.upper - cb.lower)
            if ca.observed is not None and cb.observed is not None:
                observed.append(ca.observed - cb.observed)
        out.append(
            ContrastBounds(
                model, variant, condition_a, condition_b, len(lowers), len(observed), tuple(dropped),
                _mean(lowers), _mean(uppers), _mean(observed), truth_stratum=truth if by_truth else None,
            )
        )
    return tuple(out)
