"""F2 scenario-level aggregation and F12 stratified summaries (SYNTHETIC planted datasets).

Expected values are specified by hand in this file."""

from __future__ import annotations

import pytest

from maps.analysis import aggregate_to_scenario, stratified_summary

from an_support import accept_rows, conf_rows, ok, single_rep


def _cell(table, scenario, cond, model="m1", variant="neutral"):
    return table.lookup()[(model, variant, scenario, cond)]


def test_pseudo_replication_repetitions_are_averaged_inside_one_scenario_cell():
    rows = (
        conf_rows("m1", "s1", "C2", [48, 52, 48, 52])
        + conf_rows("m1", "s1", "C4", [56, 58, 62, 64])
        + conf_rows("m1", "s2", "C2", [50])
        + conf_rows("m1", "s2", "C4", [54])
    )
    table = aggregate_to_scenario(rows, "confidence")
    assert (table.n_rows, table.n_cells, table.n_cells_without_value) == (10, 4, 0)
    c = _cell(table, "s1", "C4")
    assert (c.value, c.n_total, c.n_valid, c.n_invalid) == (60.0, 4, 4, 0)
    assert _cell(table, "s1", "C2").value == 50.0
    c2 = _cell(table, "s2", "C4")
    assert (c2.value, c2.n_valid) == (54.0, 1)
    assert table.tier == "descriptive" and c.tier == "descriptive"


def test_partial_invalid_responses_average_only_valid_repetitions():
    rows = conf_rows("m1", "s1", "C4", [60, 70, None, "call_error"]) + conf_rows("m1", "s2", "C4", [None] * 4)
    table = aggregate_to_scenario(rows, "confidence")
    a = _cell(table, "s1", "C4")
    assert (a.value, a.n_total, a.n_valid, a.n_invalid) == (65.0, 4, 2, 2)
    b = _cell(table, "s2", "C4")
    assert (b.value, b.n_total, b.n_valid, b.n_invalid) == (None, 4, 0, 4)
    assert (table.n_cells, table.n_cells_without_value) == (2, 1)


def test_binary_outcome_cell_is_the_proportion_of_valid_acceptances():
    rows = accept_rows("m1", "s1", "C4", [True, True, False, False]) + accept_rows("m1", "s1", "C2", [True, False, False, False])
    table = aggregate_to_scenario(rows, "accepts_claim")
    assert _cell(table, "s1", "C4").value == 0.5
    assert _cell(table, "s1", "C2").value == 0.25


def test_estimated_roots_outcome_and_zero_root_controls():
    rows = [
        ok("m1", "s1", "C0", 0, roots=0, n_messages=0, n_roots=0),
        ok("m1", "s1", "C0", 1, roots=2, n_messages=0, n_roots=0),
        ok("m1", "s1", "C4", 0, roots=3, n_roots=None),
    ]
    table = aggregate_to_scenario(rows, "estimated_roots")
    assert _cell(table, "s1", "C0").value == 1.0
    assert _cell(table, "s1", "C4").value == 3.0


def test_models_and_variants_stay_separate_cells():
    rows = (
        conf_rows("m1", "s1", "C2", [10]) + conf_rows("m2", "s1", "C2", [90])
        + conf_rows("m1", "s1", "C2", [30], variant="source-aware")
    )
    table = aggregate_to_scenario(rows, "confidence")
    assert table.n_cells == 3
    assert _cell(table, "s1", "C2", "m1").value == 10.0
    assert _cell(table, "s1", "C2", "m2").value == 90.0
    assert _cell(table, "s1", "C2", "m1", "source-aware").value == 30.0


def test_unknown_outcome_and_weighting_are_rejected():
    rows = conf_rows("m1", "s1", "C2", [50])
    with pytest.raises(ValueError):
        aggregate_to_scenario(rows, "reasoning")
    with pytest.raises(ValueError):
        aggregate_to_scenario(rows, "confidence", weighting="episode_weighted")


def test_aggregation_is_deterministic_and_order_independent():
    rows = conf_rows("m1", "s1", "C2", [10, 20, 30]) + conf_rows("m1", "s2", "C2", [40])
    forward = aggregate_to_scenario(rows, "confidence")
    backward = aggregate_to_scenario(list(reversed(rows)), "confidence")
    assert forward == backward


