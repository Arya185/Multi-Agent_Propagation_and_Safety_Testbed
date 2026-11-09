"""Small numeric helpers shared by the analysis building blocks (no I/O).

Near-zero spread rule (documented numerical meaning):
  Subtracting or averaging floating-point numbers of magnitude S leaves rounding noise of about
  machine_epsilon * S per operation. A sample standard deviation no larger than
  SD_ULPS * machine_epsilon * S (SD_ULPS = 16, i.e. about 16 units in the last place of S) cannot be
  told apart from that noise, so it is treated as zero and standardized quantities that divide by it
  are reported as undefined. S is the largest absolute value among the quantities that were
  subtracted or averaged ("value scale"); when only plain differences are available, S falls back to
  max(|d|).
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence

EPSILON = sys.float_info.epsilon
SD_ULPS = 16


def finite_values(values: Sequence[float]) -> list[float]:
    out = [float(v) for v in values]
    for v in out:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("values must be finite numbers")
    return out


def mean(values: Sequence[float]) -> float | None:
    vals = finite_values(values)
    return math.fsum(vals) / len(vals) if vals else None


def sample_sd(values: Sequence[float]) -> float | None:
    """Sample standard deviation with n-1 in the denominator; None for fewer than two values."""
    vals = finite_values(values)
    if len(vals) < 2:
        return None
    m = math.fsum(vals) / len(vals)
    return math.sqrt(math.fsum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def fallback_scale(values: Sequence[float]) -> float:
    """max(|v|), the documented value scale when none is supplied."""
    return max((abs(v) for v in finite_values(values)), default=0.0)


def sd_tolerance(scale: float) -> float:
    if scale < 0 or math.isnan(scale) or math.isinf(scale):
        raise ValueError("value_scale must be a finite non-negative number")
    return SD_ULPS * EPSILON * scale


def sd_is_negligible(sd: float, scale: float) -> bool:
    """True when ``sd`` is zero or within the rounding-noise tolerance for values of magnitude ``scale``."""
    return sd <= sd_tolerance(scale)
