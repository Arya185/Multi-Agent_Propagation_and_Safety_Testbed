"""Allow-list validation and scan comparison on synthetic trees (v2.3.56, Stage 4C). Offline."""

from __future__ import annotations

import copy
import json
import socket
from pathlib import Path

import pytest

from route_check import check_tree, compare, validate_entries
from route_scanner import scan_tree

SNIPPETS = Path(__file__).parent / "snippets"
CASES = json.loads((SNIPPETS / "cases.json").read_text(encoding="utf-8"))
NOTEBOOKS = json.loads((SNIPPETS / "notebooks.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted by the allow-list tests")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def entry(path, kinds, *, category="test", classification="test_only", **over):
    base = {
        "path": path, "category": category, "purpose": "A synthetic file used by the allow-list tests.",
        "classification": classification, "kinds": tuple(kinds),
        "justification": "Synthetic entry for a synthetic tree; nothing here is real.",
    }
    base.update(over)
    return base


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "maps").mkdir(parents=True)
    return tmp_path


def write(tree, rel, text):
    path = tree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---- the happy path and the exact-match rule --------------------------------------------------------------
def test_a_listed_file_with_exactly_its_kinds_passes(tree):
    write(tree, "tests/t.py", CASES["import_requests"])
    assert check_tree(tree, [entry("tests/t.py", ["network_import"])]) == []


def test_clean_files_need_no_entry(tree):
    write(tree, "tests/t.py", CASES["plain"])
    assert check_tree(tree, []) == []


def test_an_unlisted_file_with_findings_fails(tree):
    write(tree, "tests/t.py", CASES["import_requests"])
    problems = check_tree(tree, [])
    assert len(problems) == 1 and "tests/t.py" in problems[0] and "not in the provider-route allow-list" in problems[0]


@pytest.mark.parametrize("name,kind", [
    ("import_requests", "network_import"), ("client_import", "provider_client_ref"), ("complete_call", "complete_call"),
    ("endpoint_https", "endpoint_literal"), ("dyn_exec", "dynamic_load"), ("curl_string", "shell_fetch"),
])
def test_a_new_kind_in_a_listed_file_fails_until_the_entry_is_edited(tree, name, kind):
    write(tree, "tests/t.py", CASES["plain"] + CASES[name])
    # the file is listed for something else only
    other = "network_import" if kind != "network_import" else "complete_call"
    problems = check_tree(tree, [entry("tests/t.py", [other])])
    assert any("has findings not in its entry" in p and kind in p for p in problems)


def test_a_new_requests_import_added_to_an_allowed_socket_file_is_caught(tree):
    write(tree, "tests/t.py", CASES["import_socket"])
    assert check_tree(tree, [entry("tests/t.py", ["network_import"])]) == []      # the module name is not part of the entry...
    write(tree, "tests/t.py", CASES["import_socket"] + CASES["client_import"])    # ...but a new KIND is
    assert check_tree(tree, [entry("tests/t.py", ["network_import"])])


def test_an_entry_with_kinds_the_file_no_longer_has_fails(tree):
    write(tree, "tests/t.py", CASES["import_requests"])
    problems = check_tree(tree, [entry("tests/t.py", ["network_import", "complete_call"])])
    assert any("no longer has" in p for p in problems)


def test_a_listed_file_with_no_findings_is_a_stale_entry(tree):
    write(tree, "tests/t.py", CASES["plain"])
    problems = check_tree(tree, [entry("tests/t.py", ["network_import"])])
    assert any("stale entry" in p for p in problems)


def test_unparseable_files_fail_even_if_listed(tree):
    write(tree, "tests/t.py", CASES["syntax_error"])
    problems = check_tree(tree, [entry("tests/t.py", ["network_import"])])
    assert any("cannot be analysed" in p for p in problems)


# ---- notebooks: file-level listing only (PR5) -------------------------------------------------------------
def test_an_unlisted_notebook_fails_even_when_clean(tree):
    write(tree, "scripts/n.ipynb", json.dumps(NOTEBOOKS["clean"]))
    problems = check_tree(tree, [])
    assert len(problems) == 1 and "scripts/n.ipynb" in problems[0]


def test_a_listed_clean_notebook_passes_and_a_dirty_one_needs_its_kinds(tree):
    write(tree, "scripts/n.ipynb", json.dumps(NOTEBOOKS["clean"]))
    e = entry("scripts/n.ipynb", [], category="notebook", classification="diagnostic_only")
    assert check_tree(tree, [e]) == []
    write(tree, "scripts/n.ipynb", json.dumps(NOTEBOOKS["requests"]))
    assert any("has findings not in its entry" in p for p in check_tree(tree, [e]))
    assert check_tree(tree, [dict(e, kinds=("network_import",))]) == []


def test_notebook_findings_in_each_cell_type_are_caught(tree):
    for name in ("client", "complete", "magic_curl", "bash_cell", "dynamic"):
        write(tree, "scripts/n.ipynb", json.dumps(NOTEBOOKS[name]))
        e = entry("scripts/n.ipynb", [], category="notebook", classification="diagnostic_only")
        assert check_tree(tree, [e]), name