# ---------------------------------------------------------------------------
# F12 stratified summaries
# ---------------------------------------------------------------------------
def _d2_rows(model="m1"):
    rows = []
    for scenario, c4 in zip(("s1", "s2", "s3", "s4"), (52, 54, 56, 58)):
        rows += conf_rows(model, scenario, "C2", [50]) + conf_rows(model, scenario, "C4", [c4])
    return rows


def test_stratified_summary_with_t_intervals_on_hand_computed_values():
    summaries = {s.condition_id: s for s in stratified_summary(_d2_rows(), "confidence", interval_method="t")}
    c2, c4 = summaries["C2"], summaries["C4"]
    assert (c2.n_scenarios_total, c2.n_scenarios_with_value, c2.n_scenarios_missing) == (4, 4, 0)
    assert (c2.n_episodes_total, c2.n_episodes_valid, c2.n_episodes_invalid) == (4, 4, 0)
    assert (c2.mean, c2.sd) == (50.0, 0.0)
    assert (c2.interval.lower, c2.interval.upper) == (50.0, 50.0)
    assert c4.mean == 55.0
    assert c4.sd == pytest.approx(2.581989, abs=1e-6)  # sqrt(20/3)
    assert c4.interval.method == "t" and c4.interval.n == 4
    assert c4.interval.lower == pytest.approx(50.89148, abs=1e-4)
    assert c4.interval.upper == pytest.approx(59.10852, abs=1e-4)
    assert c4.tier == "descriptive"


def test_stratified_summary_without_an_interval_and_with_bootstrap():
    plain = stratified_summary(_d2_rows(), "confidence", interval_method=None)
    assert all(s.interval is None for s in plain)
    boot = {s.condition_id: s for s in stratified_summary(_d2_rows(), "confidence", interval_method="bootstrap", n_boot=200, seed=7)}
    assert (boot["C2"].interval.lower, boot["C2"].interval.upper) == (50.0, 50.0)  # constant values
    assert 52.0 <= boot["C4"].interval.lower <= boot["C4"].interval.upper <= 58.0
    again = stratified_summary(_d2_rows(), "confidence", interval_method="bootstrap", n_boot=200, seed=7)
    assert again[1].interval == boot["C4"].interval  # reproducible


def test_the_interval_method_must_be_named_and_bootstrap_needs_its_parameters():
    with pytest.raises(TypeError):
        stratified_summary(_d2_rows(), "confidence")
    with pytest.raises(ValueError):
        stratified_summary(_d2_rows(), "confidence", interval_method="bootstrap")
    with pytest.raises(ValueError):
        stratified_summary(_d2_rows(), "confidence", interval_method="wald")


def test_models_are_never_pooled_in_summaries():
    rows = _d2_rows("m1") + _d2_rows("m2")
    out = stratified_summary(rows, "confidence", interval_method=None)
    assert [(s.model_alias, s.condition_id) for s in out] == [("m1", "C2"), ("m1", "C4"), ("m2", "C2"), ("m2", "C4")]
    assert all(s.n_scenarios_total == 4 for s in out)


def test_summary_counts_scenarios_not_repetitions():
    rows = conf_rows("m1", "s1", "C4", [60] * 20) + conf_rows("m1", "s2", "C4", [54])
    (summary,) = stratified_summary(rows, "confidence", interval_method=None)
    assert summary.n_scenarios_total == 2 and summary.n_scenarios_with_value == 2
    assert summary.n_episodes_total == 21 and summary.n_episodes_valid == 21
    assert summary.mean == 57.0  # equal weight per scenario, not the episode pool (59.71...)


def test_summary_reports_scenarios_without_valid_observations():
    rows = conf_rows("m1", "s1", "C4", [60, None]) + conf_rows("m1", "s2", "C4", [None, "call_error"])
    (summary,) = stratified_summary(rows, "confidence", interval_method="t")
    assert (summary.n_scenarios_total, summary.n_scenarios_with_value, summary.n_scenarios_missing) == (2, 1, 1)
    assert (summary.n_episodes_total, summary.n_episodes_valid, summary.n_episodes_invalid) == (4, 1, 3)
    assert summary.mean == 60.0 and summary.sd is None
    assert summary.interval.lower is None and summary.interval.upper is None


# ---------------------------------------------------------------------------
# W4 / W5 / W9 / W10 corrections and truth-label stratification (hand-specified)
# ---------------------------------------------------------------------------
import dataclasses  # noqa: E402

from maps.analysis import InvalidRowsError  # noqa: E402


