"""F6 effect-size primitives and F7 interval primitives (SYNTHETIC planted values).

Expected values are specified by hand in this file:
  [2,4,6,8]: mean 5, deviations -3,-1,1,3, sum of squares 20, sd = sqrt(20/3), d_z = 5/sd,
             exact J(3) = Gamma(1.5) / (sqrt(1.5) * Gamma(1)) = 0.7236013, t(0.975, df=3) = 3.182446, se = sd/2.
  [1]*7+[29]: mean 36/8 = 4.5, sum of squares 7*3.5^2 + 24.5^2 = 686, sd = sqrt(98),
             exact J(7) = Gamma(3.5) / (sqrt(3.5) * Gamma(3)) = 0.8882029.
  [1,2,3]:   mean 2, sd 1, d_z 2, exact J(2) = 1 / Gamma(0.5) = 0.5641896.
(The J values were cross-checked once with math.gamma outside the implementation under test.)
"""

from __future__ import annotations

import math

import pytest

from maps.analysis import (
    bootstrap_percentile_interval,
    compute_interval,
    effect_sizes,
    effect_sizes_for,
    t_interval,
    wilson_interval,
    aggregate_to_scenario,
    paired_scenario_diffs,
)

from an_support import conf_rows


# ---------------------------------------------------------------------------
# F6
# ---------------------------------------------------------------------------
def test_constant_effect_has_zero_sd_and_no_standardized_effect():
    e = effect_sizes([10.0] * 8)
    assert (e.n, e.mean_diff, e.sd, e.dz, e.hedges_g) == (8, 10.0, 0.0, None, None)
    assert any("sd<=tolerance" in n for n in e.notes)


def test_variable_positive_effects():
    e = effect_sizes([2, 4, 6, 8])
    assert e.n == 4 and e.mean_diff == 5.0
    assert e.sd == pytest.approx(2.581989, abs=1e-6)
    assert e.dz == pytest.approx(1.936492, abs=1e-6)
    assert e.hedges_g == pytest.approx(1.401248, abs=1e-6)  # J(3) * d_z = 0.7236013 * 1.936492
    assert e.notes == () and e.tier == "descriptive"


def test_null_effects():
    zero = effect_sizes([0, 0, 0, 0])
    assert (zero.mean_diff, zero.sd, zero.dz) == (0.0, 0.0, None)
    sym = effect_sizes([-1, 1, -1, 1])
    assert sym.mean_diff == 0.0
    assert sym.sd == pytest.approx(1.154701, abs=1e-6)  # sqrt(4/3)
    assert sym.dz == 0.0 and sym.hedges_g == 0.0


def test_outlier_effect():
    e = effect_sizes([1] * 7 + [29])
    assert e.mean_diff == 4.5
    assert e.sd == pytest.approx(9.899495, abs=1e-6)  # sqrt(98)
    assert e.dz == pytest.approx(0.454569, abs=1e-5)
    assert e.hedges_g == pytest.approx(0.403749, abs=1e-5)  # J(7) * d_z = 0.8882029 * 0.454569


def test_small_samples_are_reported_not_invented():
    assert effect_sizes([]).mean_diff is None
    one = effect_sizes([3])
    assert (one.mean_diff, one.sd, one.dz) == (3.0, None, None)
    two = effect_sizes([1, 3])
    assert two.mean_diff == 2.0 and two.sd == pytest.approx(math.sqrt(2)) and two.dz == pytest.approx(math.sqrt(2))
    assert two.hedges_g is None and any("n<3" in n for n in two.notes)


def test_non_finite_values_are_rejected():
    with pytest.raises(ValueError):
        effect_sizes([1.0, float("nan")])
    with pytest.raises(ValueError):
        effect_sizes([1.0, float("inf")])


def test_effect_sizes_for_counts_dropped_scenarios():
    rows = (
        conf_rows("m1", "s1", "C2", [50]) + conf_rows("m1", "s1", "C4", [60])
        + conf_rows("m1", "s2", "C2", [50]) + conf_rows("m1", "s2", "C4", [66])
        + conf_rows("m1", "s3", "C2", [50])
    )
    (res,) = paired_scenario_diffs(aggregate_to_scenario(rows, "confidence"), "C4", "C2")
    e = effect_sizes_for(res)
    assert (e.n, e.n_dropped, e.mean_diff) == (2, 1, 13.0)


