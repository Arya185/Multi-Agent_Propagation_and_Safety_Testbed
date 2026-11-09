"""F11 coverage report with caller-supplied expected keys (SYNTHETIC hand-calculable fixtures).

Key = (model, prompt variant, scenario, condition, repetition). Nothing here loads a design grid.
"""

from __future__ import annotations

import dataclasses

import pytest

from maps.analysis import InvalidRowsError
from maps.analysis.provisional import coverage_report

from an_support import failed, ok


def key(model, scenario, cond, rep=0, variant="neutral"):
    return (model, variant, scenario, cond, rep)


def test_complete_coverage():
    rows = [ok("m1", s, c, 0) for s in ("s1", "s2") for c in ("C2", "C4")]
    expected = [key("m1", s, c) for s in ("s1", "s2") for c in ("C2", "C4")]
    report = coverage_report(rows, expected)
    assert (report.n_expected, report.n_observed, report.n_valid) == (4, 4, 4)
    assert (report.n_incomplete, report.n_invalid, report.n_duplicate, report.n_absent, report.n_unexpected_keys) == (0, 0, 0, 0, 0)
    assert report.coverage_rate == 1.0
    assert report.absent_keys == report.invalid_keys == report.incomplete_keys == report.unexpected_keys == ()
    assert (report.unit, report.tier) == ("episode", "descriptive")


def test_missing_invalid_incomplete_and_unexpected_keys():
    incomplete = dataclasses.replace(ok("m1", "s2", "C2", 0), confidence=None)
    rows = [
        ok("m1", "s1", "C2", 0),                          # valid
        failed("m1", "s1", "C4", 0),                      # invalid (parse_error)
        incomplete,                                       # status ok, outcome missing
        ok("m1", "s3", "C2", 0),                          # not expected
    ]
    expected = [key("m1", "s1", "C2"), key("m1", "s1", "C4"), key("m1", "s2", "C2"), key("m1", "s2", "C4")]
    r = coverage_report(rows, expected)
    assert (r.n_expected, r.n_observed, r.n_valid, r.n_invalid, r.n_incomplete, r.n_absent, r.n_duplicate) == (4, 3, 1, 1, 1, 1, 0)
    assert r.coverage_rate == 0.25
    assert r.absent_keys == (key("m1", "s2", "C4"),)
    assert r.invalid_keys == ((key("m1", "s1", "C4"), "parse_error"),)
    assert r.incomplete_keys == (key("m1", "s2", "C2"),)
    assert (r.unexpected_keys, r.n_unexpected_keys, r.n_unexpected_rows) == ((key("m1", "s3", "C2"),), 1, 1)
    c2, c4 = r.strata
    assert (c2.condition_id, c2.n_expected, c2.n_valid, c2.n_incomplete, c2.n_unexpected_keys, c2.coverage_rate) == ("C2", 2, 1, 1, 1, 0.5)
    assert (c2.n_scenarios_expected, c2.n_scenarios_without_valid) == (2, 1)
    assert (c4.condition_id, c4.n_expected, c4.n_invalid, c4.n_absent, c4.coverage_rate) == ("C4", 2, 1, 1, 0.0)
    assert (c4.n_scenarios_expected, c4.n_scenarios_without_valid) == (2, 2)


def test_failed_statuses_are_listed_with_their_status():
    rows = [failed("m1", "s1", "C2", 0, status="call_error"), dataclasses.replace(ok("m1", "s1", "C4", 0), status="timeout")]
    r = coverage_report(rows, [key("m1", "s1", "C2"), key("m1", "s1", "C4")])
    assert r.invalid_keys == ((key("m1", "s1", "C2"), "call_error"), (key("m1", "s1", "C4"), "timeout"))
    assert (r.n_invalid, r.n_valid) == (2, 0)


def test_duplicate_observed_keys_are_reported_not_merged():
    rows = [ok("m1", "s1", "C2", 0), ok("m1", "s1", "C2", 0, conf=70), ok("m1", "s1", "C4", 0)]
    r = coverage_report(rows, [key("m1", "s1", "C2"), key("m1", "s1", "C4")])
    assert r.duplicate_observed_keys == ((key("m1", "s1", "C2"), 2),)
    assert (r.n_duplicate, r.n_valid, r.n_observed, r.n_absent) == (1, 1, 2, 0)  # the duplicated key is neither valid nor absent
    assert r.coverage_rate == 0.5


