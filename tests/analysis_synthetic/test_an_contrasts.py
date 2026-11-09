"""F3-F5: paired scenario differences, matched-pair aggregation and completeness (SYNTHETIC planted effects).

Expected values are specified by hand in this file. Contrast conditions are arguments only; no
contrast is treated as primary."""

from __future__ import annotations

import pytest

from maps.analysis import (
    aggregate_to_pair,
    aggregate_to_scenario,
    pair_completeness,
    paired_scenario_diffs,
)

from an_support import conf_rows, ok, single_rep


def _paired(rows, a="C4", b="C2", outcome="confidence"):
    return paired_scenario_diffs(aggregate_to_scenario(rows, outcome), a, b)


def _eight(c2, c4, model="m1"):
    scenarios = [f"s{i}" for i in range(1, 9)]
    return single_rep(model, dict(zip(scenarios, c2)), "C2") + single_rep(model, dict(zip(scenarios, c4)), "C4")


def test_constant_positive_effect_over_eight_scenarios():
    (res,) = _paired(_eight([50] * 8, [60] * 8))
    assert (res.model_alias, res.prompt_variant, res.condition_a, res.condition_b) == ("m1", "neutral", "C4", "C2")
    assert res.values == (10.0,) * 8
    assert (res.n_scenarios_total, res.n_scenarios_used, res.dropped) == (8, 8, ())
    agg = aggregate_to_pair(res)
    assert [(p.pair_id, p.mean_diff) for p in agg.pairs] == [("p1", 10.0), ("p2", 10.0), ("p3", 10.0), ("p4", 10.0)]
    assert (agg.n_pairs_used, agg.n_pairs_incomplete, agg.n_scenarios_used) == (4, 0, 8)
    assert pair_completeness(res).complete_pairs == ("p1", "p2", "p3", "p4")


def test_variable_positive_effects_and_pair_means():
    rows = _eight([50] * 4 + [0] * 4, [52, 54, 56, 58, 0, 0, 0, 0])
    rows = [r for r in rows if r.scenario_id in {"s1", "s2", "s3", "s4"}]
    (res,) = _paired(rows)
    assert res.values == (2.0, 4.0, 6.0, 8.0)
    agg = aggregate_to_pair(res)
    assert [(p.pair_id, p.mean_diff, p.scenario_ids) for p in agg.pairs] == [("p1", 3.0, ("s1", "s2")), ("p2", 7.0, ("s3", "s4"))]


def test_difference_sign_follows_the_argument_order():
    rows = _eight([50] * 8, [60] * 8)
    (res,) = _paired(rows, a="C2", b="C4")
    assert res.values == (-10.0,) * 8


def test_null_effects():
    (res,) = _paired(_eight([50] * 8, [50] * 8))
    assert res.values == (0.0,) * 8


def test_outlier_is_kept_as_one_scenario():
    (res,) = _paired(_eight([50] * 8, [51] * 7 + [79]))
    assert res.values == (1.0,) * 7 + (29.0,)


def test_opposite_effects_in_two_models_are_not_pooled():
    rows = _eight([50] * 8, [60] * 8, "m1") + _eight([60] * 8, [50] * 8, "m2")
    results = _paired(rows)
    assert [(r.model_alias, r.values) for r in results] == [("m1", (10.0,) * 8), ("m2", (-10.0,) * 8)]


def test_variants_are_separate_strata():
    rows = (
        conf_rows("m1", "s1", "C2", [50]) + conf_rows("m1", "s1", "C4", [60])
        + conf_rows("m1", "s1", "C2", [50], variant="source-aware") + conf_rows("m1", "s1", "C4", [53], variant="source-aware")
    )
    results = _paired(rows)
    assert [(r.prompt_variant, r.values) for r in results] == [("neutral", (10.0,)), ("source-aware", (3.0,))]