# ---------------------------------------------------------------------------
# F7
# ---------------------------------------------------------------------------
def test_t_interval_on_hand_computed_values():
    i = t_interval([2, 4, 6, 8])
    assert (i.method, i.level, i.n, i.estimate) == ("t", 0.95, 4, 5.0)
    assert i.lower == pytest.approx(0.89148, abs=1e-4) and i.upper == pytest.approx(9.10852, abs=1e-4)
    sym = t_interval([-1, 1, -1, 1])
    assert sym.lower == pytest.approx(-1.83739, abs=1e-4) and sym.upper == pytest.approx(1.83739, abs=1e-4)
    two = t_interval([0, 2])  # t(0.975, df=1) = 12.706205, se = 1
    assert two.lower == pytest.approx(1 - 12.706205, abs=1e-3) and two.upper == pytest.approx(1 + 12.706205, abs=1e-3)


def test_t_interval_degenerate_and_undefined_cases():
    const = t_interval([10.0] * 8)
    assert (const.lower, const.upper) == (10.0, 10.0) and any("zero variance" in n for n in const.notes)
    one = t_interval([5])
    assert (one.estimate, one.lower, one.upper, one.n) == (5.0, None, None, 1)
    empty = t_interval([])
    assert (empty.estimate, empty.lower, empty.n) == (None, None, 0)
    for bad in (0.0, 1.0, 1.5):
        with pytest.raises(ValueError):
            t_interval([1, 2, 3], bad)


def test_wilson_interval_on_hand_computed_values():
    i = wilson_interval(8, 10)
    assert (i.method, i.n, i.estimate) == ("wilson", 10, 0.8)
    assert i.lower == pytest.approx(0.4902, abs=5e-4) and i.upper == pytest.approx(0.9433, abs=5e-4)
    zero = wilson_interval(0, 10)  # upper = z^2 / (n + z^2) = 3.841459 / 13.841459
    assert zero.lower == pytest.approx(0.0, abs=1e-12) and zero.upper == pytest.approx(0.277533, abs=1e-5)
    full = wilson_interval(10, 10)
    assert full.lower == pytest.approx(0.722467, abs=1e-5) and full.upper == pytest.approx(1.0, abs=1e-12)


def test_wilson_interval_edge_cases():
    none = wilson_interval(0, 0)
    assert (none.estimate, none.lower, none.upper) == (None, None, None)
    for args in ((11, 10), (-1, 10), (1, -1)):
        with pytest.raises(ValueError):
            wilson_interval(*args)
    with pytest.raises(ValueError):
        wilson_interval(True, 10)


def test_bootstrap_interval_is_exact_for_constant_data_and_reproducible():
    const = bootstrap_percentile_interval([50.0] * 4, n_boot=200, seed=1)
    assert (const.estimate, const.lower, const.upper, const.n) == (50.0, 50.0, 50.0, 4)
    a = bootstrap_percentile_interval([2, 4, 6, 8], n_boot=500, seed=3)
    b = bootstrap_percentile_interval([2, 4, 6, 8], n_boot=500, seed=3)
    assert a == b
    assert 2.0 <= a.lower <= a.upper <= 8.0 and a.estimate == 5.0


def test_bootstrap_interval_edge_cases():
    assert bootstrap_percentile_interval([5], n_boot=10, seed=1).lower is None
    for kwargs in ({"n_boot": 0, "seed": 1}, {"n_boot": True, "seed": 1}):
        with pytest.raises(ValueError):
            bootstrap_percentile_interval([1, 2, 3], **kwargs)
    with pytest.raises(TypeError):
        bootstrap_percentile_interval([1, 2, 3])  # n_boot and seed are required


def test_compute_interval_dispatch_has_no_default_method():
    assert compute_interval([2, 4, 6, 8], "t").method == "t"
    assert compute_interval([2, 4, 6, 8], "bootstrap", n_boot=50, seed=1).method == "bootstrap"
    with pytest.raises(TypeError):
        compute_interval([2, 4, 6, 8])
    with pytest.raises(ValueError):
        compute_interval([2, 4, 6, 8], "bootstrap")
    with pytest.raises(ValueError):
        compute_interval([2, 4, 6, 8], "bayes")


# ---------------------------------------------------------------------------
# W8 exact small-sample correction and E1 scale-aware near-zero standard deviation
# ---------------------------------------------------------------------------
import sys  # noqa: E402

from maps.analysis import hedges_correction  # noqa: E402

EPS = sys.float_info.epsilon


def test_exact_hedges_correction_factor_at_small_sample_sizes():
    assert hedges_correction(1) is None and hedges_correction(0) is None
    assert hedges_correction(2) == pytest.approx(0.5641896, abs=1e-7)
    assert hedges_correction(3) == pytest.approx(0.7236013, abs=1e-7)
    assert hedges_correction(7) == pytest.approx(0.8882029, abs=1e-7)
    e = effect_sizes([1, 2, 3])
    assert (e.mean_diff, e.sd, e.dz) == (2.0, 1.0, 2.0)
    assert e.hedges_g == pytest.approx(1.128379, abs=1e-6)  # 2 * 0.5641896
    assert hedges_correction(200) == pytest.approx(1.0 - 3.0 / (4.0 * 200 - 1.0), abs=1e-4)  # approaches 1


