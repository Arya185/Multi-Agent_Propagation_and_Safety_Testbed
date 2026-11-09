"""F1 structural validation of AnalysisRow input (SYNTHETIC data only)."""

from __future__ import annotations

import dataclasses

import pytest

from maps.analysis import AnalysisRow, DuplicateRowError, validate_rows

from an_support import conf_rows, failed, ok


def test_clean_rows_have_no_issues():
    rows = conf_rows("m1", "s1", "C2", [50, 52]) + conf_rows("m1", "s2", "C4", [60, None, "call_error"])
    report = validate_rows(rows)
    assert report.ok is True and report.issues == () and report.n_rows == 5
    assert report.tier == "descriptive"


def test_duplicate_keys_raise():
    rows = [ok("m1", "s1", "C2", 0), ok("m1", "s1", "C2", 0, conf=70)]
    with pytest.raises(DuplicateRowError):
        validate_rows(rows)


def test_same_scenario_in_different_models_or_variants_is_not_a_duplicate():
    rows = [ok("m1", "s1", "C2", 0), ok("m2", "s1", "C2", 0), ok("m1", "s1", "C2", 0, variant="source-aware")]
    assert validate_rows(rows).ok


def _bad(**changes):
    return dataclasses.replace(ok("m1", "s1", "C2", 0), **changes)


CASES = [
    ("empty_identifier", _bad(scenario_id="")),
    ("empty_identifier", _bad(pair_id="")),
    ("repetition_invalid", _bad(repetition=-1)),
    ("n_messages_invalid", _bad(n_messages=-1)),
    ("n_roots_invalid", _bad(n_roots=-2)),
    ("unknown_status", _bad(status="timeout")),
    ("missing_outcome", _bad(confidence=None)),
    ("missing_outcome", _bad(accepts_claim=None)),
    ("missing_outcome", _bad(estimated_roots=None)),
    ("confidence_invalid", _bad(confidence=101)),
    ("confidence_invalid", _bad(confidence=-1)),
    ("confidence_invalid", _bad(confidence=80.5)),
    ("confidence_invalid", _bad(confidence=True)),
    ("accepts_invalid", _bad(accepts_claim=1)),
    ("estimated_roots_invalid", _bad(estimated_roots=-1)),
    ("outcome_on_failed_row", _bad(status="parse_error")),
]


@pytest.mark.parametrize("code,row", CASES, ids=[f"{c}-{i}" for i, (c, _) in enumerate(CASES)])
def test_each_structural_problem_is_reported(code, row):
    report = validate_rows([row])
    assert report.ok is False
    assert code in report.codes()


def test_inconsistent_pair_ids_for_one_scenario_are_reported():
    rows = [ok("m1", "s1", "C2", 0, pair="p1"), ok("m1", "s1", "C4", 0, pair="p9")]
    report = validate_rows(rows)
    assert report.codes() == ("pair_id_inconsistent",)


def test_zero_root_controls_and_unknown_roots_are_accepted_by_the_contract():
    rows = [
        ok("m1", "s1", "C0", 0, n_messages=0, n_roots=0, roots=0),
        ok("m1", "s1", "C4", 0, n_roots=None),
        failed("m1", "s2", "C4", 0, n_roots=None),
    ]
    assert validate_rows(rows).ok


def test_failed_rows_without_outcomes_are_valid():
    assert validate_rows([failed("m1", "s1", "C2", 0, status="call_error")]).ok


def test_validation_accepts_a_generator_and_leaves_rows_unchanged():
    rows = conf_rows("m1", "s1", "C2", [50, 51])
    snapshot = list(rows)
    assert validate_rows(r for r in rows).ok
    assert rows == snapshot


# ---------------------------------------------------------------------------
# Shared validity definition, truth-label consistency and the shared structural check
# ---------------------------------------------------------------------------
from maps.analysis import InvalidRowsError, is_complete, require_wellformed  # noqa: E402


def test_one_definition_of_a_valid_observation():
    assert is_complete(ok("m1", "s1", "C2", 0))
    assert not is_complete(_bad(confidence=None))
    assert not is_complete(_bad(accepts_claim=None))
    assert not is_complete(_bad(estimated_roots=None))
    assert not is_complete(failed("m1", "s1", "C2", 0, status="parse_error"))
    assert not is_complete(_bad(status="timeout"))


def test_truth_label_consistency_is_only_checked_on_request():
    rows = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C4", 0, truth="false")]
    assert validate_rows(rows).ok
    report = validate_rows(rows, check_truth_labels=True)
    assert report.codes() == ("truth_label_inconsistent",)
    mixed = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C4", 0)]  # unlabelled counts as a label
    assert validate_rows(mixed, check_truth_labels=True).codes() == ("truth_label_inconsistent",)
    consistent = [ok("m1", "s1", "C2", 0, truth="true"), ok("m1", "s1", "C4", 0, truth="true")]
    assert validate_rows(consistent, check_truth_labels=True).ok


def test_require_wellformed_tolerates_only_what_it_is_told_to():
    incomplete = _bad(confidence=None)
    assert require_wellformed([incomplete]) == [incomplete]  # missing_outcome is tolerated by default
    with pytest.raises(InvalidRowsError) as exc:
        require_wellformed([_bad(confidence=150)])
    assert exc.value.issues[0].code == "confidence_invalid"
    with pytest.raises(InvalidRowsError):
        require_wellformed([_bad(status="timeout")])
    assert require_wellformed([_bad(status="timeout")], tolerate=("unknown_status",))
    with pytest.raises(DuplicateRowError):
        require_wellformed([ok("m1", "s1", "C2", 0), ok("m1", "s1", "C2", 0)])
    with pytest.raises(InvalidRowsError):
        require_wellformed([ok("m1", "s1", "C2", 0, truth="a"), ok("m1", "s1", "C4", 0, truth="b")], check_truth_labels=True)
