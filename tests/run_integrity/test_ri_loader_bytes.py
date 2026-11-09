"""The byte-based parser must behave exactly like the path loader (one shared scanning implementation; offline)."""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

import maps.adapters.run_loader as loader_module
from maps.adapters.run_loader import load_episode_results, parse_episode_results

from ri_support import make_result, numbered, raw_line


def good_lines(n=3):
    return [raw_line(r) for r in numbered(n)]


CORPUS = {
    "valid": ("\n".join(good_lines(3)) + "\n").encode(),
    "no-trailing-newline": "\n".join(good_lines(2)).encode(),
    "blank-lines": ("\n\n" + good_lines(2)[0] + "\n\n   \n" + good_lines(2)[1] + "\n").encode(),
    "empty": b"",
    "only-blanks": b"\n\n  \n",
    "invalid-json": ("{broken\n" + good_lines(1)[0] + "\n").encode(),
    "nan-constant": (good_lines(1)[0].replace('"confidence": 80', '"confidence": NaN') + "\n").encode(),
    "non-object": b'[1, 2]\n"text"\n5\nnull\n',
    "schema-invalid": (json.dumps({"spec": {"episode_id": "ep_x"}, "status": "ok"}) + "\n" + good_lines(1)[0] + "\n").encode(),
    "extra-field": (raw_line(make_result(), bogus=1) + "\n").encode(),
    "duplicate": ("\n".join([good_lines(1)[0]] * 2) + "\n").encode(),
    "crlf": ("\r\n".join(good_lines(3)) + "\r\n").encode(),
    "lone-cr": ("\r".join(good_lines(2)) + "\r").encode(),
    "bom": b"\xef\xbb\xbf" + ("\n".join(good_lines(2)) + "\n").encode(),
    "invalid-utf8-start": b"\xff\xfe" + b"x\n",
    "invalid-utf8-after-lines": ("\n".join(good_lines(2)) + "\n").encode() + b"\xff\xfe\n",
    "unicode": (raw_line(make_result(reasoning="héllo wörld ✓")) + "\n").encode(),
    "long-line": (json.dumps({"x": "y" * 20000}) + "\n").encode(),
}


def comparable(result):
    report = dataclasses.asdict(result.report)
    report.pop("path")
    return ([r.model_dump(mode="json") for r in result.records], result.line_numbers, report)


@pytest.mark.parametrize("name", sorted(CORPUS))
@pytest.mark.parametrize("expected", [None, ["ep_000000000001", "ep_000000000002", "ep_000000000003"], ["ep_000000000009"]], ids=["no-inventory", "inventory", "other-inventory"])
def test_the_byte_parser_matches_the_path_loader_exactly(tmp_path, name, expected):
    (tmp_path / "episodes.jsonl").write_bytes(CORPUS[name])
    by_path = load_episode_results(tmp_path, expected_episode_ids=expected)
    by_bytes = parse_episode_results(CORPUS[name], expected_episode_ids=expected)
    assert comparable(by_bytes) == comparable(by_path), name


def test_the_report_path_text_is_the_source_label_or_the_real_path(tmp_path):
    (tmp_path / "episodes.jsonl").write_bytes(CORPUS["valid"])
    assert load_episode_results(tmp_path).report.path == str(tmp_path / "episodes.jsonl")
    assert parse_episode_results(CORPUS["valid"]).report.path == "episodes.jsonl"
    assert parse_episode_results(CORPUS["valid"], source="custom").report.path == "custom"


def test_missing_and_non_regular_paths_keep_their_existing_reports(tmp_path):
    missing = load_episode_results(tmp_path).report
    assert not missing.file_exists and any("not found" in p for p in missing.problems) and not missing.structurally_valid
    (tmp_path / "episodes.jsonl").mkdir()
    directory = load_episode_results(tmp_path).report
    assert directory.read_error == "path exists but is not a regular file" and not directory.file_exists


def test_the_byte_parser_validates_its_inputs(tmp_path):
    with pytest.raises(TypeError):
        parse_episode_results("a string, not bytes")            # type: ignore[arg-type]
    with pytest.raises(ValueError):
        parse_episode_results(CORPUS["valid"], expected_episode_ids=["ok", ""])
    assert parse_episode_results(bytearray(CORPUS["valid"])).report.valid_records == 3


def test_the_byte_parser_never_touches_the_filesystem(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    parse_episode_results(CORPUS["valid"], source=str(tmp_path / "does-not-exist.jsonl"))
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_there_is_a_single_scanning_implementation():
    tree = ast.parse(Path(loader_module.__file__).read_text(encoding="utf-8"))
    parsers = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "model_validate"]
    scans = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "loads"]
    assert len(parsers) == 1 and len(scans) == 1                # one validation site and one JSON decode site, reached from both entry points
    public = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in ("load_episode_results", "parse_episode_results"):
        callees = {c.func.id for c in ast.walk(public[name]) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        assert "_load" in callees, name
