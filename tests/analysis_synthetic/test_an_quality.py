"""F8 invalid-response reporting and F9 binary missingness bounds (SYNTHETIC planted patterns).

Expected values are specified by hand in this file."""

from __future__ import annotations

import dataclasses

import pytest

from maps.analysis import DuplicateRowError, invalid_bounds, invalid_response_report

from an_support import accept_rows, conf_rows, failed, ok


def _d7_rows(model="m1"):
    # C2: 8 ok episodes. C4: s1 = ok, ok, parse_error, call_error; s2 = four parse errors.
    rows = conf_rows(model, "s1", "C2", [50] * 4) + conf_rows(model, "s2", "C2", [50] * 4)
    rows += conf_rows(model, "s1", "C4", [60, 70, "parse_error", "call_error"])
    rows += conf_rows(model, "s2", "C4", ["parse_error"] * 4)
    return rows


def test_invalid_response_report_counts_and_rates():
    report = invalid_response_report(_d7_rows())
    assert report.n_rows_total == 16 and report.tier == "descriptive"
    c2, c4 = report.rows
    assert (c2.condition_id, c2.n_total, c2.n_ok, c2.n_parse_error, c2.n_call_error, c2.n_other) == ("C2", 8, 8, 0, 0, 0)
    assert (c2.n_invalid, c2.invalid_rate, c2.n_scenarios, c2.n_scenarios_no_valid) == (0, 0.0, 2, 0)
    assert (c4.condition_id, c4.n_total, c4.n_ok, c4.n_parse_error, c4.n_call_error, c4.n_other) == ("C4", 8, 2, 5, 1, 0)
    assert (c4.n_invalid, c4.invalid_rate, c4.n_scenarios, c4.n_scenarios_no_valid) == (6, 0.75, 2, 1)


def test_differential_missingness_across_conditions():
    (diff,) = invalid_response_report(_d7_rows()).differential
    assert (diff.model_alias, diff.prompt_variant) == ("m1", "neutral")
    assert diff.rate_by_condition == (("C2", 0.0), ("C4", 0.75))
    assert (diff.spread, diff.condition_max, diff.condition_min) == (0.75, "C4", "C2")


def test_models_are_reported_separately():
    clean = conf_rows("m2", "s1", "C2", [50] * 2) + conf_rows("m2", "s1", "C4", [50] * 2)
    report = invalid_response_report(_d7_rows("m1") + clean)
    assert [(d.model_alias, d.spread) for d in report.differential] == [("m1", 0.75), ("m2", 0.0)]
    assert len(report.rows) == 4


def test_uniform_invalid_rate_has_no_spread():
    rows = conf_rows("m1", "s1", "C2", [50, None]) + conf_rows("m1", "s1", "C4", [50, None])
    (diff,) = invalid_response_report(rows).differential
    assert diff.spread == 0.0 and diff.condition_max == "C2" and diff.condition_min == "C2"


def test_unrecognized_status_is_counted_separately_as_invalid():
    rows = [ok("m1", "s1", "C2", 0), dataclasses.replace(ok("m1", "s1", "C2", 1), status="timeout", confidence=None)]
    (row,) = invalid_response_report(rows).rows
    assert (row.n_ok, row.n_other, row.n_invalid, row.invalid_rate) == (1, 1, 1, 0.5)


def test_duplicate_rows_are_rejected_by_the_reports():
    rows = [ok("m1", "s1", "C2", 0), ok("m1", "s1", "C2", 0)]
    with pytest.raises(DuplicateRowError):
        invalid_response_report(rows)
    with pytest.raises(DuplicateRowError):
        invalid_bounds(rows)


# ---------------------------------------------------------------------------
# F9
# ---------------------------------------------------------------------------
def _d9_rows():
    # C4: ten episodes (5 scenarios x 2 repetitions): 6 accept, 2 reject, 1 parse error, 1 call error.
    rows = []
    plan = [
        ("s1", [True, True]), ("s2", [True, True]), ("s3", [True, True]),
        ("s4", [False, False]), ("s5", ["parse_error", "call_error"]),
    ]
    for scenario, items in plan:
        for rep, item in enumerate(items):
            rows.append(failed("m1", scenario, "C4", rep, status=item) if isinstance(item, str) else ok("m1", scenario, "C4", rep, accepts=item))
    return rows


