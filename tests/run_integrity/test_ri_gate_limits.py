"""What the gate can and cannot detect (offline). Since v2.3.53 the binding is SHA-256 INTEGRITY CHECKING (not authentication)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import maps.runs.integrity_gate as gate_module
from maps.runs.integrity_gate import REASONS, Verdict, check_run_integrity

from ri_gate_support import build_mock_run, edit_report, read_report
from ri_support import make_result, raw_line


def lines(run: Path) -> list[str]:
    return (run / "episodes.jsonl").read_text(encoding="utf-8").splitlines()


def write_lines(run: Path, new: list[str]) -> None:
    (run / "episodes.jsonl").write_text("".join(line + "\n" for line in new), encoding="utf-8")


# ---- detectable ---------------------------------------------------------------------------------------------------
def test_changing_the_report_counts_is_detected(tmp_path):
    run, _ = build_mock_run(tmp_path, name="a")
    edit_report(run, lambda r: r["loader"].update(records_loaded=7))
    assert check_run_integrity(run).verdict is Verdict.MISMATCH
    run, _ = build_mock_run(tmp_path, name="b")
    edit_report(run, lambda r: (r["loader"].update(records_loaded=7), r["runner"].update(results_returned=7)))
    assert check_run_integrity(run).reason == "loader_count_differs"


def test_changing_the_report_run_id_is_detected(tmp_path):
    run, _ = build_mock_run(tmp_path)
    edit_report(run, lambda r: r.update(run_id="forged-run-id"))
    assert check_run_integrity(run).reason == "run_id_differs_from_claim"


def test_changes_that_alter_the_record_count_or_the_structure_are_detected(tmp_path):
    for i, change in enumerate((
        lambda ls: ls[:-1],                                          # a record removed
        lambda ls: ls + [raw_line(make_result(episode_id="ep_000000000099"))],      # a valid record added
        lambda ls: ls + [ls[0]],                                     # a duplicate added
        lambda ls: ls + ["{broken"],                                 # garbage added
    )):
        run, _ = build_mock_run(tmp_path, name=f"r{i}")
        write_lines(run, change(lines(run)))
        assert check_run_integrity(run).verdict is Verdict.MISMATCH, i


# ---- since v2.3.53 these used to be known limitations; the file hashes now detect them ------------------------------------------
def test_editing_a_value_inside_a_record_is_detected(tmp_path):
    run, _ = build_mock_run(tmp_path)
    original = lines(run)
    assert '"confidence": 80' in original[1]
    edited = original[1].replace('"confidence": 80', '"confidence": 81')       # same length, still a valid record: only the hash can tell
    write_lines(run, [original[0], edited, original[2]])
    result = check_run_integrity(run)
    assert (result.verdict, result.reason) == (Verdict.MISMATCH, "artifact_hash_differs")


def test_replacing_a_record_by_another_valid_one_with_the_same_id_is_detected(tmp_path):
    run, _ = build_mock_run(tmp_path)
    original = lines(run)
    replacement = json.loads(original[0])
    replacement["spec"]["seed"] = 12345
    write_lines(run, [json.dumps(replacement), *original[1:]])
    assert check_run_integrity(run).reason in ("artifact_hash_differs", "artifact_size_differs")


def test_reordering_records_is_detected(tmp_path):
    run, _ = build_mock_run(tmp_path)
    write_lines(run, list(reversed(lines(run))))
    assert (check_run_integrity(run).verdict, check_run_integrity(run).reason) == (Verdict.MISMATCH, "artifact_hash_differs")


def test_a_forged_file_set_with_matching_ids_and_counts_is_detected_while_the_report_is_untouched(tmp_path):
    run, _ = build_mock_run(tmp_path)
    forged = [raw_line(make_result(episode_id=f"ep_{i:012d}", confidence=0)) for i in range(1, 4)]
    write_lines(run, forged)
    assert check_run_integrity(run).verdict is Verdict.MISMATCH


# ---- what the hashes still cannot do ------------------------------------------------------------------------------------------------------
def rewrite_consistently(run: Path, new_lines: list[str]) -> None:
    """What an attacker with write access could do: change the data AND recompute the hash block in the report."""
    from maps.runs.artifact_hashes import build_artifact_block

    write_lines(run, new_lines)
    block, _ = build_artifact_block(run)
    edit_report(run, lambda r: r.update(artifacts=block, loader={**r["loader"], "records_loaded": len(new_lines)}, runner={**r["runner"], "results_returned": len(new_lines)}))


def test_KNOWN_LIMITATION_a_consistent_rewrite_of_data_and_report_together_is_not_detected(tmp_path):
    run, _ = build_mock_run(tmp_path)
    forged = [raw_line(make_result(episode_id=f"ep_{i:012d}", confidence=0)) for i in range(1, 4)]
    rewrite_consistently(run, forged)
    assert check_run_integrity(run).verdict is Verdict.ELIGIBLE        # integrity checking is not authentication


def test_a_consistent_rewrite_that_leaves_the_data_invalid_is_still_refused(tmp_path):
    run, _ = build_mock_run(tmp_path)
    rewrite_consistently(run, lines(run) + ["{broken"])
    result = check_run_integrity(run)
    assert (result.verdict, result.reason) == (Verdict.MISMATCH, "data_not_structurally_valid")


def test_KNOWN_LIMITATION_unlisted_files_are_not_bound(tmp_path):
    run, _ = build_mock_run(tmp_path)
    (run / "run_events.jsonl").write_text("forged events\n", encoding="utf-8")
    (run / "summary.json").write_text('{"forged": true}', encoding="utf-8")
    (run / "extra-results.jsonl").write_text("{}\n", encoding="utf-8")
    result = check_run_integrity(run)
    assert result.verdict is Verdict.ELIGIBLE and "extra-results.jsonl" in result.notes          # noted, never rejected
    assert "run_events.jsonl" not in result.notes and "summary.json" not in result.notes          # known-unhashed names are not noise


# ---- no overclaiming ----------------------------------------------------------------------------------------------------------------
def test_the_module_states_what_the_hashes_are_and_are_not():
    doc = gate_module.__doc__
    assert "INTEGRITY CHECKING" in doc and "not authentication" in doc and "OUTSIDE the repository" in doc and "not implemented" in doc
    assert "statistical validity" in doc and "Files that are not listed are not bound" in doc
    for text in REASONS.values():
        assert not any(w in text.lower() for w in ("tamper-proof", "authentic", "verified data", "trusted", "secure"))


def test_the_report_carries_the_hash_block_since_schema_version_2(tmp_path):
    run, _ = build_mock_run(tmp_path)
    report = read_report(run)
    assert report["version"] == 2 and report["artifacts"]["hash_algorithm"] == "sha256"
    assert {f["name"] for f in report["artifacts"]["files"]} >= {"episodes.jsonl", ".maps_run_claim"}
