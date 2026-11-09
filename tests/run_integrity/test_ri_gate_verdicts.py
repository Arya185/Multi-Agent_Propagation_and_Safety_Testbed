"""The integrity gate's verdicts (real reports from the executors, then mutated copies; offline)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from maps.runs.integrity_gate import FIELDS_USED, MAX_REPORT_BYTES, REASONS, Verdict, check_run_integrity

from ri_gate_support import CLAIM, REPORT, build_live_run, build_mock_run, edit_claim, edit_report, ids, read_report, write_report


def verdict(run_dir, **kw):
    result = check_run_integrity(run_dir, **kw)
    assert result.reason in REASONS and result.message == REASONS[result.reason]
    return result.verdict, result.reason


# ---- A. eligible runs ---------------------------------------------------------------------------------------------
def test_a_complete_mock_run_is_eligible(tmp_path):
    run, outcome = build_mock_run(tmp_path)
    assert outcome.analysis_eligible and verdict(run) == (Verdict.ELIGIBLE, "ok")
    result = check_run_integrity(run)
    assert result.eligible and result.run_id == "gate-001" and result.execution_mode == "mock" and result.report_path == run / REPORT


def test_a_complete_live_run_is_eligible(tmp_path):
    run, outcome = build_live_run(tmp_path)
    assert outcome.analysis_eligible and verdict(run) == (Verdict.ELIGIBLE, "ok") and check_run_integrity(run).execution_mode == "live"


def test_the_claim_record_must_match_the_report_run_id(tmp_path):
    run, _ = build_mock_run(tmp_path)
    edit_claim(run, lambda c: c.update(run_id="someone-else"))
    assert verdict(run) == (Verdict.MISMATCH, "run_id_differs_from_claim")


def test_an_expected_inventory_must_match_the_data_exactly(tmp_path):
    run, _ = build_mock_run(tmp_path, n=3)
    assert verdict(run, expected_episode_ids=ids(3)) == (Verdict.ELIGIBLE, "ok")
    assert verdict(run, expected_episode_ids=ids(4)) == (Verdict.MISMATCH, "inventory_differs_from_expected")
    assert verdict(run, expected_episode_ids=ids(2)) == (Verdict.MISMATCH, "inventory_differs_from_expected")


def test_every_field_the_gate_reads_exists_in_real_reports(tmp_path):
    mock_run, _ = build_mock_run(tmp_path, name="mock")
    live_run, _ = build_live_run(tmp_path, name="live")
    assert set(FIELDS_USED) - {"live"} <= set(read_report(mock_run)) and set(FIELDS_USED) <= set(read_report(live_run))
    assert "live" not in read_report(mock_run)


def test_all_mandatory_eligibility_conditions_must_be_present_and_true(tmp_path):
    from maps.runs.integrity_report import ELIGIBILITY_CONDITIONS

    for i, name in enumerate(ELIGIBILITY_CONDITIONS):
        run, _ = build_mock_run(tmp_path, name=f"missing-{i}")
        edit_report(run, lambda r, name=name: r["eligibility"].pop(name))
        assert verdict(run) == (Verdict.MALFORMED, "field_missing_or_invalid"), name
        run2, _ = build_mock_run(tmp_path, name=f"false-{i}")
        edit_report(run2, lambda r, name=name: r["eligibility"].update({name: False}))
        assert verdict(run2) == (Verdict.MISMATCH, "report_internally_inconsistent"), name        # claims eligible, a condition says no


# ---- B. ineligible runs -----------------------------------------------------------------------------------------------
def test_real_failed_runs_are_ineligible(tmp_path):
    cases = {
        "duplicate": dict(after=lambda p: p.write_text(p.read_text(encoding="utf-8") + p.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")),
        "runner-failure": dict(fail_after=2),
        "inventory": dict(inventory=ids(5)),
    }
    for name, kwargs in cases.items():
        run, outcome = build_mock_run(tmp_path, name=name, **kwargs)
        assert not outcome.analysis_eligible
        assert verdict(run) == (Verdict.INELIGIBLE, "failure_stage_recorded"), name
    run, _ = build_mock_run(tmp_path, name="inv-evidence", inventory=ids(5))
    assert read_report(run)["inventory_validation"]["missing"] == 2 and read_report(run)["inventory_validation"]["status"] == "mismatch"


def test_a_real_policy_stopped_live_run_is_ineligible(tmp_path):
    from maps.schemas import LLMResult

    run, outcome = build_live_run(tmp_path, n=6, script={3: LLMResult(error="http_401: nope", attempts=1)})
    assert outcome.failed_stage == "policy_stop"
    assert verdict(run) == (Verdict.INELIGIBLE, "policy_stop_recorded")
    assert read_report(run)["inventory_validation"]["missing"] == 3                              # incomplete inventory is recorded


def test_a_real_interrupted_live_run_is_ineligible(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        build_live_run(tmp_path, n=6, script={4: KeyboardInterrupt()})
    assert verdict(tmp_path / "run") == (Verdict.INELIGIBLE, "interrupted")


@pytest.mark.parametrize(
    "change,reason",
    [
        (lambda r: r.update(analysis_eligible=False), "report_says_ineligible"),
        (lambda r: r.update(analysis_eligible=False, overall_status="failed"), "overall_status_not_complete"),
        (lambda r: r.update(analysis_eligible=False, failure_stage="runner"), "failure_stage_recorded"),
        (lambda r: (r.update(analysis_eligible=False), r["eligibility"].update(loader_safe=False)), "eligibility_condition_false"),
        (lambda r: (r.update(analysis_eligible=False), r["inventory_validation"].update(performed=True, status="mismatch", missing=2, unexpected=0, invalid_expected=0)), "inventory_not_matched"),
        (lambda r: (r.update(analysis_eligible=False), r["runner"].update(status="interrupted")), "interrupted"),
    ],
    ids=["flag", "status", "stage", "subfield", "inventory", "interrupted"],
)
def test_a_report_that_says_no_is_ineligible(tmp_path, change, reason):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, change)
    assert verdict(run) == (Verdict.INELIGIBLE, reason)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(failure_stage="runner"),
        lambda r: r.update(overall_status="failed"),
        lambda r: r["runner"].update(status="failed"),
        lambda r: r["provenance_drift"].update(status="detected"),
        lambda r: r["post_run_provenance"].update(status="failed"),
        lambda r: r["pre_run_provenance"].update(status="failed"),
        lambda r: r["structural_validation"].update(status="failed"),
        lambda r: r["loader"].update(status="failed"),
        lambda r: r["inventory_validation"].update(performed=True, status="mismatch", missing=1, unexpected=0, invalid_expected=0),
        lambda r: r["runner"].update(results_returned=99),
    ],
    ids=["stage", "status", "runner", "drift", "post", "pre", "structure", "loader", "inventory", "runner-count"],
)
def test_a_report_that_claims_eligibility_but_contradicts_itself_is_a_mismatch(tmp_path, change):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, change)
    assert check_run_integrity(run).verdict is Verdict.MISMATCH


def test_a_live_report_claiming_eligibility_with_a_policy_stop_recorded_is_a_mismatch(tmp_path):
    run, _ = build_live_run(tmp_path)
    edit_report(run, lambda r: r["live"].update(policy_stop_recorded=True))
    assert verdict(run) == (Verdict.MISMATCH, "report_internally_inconsistent")
    run2, _ = build_live_run(tmp_path, name="run2")
    edit_report(run2, lambda r: r["live"].update(wrapper_stop_reason="deadline"))
    assert verdict(run2) == (Verdict.MISMATCH, "report_internally_inconsistent")


def test_a_live_report_without_an_inventory_check_is_never_eligible(tmp_path):
    clear = lambda r: r["inventory_validation"].update(performed=False, status="not_performed", missing=None, unexpected=None, invalid_expected=None)  # noqa: E731
    run, _ = build_live_run(tmp_path)
    edit_report(run, clear)
    assert verdict(run) == (Verdict.MISMATCH, "report_internally_inconsistent")                  # claims eligible, but a live run must have checked
    run2, _ = build_live_run(tmp_path, name="run2")
    edit_report(run2, lambda r: (clear(r), r.update(analysis_eligible=False)))
    assert verdict(run2) == (Verdict.INELIGIBLE, "inventory_required_but_not_performed")


# ---- C. missing and invalid reports -----------------------------------------------------------------------------------------
def test_a_missing_report_or_run_directory(tmp_path):
    run, _ = build_mock_run(tmp_path)
    (run / REPORT).unlink()
    assert verdict(run) == (Verdict.MISSING, "report_missing")
    assert verdict(tmp_path / "no-such-run") == (Verdict.MISSING, "run_directory_missing")
    (tmp_path / "plain-file").write_text("x", encoding="utf-8")
    assert verdict(tmp_path / "plain-file") == (Verdict.MISSING, "run_directory_missing")


@pytest.mark.parametrize(
    "content,reason",
    [
        (b"", "report_not_json"), (b"{not json", "report_not_json"), (b'{"a": NaN}', "report_not_json"), (b"{}", "field_missing_or_invalid"),
        (b"[]", "report_not_an_object"), (b'"text"', "report_not_an_object"), (b"null", "report_not_an_object"), (b"\xff\xfe\x00", "report_not_utf8"),
    ],
    ids=["empty", "invalid", "nan", "empty-object", "array", "string", "null", "non-utf8"],
)
def test_unreadable_or_empty_reports_are_malformed(tmp_path, content, reason):
    run, _ = build_mock_run(tmp_path)
    (run / REPORT).write_bytes(content)
    assert check_run_integrity(run).verdict is Verdict.MALFORMED and check_run_integrity(run).reason == reason


def test_an_oversized_report_a_symlinked_report_and_a_directory_report_are_malformed(tmp_path):
    run, _ = build_mock_run(tmp_path)
    (run / REPORT).write_bytes(b" " * (MAX_REPORT_BYTES + 1))
    assert verdict(run) == (Verdict.MALFORMED, "report_too_large")
    run2, _ = build_mock_run(tmp_path, name="linked")
    real = tmp_path / "elsewhere.json"
    real.write_bytes((run2 / REPORT).read_bytes())
    (run2 / REPORT).unlink()
    os.symlink(real, run2 / REPORT)
    assert verdict(run2) == (Verdict.MALFORMED, "report_is_symlink")
    run3, _ = build_mock_run(tmp_path, name="dirrep")
    (run3 / REPORT).unlink()
    (run3 / REPORT).mkdir()
    assert verdict(run3) == (Verdict.MALFORMED, "report_not_a_regular_file")


REQUIRED_TOP_LEVEL = [k for k in FIELDS_USED if k != "live"]


@pytest.mark.parametrize("field", REQUIRED_TOP_LEVEL)
def test_every_required_field_must_be_present(tmp_path, field):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.pop(field))
    assert check_run_integrity(run).verdict is Verdict.MALFORMED


@pytest.mark.parametrize(
    "path,bad",
    [
        ("analysis_eligible", "true"), ("analysis_eligible", 1), ("analysis_eligible", 0), ("analysis_eligible", None),
        ("overall_status", True), ("overall_status", "COMPLETE"), ("overall_status", 5), ("failure_stage", 5), ("failure_stage", False),
        ("eligibility", []), ("eligibility", "all"), ("statistical_validity_claimed", "false"), ("statistical_validity_claimed", 0),
        ("runner", "ok"), ("loader", None), ("inventory_validation", []), ("structural_validation", {}), ("provenance_drift", {"status": 5}),
        ("execution_mode", ""), ("execution_mode", 5), ("directory_initialization", "unclaimed"), ("schema", 5), ("version", "1"),
        ("version", 1.0), ("version", True), ("run_id", 5), ("live", "block"),
    ],
)
def test_wrongly_typed_or_invalid_values_are_malformed_and_never_coerced(tmp_path, path, bad):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.update({path: bad}))
    assert check_run_integrity(run).verdict is Verdict.MALFORMED, (path, bad)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["eligibility"].update(runner_completed="true"),
        lambda r: r["eligibility"].update(runner_completed=1),
        lambda r: r["loader"].update(records_loaded="3"),
        lambda r: r["loader"].update(records_loaded=True),
        lambda r: r["loader"].update(records_loaded=-1),
        lambda r: r["loader"].update(records_loaded=3.0),
        lambda r: r["runner"].update(status=5),
        lambda r: r["runner"].update(results_returned="3"),
        lambda r: r["inventory_validation"].update(performed=1),
        lambda r: r["inventory_validation"].update(status=None),
        lambda r: r["loader"].pop("records_loaded"),
        lambda r: r["runner"].pop("results_returned"),
    ],
    ids=["elig-str", "elig-int", "count-str", "count-bool", "count-negative", "count-float", "runner-status", "results-str", "performed-int", "inv-status", "no-count", "no-results"],
)
def test_wrongly_typed_nested_values_are_malformed(tmp_path, change):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, change)
    assert check_run_integrity(run).verdict is Verdict.MALFORMED


@pytest.mark.parametrize("schema", ["other-schema", "MAPS-RUN-INTEGRITY", ""])
def test_an_unsupported_schema_name_is_not_accepted(tmp_path, schema):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.update(schema=schema))
    assert check_run_integrity(run).verdict is Verdict.MALFORMED


@pytest.mark.parametrize("version", [0, 3, 99, -1])    # 1 (legacy) and 2 (hash-bound) are the supported versions since v2.3.53
def test_an_unknown_schema_version_is_not_accepted(tmp_path, version):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.update(version=version))
    assert verdict(run) == (Verdict.MALFORMED, "unsupported_version")


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "x" * 129, ".", ".."])
def test_an_invalid_report_run_id_is_malformed(tmp_path, bad):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.update(run_id=bad))
    assert verdict(run) == (Verdict.MALFORMED, "run_id_invalid")


def test_a_report_claiming_statistical_validity_is_malformed(tmp_path):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.update(statistical_validity_claimed=True))
    assert verdict(run) == (Verdict.MALFORMED, "validity_claim_present")


def test_a_live_report_without_its_live_block_is_malformed(tmp_path):
    run, _ = build_live_run(tmp_path)
    edit_report(run, lambda r: r.pop("live"))
    assert verdict(run) == (Verdict.MALFORMED, "live_block_missing")
    run2, _ = build_live_run(tmp_path, name="run2")
    edit_report(run2, lambda r: r["live"].update(policy_stop_recorded="no"))
    assert verdict(run2) == (Verdict.MALFORMED, "field_missing_or_invalid")


def test_unknown_extra_report_fields_are_tolerated_but_never_make_a_bad_report_good(tmp_path):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.update(future_field={"x": 1}))
    assert verdict(run) == (Verdict.ELIGIBLE, "ok")
    run2, _ = build_mock_run(tmp_path, name="bad")
    edit_report(run2, lambda r: r.update(future_field=1, analysis_eligible="true"))
    assert check_run_integrity(run2).verdict is Verdict.MALFORMED


def test_report_and_data_disagreements_that_can_be_detected(tmp_path):
    run, _ = build_mock_run(tmp_path, name="a")
    edit_report(run, lambda r: (r["loader"].update(records_loaded=4), r["runner"].update(results_returned=4)))
    assert verdict(run) == (Verdict.MISMATCH, "loader_count_differs")                          # a self-consistent report for 4 records, 3 on disk
    run2, _ = build_mock_run(tmp_path, name="b")
    edit_report(run2, lambda r: r["loader"].update(records_loaded=4))
    assert verdict(run2) == (Verdict.MISMATCH, "runner_count_differs")
    # Since v2.3.53 edits to the data themselves are caught by the file hashes before any count comparison:
    run3, _ = build_mock_run(tmp_path, name="c")
    lines = (run3 / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
    (run3 / "episodes.jsonl").write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")        # a record removed after the report
    assert verdict(run3) == (Verdict.MISMATCH, "artifact_size_differs")
    run4, _ = build_mock_run(tmp_path, name="d")
    with open(run4 / "episodes.jsonl", "a", encoding="utf-8") as handle:
        handle.write("{broken\n")
    assert verdict(run4) == (Verdict.MISMATCH, "artifact_size_differs")
    run5, _ = build_mock_run(tmp_path, name="e")
    (run5 / "episodes.jsonl").unlink()
    assert verdict(run5) == (Verdict.MISMATCH, "artifact_missing")


def test_the_report_run_id_must_agree_with_the_claim_even_when_both_are_valid(tmp_path):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.update(run_id="another-valid-id"))
    assert verdict(run) == (Verdict.MISMATCH, "run_id_differs_from_claim")


# ---- claim record ------------------------------------------------------------------------------------------------------------
def test_a_missing_or_malformed_claim_record(tmp_path):
    run, _ = build_mock_run(tmp_path, name="a")
    (run / CLAIM).unlink()
    assert verdict(run) == (Verdict.MALFORMED, "claim_missing")
    run, _ = build_mock_run(tmp_path, name="b")
    (run / CLAIM).write_text("{not json", encoding="utf-8")
    assert verdict(run) == (Verdict.MALFORMED, "claim_unreadable")
    run, _ = build_mock_run(tmp_path, name="c")
    (run / CLAIM).write_text("[]", encoding="utf-8")
    assert verdict(run) == (Verdict.MALFORMED, "claim_malformed")
    for i, bad in enumerate((None, 5, "", "../x", "..")):
        run, _ = build_mock_run(tmp_path, name=f"d{i}")
        edit_claim(run, lambda c, bad=bad: c.update(run_id=bad))
        assert verdict(run) == (Verdict.MALFORMED, "claim_malformed"), bad
    run, _ = build_mock_run(tmp_path, name="e")
    edit_claim(run, lambda c: c.pop("run_id"))
    assert verdict(run) == (Verdict.MALFORMED, "claim_malformed")
    run, _ = build_mock_run(tmp_path, name="f")
    (run / CLAIM).unlink()
    os.symlink(run / REPORT, run / CLAIM)
    assert check_run_integrity(run).verdict is Verdict.MALFORMED


def test_the_order_of_checks_is_missing_then_malformed_then_claim_then_ineligible_then_data(tmp_path):
    run, _ = build_mock_run(tmp_path, name="a", fail_after=1)                       # an ineligible report ...
    edit_claim(run, lambda c: c.update(run_id="other"))                              # ... for a different claim: the mismatch is reported first
    assert verdict(run) == (Verdict.MISMATCH, "run_id_differs_from_claim")
    (run / REPORT).write_bytes(b"{bad")
    assert verdict(run)[0] is Verdict.MALFORMED
    (run / REPORT).unlink()
    assert verdict(run)[0] is Verdict.MISSING
