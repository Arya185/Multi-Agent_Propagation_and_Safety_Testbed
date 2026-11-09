"""Synthetic tests for theta/pi decision-rule helpers. No threshold value is chosen here."""

from __future__ import annotations

import copy
import math
from types import SimpleNamespace

import pytest

from maps.analysis import wilson_interval
from maps.analysis.decision_rules import (
    UNAPPROVED_TEXT, ThetaConfig, breach_probability, c0_breach, c0_contamination, classify_contrast,
    classify_interval, conditions_n_roots, nominal_gap, pi_sensitivity, theta_sensitivity,
)

from an_support import failed, ok

COND = {"C0": 0, "C2": 1, "C3": 1, "C4": 2, "C5": 4}


def test_gap_from_mapping_and_config_like():
    assert nominal_gap(COND, "C4", "C2") == 1
    assert nominal_gap(COND, "C5", "C3") == 3
    cfg = SimpleNamespace(design=SimpleNamespace(conditions=[SimpleNamespace(id=k, n_roots=v) for k, v in COND.items()]))
    assert conditions_n_roots(cfg) == COND
    with pytest.raises(ValueError):
        nominal_gap(COND, "C2", "C4")
    with pytest.raises(ValueError):
        nominal_gap(COND, "C9", "C2")


# diffs [2,2,2,2] have zero variance -> degenerate interval at 2 (hand-checked: lower=upper=2)
def test_normalization_preserves_raw():
    r = classify_contrast([1.0, 2.0, 3.0], 2.0, ThetaConfig(0.5))
    assert r.raw_estimate == 2.0 and r.norm_estimate == 1.0
    assert r.norm_lower == pytest.approx(r.raw_lower / 2.0) and r.norm_upper == pytest.approx(r.raw_upper / 2.0)
    assert r.n_pairs == 3 and r.interval_level == 0.95 and r.interval_method == "t" and r.direction == "positive"


def test_classification_scale_invariant():
    a = classify_contrast([2.0, 2.0, 2.0], 1.0, ThetaConfig(0.5)).label
    b = classify_contrast([6.0, 6.0, 6.0], 3.0, ThetaConfig(0.5)).label
    assert a == b == "meaningful"


@pytest.mark.parametrize("lo,hi,f,label", [
    (0.6, 0.9, 0.5, "meaningful"),
    (-0.2, 0.3, 0.5, "not_meaningful"),
    (0.2, 0.7, 0.5, "inconclusive"),
    (-0.7, 0.2, 0.5, "inconclusive"),
    (-0.9, -0.6, 0.5, "reverse"),
    (0.5, 0.9, 0.5, "inconclusive"),        # lower exactly at +theta: not wholly above
    (-0.5, 0.2, 0.5, "inconclusive"),       # lower exactly at -theta: not wholly inside
    (-0.2, 0.5, 0.5, "inconclusive"),       # upper exactly at +theta
    (-0.9, -0.5, 0.5, "inconclusive"),      # upper exactly at -theta: not wholly below
    (None, None, 0.5, "undefined"),
])
def test_labels_and_boundaries(lo, hi, f, label):
    assert classify_interval(lo, hi, f) == label


def test_reverse_flagged_and_zero_variance():
    r = classify_contrast([-3.0, -3.0, -3.0], 1.0, ThetaConfig(0.5, approved=True))
    assert r.label == "reverse" and r.reverse_is_unapproved_extension and r.direction == "negative"
    assert UNAPPROVED_TEXT not in r.notes and r.threshold_approved


def test_n_below_2_undefined():
    r = classify_contrast([1.0], 1.0, ThetaConfig(0.5))
    assert r.label == "undefined" and r.n_pairs == 1


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), 0.0, -0.1, 1.01])
def test_invalid_fraction_raises(bad):
    with pytest.raises(ValueError, match="threshold not configured / invalid"):
        classify_contrast([1.0, 2.0], 1.0, ThetaConfig(bad))
    with pytest.raises(ValueError):
        theta_sensitivity({"a": [1.0, 2.0]}, {"a": 1.0}, [bad])