def test_a_malformed_notebook_fails_closed(tree):
    write(tree, "scripts/n.ipynb", "{not json")
    e = entry("scripts/n.ipynb", [], category="notebook", classification="diagnostic_only")
    assert any("cannot be analysed" in p for p in check_tree(tree, [e]))


def test_a_notebook_entry_needs_the_notebook_category_and_extension(tree):
    write(tree, "scripts/n.ipynb", json.dumps(NOTEBOOKS["clean"]))
    write(tree, "scripts/s.py", CASES["import_requests"])
    assert validate_entries([entry("scripts/n.ipynb", [], category="script", classification="diagnostic_only")], tree)
    assert validate_entries([entry("scripts/s.py", ["network_import"], category="notebook", classification="diagnostic_only")], tree)


# ---- shell scripts -----------------------------------------------------------------------------------------
def test_a_shell_script_with_curl_needs_an_entry(tree):
    write(tree, "scripts/get.sh", CASES["sh_curl"])
    assert any("scripts/get.sh" in p for p in check_tree(tree, []))
    ok = entry("scripts/get.sh", ["endpoint_literal", "shell_fetch"], category="script", classification="diagnostic_only")
    assert check_tree(tree, [ok]) == []


# ---- malformed allow-lists fail closed ---------------------------------------------------------------------
def test_malformed_entries_are_reported_and_the_tree_is_not_judged(tree):
    write(tree, "tests/t.py", CASES["import_requests"])
    good = entry("tests/t.py", ["network_import"])
    assert validate_entries([good], tree) == []
    bad_cases = {
        "missing field": {k: v for k, v in good.items() if k != "justification"},
        "extra field": dict(good, owner="x"),
        "not a mapping": "tests/t.py",
        "empty path": dict(good, path=""),
        "non-string path": dict(good, path=3),
        "wildcard": dict(good, path="tests/*.py"),
        "directory": dict(good, path="tests/"),
        "bare directory": dict(good, path="tests"),
        "parent traversal": dict(good, path="tests/../tests/t.py"),
        "absolute": dict(good, path="/etc/passwd"),
        "backslash": dict(good, path="tests\\t.py"),
        "dot slash": dict(good, path="./tests/t.py"),
        "missing file": dict(good, path="tests/missing.py"),
        "unknown classification": dict(good, classification="whatever"),
        "unknown category": dict(good, category="whatever"),
        "empty purpose": dict(good, purpose=""),
        "placeholder justification": dict(good, justification="TODO"),
        "unknown kind": dict(good, kinds=("telepathy",)),
        "never-allowlistable kind": dict(good, kinds=("unparseable",)),
        "kinds not a sequence": dict(good, kinds="network_import"),
        "duplicate kinds": dict(good, kinds=("network_import", "network_import")),
        "empty kinds on a non-notebook": dict(good, kinds=()),
        "wrong root for classification": dict(good, classification="guarded_experiment", category="source"),
        "category does not fit": dict(good, classification="guarded_experiment", category="test", path="tests/t.py"),
    }
    for label, bad in bad_cases.items():
        assert validate_entries([bad], tree), label
        problems = check_tree(tree, [bad])
        assert problems and not any("not in the provider-route allow-list" in p for p in problems), label    # fails before judging the tree


def test_a_directory_entry_is_rejected_even_if_the_directory_exists(tree):
    write(tree, "tests/t.py", CASES["import_requests"])
    assert any("directory" in p or "plain relative" in p for p in validate_entries([entry("tests", ["network_import"])], tree))


def test_duplicate_entries_are_rejected(tree):
    write(tree, "tests/t.py", CASES["import_requests"])
    e = entry("tests/t.py", ["network_import"])
    assert any("duplicate" in p for p in validate_entries([e, copy.deepcopy(e)], tree))


def test_a_non_sequence_allow_list_is_rejected(tree):
    assert validate_entries(None, tree) and validate_entries({"tests/t.py": 1}, tree)


def test_classification_roots_are_enforced(tree):
    write(tree, "src/maps/m.py", CASES["import_requests"])
    write(tree, "scripts/s.py", CASES["import_requests"])
    write(tree, "tests/t.py", CASES["import_requests"])
    ok = [
        entry("src/maps/m.py", ["network_import"], category="source", classification="guarded_experiment"),
        entry("scripts/s.py", ["network_import"], category="script", classification="diagnostic_only"),
        entry("tests/t.py", ["network_import"]),
    ]
    assert validate_entries(ok, tree) == []
    for index, wrong in ((0, "diagnostic_only"), (1, "test_only"), (2, "guarded_experiment")):
        broken = copy.deepcopy(ok)
        broken[index]["classification"] = wrong
        assert validate_entries(broken, tree), wrong


# ---- compare() on its own ------------------------------------------------------------------------------------
def test_compare_reports_each_problem_once_and_never_file_content(tree):
    write(tree, "tests/a.py", CASES["import_requests"])
    write(tree, "tests/b.py", CASES["endpoint_https"])
    problems = compare(scan_tree(tree), [entry("tests/a.py", ["network_import"])])
    assert len(problems) == 1 and "tests/b.py" in problems[0] and "api.example.invalid" not in problems[0]
