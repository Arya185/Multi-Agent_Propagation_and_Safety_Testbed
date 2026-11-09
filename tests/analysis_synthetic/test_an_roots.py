"""F10 nominal root comparison (SYNTHETIC hand-calculable fixtures).

error = estimated_roots - n_roots, inflation = max(0, error), deflation = max(0, -error), all in roots.
Policy exclude_undefined: n_roots == 0 or unknown contributes to no metric and has its own counter.
"""

from __future__ import annotations

import dataclasses

import pytest

from maps.analysis import DuplicateRowError, InvalidRowsError
from maps.analysis.provisional import root_metrics

from an_support import failed, ok


def _rows(model, scenario, cond, estimates, *, n_roots, variant="neutral"):
    return [ok(model, scenario, cond, rep, roots=est, n_roots=n_roots, variant=variant) for rep, est in enumerate(estimates)]


def _one(rows, **kw):
    (result,) = root_metrics(rows, **kw)
    return result


def test_inflation_and_deflation_hand_values_at_scenario_level():
    # C4 has n_roots = 2. s1 estimates [1, 2, 3] -> errors [-1, 0, 1]; s2 estimates [2, 2, 2] -> errors [0, 0, 0].
    rows = _rows("m1", "s1", "C4", [1, 2, 3], n_roots=2) + _rows("m1", "s2", "C4", [2, 2, 2], n_roots=2)
    r = _one(rows)
    cells = {c.scenario_id: c for c in r.cells}
    assert (cells["s1"].n_used, cells["s1"].error, cells["s1"].inflation, cells["s1"].deflation) == (3, 0.0, pytest.approx(1 / 3), pytest.approx(1 / 3))
    assert (cells["s2"].error, cells["s2"].inflation, cells["s2"].deflation) == (0.0, 0.0, 0.0)
    assert r.mean_error == 0.0
    assert r.mean_inflation == pytest.approx(1 / 6) and r.mean_deflation == pytest.approx(1 / 6)  # (1/3 + 0) / 2
    assert (r.n_rows, r.n_used, r.n_invalid, r.n_zero_root, r.n_unknown_root) == (6, 6, 0, 0, 0)
    assert (r.n_scenarios_total, r.n_scenarios_with_value) == (2, 2)


def test_inflation_and_deflation_stay_separately_interpretable():
    # C4 (n_roots 2): estimates [4, 0] -> errors [+2, -2]. The mean error cancels; inflation and deflation do not.
    r = _one(_rows("m1", "s1", "C4", [4, 0], n_roots=2))
    assert (r.mean_error, r.mean_inflation, r.mean_deflation) == (0.0, 1.0, 1.0)


def test_scenario_level_aggregation_not_episode_pooling():
    # C2 (n_roots 1): s1 has three repetitions with error +3, s2 has one repetition with error 0.
    rows = _rows("m1", "s1", "C2", [4, 4, 4], n_roots=1) + _rows("m1", "s2", "C2", [1], n_roots=1)
    r = _one(rows)
    assert r.mean_error == 1.5 and r.mean_inflation == 1.5 and r.mean_deflation == 0.0  # (3 + 0) / 2, not 9/4
    assert r.n_used == 4 and r.n_scenarios_with_value == 2


def test_zero_root_controls_are_excluded_and_counted_separately():
    r = _one(_rows("m1", "s1", "C0", [0, 2], n_roots=0))
    assert (r.n_rows, r.n_zero_root, r.n_unknown_root, r.n_invalid, r.n_used) == (2, 2, 0, 0, 0)
    assert (r.cells, r.mean_error, r.mean_inflation, r.mean_deflation) == ((), None, None, None)
    assert (r.n_scenarios_total, r.n_scenarios_with_value) == (1, 0)


def test_unknown_roots_are_excluded_and_counted_separately():
    rows = _rows("m1", "s1", "C4", [3], n_roots=None) + _rows("m1", "s2", "C4", [3], n_roots=2)
    r = _one(rows)
    assert (r.n_rows, r.n_unknown_root, r.n_zero_root, r.n_used) == (2, 1, 0, 1)
    assert r.mean_error == 1.0 and [c.scenario_id for c in r.cells] == ["s2"]


def test_invalid_rows_are_excluded_and_the_counters_may_overlap():
    incomplete = dataclasses.replace(ok("m1", "s1", "C2", 3, n_roots=1), estimated_roots=None)
    rows = (
        _rows("m1", "s1", "C2", [1, 1, 2], n_roots=1)                  # errors 0, 0, +1
        + [failed("m1", "s1", "C2", 4, n_roots=1), incomplete]          # two invalid rows
        + [failed("m1", "s2", "C2", 0, n_roots=0)]                      # invalid AND zero-root
    )
    r = _one(rows)
    assert (r.n_rows, r.n_used, r.n_invalid, r.n_zero_root, r.n_unknown_root) == (6, 3, 3, 1, 0)
    assert r.cells[0].scenario_id == "s1" and r.cells[0].error == pytest.approx(1 / 3)
    assert r.mean_inflation == pytest.approx(1 / 3) and r.mean_deflation == 0.0
    assert (r.n_scenarios_total, r.n_scenarios_with_value) == (2, 1)


def test_models_and_prompt_variants_are_never_pooled():
    rows = (
        _rows("m1", "s1", "C4", [3], n_roots=2)                      # +1
        + _rows("m2", "s1", "C4", [1], n_roots=2)                    # -1
        + _rows("m1", "s1", "C4", [2], n_roots=2, variant="source-aware")  # 0
    )
    out = {(r.model_alias, r.prompt_variant): r for r in root_metrics(rows)}
    assert set(out) == {("m1", "neutral"), ("m2", "neutral"), ("m1", "source-aware")}
    assert (out[("m1", "neutral")].mean_error, out[("m2", "neutral")].mean_error, out[("m1", "source-aware")].mean_error) == (1.0, -1.0, 0.0)