def test_invalid_gap_raises():
    for g in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            classify_contrast([1.0, 2.0], g, ThetaConfig(0.5))


def test_unapproved_labelling():
    assert UNAPPROVED_TEXT in classify_contrast([2.0, 2.0], 1.0, ThetaConfig(0.5)).notes
    assert not classify_contrast([2.0, 2.0], 1.0, ThetaConfig(0.5)).threshold_approved


def test_theta_sensitivity_deterministic_and_monotone():
    diffs = {"C4-C2": [0.1, -0.1, 0.0, 0.05], "C5-C3": [2.0, 2.1, 1.9, 2.0]}
    gaps = {"C4-C2": 1, "C5-C3": 3}
    fr = [0.1, 0.25, 0.5, 0.75, 1.0]
    t1 = theta_sensitivity(diffs, gaps, fr)
    assert t1 == theta_sensitivity(diffs, gaps, fr)
    for row in t1.values():
        seen_meaningful_after_not = False
        prev = None
        for f in fr:
            if prev == "not_meaningful" and row[f] == "meaningful":
                seen_meaningful_after_not = True
            prev = row[f]
        assert not seen_meaningful_after_not
    assert t1["C4-C2"][0.5] == "not_meaningful"
    assert t1["C5-C3"][0.25] == "meaningful" and t1["C5-C3"][1.0] != "meaningful"


def test_accepts_paired_diffs_object():
    pd = SimpleNamespace(values=(2.0, 2.0, 2.0))
    assert classify_contrast(pd, 1.0, ThetaConfig(0.5)).label == "meaningful"


# ------------------------------------------------------------------------------ pi

def _c0(model, variant, roots_list, start=0):
    rows = []
    for i, x in enumerate(roots_list):
        sc = f"s{start + i}"
        if x == "fail":
            rows.append(failed(model, "s1", "C0", start + i, variant=variant, pair="p1"))
        elif x is None:
            r = ok(model, "s1", "C0", start + i, roots=None, variant=variant, pair="p1")
            rows.append(r)
        else:
            rows.append(ok(model, "s1", "C0", start + i, roots=x, variant=variant, pair="p1"))
    return rows


def test_c0_counts_pooled_and_stratified():
    rows = _c0("m1", "neutral", [0, 0, 1, 3]) + _c0("m2", "neutral", [0, 2]) + [ok("m1", "s1", "C2", 0, roots=5)]
    res = c0_contamination(rows)
    p = res.pooled
    assert (p.n_c0_rows, p.denominator, p.numerator) == (6, 6, 3)
    assert p.proportion == 0.5 and p.mean_roots == pytest.approx(1.0)
    assert p.wilson.lower == wilson_interval(3, 6).lower
    assert [(s.model_alias, s.denominator, s.numerator) for s in res.strata] == [("m1", 4, 2), ("m2", 2, 1)]


def test_c0_missing_and_incomplete():
    rows = _c0("m1", "neutral", [0, 1, "fail", None])
    p = c0_contamination(rows).pooled
    assert p.n_c0_rows == 4 and p.denominator == 2 and p.numerator == 1
    assert p.n_incomplete == 2 and p.n_unknown_roots == 2  # failed row has no roots either


def test_c0_empty_and_zero_valid_stratum():
    e = c0_contamination([ok("m1", "s1", "C2", 0)])
    assert e.pooled.n_c0_rows == 0 and e.pooled.proportion is None and e.pooled.mean_roots is None
    assert e.strata == ()
    res = c0_contamination(_c0("m1", "neutral", [1, 0]) + _c0("m2", "neutral", ["fail", "fail"]))
    z = [s for s in res.strata if s.model_alias == "m2"][0]
    assert z.denominator == 0 and z.n_c0_rows == 2 and z.proportion is None and z.n_incomplete == 2
    assert c0_breach(z, 0.05, "observed").breach is None


