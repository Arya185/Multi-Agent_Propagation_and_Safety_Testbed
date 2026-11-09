"""Validated result loader (SYNTHETIC mock records; temporary directories only; no statistics)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import maps.adapters.run_loader as loader_module
from maps.adapters.episode_results import episode_results_to_rows
from maps.adapters.run_loader import UnsafeRunError, load_episode_results

from ri_support import file_hash, make_result, numbered, raw_line, write_lines, write_records


def ids(results):
    return [r.spec.episode_id for r in results]


def test_valid_records_load_in_file_order_and_the_run_is_safe(tmp_path):
    results = numbered(3)
    write_records(tmp_path / "episodes.jsonl", results)
    loaded = load_episode_results(tmp_path)
    report = loaded.report
    assert loaded.records == tuple(results) and loaded.line_numbers == (1, 2, 3)
    assert (report.total_lines, report.blank_lines, report.valid_records) == (3, 0, 3)
    assert not report.invalid_json and not report.schema_invalid and not report.duplicate_ids
    assert (report.file_exists, report.file_empty, report.read_error) == (True, False, None)
    assert report.structurally_valid and report.safe_for_analysis and report.inventory_matches is None
    assert report.expected_supplied is False and report.problems == ()
    assert loaded.require_safe() == tuple(results)


def test_original_order_is_preserved_even_when_ids_are_not_sorted(tmp_path):
    results = [make_result(episode_id=f"ep_{i:012d}", rep=r) for i, r in ((9, 0), (2, 1), (5, 2))]
    write_records(tmp_path / "episodes.jsonl", results)
    assert ids(load_episode_results(tmp_path).records) == [f"ep_{9:012d}", f"ep_{2:012d}", f"ep_{5:012d}"]


def test_an_empty_file_is_reported_and_unsafe(tmp_path):
    (tmp_path / "episodes.jsonl").write_text("", encoding="utf-8")
    report = load_episode_results(tmp_path).report
    assert (report.file_exists, report.file_empty, report.valid_records, report.total_lines) == (True, True, 0, 0)
    assert not report.safe_for_analysis and "result file is empty" in report.problems
    blank_only = tmp_path / "b" / "episodes.jsonl"
    write_lines(blank_only, ["", "   "])
    report = load_episode_results(blank_only.parent).report
    assert (report.file_empty, report.blank_lines, report.total_lines, report.safe_for_analysis) == (True, 2, 2, False)


def test_a_missing_file_or_directory_is_reported_and_unsafe(tmp_path):
    for run_dir in (tmp_path, tmp_path / "no-such-run"):
        loaded = load_episode_results(run_dir)
        assert loaded.records == () and loaded.report.file_exists is False and not loaded.report.safe_for_analysis
        assert loaded.report.problems and "not found" in loaded.report.problems[0]
        with pytest.raises(UnsafeRunError):
            loaded.require_safe()
    (tmp_path / "episodes.jsonl").mkdir()                       # a directory where the file should be
    assert load_episode_results(tmp_path).report.read_error == "path exists but is not a regular file"


def test_malformed_json_nonstandard_constants_and_non_objects_are_reported_with_line_numbers(tmp_path):
    good = make_result()
    write_lines(tmp_path / "episodes.jsonl", [
        raw_line(good)[:-10],                       # truncated JSON
        raw_line(good),
        '{"spec": NaN}',                            # non-standard constant, rejected like the response parser does
        "[1, 2, 3]",                                # valid JSON, not a record
        "not json at all",
    ])
    report = load_episode_results(tmp_path).report
    assert [p.line for p in report.invalid_json] == [1, 3, 5]
    assert [p.line for p in report.schema_invalid] == [4] and report.schema_invalid[0].message == "record is not a JSON object"
    assert report.valid_records == 1 and not report.safe_for_analysis


def test_schema_invalid_records_are_reported_not_repaired(tmp_path):
    base = make_result()
    write_lines(tmp_path / "episodes.jsonl", [
        raw_line(base, response__confidence=150),                 # out of range
        raw_line(base, unexpected_field=1),                       # extra field is forbidden
        raw_line(make_result(episode_id="ep_000000000002", status="parse_error"), error=None),  # failed result without error
        raw_line(make_result(episode_id="ep_000000000003")),      # valid
    ])
    loaded = load_episode_results(tmp_path)
    problems = loaded.report.schema_invalid
    assert [p.line for p in problems] == [1, 2, 3]
    assert "response.confidence" in problems[0].message and "unexpected_field" in problems[1].message
    assert all(p.message.startswith("schema violation") for p in problems)
    assert [p.episode_id for p in problems] == ["ep_000000000001", "ep_000000000001", "ep_000000000002"]
    assert ids(loaded.records) == ["ep_000000000003"] and not loaded.report.safe_for_analysis


def test_multiple_invalid_lines_keep_their_physical_line_numbers_across_blank_lines(tmp_path):
    write_lines(tmp_path / "episodes.jsonl", [
        raw_line(make_result(episode_id="ep_000000000001")),      # line 1 valid
        "",                                                       # line 2 blank
        "{broken",                                                # line 3
        raw_line(make_result(episode_id="ep_000000000002", rep=1), response__accepts_claim="yes"),   # line 4
        raw_line(make_result(episode_id="ep_000000000003", rep=2)),                                  # line 5 valid
        "{also broken",                                           # line 6
    ])
    report = load_episode_results(tmp_path).report
    assert (report.total_lines, report.blank_lines, report.valid_records) == (6, 1, 2)
    assert [p.line for p in report.invalid_json] == [3, 6] and [p.line for p in report.schema_invalid] == [4]


def test_duplicate_episode_ids_are_reported_never_merged(tmp_path):
    first, second = make_result(episode_id="ep_000000000001", confidence=10), make_result(episode_id="ep_000000000001", confidence=90)
    write_records(tmp_path / "episodes.jsonl", [first, make_result(episode_id="ep_000000000002", rep=1), second])
    loaded = load_episode_results(tmp_path)
    assert [(d.episode_id, d.lines) for d in loaded.report.duplicate_ids] == [("ep_000000000001", (1, 3))]
    assert len(loaded.records) == 3 and loaded.records[0] == first and loaded.records[2] == second   # both kept as written
    assert loaded.report.structurally_valid is False and loaded.report.safe_for_analysis is False
    with pytest.raises(UnsafeRunError, match="duplicated episode id"):
        loaded.require_safe()


def test_the_expected_inventory_is_optional_and_compared_only_when_supplied(tmp_path):
    results = numbered(3)
    write_records(tmp_path / "episodes.jsonl", results)
    exact = load_episode_results(tmp_path, expected_episode_ids=ids(results)).report
    assert exact.expected_supplied and exact.inventory_matches is True and exact.safe_for_analysis
    assert not (exact.missing_expected or exact.invalid_expected or exact.unexpected)
    wrong = load_episode_results(tmp_path, expected_episode_ids=["ep_000000000001", "ep_000000000002", "ep_000000000009", "ep_000000000009"]).report
    assert wrong.missing_expected == ("ep_000000000009",) and wrong.unexpected == ("ep_000000000003",)
    assert wrong.duplicate_expected_ids == ("ep_000000000009",)
    assert wrong.inventory_matches is False and not wrong.safe_for_analysis
    assert load_episode_results(tmp_path, expected_episode_ids=[]).report.unexpected == tuple(ids(results))
    with pytest.raises(ValueError):
        load_episode_results(tmp_path, expected_episode_ids=["ok", ""])


def test_missing_invalid_and_zero_valued_records_remain_distinguishable(tmp_path):
    zero = make_result(episode_id="ep_000000000001", cond="C0", accepts=False, confidence=0, roots=0)
    write_lines(tmp_path / "episodes.jsonl", [
        raw_line(zero),                                                                   # valid, every value zero / false
        raw_line(make_result(episode_id="ep_000000000002", rep=1), response__confidence=-5),   # present but invalid
        # ep_000000000003 never appears: missing
    ])
    loaded = load_episode_results(tmp_path, expected_episode_ids=["ep_000000000001", "ep_000000000002", "ep_000000000003"])
    report = loaded.report
    assert report.valid_records == 1 and report.missing_expected == ("ep_000000000003",)
    assert report.invalid_expected == ("ep_000000000002",) and report.unexpected == ()
    only = loaded.records[0].response
    assert (only.accepts_claim, only.confidence, only.estimated_independent_roots) == (False, 0, 0)   # a real response, not missing
    assert loaded.records[0].spec.n_messages == 0


def test_an_unattributable_invalid_line_does_not_count_as_a_missing_or_unexpected_id(tmp_path):
    write_lines(tmp_path / "episodes.jsonl", ["{broken", raw_line(make_result(episode_id="ep_000000000001"))])
    report = load_episode_results(tmp_path, expected_episode_ids=["ep_000000000001"]).report
    assert report.missing_expected == () and report.unexpected == () and report.inventory_matches is True
    assert report.safe_for_analysis is False                    # still unsafe: a line was invalid


def test_failed_episodes_are_valid_records_not_load_errors(tmp_path):
    write_records(tmp_path / "episodes.jsonl", [
        make_result(episode_id="ep_000000000001"),
        make_result(episode_id="ep_000000000002", rep=1, status="call_error"),
        make_result(episode_id="ep_000000000003", rep=2, status="parse_error"),
    ])
    loaded = load_episode_results(tmp_path)
    assert loaded.report.safe_for_analysis and [r.status for r in loaded.records] == ["ok", "call_error", "parse_error"]


def test_report_never_contains_record_content(tmp_path):
    secret = "SYN-CONTENT-SENTINEL"
    base = make_result(reasoning=secret)
    write_lines(tmp_path / "episodes.jsonl", [
        raw_line(base, response__confidence=secret),            # wrong type carrying the sentinel
        raw_line(base, extra=secret),
        secret + " {not json",
    ])
    report = load_episode_results(tmp_path).report
    assert report.schema_invalid and report.invalid_json
    assert secret not in repr(report)


def test_invalid_utf8_is_a_read_error(tmp_path):
    (tmp_path / "episodes.jsonl").write_bytes(raw_line(make_result()).encode() + b"\n\xff\xfe\n")
    report = load_episode_results(tmp_path).report
    assert report.read_error and "UTF-8" in report.read_error and not report.safe_for_analysis


def test_loading_never_modifies_the_file_and_the_output_feeds_the_adapter(tmp_path):
    results = numbered(2, cond="C4")
    path = write_records(tmp_path / "episodes.jsonl", results)
    before = file_hash(path)
    loaded = load_episode_results(tmp_path)
    assert file_hash(path) == before and sorted(p.name for p in tmp_path.iterdir()) == ["episodes.jsonl"]
    rows = episode_results_to_rows(loaded.require_safe())
    assert [r.episode_id for r in rows] == ids(results) and all(r.truth_label is None for r in rows)


def test_the_loader_adds_no_labels_and_uses_no_network_or_subprocess_modules():
    source = Path(loader_module.__file__).read_text(encoding="utf-8")
    assert "truth" not in source.lower()                       # no hidden-label field is read, derived or reported
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    # "io" was added in v2.3.53 for the byte-based parser (io.TextIOWrapper over io.BytesIO): no network or process code
    assert imported <= {"__future__", "io", "json", "collections", "dataclasses", "pathlib", "pydantic", "maps"}
    assert json  # the module's own parser is the standard library's