def test_exact_zero_variance_is_undefined_at_any_scale():
    for diffs in ([5, 5, 5], [0, 0, 0, 0], [-3.5] * 6):
        e = effect_sizes(diffs)
        assert (e.sd, e.dz, e.hedges_g) == (0.0, None, None) and any("sd<=tolerance" in n for n in e.notes)


def test_near_constant_differences_at_a_large_scale_are_undefined():
    # one unit in the last place of 10 apart: sd is about 1.45e-15, far below 16 * eps * 10 = 3.6e-14
    e = effect_sizes([10.0, 10.000000000000002, 10.0, 10.000000000000002])
    assert e.sd == pytest.approx(1.4503893e-15, rel=1e-6)
    assert e.sd_tolerance == pytest.approx(16 * EPS * 10.000000000000002, rel=1e-12)
    assert e.dz is None and e.hedges_g is None
    assert e.mean_diff == pytest.approx(10.0)  # the mean difference is still reported


def test_the_carried_value_scale_changes_the_tolerance_not_the_rule():
    tiny = [1e-14, 2e-14, 1e-14, 2e-14]
    fallback = effect_sizes(tiny)  # scale falls back to max|d| = 2e-14: the spread is real at that scale
    assert fallback.dz == pytest.approx(2.598076, abs=1e-6)  # mean 1.5e-14 / sd 5.7735e-15
    carried = effect_sizes(tiny, value_scale=60.0)  # the differences came from cell values of size 60
    assert carried.sd_tolerance == pytest.approx(16 * EPS * 60.0, rel=1e-12)  # about 2.13e-13
    assert carried.dz is None and carried.value_scale == 60.0


def test_genuinely_varying_values_are_not_suppressed():
    e = effect_sizes([10, 10.0001, 10, 10.0001], value_scale=100.0)
    assert e.sd == pytest.approx(5.7735e-5, rel=1e-3) and e.sd > e.sd_tolerance
    assert e.dz is not None and e.dz > 1e5
    assert effect_sizes([2, 4, 6, 8], value_scale=100.0).dz == pytest.approx(1.936492, abs=1e-6)


def test_values_near_zero_are_interpreted_the_same_way_at_every_scale():
    small = effect_sizes([1e-20, 3e-20, 1e-20, 3e-20])
    unit = effect_sizes([1, 3, 1, 3])
    large = effect_sizes([1e20, 3e20, 1e20, 3e20])
    for e in (small, unit, large):
        assert e.dz == pytest.approx(1.7320508, abs=1e-6)  # mean 2 / sd sqrt(4/3)
    assert small.sd_tolerance < unit.sd_tolerance < large.sd_tolerance


def test_scaling_all_differences_preserves_the_standardized_effect():
    base = effect_sizes([2, 4, 6, 8])
    for factor in (1e-6, 1e6):
        scaled = effect_sizes([2 * factor, 4 * factor, 6 * factor, 8 * factor])
        assert scaled.dz == pytest.approx(base.dz, rel=1e-12) and scaled.hedges_g == pytest.approx(base.hedges_g, rel=1e-12)


def test_effect_sizes_for_uses_the_stratum_value_scale():
    rows = (
        conf_rows("m1", "s1", "C2", [50]) + conf_rows("m1", "s1", "C4", [60])
        + conf_rows("m1", "s2", "C2", [50]) + conf_rows("m1", "s2", "C4", [60])
    )
    (res,) = paired_scenario_diffs(aggregate_to_scenario(rows, "confidence"), "C4", "C2")
    e = effect_sizes_for(res)
    assert (e.mean_diff, e.sd, e.dz, e.value_scale) == (10.0, 0.0, None, 60.0)
    assert e.sd_tolerance == pytest.approx(16 * EPS * 60.0, rel=1e-12)


def test_t_interval_treats_noise_level_spread_as_zero_variance():
    near = t_interval([50.0, 50.00000000000001, 50.0, 50.00000000000001])  # 1 ulp of 50 apart
    assert near.lower == near.upper == near.estimate and any("zero variance" in n for n in near.notes)
    tiny = [1e-14, 2e-14, 1e-14, 2e-14]
    assert t_interval(tiny).lower < t_interval(tiny).upper
    degenerate = t_interval(tiny, value_scale=60.0)
    assert degenerate.lower == degenerate.upper == degenerate.estimate
    assert compute_interval(tiny, "t", value_scale=60.0) == degenerate