def test_repetitions_do_not_become_extra_scenarios():
    rows = (
        conf_rows("m1", "s1", "C2", [48, 52, 48, 52] * 5) + conf_rows("m1", "s1", "C4", [56, 58, 62, 64] * 5)
        + conf_rows("m1", "s2", "C2", [50]) + conf_rows("m1", "s2", "C4", [54])
    )
    (res,) = _paired(rows)
    assert res.n_scenarios_used == 2
    assert [(d.scenario_id, d.diff, d.n_valid_a, d.n_valid_b) for d in res.diffs] == [("s1", 10.0, 20, 20), ("s2", 4.0, 1, 1)]
    assert sum(res.values) / res.n_scenarios_used == 7.0  # not the episode-weighted 9.71...


def _d8_rows(s4_c4):
    return (
        single_rep("m1", {"s1": 50, "s2": 50, "s3": 50, "s4": 50}, "C2")
        + single_rep("m1", {"s1": 60, "s2": 56, "s3": 54}, "C4")
        + s4_c4
    )


@pytest.mark.parametrize(
    "s4_c4,reason",
    [([], "a:absent"), (conf_rows("m1", "s4", "C4", [None, "call_error"]), "a:no_valid_observations")],
    ids=["cell-absent", "no-valid-repetition"],
)
def test_missing_cell_drops_the_scenario_and_leaves_an_incomplete_pair(s4_c4, reason):
    (res,) = _paired(_d8_rows(s4_c4))
    assert res.values == (10.0, 6.0, 4.0)
    assert [(d.scenario_id, d.pair_id, d.reason) for d in res.dropped] == [("s4", "p2", reason)]
    assert (res.n_scenarios_total, res.n_scenarios_used) == (4, 3)
    done = pair_completeness(res)
    assert done.complete_pairs == ("p1",)
    assert [(i.pair_id, i.present_scenarios, i.unusable_scenarios, i.missing_count) for i in done.incomplete] == [
        ("p2", ("s3",), ("s4",), 1)
    ]
    agg = aggregate_to_pair(res)
    assert [(p.pair_id, p.mean_diff) for p in agg.pairs] == [("p1", 8.0)]
    assert (agg.n_pairs_used, agg.n_pairs_incomplete, agg.n_scenarios_used) == (1, 1, 2)


def test_reasons_when_both_sides_are_unusable_or_a_scenario_has_other_conditions_only():
    rows = (
        single_rep("m1", {"s1": 50}, "C2") + single_rep("m1", {"s1": 60}, "C4")
        + conf_rows("m1", "s2", "C2", [None])                      # C2 cell exists, no valid repetition; C4 absent
        + single_rep("m1", {"s5": 70}, "C0")                       # only a different condition
    )
    (res,) = _paired(rows)
    assert res.values == (10.0,)
    assert [(d.scenario_id, d.reason) for d in res.dropped] == [("s2", "a:absent;b:no_valid_observations"), ("s5", "a:absent;b:absent")]
    done = pair_completeness(res)
    assert done.complete_pairs == ()
    assert {(i.pair_id, i.missing_count) for i in done.incomplete} == {("p1", 1), ("p3", 2)}
    assert aggregate_to_pair(res).n_pairs_used == 0


def test_expected_pair_size_must_cover_the_known_pair_members():
    (res,) = _paired(_d8_rows([]))
    with pytest.raises(ValueError):
        aggregate_to_pair(res, expected_pair_size=1)  # p1 has two known scenarios
    with pytest.raises(ValueError):
        pair_completeness(res, expected_pair_size=0)
    agg = aggregate_to_pair(res, expected_pair_size=3)
    assert (agg.n_pairs_used, agg.n_pairs_incomplete) == (0, 2)
    assert {(i.pair_id, i.missing_count) for i in agg.incomplete} == {("p1", 1), ("p2", 2)}


def test_the_two_conditions_must_differ():
    with pytest.raises(ValueError):
        _paired(_eight([50] * 8, [60] * 8), a="C2", b="C2")


