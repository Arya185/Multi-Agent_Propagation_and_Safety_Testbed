"""F3-F5: paired scenario differences, matched-pair aggregation and pair completeness (generic).

Unit of analysis: the scenario (F3) and the matched pair of scenarios (F4, F5). The two conditions
of a contrast are arguments; this module does not endorse any contrast as primary. Strata are
(model, prompt variant) and are never pooled. Scenarios that cannot contribute are dropped and
listed with a reason; nothing is imputed.

Optional, descriptive only:
  * ``by_truth=True`` adds the truth label to the stratum key (F3 only). Pair aggregation (F4, F5)
    needs both members of a matched pair, which carry different labels, so it refuses truth-stratified
    input.
  * ``expected_scenarios`` (and optionally ``expected_pair_ids``) name the scenarios the design
    should contain, so that scenarios with no rows at all are reported as dropped (reason
    ``no_rows``) and scenarios seen but not expected are listed. This is a scenario-id check only,
    not a design-key contract.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from maps.analysis.aggregate import INCONSISTENT, Cell, CellTable
from maps.analysis.rows import UNLABELLED
from maps.analysis.tiers import DESCRIPTIVE, check_tier


@dataclass(frozen=True)
class ScenarioDiff:
    scenario_id: str
    pair_id: str
    diff: float
    n_valid_a: int
    n_valid_b: int


@dataclass(frozen=True)
class Dropped:
    scenario_id: str
    pair_id: str  # "" when unknown (a scenario with no rows and no expected pair id)
    reason: str  # e.g. "a:absent", "b:no_valid_observations", "a:absent;b:absent", "no_rows"


@dataclass(frozen=True)
class PairedDiffs:
    model_alias: str
    prompt_variant: str
    outcome: str
    condition_a: str
    condition_b: str
    diffs: tuple[ScenarioDiff, ...]
    dropped: tuple[Dropped, ...]
    n_scenarios_total: int
    n_scenarios_used: int
    value_scale: float = 0.0  # largest absolute cell value among the contributing cells
    truth_stratum: str | None = None  # set only when the diffs are truth-stratified
    unexpected_scenarios: tuple[str, ...] = ()
    expected_checked: bool = False
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)

    @property
    def values(self) -> tuple[float, ...]:
        return tuple(d.diff for d in self.diffs)


def _expected_map(expected: Iterable[str] | Mapping[str, str | None] | None, by_truth: bool) -> dict[str, str] | None:
    if expected is None:
        return None
    if isinstance(expected, Mapping):
        return {sid: (label if label else UNLABELLED) for sid, label in expected.items()}
    if by_truth:
        raise ValueError("with by_truth=True, expected_scenarios must be a mapping of scenario id to truth label")
    return {sid: UNLABELLED for sid in expected}


def paired_scenario_diffs(
    table: CellTable,
    condition_a: str,
    condition_b: str,
    *,
    by_truth: bool = False,
    expected_scenarios: Iterable[str] | Mapping[str, str | None] | None = None,
    expected_pair_ids: Mapping[str, str] | None = None,
) -> tuple[PairedDiffs, ...]:
    """F3. For each (model, variant[, truth]) stratum and scenario: diff = value(a) - value(b).

    A scenario contributes only if both cells exist and have at least one valid repetition. The
    scenario universe of a stratum is every scenario seen in any condition of the table plus, when
    given, the expected scenarios."""
    if condition_a == condition_b:
        raise ValueError("a contrast needs two different conditions")
    expected = _expected_map(expected_scenarios, by_truth)
    pair_lookup = dict(expected_pair_ids or {})

    seen_strata: dict[tuple[str, str, str], set[str]] = {}
    for c in table.cells:
        if by_truth and c.truth_stratum == INCONSISTENT:
            raise ValueError(f"inconsistent truth labels inside a cell of scenario {c.scenario_id}")
        seen_strata.setdefault((c.model_alias, c.prompt_variant, c.scenario_id), set()).add(c.truth_stratum)
    if by_truth:
        for (model, variant, scenario), labels in sorted(seen_strata.items()):
            if len(labels) > 1:
                raise ValueError(f"inconsistent truth labels for scenario {scenario}: {sorted(labels)}")

    strata: dict[tuple[str, str, str], dict[str, dict[str, Cell]]] = {}
    for c in table.cells:
        key = (c.model_alias, c.prompt_variant, c.truth_stratum if by_truth else "")
        strata.setdefault(key, {}).setdefault(c.scenario_id, {})[c.condition_id] = c
    if expected is not None:
        for model, variant in sorted({(k[0], k[1]) for k in strata}):
            for sid, label in expected.items():
                strata.setdefault((model, variant, label if by_truth else ""), {})

    out: list[PairedDiffs] = []
    for key in sorted(strata):
        model, variant, truth = key
        scenarios = strata[key]
        diffs: list[ScenarioDiff] = []
        dropped: list[Dropped] = []
        scale = 0.0
        for scenario_id in sorted(scenarios):
            cells = scenarios[scenario_id]
            pair_id = next(iter(cells.values())).pair_id
            if scenario_id in pair_lookup and pair_lookup[scenario_id] != pair_id:
                raise ValueError(f"scenario {scenario_id} has pair id {pair_id!r} in the data but {pair_lookup[scenario_id]!r} in expected_pair_ids")
            if by_truth and expected is not None and scenario_id in expected and expected[scenario_id] != truth:
                raise ValueError(f"scenario {scenario_id} has truth label {truth!r} in the data but {expected[scenario_id]!r} in expected_scenarios")
            reasons = []
            for side, cond in (("a", condition_a), ("b", condition_b)):
                cell = cells.get(cond)
                if cell is None:
                    reasons.append(f"{side}:absent")
                elif cell.value is None:
                    reasons.append(f"{side}:no_valid_observations")
            if reasons:
                dropped.append(Dropped(scenario_id, pair_id, ";".join(reasons)))
                continue
            a, b = cells[condition_a], cells[condition_b]
            diffs.append(ScenarioDiff(scenario_id, pair_id, a.value - b.value, a.n_valid, b.n_valid))
            scale = max(scale, abs(a.value), abs(b.value))
        unexpected: tuple[str, ...] = ()
        total = len(scenarios)
        if expected is not None:
            for sid in sorted(expected):
                if (expected[sid] == truth or not by_truth) and sid not in scenarios:
                    dropped.append(Dropped(sid, pair_lookup.get(sid, ""), "no_rows"))
                    total += 1
            unexpected = tuple(sorted(sid for sid in scenarios if sid not in expected))
        dropped.sort(key=lambda d: d.scenario_id)
        out.append(
            PairedDiffs(
                model_alias=model,
                prompt_variant=variant,
                outcome=table.outcome,
                condition_a=condition_a,
                condition_b=condition_b,
                diffs=tuple(diffs),
                dropped=tuple(dropped),
                n_scenarios_total=total,
                n_scenarios_used=len(diffs),
                value_scale=scale,
                truth_stratum=truth if by_truth else None,
                unexpected_scenarios=unexpected,
                expected_checked=expected is not None,
            )
        )
    return tuple(out)


@dataclass(frozen=True)
class IncompletePair:
    pair_id: str
    present_scenarios: tuple[str, ...]
    unusable_scenarios: tuple[str, ...]
    missing_count: int


@dataclass(frozen=True)
class PairDiff:
    pair_id: str
    mean_diff: float
    scenario_ids: tuple[str, ...]


@dataclass(frozen=True)
class PairCompleteness:
    model_alias: str
    prompt_variant: str
    condition_a: str
    condition_b: str
    expected_pair_size: int
    complete_pairs: tuple[str, ...]
    incomplete: tuple[IncompletePair, ...]
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


@dataclass(frozen=True)
class PairAggregate:
    model_alias: str
    prompt_variant: str
    condition_a: str
    condition_b: str
    pairs: tuple[PairDiff, ...]
    incomplete: tuple[IncompletePair, ...]
    n_pairs_used: int
    n_pairs_incomplete: int
    n_scenarios_used: int
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


def _pair_status(paired: PairedDiffs, expected_pair_size: int) -> tuple[list[PairDiff], list[IncompletePair]]:
    if paired.truth_stratum is not None:
        raise ValueError("pair aggregation needs both members of a matched pair; it cannot use truth-stratified differences")
    if expected_pair_size < 1:
        raise ValueError("expected_pair_size must be at least 1")
    used: dict[str, list[ScenarioDiff]] = {}
    unusable: dict[str, list[str]] = {}
    for d in paired.diffs:
        used.setdefault(d.pair_id, []).append(d)
    for d in paired.dropped:
        if d.pair_id:
            unusable.setdefault(d.pair_id, []).append(d.scenario_id)
    complete: list[PairDiff] = []
    incomplete: list[IncompletePair] = []
    for pair_id in sorted(set(used) | set(unusable)):
        members = used.get(pair_id, [])
        known = len(members) + len(unusable.get(pair_id, []))
        if known > expected_pair_size:
            raise ValueError(f"pair {pair_id} has {known} known scenarios, more than expected_pair_size={expected_pair_size}")
        if len(members) == expected_pair_size:
            complete.append(
                PairDiff(pair_id, math.fsum(m.diff for m in members) / expected_pair_size, tuple(sorted(m.scenario_id for m in members)))
            )
        else:
            incomplete.append(
                IncompletePair(
                    pair_id,
                    tuple(sorted(m.scenario_id for m in members)),
                    tuple(sorted(unusable.get(pair_id, []))),
                    expected_pair_size - len(members),
                )
            )
    return complete, incomplete


def pair_completeness(paired: PairedDiffs, expected_pair_size: int = 2) -> PairCompleteness:
    """F5. A pair is complete when exactly ``expected_pair_size`` of its scenarios contribute a diff."""
    complete, incomplete = _pair_status(paired, expected_pair_size)
    return PairCompleteness(
        model_alias=paired.model_alias,
        prompt_variant=paired.prompt_variant,
        condition_a=paired.condition_a,
        condition_b=paired.condition_b,
        expected_pair_size=expected_pair_size,
        complete_pairs=tuple(p.pair_id for p in complete),
        incomplete=tuple(incomplete),
    )


def aggregate_to_pair(paired: PairedDiffs, expected_pair_size: int = 2) -> PairAggregate:
    """F4. Mean of the scenario diffs inside each complete matched pair; incomplete pairs are
    reported and excluded, never filled."""
    complete, incomplete = _pair_status(paired, expected_pair_size)
    return PairAggregate(
        model_alias=paired.model_alias,
        prompt_variant=paired.prompt_variant,
        condition_a=paired.condition_a,
        condition_b=paired.condition_b,
        pairs=tuple(complete),
        incomplete=tuple(incomplete),
        n_pairs_used=len(complete),
        n_pairs_incomplete=len(incomplete),
        n_scenarios_used=sum(len(p.scenario_ids) for p in complete),
    )