def test_bounds_with_two_invalid_episodes():
    (b,) = invalid_bounds(_d9_rows())
    assert (b.model_alias, b.prompt_variant, b.condition_id, b.unit) == ("m1", "neutral", "C4", "episode")
    assert (b.n_total, b.n_valid, b.n_invalid, b.n_accept) == (10, 8, 2, 6)
    assert (b.observed_rate, b.lower, b.upper) == (0.75, 0.6, 0.8)
    assert b.tier == "sensitivity"


def test_bounds_when_every_episode_is_invalid():
    rows = conf_rows("m1", "s1", "C4", ["parse_error"] * 4)
    (b,) = invalid_bounds(rows)
    assert (b.n_valid, b.n_invalid, b.observed_rate, b.lower, b.upper) == (0, 4, None, 0.0, 1.0)


def test_bounds_collapse_without_invalid_episodes():
    (b,) = invalid_bounds(accept_rows("m1", "s1", "C4", [True, True, True, False, False]))
    assert (b.observed_rate, b.lower, b.upper, b.n_invalid) == (0.6, 0.6, 0.6, 0)


def test_bounds_are_computed_per_stratum():
    rows = accept_rows("m1", "s1", "C4", [True, False]) + accept_rows("m1", "s1", "C2", [False, False]) + accept_rows("m2", "s1", "C4", [True, True])
    out = invalid_bounds(rows)
    assert [(b.model_alias, b.condition_id, b.observed_rate) for b in out] == [("m1", "C2", 0.0), ("m1", "C4", 0.5), ("m2", "C4", 1.0)]


# ---------------------------------------------------------------------------
# W4 / W9 / W11, truth stratification and W6 scenario-level sensitivity bounds (hand-specified)
# ---------------------------------------------------------------------------
from maps.analysis import InvalidRowsError, contrast_bounds, scenario_level_bounds  # noqa: E402


def test_a_status_ok_row_with_a_missing_outcome_is_counted_as_incomplete_and_invalid():
    rows = [ok("m1", "s1", "C2", 0), dataclasses.replace(ok("m1", "s1", "C2", 1), confidence=None)]
    (row,) = invalid_response_report(rows).rows
    assert (row.n_total, row.n_ok, row.n_incomplete, row.n_invalid, row.invalid_rate) == (2, 1, 1, 1, 0.5)
    (bound,) = invalid_bounds(rows)
    assert (bound.n_valid, bound.n_invalid) == (1, 1)  # F9 uses the same definition


def test_unit_labels_are_explicit():
    report = invalid_response_report(_d7_rows())
    assert report.unit == "episode" and all(r.unit == "episode" for r in report.rows)
    assert all(d.unit == "episode" for d in report.differential)
    assert all(b.unit == "episode" for b in invalid_bounds(_d9_rows()))


def test_structural_validation_applies_but_the_report_still_tolerates_unknown_statuses():
    bad = dataclasses.replace(ok("m1", "s1", "C2", 0), confidence=150)
    with pytest.raises(InvalidRowsError):
        invalid_response_report([bad])
    with pytest.raises(InvalidRowsError):
        invalid_bounds([bad])
    timeout = dataclasses.replace(ok("m1", "s1", "C2", 0), status="timeout")
    assert invalid_response_report([timeout]).rows[0].n_other == 1
    with pytest.raises(InvalidRowsError):
        invalid_bounds([timeout])  # only the invalid-response report reports unknown statuses
    assert invalid_response_report([]).rows == () and invalid_bounds([]) == ()


def _labelled_quality_rows():
    return (
        conf_rows("m1", "s1", "C2", [50, 50], truth="true")
        + conf_rows("m1", "s2", "C2", [50, "parse_error"], truth="false")
        + conf_rows("m1", "s1", "C4", [50, "call_error"], truth="true")
    )