def test_binary_outcome_contrast_uses_scenario_proportions():
    from an_support import accept_rows

    rows = accept_rows("m1", "s1", "C4", [True, True, False, False]) + accept_rows("m1", "s1", "C2", [True, False, False, False])
    (res,) = _paired(rows, outcome="accepts_claim")
    assert res.values == (0.25,) and res.outcome == "accepts_claim"


def test_results_carry_the_descriptive_tier_and_leave_inputs_unchanged():
    rows = _eight([50] * 8, [60] * 8)
    snapshot = list(rows)
    (res,) = _paired(rows)
    assert res.tier == "descriptive" and aggregate_to_pair(res).tier == "descriptive" and pair_completeness(res).tier == "descriptive"
    assert rows == snapshot


# ---------------------------------------------------------------------------
# W2 expected scenarios, value scale and opt-in truth stratification (hand-specified)
# ---------------------------------------------------------------------------
def test_value_scale_is_the_largest_contributing_cell_value():
    (res,) = _paired(_eight([50] * 8, [60] * 8))
    assert res.value_scale == 60.0
    (none_used,) = _paired(single_rep("m1", {"s1": 50}, "C2"))
    assert (none_used.n_scenarios_used, none_used.value_scale) == (0, 0.0)


def test_a_scenario_with_no_rows_is_reported_when_the_expected_scenarios_are_given():
    rows = _d8_rows([])  # s4 has only a C2 row here; build a version where s4 is wholly absent
    rows = [r for r in rows if r.scenario_id != "s4"]
    plain = _paired(rows)[0]
    assert plain.n_scenarios_total == 3 and plain.dropped == () and plain.expected_checked is False
    (res,) = paired_scenario_diffs(
        aggregate_to_scenario(rows, "confidence"), "C4", "C2",
        expected_scenarios=["s1", "s2", "s3", "s4"], expected_pair_ids={"s4": "p2"},
    )
    assert res.expected_checked is True
    assert (res.n_scenarios_total, res.n_scenarios_used, res.unexpected_scenarios) == (4, 3, ())
    assert [(d.scenario_id, d.pair_id, d.reason) for d in res.dropped] == [("s4", "p2", "no_rows")]
    done = pair_completeness(res)
    assert done.complete_pairs == ("p1",)
    assert [(i.pair_id, i.present_scenarios, i.unusable_scenarios, i.missing_count) for i in done.incomplete] == [("p2", ("s3",), ("s4",), 1)]


def test_a_wholly_absent_pair_member_without_a_known_pair_id_still_leaves_the_pair_incomplete():
    rows = [r for r in _d8_rows([]) if r.scenario_id != "s4"]
    (res,) = paired_scenario_diffs(aggregate_to_scenario(rows, "confidence"), "C4", "C2", expected_scenarios={"s1", "s2", "s3", "s4"})
    assert [(d.scenario_id, d.pair_id) for d in res.dropped] == [("s4", "")]
    done = pair_completeness(res)
    assert [(i.pair_id, i.present_scenarios, i.unusable_scenarios, i.missing_count) for i in done.incomplete] == [("p2", ("s3",), (), 1)]


def test_unexpected_scenarios_are_listed_and_conflicting_pair_ids_are_rejected():
    rows = single_rep("m1", {"s1": 50}, "C2") + single_rep("m1", {"s1": 60}, "C4")
    rows += [ok("m1", "s9", "C2", 0, pair="p9"), ok("m1", "s9", "C4", 0, pair="p9", conf=70)]
    (res,) = paired_scenario_diffs(aggregate_to_scenario(rows, "confidence"), "C4", "C2", expected_scenarios=["s1"])
    assert res.unexpected_scenarios == ("s9",) and res.n_scenarios_used == 2
    with pytest.raises(ValueError, match="pair id"):
        paired_scenario_diffs(aggregate_to_scenario(rows, "confidence"), "C4", "C2", expected_scenarios=["s1"], expected_pair_ids={"s1": "p5"})