def test_duplicate_expected_keys_are_reported_and_counted_once():
    rows = [ok("m1", "s1", "C2", 0)]
    r = coverage_report(rows, [key("m1", "s1", "C2"), key("m1", "s1", "C2"), key("m1", "s1", "C4")])
    assert r.duplicate_expected_keys == ((key("m1", "s1", "C2"), 2),)
    assert (r.n_expected, r.n_valid, r.n_absent) == (2, 1, 1)


def test_unexpected_duplicates_count_rows_and_keys_separately():
    rows = [ok("m1", "s9", "C2", 0, pair="p5"), ok("m1", "s9", "C2", 0, conf=60, pair="p5")]
    r = coverage_report(rows, [])
    assert (r.n_unexpected_keys, r.n_unexpected_rows) == (1, 2)
    assert r.duplicate_observed_keys == ((key("m1", "s9", "C2"), 2),)


def test_empty_expected_and_observed_sets():
    empty = coverage_report([], [])
    assert (empty.n_expected, empty.n_observed, empty.n_valid, empty.n_absent, empty.n_unexpected_keys) == (0, 0, 0, 0, 0)
    assert empty.coverage_rate is None and empty.strata == ()
    all_absent = coverage_report([], [key("m1", "s1", "C2"), key("m1", "s1", "C4")])
    assert (all_absent.n_absent, all_absent.n_observed, all_absent.coverage_rate) == (2, 0, 0.0)
    assert len(all_absent.absent_keys) == 2
    all_unexpected = coverage_report([ok("m1", "s1", "C2", 0)], [])
    assert (all_unexpected.n_unexpected_keys, all_unexpected.n_expected, all_unexpected.coverage_rate) == (1, 0, None)
    assert all_unexpected.strata[0].coverage_rate is None and all_unexpected.strata[0].n_unexpected_keys == 1


def test_models_and_variants_remain_separate():
    rows = [ok("m1", "s1", "C2", 0), ok("m2", "s1", "C2", 0, variant="source-aware")]
    expected = [key("m1", "s1", "C2"), key("m2", "s1", "C2"), key("m1", "s1", "C2", variant="source-aware")]
    r = coverage_report(rows, expected)
    assert (r.n_expected, r.n_valid, r.n_absent) == (3, 1, 2)   # a row for another model or variant never satisfies a key
    assert r.absent_keys == (key("m1", "s1", "C2", variant="source-aware"), key("m2", "s1", "C2"))
    assert r.unexpected_keys == (key("m2", "s1", "C2", variant="source-aware"),)
    assert [(s.model_alias, s.prompt_variant) for s in r.strata] == [("m1", "neutral"), ("m1", "source-aware"), ("m2", "neutral"), ("m2", "source-aware")]
    by = {(s.model_alias, s.prompt_variant): s for s in r.strata}
    assert (by[("m1", "neutral")].n_valid, by[("m2", "neutral")].n_absent, by[("m2", "source-aware")].n_unexpected_keys) == (1, 1, 1)


def test_repetitions_are_part_of_the_key():
    rows = [ok("m1", "s1", "C2", 0), ok("m1", "s1", "C2", 1)]
    r = coverage_report(rows, [key("m1", "s1", "C2", rep) for rep in range(3)])
    assert (r.n_expected, r.n_valid, r.n_absent) == (3, 2, 1)
    assert r.absent_keys == (key("m1", "s1", "C2", 2),)


def test_malformed_expected_keys_and_structurally_invalid_rows_are_rejected():
    rows = [ok("m1", "s1", "C2", 0)]
    for bad in (("m1", "neutral", "s1", "C2"), ("m1", "neutral", "s1", "C2", "0"), ("m1", "neutral", "s1", "C2", True),
                ("m1", "neutral", "s1", "C2", -1), ("", "neutral", "s1", "C2", 0), ["m1", "neutral", "s1", "C2", 0]):
        with pytest.raises(ValueError, match="malformed expected key"):
            coverage_report(rows, [bad])
    with pytest.raises(InvalidRowsError):
        coverage_report([dataclasses.replace(ok("m1", "s1", "C2", 0), confidence=150)], [key("m1", "s1", "C2")])


def test_results_are_deterministic_regardless_of_input_order():
    rows = [ok("m1", "s2", "C2", 0), failed("m1", "s1", "C2", 0), ok("m1", "s3", "C2", 0)]
    expected = [key("m1", s, "C2") for s in ("s4", "s1", "s2", "s5")]
    assert coverage_report(rows, expected) == coverage_report(list(reversed(rows)), list(reversed(expected)))
    assert coverage_report(rows, expected).absent_keys == (key("m1", "s4", "C2"), key("m1", "s5", "C2"))