def test_invalid_report_truth_stratification_is_opt_in():
    pooled = invalid_response_report(_labelled_quality_rows())
    assert [(r.condition_id, r.truth_stratum, r.n_total, r.n_invalid) for r in pooled.rows] == [("C2", None, 4, 1), ("C4", None, 2, 1)]
    split = invalid_response_report(_labelled_quality_rows(), by_truth=True)
    assert [(r.condition_id, r.truth_stratum, r.n_total, r.n_invalid) for r in split.rows] == [
        ("C2", "false", 2, 1), ("C2", "true", 2, 0), ("C4", "true", 2, 1),
    ]
    assert [(d.truth_stratum, d.rate_by_condition) for d in split.differential] == [
        ("false", (("C2", 0.5),)), ("true", (("C2", 0.0), ("C4", 0.5))),
    ]
    bounds = {(b.condition_id, b.truth_stratum): b for b in invalid_bounds(_labelled_quality_rows(), by_truth=True)}
    assert bounds[("C2", "false")].lower == 0.5 and bounds[("C2", "false")].upper == 1.0


def test_inconsistent_or_unlabelled_truth_labels_with_stratification():
    clash = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C4", 0, truth="false")]
    with pytest.raises(InvalidRowsError):
        invalid_response_report(clash, by_truth=True)
    assert len(invalid_response_report(clash).rows) == 2  # off by default
    (row,) = invalid_response_report([ok("m1", "s1", "C2", 0)], by_truth=True).rows
    assert row.truth_stratum == "unlabelled"


def _bounds_rows(truth_s1=None, truth_s2=None):
    return (
        accept_rows("m1", "s1", "C4", [True, True, False, "parse_error"], truth=truth_s1)   # lower .5, upper .75, observed 2/3
        + accept_rows("m1", "s1", "C2", [True, False, False, False], truth=truth_s1)        # .25 / .25 / .25
        + accept_rows("m1", "s2", "C4", ["parse_error"] * 4, truth=truth_s2)                 # 0 / 1 / undefined
        + accept_rows("m1", "s2", "C2", [True, True, False, False], truth=truth_s2)          # .5 / .5 / .5
    )


def test_scenario_level_bounds_hand_values():
    out = {b.condition_id: b for b in scenario_level_bounds(_bounds_rows())}
    c4, c2 = out["C4"], out["C2"]
    assert (c4.unit, c4.tier, c4.n_scenarios, c4.n_scenarios_with_observed) == ("scenario", "sensitivity", 2, 1)
    assert (c4.n_episodes, c4.n_invalid_episodes) == (8, 5)
    assert c4.lower == 0.25 and c4.upper == 0.875                       # (0.5 + 0)/2 and (0.75 + 1)/2
    assert c4.observed_rate == pytest.approx(2 / 3, abs=1e-12)          # only s1 has an observed proportion
    assert (c2.lower, c2.upper, c2.observed_rate, c2.n_invalid_episodes) == (0.375, 0.375, 0.375, 0)


def test_contrast_bounds_hand_values_and_dropped_scenarios():
    rows = _bounds_rows() + accept_rows("m1", "s3", "C4", [True, True])  # s3 has no C2 cell
    (res,) = contrast_bounds(rows, "C4", "C2")
    assert (res.unit, res.tier, res.n_scenarios_used, res.n_scenarios_with_observed) == ("scenario", "sensitivity", 2, 1)
    assert res.dropped == (("s3", "b:absent"),)
    assert res.lower == -0.125                                           # ((0.5 - 0.25) + (0 - 0.5)) / 2
    assert res.upper == 0.5                                              # ((0.75 - 0.25) + (1 - 0.5)) / 2
    assert res.observed_diff == pytest.approx(2 / 3 - 0.25, abs=1e-12)   # 0.4166667, only s1 is observed
    assert res.lower <= res.observed_diff <= res.upper


def test_contrast_bounds_by_truth_and_argument_checks():
    rows = _bounds_rows(truth_s1="true", truth_s2="false")
    split = {c.truth_stratum: c for c in contrast_bounds(rows, "C4", "C2", by_truth=True)}
    assert (split["true"].lower, split["true"].upper) == (0.25, 0.5)
    assert (split["false"].lower, split["false"].upper, split["false"].observed_diff) == (-0.5, 0.5, None)
    with pytest.raises(ValueError):
        contrast_bounds(rows, "C4", "C4")
    clash = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C4", 0, truth="false")]
    with pytest.raises(InvalidRowsError):
        scenario_level_bounds(clash, by_truth=True)
