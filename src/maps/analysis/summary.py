"""F12: model- and prompt-variant-stratified descriptive summaries (generic).

Strata are (model, prompt variant, condition) and, only when ``by_truth=True`` (opt-in, default off),
the truth label as well; models and variants are never pooled. The unit is the scenario: each stratum
summarizes scenario-level cell values (equal weight per scenario), so repetitions cannot inflate the
reported number of scenarios. The interval method must be named by the caller (or None for no
interval); no method is a default. Unlabelled rows form an explicit ``unlabelled`` stratum and a
scenario with inconsistent labels raises.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from maps.analysis import _stats
from maps.analysis.aggregate import aggregate_to_scenario
from maps.analysis.intervals import Interval, compute_interval
from maps.analysis.rows import AnalysisRow, require_wellformed
from maps.analysis.tiers import DESCRIPTIVE, check_tier


@dataclass(frozen=True)
class StratumSummary:
    model_alias: str
    prompt_variant: str
    condition_id: str
    outcome: str
    n_scenarios_total: int
    n_scenarios_with_value: int
    n_scenarios_missing: int
    n_episodes_total: int
    n_episodes_valid: int
    n_episodes_invalid: int
    mean: float | None
    sd: float | None
    interval: Interval | None
    truth_stratum: str | None = None
    unit: str = "scenario"
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


def stratified_summary(
    rows: Iterable[AnalysisRow],
    outcome: str,
    *,
    interval_method: str | None,
    level: float = 0.95,
    n_boot: int | None = None,
    seed: int | None = None,
    by_truth: bool = False,
) -> tuple[StratumSummary, ...]:
    rows = require_wellformed(rows, check_truth_labels=by_truth)
    table = aggregate_to_scenario(rows, outcome)
    groups: dict[tuple[str, str, str, str], list] = {}
    for c in table.cells:
        groups.setdefault((c.model_alias, c.prompt_variant, c.truth_stratum if by_truth else "", c.condition_id), []).append(c)
    out: list[StratumSummary] = []
    for (model, variant, truth, cond), cells in sorted(groups.items()):
        values = [c.value for c in cells if c.value is not None]
        interval = None
        if interval_method is not None:
            interval = compute_interval(
                values, interval_method, level=level, n_boot=n_boot, seed=seed,
                value_scale=_stats.fallback_scale(values),
            )
        out.append(
            StratumSummary(
                model_alias=model,
                prompt_variant=variant,
                condition_id=cond,
                outcome=outcome,
                n_scenarios_total=len(cells),
                n_scenarios_with_value=len(values),
                n_scenarios_missing=len(cells) - len(values),
                n_episodes_total=sum(c.n_total for c in cells),
                n_episodes_valid=sum(c.n_valid for c in cells),
                n_episodes_invalid=sum(c.n_invalid for c in cells),
                mean=_stats.mean(values),
                sd=_stats.sample_sd(values),
                interval=interval,
                truth_stratum=truth if by_truth else None,
            )
        )
    return tuple(out)
