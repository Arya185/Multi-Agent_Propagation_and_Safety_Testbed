"""F6: descriptive effect-size primitives for paired scenario-level differences (generic).

These are descriptive summaries of the supplied differences. No effect size is designated primary.

Definitions, for differences d_1..d_n (n scenarios, sample sd with n-1):
  mean difference   d_bar = (1/n) * sum(d_i)            (for a 0/1 outcome this is the risk difference)
  standardized      d_z = d_bar / s_d
                    undefined (None) when n < 2 or s_d <= 16 * eps * S  (see maps.analysis._stats:
                    S is the value scale, i.e. the largest absolute value among the quantities that were
                    subtracted; for plain sequences S falls back to max|d_i|)
  Hedges-type g_z   g_z = J(df) * d_z with df = n - 1 and the exact correction factor
                    J(df) = Gamma(df/2) / ( sqrt(df/2) * Gamma((df-1)/2) )
                    (computed with log-gamma); undefined (None) when df < 2, i.e. n < 3
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from maps.analysis import _stats
from maps.analysis.contrasts import PairedDiffs
from maps.analysis.tiers import DESCRIPTIVE, check_tier


def hedges_correction(df: int) -> float | None:
    """Exact small-sample correction factor J(df); None for df < 2."""
    if df < 2:
        return None
    return math.exp(math.lgamma(df / 2.0) - math.lgamma((df - 1) / 2.0)) / math.sqrt(df / 2.0)


@dataclass(frozen=True)
class EffectSizes:
    n: int
    n_dropped: int
    mean_diff: float | None
    sd: float | None
    dz: float | None
    hedges_g: float | None
    notes: tuple[str, ...]
    value_scale: float = 0.0
    sd_tolerance: float = 0.0
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


def effect_sizes(diffs: Sequence[float], *, n_dropped: int = 0, value_scale: float | None = None) -> EffectSizes:
    vals = _stats.finite_values(diffs)
    n = len(vals)
    scale = _stats.fallback_scale(vals) if value_scale is None else float(value_scale)
    tol = _stats.sd_tolerance(scale)
    notes: list[str] = []
    mean_diff = _stats.mean(vals)
    sd = _stats.sample_sd(vals)
    dz = hedges = None
    if n == 0:
        notes.append("n=0: no differences")
    elif sd is None:
        notes.append("n<2: sd and standardized effect are undefined")
    elif sd <= tol:
        notes.append(f"sd<=tolerance ({tol:.3g}, value scale {scale:.3g}): standardized effect is undefined")
    else:
        dz = mean_diff / sd
        factor = hedges_correction(n - 1)
        if factor is None:
            notes.append("n<3: Hedges correction is undefined; g_z not reported")
        else:
            hedges = factor * dz
    return EffectSizes(
        n=n, n_dropped=n_dropped, mean_diff=mean_diff, sd=sd, dz=dz, hedges_g=hedges, notes=tuple(notes),
        value_scale=scale, sd_tolerance=tol,
    )


def effect_sizes_for(paired: PairedDiffs) -> EffectSizes:
    """Effect sizes over the contributing scenarios of one stratum; dropped scenarios are counted.

    The stratum's value scale (largest absolute contributing cell value) sets the tolerance."""
    return effect_sizes(paired.values, n_dropped=len(paired.dropped), value_scale=paired.value_scale)
