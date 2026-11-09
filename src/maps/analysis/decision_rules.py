"""Decision-rule helpers for theta (meaningful effect) and pi (C0 contamination tolerance).

IMPORTANT. Nothing here selects theta or pi. Every threshold is an explicit parameter; no default
value exists and no value is approved. The nominal-gap normalisation of theta (a fraction of the
nominal root gap of a contrast) is a design direction awaiting owner approval. Labels are
interpretations of an interval, not hypothesis tests. No pilot data may be used to choose a
threshold; the sensitivity tables below are for the owner to read BEFORE any pilot data exist
(they take only synthetic or hypothetical inputs).

THETA. effect / gap, with interval bounds divided by the same positive gap; the unnormalised estimate
and interval are preserved beside the normalised ones. With fraction f: normalised interval wholly
above +f -> 'meaningful'; wholly inside (-f, f) -> 'not_meaningful'; otherwise 'inconclusive'.
Comparisons are strict: an endpoint exactly at a threshold is NOT beyond it. An interval wholly
below -f is labelled 'reverse': this is an UNAPPROVED EXTENSION, the owner defined no rule for it.
An undefined interval (n < 2) is labelled 'undefined'.

PI. pi = proportion of C0 episodes (valid, complete rows only) with estimated_roots > 0. Breach rules
(explicit parameter): 'observed' (proportion > pi) or 'wilson_lower' (Wilson lower bound > pi).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from maps.analysis.intervals import Interval, compute_interval, wilson_interval
from maps.analysis.rows import AnalysisRow, is_complete

UNAPPROVED_TEXT = "UNAPPROVED threshold: exploratory only"
THETA_LABELS = ("meaningful", "not_meaningful", "inconclusive", "reverse", "undefined")
BREACH_RULES = ("observed", "wilson_lower")
_EPS = 1e-12


# ----------------------------------------------------------------------------------- theta

@dataclass(frozen=True)
class ThetaConfig:
    """``fraction``: theta as a fraction of the nominal root gap, 0 < f <= 1. Unset by default."""

    fraction: float | None
    approved: bool = False


def _valid_fraction(f: object) -> float:
    if f is None or isinstance(f, bool) or not isinstance(f, (int, float)):
        raise ValueError("theta threshold not configured / invalid")
    f = float(f)
    if not math.isfinite(f) or f <= 0.0 or f > 1.0:
        raise ValueError("theta threshold not configured / invalid (need 0 < fraction <= 1)")
    return f


def nominal_gap(conditions: Mapping[str, int], first: str, second: str) -> int:
    """n_roots(first) - n_roots(second) from a condition -> n_roots mapping; must be positive."""
    for c in (first, second):
        if c not in conditions:
            raise ValueError(f"unknown condition {c!r}")
    gap = conditions[first] - conditions[second]
    if gap <= 0:
        raise ValueError(f"nominal gap for {first}-{second} must be positive, got {gap}")
    return gap


def conditions_n_roots(config: object) -> dict[str, int]:
    """Read condition -> n_roots from a maps.config.ExperimentConfig (``design.conditions``)."""
    return {c.id: c.n_roots for c in config.design.conditions}  # type: ignore[attr-defined]


@dataclass(frozen=True)
class ThetaResult:
    label: str
    direction: str  # 'positive' | 'negative' | 'zero' | 'undefined' (sign of the raw estimate)
    n_pairs: int
    gap: float
    fraction: float
    threshold_approved: bool
    raw_estimate: float | None
    raw_lower: float | None
    raw_upper: float | None
    norm_estimate: float | None
    norm_lower: float | None
    norm_upper: float | None
    interval_level: float
    interval_method: str
    notes: tuple[str, ...] = ()
    reverse_is_unapproved_extension: bool = False


def classify_interval(lower: float | None, upper: float | None, fraction: float) -> str:
    """Label an interval (already on the normalised scale) against +/- fraction."""
    f = _valid_fraction(fraction)
    if lower is None or upper is None:
        return "undefined"
    if lower > f:
        return "meaningful"
    if upper < -f:
        return "reverse"
    if lower > -f and upper < f:
        return "not_meaningful"
    return "inconclusive"


def _values_of(diffs: object) -> Sequence[float]:
    vals = getattr(diffs, "values", diffs)
    return tuple(vals)  # type: ignore[arg-type]


def classify_contrast(
    diffs: object, gap: float, theta_cfg: ThetaConfig, level: float = 0.95, interval_method: str = "t",
    **interval_kwargs: object,
) -> ThetaResult:
    """Classify a contrast. ``diffs``: a PairedDiffs (or a plain sequence of scenario differences)."""
    f = _valid_fraction(theta_cfg.fraction)
    if isinstance(gap, bool) or not isinstance(gap, (int, float)) or not math.isfinite(gap) or gap <= 0:
        raise ValueError("gap must be a positive finite number")
    vals = _values_of(diffs)
    iv: Interval = compute_interval(vals, interval_method, level=level, **interval_kwargs)  # type: ignore[arg-type]
    g = float(gap)

    def div(x: float | None) -> float | None:
        return None if x is None else x / g

    nl, nu = div(iv.lower), div(iv.upper)
    label = classify_interval(nl, nu, f)
    if iv.estimate is None:
        direction = "undefined"
    else:
        direction = "positive" if iv.estimate > 0 else "negative" if iv.estimate < 0 else "zero"
    notes = tuple(iv.notes)
    if not theta_cfg.approved:
        notes += (UNAPPROVED_TEXT,)
    if label == "reverse":
        notes += ("'reverse' is an unapproved extension; the owner defined no rule for it",)
    return ThetaResult(
        label=label, direction=direction, n_pairs=iv.n, gap=g, fraction=f,
        threshold_approved=bool(theta_cfg.approved),
        raw_estimate=iv.estimate, raw_lower=iv.lower, raw_upper=iv.upper,
        norm_estimate=div(iv.estimate), norm_lower=nl, norm_upper=nu,
        interval_level=level, interval_method=iv.method, notes=notes,
        reverse_is_unapproved_extension=(label == "reverse"),
    )


def theta_sensitivity(
    diffs_by_contrast: Mapping[str, object], gaps: Mapping[str, float], fractions: Iterable[float],
    level: float = 0.95, interval_method: str = "t",
) -> dict[str, dict[float, str]]:
    """contrast -> fraction -> label. Needs no approved value; every cell is exploratory."""
    fractions = tuple(fractions)
    out: dict[str, dict[float, str]] = {}
    for name, diffs in diffs_by_contrast.items():
        if name not in gaps:
            raise ValueError(f"no gap for contrast {name!r}")
        out[name] = {
            f: classify_contrast(diffs, gaps[name], ThetaConfig(f, approved=False), level, interval_method).label
            for f in fractions
        }
    return out


# ------------------------------------------------------------------------------------- pi

@dataclass(frozen=True)
class C0Stratum:
    model_alias: str | None  # None in the pooled result
    prompt_variant: str | None
    n_c0_rows: int
    denominator: int  # valid, complete C0 rows
    numerator: int  # of those, estimated_roots > 0
    proportion: float | None
    wilson: Interval
    mean_roots: float | None
    n_incomplete: int  # C0 rows that are not valid/complete
    n_unknown_roots: int  # C0 rows whose estimated_roots is None


@dataclass(frozen=True)
class C0Result:
    pooled: C0Stratum
    strata: tuple[C0Stratum, ...]
    level: float


def _stratum(model: str | None, variant: str | None, rows: Sequence[AnalysisRow], level: float) -> C0Stratum:
    valid = [r for r in rows if is_complete(r)]
    num = sum(1 for r in valid if r.estimated_roots > 0)  # type: ignore[operator]
    den = len(valid)
    return C0Stratum(
        model_alias=model, prompt_variant=variant, n_c0_rows=len(rows), denominator=den, numerator=num,
        proportion=(num / den if den else None), wilson=wilson_interval(num, den, level),
        mean_roots=(math.fsum(r.estimated_roots for r in valid) / den if den else None),  # type: ignore[misc]
        n_incomplete=len(rows) - den, n_unknown_roots=sum(1 for r in rows if r.estimated_roots is None),
    )


def c0_contamination(rows: Iterable[AnalysisRow], level: float = 0.95) -> C0Result:
    """Pooled and per-(model_alias, prompt_variant) C0 contamination. Rows are not modified."""
    c0 = [r for r in rows if r.condition_id == "C0"]
    groups: dict[tuple[str, str], list[AnalysisRow]] = {}
    for r in c0:
        groups.setdefault((r.model_alias, r.prompt_variant), []).append(r)
    strata = tuple(_stratum(m, v, groups[(m, v)], level) for (m, v) in sorted(groups))
    return C0Result(pooled=_stratum(None, None, c0, level), strata=strata, level=level)


def _check_pi(pi: object) -> float:
    if pi is None or isinstance(pi, bool) or not isinstance(pi, (int, float)):
        raise ValueError("pi not configured / invalid")
    pi = float(pi)
    if not math.isfinite(pi) or not 0.0 <= pi <= 1.0:
        raise ValueError("pi not configured / invalid (need 0 <= pi <= 1)")
    return pi


def _check_rule(rule: object) -> str:
    if rule not in BREACH_RULES:
        raise ValueError(f"unknown breach rule {rule!r}; expected one of {BREACH_RULES}")
    return rule  # type: ignore[return-value]


@dataclass(frozen=True)
class BreachResult:
    breach: bool | None  # None when the denominator is 0 (undefined)
    rule: str
    pi: float
    numerator: int
    denominator: int
    proportion: float | None
    wilson_lower: float | None
    level: float
    pi_approved: bool
    notes: tuple[str, ...] = ()


def _breach_state(k: int, n: int, pi: float, rule: str, level: float) -> bool:
    if rule == "observed":
        return k / n > pi + _EPS
    return wilson_interval(k, n, level).lower > pi + _EPS  # type: ignore[operator]


def c0_breach(result_or_counts: object, pi: float | None, rule: str, *, approved: bool = False, level: float = 0.95) -> BreachResult:
    """``result_or_counts``: a C0Stratum/C0Result (pooled used) or a (numerator, denominator) tuple."""
    p = _check_pi(pi)
    rule = _check_rule(rule)
    obj = result_or_counts
    if isinstance(obj, C0Result):
        obj = obj.pooled
    if isinstance(obj, C0Stratum):
        k, n = obj.numerator, obj.denominator
    else:
        k, n = obj  # type: ignore[misc]
    notes = () if approved else (UNAPPROVED_TEXT,)
    if n == 0:
        return BreachResult(None, rule, p, k, n, None, None, level, approved, notes + ("denominator 0: undefined",))
    lower = wilson_interval(k, n, level).lower
    return BreachResult(_breach_state(k, n, p, rule, level), rule, p, k, n, k / n, lower, level, approved, notes)


def breach_probability(n: int, pi: float | None, true_rate: float, rule: str, level: float = 0.95) -> float:
    """Exact P(breach) when the count is Binomial(n, true_rate)."""
    p = _check_pi(pi)
    rule = _check_rule(rule)
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer")
    q = _check_pi(true_rate)
    return math.fsum(
        math.comb(n, k) * q**k * (1.0 - q) ** (n - k) for k in range(n + 1) if _breach_state(k, n, p, rule, level)
    )


def pi_sensitivity(
    ns: Sequence[int] = (40, 32), pis: Iterable[float] = (), true_rates: Iterable[float] = (),
    rules: Sequence[str] = BREACH_RULES, level: float = 0.95,
) -> dict[tuple[int, str, float, float], float]:
    """(n, rule, pi, true_rate) -> P(breach). Needs no approved pi; exploratory only."""
    pis, true_rates = tuple(pis), tuple(true_rates)
    return {
        (n, rule, pi, tr): breach_probability(n, pi, tr, rule, level)
        for n in ns for rule in rules for pi in pis for tr in true_rates
    }
