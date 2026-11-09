"""F7: generic interval primitives (generic; no primary default is selected).

Each function names its method explicitly and reports the sample size. None of them is designated
the interval for any primary analysis; with a small number of scenarios all of them are fragile.

  t_interval          d_bar +/- t(1 - alpha/2, n-1) * s / sqrt(n)           (uses scipy.stats lazily)
  wilson_interval     Wilson score interval for a binomial proportion        (stdlib only)
  bootstrap_percentile_interval
                      percentile interval of resampled means. With B resamples sorted ascending,
                      lower = element floor(alpha/2 * B), upper = element ceil((1 - alpha/2) * B) - 1
                      (0-based, clamped); resampling is seeded and reproducible.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist

from maps.analysis import _stats
from maps.analysis.tiers import DESCRIPTIVE, check_tier

METHODS = ("t", "bootstrap")


@dataclass(frozen=True)
class Interval:
    method: str
    level: float
    n: int
    estimate: float | None
    lower: float | None
    upper: float | None
    notes: tuple[str, ...] = ()
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


def _check_level(level: float) -> None:
    if not 0.0 < level < 1.0:
        raise ValueError("level must be strictly between 0 and 1")


def t_interval(values: Sequence[float], level: float = 0.95, *, value_scale: float | None = None) -> Interval:
    """t interval for the mean. A spread within the rounding-noise tolerance (16 * eps * S, see
    maps.analysis._stats; S = ``value_scale`` or max|v|) is treated as zero variance."""
    _check_level(level)
    vals = _stats.finite_values(values)
    n = len(vals)
    est = _stats.mean(vals)
    if n < 2:
        return Interval("t", level, n, est, None, None, ("n<2: interval is undefined",))
    sd = _stats.sample_sd(vals)
    scale = _stats.fallback_scale(vals) if value_scale is None else float(value_scale)
    if _stats.sd_is_negligible(sd, scale):
        return Interval("t", level, n, est, est, est, ("zero variance (within numerical tolerance): degenerate interval",))
    from scipy import stats  # lazy: only this function needs scipy

    half = float(stats.t.ppf(1.0 - (1.0 - level) / 2.0, n - 1)) * sd / math.sqrt(n)
    return Interval("t", level, n, est, est - half, est + half)


def wilson_interval(successes: int, n: int, level: float = 0.95) -> Interval:
    _check_level(level)
    if isinstance(successes, bool) or isinstance(n, bool) or not isinstance(successes, int) or not isinstance(n, int):
        raise ValueError("successes and n must be integers")
    if n < 0 or not 0 <= successes <= max(n, 0):
        raise ValueError("require 0 <= successes <= n")
    if n == 0:
        return Interval("wilson", level, 0, None, None, None, ("n=0: interval is undefined",))
    z = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return Interval("wilson", level, n, p, max(0.0, center - half), min(1.0, center + half))


def bootstrap_percentile_interval(values: Sequence[float], level: float = 0.95, *, n_boot: int, seed: int) -> Interval:
    _check_level(level)
    if isinstance(n_boot, bool) or not isinstance(n_boot, int) or n_boot < 1:
        raise ValueError("n_boot must be a positive integer")
    vals = _stats.finite_values(values)
    n = len(vals)
    est = _stats.mean(vals)
    if n < 2:
        return Interval("bootstrap", level, n, est, None, None, ("n<2: interval is undefined",))
    rng = random.Random(seed)
    means = sorted(math.fsum(rng.choices(vals, k=n)) / n for _ in range(n_boot))
    alpha = 1.0 - level
    lo = min(max(int(math.floor(alpha / 2.0 * n_boot)), 0), n_boot - 1)
    hi = min(max(int(math.ceil((1.0 - alpha / 2.0) * n_boot)) - 1, 0), n_boot - 1)
    return Interval("bootstrap", level, n, est, means[lo], means[hi], (f"n_boot={n_boot}", f"seed={seed}"))


def compute_interval(
    values: Sequence[float],
    method: str,
    *,
    level: float = 0.95,
    n_boot: int | None = None,
    seed: int | None = None,
    value_scale: float | None = None,
) -> Interval:
    """Dispatch to a mean-interval primitive; the method must be named (there is no default)."""
    if method == "t":
        return t_interval(values, level, value_scale=value_scale)
    if method == "bootstrap":
        if n_boot is None or seed is None:
            raise ValueError("the bootstrap method requires n_boot and seed")
        return bootstrap_percentile_interval(values, level, n_boot=n_boot, seed=seed)
    raise ValueError(f"unknown interval method {method!r}; expected one of {METHODS}")