def _labelled_eight():
    labels = {"s1": "true", "s2": "false", "s3": "true", "s4": "false"}
    c2 = {"s1": 50, "s2": 50, "s3": 50, "s4": 50}
    c4 = {"s1": 60, "s2": 56, "s3": 54, "s4": 52}  # diffs 10, 6, 4, 2
    return single_rep("m1", c2, "C2", truth_by_scenario=labels) + single_rep("m1", c4, "C4", truth_by_scenario=labels)


def test_truth_stratification_is_opt_in_and_splits_the_differences_by_label():
    table = aggregate_to_scenario(_labelled_eight(), "confidence")
    (pooled,) = paired_scenario_diffs(table, "C4", "C2")
    assert pooled.truth_stratum is None and pooled.values == (10.0, 6.0, 4.0, 2.0)
    strata = {r.truth_stratum: r for r in paired_scenario_diffs(table, "C4", "C2", by_truth=True)}
    assert set(strata) == {"true", "false"}
    assert strata["true"].values == (10.0, 4.0) and strata["false"].values == (6.0, 2.0)
    assert strata["true"].n_scenarios_total == 2 and strata["true"].value_scale == 60.0


def test_truth_stratification_never_applies_to_pair_aggregation():
    table = aggregate_to_scenario(_labelled_eight(), "confidence")
    stratified = paired_scenario_diffs(table, "C4", "C2", by_truth=True)[0]
    with pytest.raises(ValueError, match="truth-stratified"):
        aggregate_to_pair(stratified)
    with pytest.raises(ValueError, match="truth-stratified"):
        pair_completeness(stratified)
    (pooled,) = paired_scenario_diffs(table, "C4", "C2")
    assert [(p.pair_id, p.mean_diff) for p in aggregate_to_pair(pooled).pairs] == [("p1", 8.0), ("p2", 3.0)]


def test_truth_stratification_handles_unlabelled_rows_and_rejects_inconsistent_labels():
    rows = single_rep("m1", {"s1": 50}, "C2", truth_by_scenario={"s1": "true"}) + single_rep("m1", {"s1": 60}, "C4", truth_by_scenario={"s1": "true"})
    rows += single_rep("m1", {"s2": 50}, "C2") + single_rep("m1", {"s2": 55}, "C4")
    out = {r.truth_stratum: r.values for r in paired_scenario_diffs(aggregate_to_scenario(rows, "confidence"), "C4", "C2", by_truth=True)}
    assert out == {"true": (10.0,), "unlabelled": (5.0,)}
    clash = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C4", 0, truth="false", conf=60)]
    with pytest.raises(ValueError, match="inconsistent truth labels"):
        paired_scenario_diffs(aggregate_to_scenario(clash, "confidence"), "C4", "C2", by_truth=True)
    within = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C2", 1, truth="false")]
    with pytest.raises(ValueError, match="inconsistent truth labels"):
        paired_scenario_diffs(aggregate_to_scenario(within, "confidence"), "C4", "C2", by_truth=True)


def test_expected_scenarios_with_truth_stratification_need_labels():
    table = aggregate_to_scenario(_labelled_eight(), "confidence")
    with pytest.raises(ValueError, match="mapping"):
        paired_scenario_diffs(table, "C4", "C2", by_truth=True, expected_scenarios=["s1"])
    expected = {"s1": "true", "s2": "false", "s3": "true", "s4": "false", "s5": "false"}
    strata = {r.truth_stratum: r for r in paired_scenario_diffs(table, "C4", "C2", by_truth=True, expected_scenarios=expected)}
    assert [(d.scenario_id, d.reason) for d in strata["false"].dropped] == [("s5", "no_rows")]
    assert strata["false"].n_scenarios_total == 3 and strata["true"].dropped == ()
    with pytest.raises(ValueError, match="truth label"):
        paired_scenario_diffs(table, "C4", "C2", by_truth=True, expected_scenarios={**expected, "s1": "false"})