def test_conditions_are_separate_strata_and_the_baseline_is_labelled_nominal():
    rows = _rows("m1", "s1", "C2", [1], n_roots=1) + _rows("m1", "s1", "C4", [2], n_roots=2)
    out = root_metrics(rows)
    assert [r.condition_id for r in out] == ["C2", "C4"]
    assert all(r.baseline == "nominal_n_roots" and r.policy == "exclude_undefined" for r in out)
    assert all(r.unit == "scenario" and r.counter_unit == "episode" and r.tier == "descriptive" for r in out)


def test_empty_input_gives_no_strata():
    assert root_metrics([]) == ()


def test_only_the_approved_policy_is_available():
    rows = _rows("m1", "s1", "C0", [2], n_roots=0)
    assert _one(rows, policy="exclude_undefined").n_zero_root == 1
    for other in ("zero_root_error_is_estimate", "include_zero", ""):
        with pytest.raises(ValueError, match="approved"):
            root_metrics(rows, policy=other)


def test_structural_problems_are_rejected():
    with pytest.raises(DuplicateRowError):
        root_metrics(_rows("m1", "s1", "C2", [1], n_roots=1) * 2)
    with pytest.raises(InvalidRowsError):
        root_metrics([dataclasses.replace(ok("m1", "s1", "C2", 0), confidence=150)])
    with pytest.raises(InvalidRowsError):
        root_metrics([ok("m1", "s1", "C2", 0, n_roots=-1)])


def test_inputs_are_not_modified_and_generators_are_accepted():
    rows = _rows("m1", "s1", "C4", [1, 3], n_roots=2)
    snapshot = list(rows)
    assert _one(iter(rows)).mean_error == 0.0
    assert rows == snapshot


# ---------------------------------------------------------------------------
# Documented counter semantics and existing-contract edge cases (v2.3.17)
# ---------------------------------------------------------------------------
from maps.analysis.provisional import RootMetrics  # noqa: E402


def test_unknown_status_raises_under_the_current_contract():
    timeout = dataclasses.replace(ok("m1", "s1", "C2", 0, n_roots=1), status="timeout")
    with pytest.raises(InvalidRowsError) as exc:
        root_metrics([timeout])
    assert exc.value.issues[0].code == "unknown_status"


def test_inconsistent_pair_ids_for_one_scenario_are_rejected_by_the_structural_validation():
    rows = [ok("m1", "s1", "C2", 0, n_roots=1, pair="p1"), ok("m2", "s1", "C4", 0, n_roots=2, pair="p9")]
    with pytest.raises(InvalidRowsError) as exc:
        root_metrics(rows)
    assert exc.value.issues[0].code == "pair_id_inconsistent"


def test_mixed_repetition_counts_give_one_cell_per_scenario_and_n_used_exposes_the_contribution():
    # C2 (n_roots 1): s1 has three used episodes (errors 0, 0, +1); s2 has one used episode (error +2).
    rows = _rows("m1", "s1", "C2", [1, 1, 2], n_roots=1) + _rows("m1", "s2", "C2", [3], n_roots=1)
    r = _one(rows)
    assert [(c.scenario_id, c.n_used) for c in r.cells] == [("s1", 3), ("s2", 1)]
    assert r.n_scenarios_with_value == 2 and r.n_used == 4 == sum(c.n_used for c in r.cells)
    assert r.cells[0].error == pytest.approx(1 / 3) and r.cells[1].error == 2.0
    assert r.mean_error == pytest.approx(7 / 6)         # (1/3 + 2) / 2: equal weight per scenario
    assert r.mean_error != pytest.approx(0.75)           # the episode-weighted mean would be (0 + 0 + 1 + 2) / 4


def test_invalid_and_unknown_root_counters_overlap_and_are_not_exclusive_categories():
    rows = [
        failed("m1", "s1", "C4", 0, n_roots=None),            # invalid AND unknown-root
        ok("m1", "s1", "C4", 1, roots=3, n_roots=None),       # unknown-root only
        failed("m1", "s2", "C4", 0, n_roots=2),               # invalid only
        ok("m1", "s2", "C4", 1, roots=3, n_roots=2),          # used: error +1
    ]
    r = _one(rows)
    assert (r.n_rows, r.n_invalid, r.n_unknown_root, r.n_zero_root, r.n_used) == (4, 2, 2, 0, 1)
    assert r.n_invalid + r.n_unknown_root + r.n_zero_root == 4   # the counters add up to more than the excluded rows ...
    assert r.n_rows - r.n_used == 3                              # ... because one row is in two counters
    assert r.mean_error == 1.0 and r.counter_unit == "episode" and r.unit == "scenario"


def test_n_used_is_the_complete_nonzero_root_subset_and_the_docstrings_state_the_overlap():
    rows = (
        [ok("m1", "s1", "C0", 0, roots=0, n_roots=0)]                  # complete, zero-root: not used
        + [failed("m1", "s1", "C0", 1, n_roots=0)]                      # invalid and zero-root
    )
    r = _one(rows)
    assert (r.n_rows, r.n_zero_root, r.n_invalid, r.n_used) == (2, 2, 1, 0)
    import maps.analysis.provisional as module

    cls_doc, mod_doc = " ".join(RootMetrics.__doc__.split()), " ".join(module.__doc__.split())  # ignore line wrapping
    assert "may overlap" in cls_doc and "equal-weight means" in cls_doc
    assert "NOT mutually exclusive" in mod_doc and "not episode-weighted" in mod_doc