def test_status_ok_with_a_missing_outcome_is_an_invalid_observation_in_every_cell():
    incomplete = dataclasses.replace(ok("m1", "s1", "C4", 2, conf=99), confidence=None)
    rows = conf_rows("m1", "s1", "C4", [60, 70]) + [incomplete]
    cell = _cell(aggregate_to_scenario(rows, "confidence"), "s1", "C4")
    assert (cell.n_total, cell.n_valid, cell.n_invalid, cell.value) == (3, 2, 1, 65.0)
    # the incomplete row is invalid for every outcome, not only the one that is missing
    cell_accepts = _cell(aggregate_to_scenario(rows, "accepts_claim"), "s1", "C4")
    assert (cell_accepts.n_valid, cell_accepts.n_invalid) == (2, 1)


def test_inconsistent_pair_ids_across_conditions_are_rejected():
    rows = [ok("m1", "s1", "C2", 0, pair="p1"), ok("m1", "s1", "C4", 0, pair="p9")]
    with pytest.raises(InvalidRowsError) as exc:
        aggregate_to_scenario(rows, "confidence")
    assert exc.value.issues[0].code == "pair_id_inconsistent"


def test_malformed_rows_are_rejected_by_the_public_functions():
    bad = dataclasses.replace(ok("m1", "s1", "C2", 0), confidence=150)
    with pytest.raises(InvalidRowsError):
        aggregate_to_scenario([bad], "confidence")
    with pytest.raises(InvalidRowsError):
        stratified_summary([bad], "confidence", interval_method=None)


def test_outcome_and_weighting_are_validated_before_any_row_is_read():
    with pytest.raises(ValueError, match="unknown outcome"):
        aggregate_to_scenario([], "bogus")
    with pytest.raises(ValueError, match="unsupported weighting"):
        aggregate_to_scenario([], "confidence", weighting="episode_weighted")
    empty = aggregate_to_scenario([], "confidence")
    assert (empty.n_rows, empty.n_cells, empty.cells) == (0, 0, ())
    assert stratified_summary([], "confidence", interval_method="t") == ()


def test_cells_record_the_truth_stratum_and_flag_inconsistent_labels():
    rows = conf_rows("m1", "s1", "C2", [50], truth="true") + conf_rows("m1", "s2", "C2", [50]) + conf_rows("m1", "s3", "C2", [50, 51])
    table = aggregate_to_scenario(rows, "confidence")
    assert [c.truth_stratum for c in table.cells] == ["true", "unlabelled", "unlabelled"]
    mixed = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C2", 1, truth="false")]
    assert aggregate_to_scenario(mixed, "confidence").cells[0].truth_stratum == "inconsistent"


def _labelled_rows():
    # s1, s3 true; s2, s4 false. One repetition each: C4 = 52, 54, 56, 58.
    labels = {"s1": "true", "s2": "false", "s3": "true", "s4": "false"}
    rows = []
    for scenario, c4 in zip(("s1", "s2", "s3", "s4"), (52, 54, 56, 58)):
        rows += conf_rows("m1", scenario, "C4", [c4], truth=labels[scenario])
    return rows


def test_summary_truth_stratification_is_opt_in_and_off_by_default():
    (pooled,) = stratified_summary(_labelled_rows(), "confidence", interval_method=None)
    assert (pooled.truth_stratum, pooled.n_scenarios_total, pooled.mean) == (None, 4, 55.0)
    by_truth = {s.truth_stratum: s for s in stratified_summary(_labelled_rows(), "confidence", interval_method=None, by_truth=True)}
    assert set(by_truth) == {"true", "false"}
    assert (by_truth["true"].n_scenarios_total, by_truth["true"].mean) == (2, 54.0)    # (52 + 56) / 2
    assert (by_truth["false"].n_scenarios_total, by_truth["false"].mean) == (2, 56.0)  # (54 + 58) / 2
    assert by_truth["true"].sd == pytest.approx(2.828427, abs=1e-6)                     # sqrt(8): |52 - 56| / sqrt(2)


def test_summary_unlabelled_rows_form_an_explicit_stratum_and_inconsistent_labels_raise():
    rows = conf_rows("m1", "s1", "C4", [60], truth="true") + conf_rows("m1", "s2", "C4", [50])
    out = {s.truth_stratum: s for s in stratified_summary(rows, "confidence", interval_method=None, by_truth=True)}
    assert set(out) == {"true", "unlabelled"} and out["unlabelled"].mean == 50.0
    clash = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C4", 0, truth="false")]
    with pytest.raises(InvalidRowsError):
        stratified_summary(clash, "confidence", interval_method=None, by_truth=True)