# ---------------------------------------------------------------------------
# Existing-contract edge cases (v2.3.17)
# ---------------------------------------------------------------------------
def test_generator_inputs_for_rows_and_expected_keys_match_list_inputs():
    rows = [ok("m1", "s1", "C2", 0), failed("m1", "s1", "C4", 0), ok("m1", "s9", "C2", 0, pair="p5")]
    expected = [key("m1", "s1", "C2"), key("m1", "s1", "C4"), key("m1", "s2", "C2")]
    from_lists = coverage_report(rows, expected)
    from_generators = coverage_report((r for r in rows), (k for k in expected))
    assert from_generators == from_lists
    assert (from_lists.n_valid, from_lists.n_invalid, from_lists.n_absent, from_lists.n_unexpected_keys) == (1, 1, 1, 1)


def test_duplicate_observed_keys_with_differing_statuses_stay_duplicates():
    k = key("m1", "s1", "C2")
    rows = [ok("m1", "s1", "C2", 0), failed("m1", "s1", "C2", 0, status="call_error"), failed("m1", "s1", "C4", 0)]
    r = coverage_report(rows, [k, key("m1", "s1", "C4")])
    assert r.duplicate_observed_keys == ((k, 2),)
    assert (r.n_duplicate, r.n_valid, r.n_invalid, r.n_absent) == (1, 0, 1, 0)   # neither valid nor invalid: duplicate
    assert r.invalid_keys == ((key("m1", "s1", "C4"), "parse_error"),)            # the duplicated key's statuses are not listed


def test_only_the_first_row_of_a_duplicate_key_is_structurally_validated():
    k = key("m1", "s1", "C2")
    good = ok("m1", "s1", "C2", 0)
    malformed = dataclasses.replace(ok("m1", "s1", "C2", 0), confidence=150)
    report = coverage_report([good, malformed], [k])          # the malformed second row is neither validated nor merged
    assert report.duplicate_observed_keys == ((k, 2),) and report.n_duplicate == 1 and report.n_valid == 0
    with pytest.raises(InvalidRowsError):
        coverage_report([malformed, good], [k])              # the same rows with the malformed row first are rejected


def test_presence_and_valid_coverage_are_different_quantities():
    """Every expected key is PRESENT (n_observed == n_expected) but only one is VALID (coverage_rate = valid / expected)."""
    incomplete = dataclasses.replace(ok("m1", "s2", "C2", 0), confidence=None)
    rows = [ok("m1", "s1", "C2", 0), failed("m1", "s1", "C4", 0), incomplete]
    expected = [key("m1", "s1", "C2"), key("m1", "s1", "C4"), key("m1", "s2", "C2")]
    r = coverage_report(rows, expected)
    assert r.n_observed == r.n_expected == 3 and r.n_absent == 0     # presence is complete
    assert r.n_valid == 1 and r.coverage_rate == pytest.approx(1 / 3)  # validity is not
    for stratum in r.strata:
        assert stratum.n_observed == stratum.n_expected


def test_ordering_is_deterministic_for_every_list_in_the_report():
    rows = [
        ok("m2", "s2", "C4", 1), failed("m1", "s1", "C2", 0, status="call_error"), ok("m1", "s1", "C4", 2),
        ok("m1", "s1", "C4", 2, conf=70), ok("m2", "s7", "C2", 0, pair="p4"), ok("m1", "s2", "C2", 0),
        dataclasses.replace(ok("m1", "s3", "C2", 0), confidence=None),
    ]
    expected = [key("m2", "s2", "C4", 1), key("m1", "s1", "C2"), key("m1", "s1", "C4", 2), key("m1", "s2", "C2"),
                key("m1", "s3", "C2"), key("m2", "s1", "C4"), key("m1", "s2", "C4", 5), key("m1", "s2", "C4", 5)]
    reference = coverage_report(rows, expected)
    for order in (list(reversed(rows)), rows[3:] + rows[:3]):
        for exp_order in (list(reversed(expected)), expected[4:] + expected[:4]):
            assert coverage_report(order, exp_order) == reference
    for keys in (reference.absent_keys, reference.incomplete_keys, reference.unexpected_keys):
        assert list(keys) == sorted(keys)
    assert [k for k, _ in reference.invalid_keys] == sorted(k for k, _ in reference.invalid_keys)
    assert [k for k, _ in reference.duplicate_observed_keys] == sorted(k for k, _ in reference.duplicate_observed_keys)
    assert [k for k, _ in reference.duplicate_expected_keys] == sorted(k for k, _ in reference.duplicate_expected_keys)
    assert [(s.model_alias, s.prompt_variant, s.condition_id) for s in reference.strata] == sorted(
        (s.model_alias, s.prompt_variant, s.condition_id) for s in reference.strata
    )