def test_variant_strata_separate():
    rows = _c0("m1", "neutral", [0]) + _c0("m1", "formal", [1], start=5)
    assert len(c0_contamination(rows).strata) == 2


def test_rows_not_mutated():
    rows = _c0("m1", "neutral", [0, 1, "fail"])
    before = copy.deepcopy(rows)
    c0_contamination(rows)
    assert rows == before


def test_wilson_known_values():
    # Wilson 95%, 0/40: upper = z^2/(n+z^2) = 3.8415/43.8415 = 0.08762; 1/2: [0.0945, 0.9055]
    w = c0_contamination(_c0("m", "v", [0] * 40)).pooled.wilson
    assert w.lower == 0.0 and w.upper == pytest.approx(0.0876, abs=5e-4)
    w2 = wilson_interval(1, 2)
    assert w2.lower == pytest.approx(0.0945, abs=5e-4) and w2.upper == pytest.approx(0.9055, abs=5e-4)


def test_breach_rules_and_errors():
    assert c0_breach((3, 40), 0.05, "observed").breach is True
    assert c0_breach((2, 40), 0.05, "observed").breach is False  # 0.05 not > 0.05
    assert c0_breach((3, 40), 0.05, "wilson_lower").breach is False  # lower bound ~0.026
    assert c0_breach((20, 40), 0.05, "wilson_lower").breach is True
    r = c0_breach((3, 40), 0.05, "observed")
    assert UNAPPROVED_TEXT in r.notes and not r.pi_approved
    assert UNAPPROVED_TEXT not in c0_breach((3, 40), 0.05, "observed", approved=True).notes
    assert c0_breach(c0_contamination(_c0("m", "v", [1, 0, 0, 0])), 0.1, "observed").breach is True
    for bad in (None, -0.1, 1.5, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            c0_breach((1, 10), bad, "observed")
        with pytest.raises(ValueError):
            breach_probability(10, bad, 0.1, "observed")
    with pytest.raises(ValueError):
        c0_breach((1, 10), 0.05, "bogus")


def test_breach_probability_exact():
    assert breach_probability(40, 0.05, 0.05, "observed") == pytest.approx(0.323, abs=1e-3)
    assert breach_probability(40, 0.05, 0.10, "observed") == pytest.approx(0.777, abs=1e-3)
    assert breach_probability(40, 0.10, 0.05, "observed") == pytest.approx(0.048, abs=1e-3)
    assert breach_probability(40, 0.10, 0.10, "observed") == pytest.approx(0.371, abs=1e-3)
    # hand: n=4, pi=0.25 observed breach iff k>1; q=0.5 -> P(k>=2) = 11/16
    assert breach_probability(4, 0.25, 0.5, "observed") == pytest.approx(11 / 16)
    assert breach_probability(5, 0.0, 0.0, "observed") == 0.0
    assert breach_probability(5, 0.0, 1.0, "observed") == 1.0
    # wilson_lower is never more liberal than observed
    for tr in (0.02, 0.05, 0.1, 0.2):
        assert breach_probability(40, 0.05, tr, "wilson_lower") <= breach_probability(40, 0.05, tr, "observed") + 1e-12


def test_pi_sensitivity_table():
    t = pi_sensitivity((40, 32), (0.05, 0.10), (0.05, 0.10), ("observed", "wilson_lower"))
    assert len(t) == 2 * 2 * 2 * 2 and t == pi_sensitivity((40, 32), (0.05, 0.10), (0.05, 0.10), ("observed", "wilson_lower"))
    assert t[(40, "observed", 0.05, 0.10)] == pytest.approx(0.777, abs=1e-3)
    for n in (40, 32):  # larger pi never raises breach probability; larger rate never lowers it
        assert t[(n, "observed", 0.10, 0.05)] <= t[(n, "observed", 0.05, 0.05)]
        assert t[(n, "observed", 0.05, 0.05)] <= t[(n, "observed", 0.05, 0.10)]
