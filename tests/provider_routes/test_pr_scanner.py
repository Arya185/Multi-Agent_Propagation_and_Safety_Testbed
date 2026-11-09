"""Provider-route scanner behaviour on small synthetic snippets (v2.3.56, Stage 4C). Offline; nothing is imported or run.

The snippets live in ``snippets/*.json`` as text, so this file itself contains none of the patterns it tests.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import route_scanner as rs

SNIPPETS = Path(__file__).parent / "snippets"
CASES = json.loads((SNIPPETS / "cases.json").read_text(encoding="utf-8"))
NOTEBOOKS = json.loads((SNIPPETS / "notebooks.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted by the scanner tests")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def kinds(name: str) -> set[str]:
    return {f.kind for f in rs.scan_python_source(CASES[name])}


# ---- clean code is clean ---------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["plain", "re_compile_ok", "bare_word_names", "curl_word_inside", "fake_client_class", "complete_define_only"])
def test_clean_snippets_have_no_findings_except_documented_ones(name):
    expected = {"fake_client_class": set(), "complete_define_only": set()}.get(name, set())
    assert kinds(name) == expected


# ---- network imports, including aliases -----------------------------------------------------------------
@pytest.mark.parametrize("name", [
    "import_requests", "import_requests_alias", "from_requests", "import_urllib_request", "from_urllib", "import_http_client",
    "import_socket", "import_httpx", "star_import",
])
def test_network_imports_are_found_including_aliases(name):
    assert "network_import" in kinds(name)


def test_the_module_name_is_reported_not_the_alias():
    (finding,) = [f for f in rs.scan_python_source(CASES["import_requests_alias"]) if f.kind == "network_import"]
    assert finding.detail == "requests" and finding.line == 1


# ---- the provider client: module, class, aliases, indirect references -----------------------------------
@pytest.mark.parametrize("name", [
    "client_import", "client_import_alias", "client_assign_alias", "client_getattr", "client_concat", "client_join",
    "client_subclass", "client_class_named",
])
def test_provider_client_references_are_found_directly_by_alias_and_indirectly(name):
    assert "provider_client_ref" in kinds(name)


@pytest.mark.parametrize("name", ["client_import", "client_assign_alias", "module_import_only", "module_from_import", "module_relative_import", "module_relative_from"])
def test_importing_the_client_module_is_a_finding_in_every_spelling(name):
    assert "provider_client_module" in kinds(name)


# ---- .complete( calls --------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["complete_call", "complete_getattr"])
def test_complete_calls_are_found(name):
    assert "complete_call" in kinds(name)


@pytest.mark.parametrize("name", ["complete_define_only", "fake_client_class"])
def test_defining_a_fake_client_with_a_complete_method_is_not_a_call(name):
    assert "complete_call" not in kinds(name)


# ---- endpoints ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["endpoint_https", "endpoint_openrouter", "endpoint_path", "endpoint_fstring", "endpoint_concat", "endpoint_ws"])
def test_endpoint_literals_are_found(name):
    assert "endpoint_literal" in kinds(name)


# ---- dynamic loading ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", [
    "dyn_import", "dyn_importlib", "dyn_import_module_from", "dyn_exec", "dyn_eval", "dyn_compile", "dyn_spec", "dyn_loader", "dyn_alias",
])
def test_dynamic_loading_is_found(name):
    assert "dynamic_load" in kinds(name)


def test_re_compile_is_not_dynamic_loading():
    assert "dynamic_load" not in kinds("re_compile_ok")


# ---- curl / wget -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["curl_string", "wget_string"])
def test_curl_and_wget_in_python_strings_are_found(name):
    assert "shell_fetch" in kinds(name)


def test_words_that_merely_contain_curl_are_not_found():
    assert "shell_fetch" not in kinds("curl_word_inside")


@pytest.mark.parametrize("name,expected", [("sh_curl", True), ("sh_wget", True), ("sh_comment", False), ("sh_clean", False)])
def test_shell_scripts(name, expected):
    found = {f.kind for f in rs.scan_shell_source(CASES[name])}
    assert ("shell_fetch" in found) is expected


# ---- comments and docstrings are ignored ---------------------------------------------------------------------
@pytest.mark.parametrize("name", ["comment_only", "docstring_only"])
def test_comments_and_docstrings_are_not_findings(name):
    assert rs.scan_python_source(CASES[name]) == []


def test_a_bare_name_that_merely_looks_like_a_module_is_not_an_import():
    assert kinds("bare_word_names") == set()


# ---- unparseable code fails closed ----------------------------------------------------------------------------
def test_unparseable_python_raises_in_the_snippet_scanner_and_is_a_problem_for_a_file(tmp_path):
    with pytest.raises(SyntaxError):
        rs.scan_python_source(CASES["syntax_error"])
    (tmp_path / "bad.py").write_text(CASES["syntax_error"], encoding="utf-8")
    scan = rs.scan_file(tmp_path / "bad.py", tmp_path)
    assert scan is not None and scan.problem == "unparseable"
    assert "bad.py" in rs.scan_tree(tmp_path)


# ---- notebooks -------------------------------------------------------------------------------------------------
def nb_kinds(name: str) -> tuple[set[str], str | None]:
    text = NOTEBOOKS[name] if isinstance(NOTEBOOKS[name], str) else json.dumps(NOTEBOOKS[name])
    findings, problem = rs.scan_notebook_text(text)
    return {f.kind for f in findings}, problem


@pytest.mark.parametrize("name", ["clean", "empty", "magic_pip_clean"])
def test_clean_notebooks_have_no_findings(name):
    assert nb_kinds(name) == (set(), None)


@pytest.mark.parametrize("name,kind", [
    ("requests", "network_import"), ("client", "provider_client_ref"), ("complete", "complete_call"), ("magic_curl", "shell_fetch"),
    ("bash_cell", "shell_fetch"), ("dynamic", "dynamic_load"), ("string_source", "network_import"),
])
def test_notebook_code_cells_are_scanned(name, kind):
    found, problem = nb_kinds(name)
    assert problem is None and kind in found


def test_markdown_cells_are_not_scanned():
    assert nb_kinds("clean") == (set(), None)


@pytest.mark.parametrize("name", ["bad_python", "bad_json", "no_cells"])
def test_malformed_notebooks_fail_closed(name):
    found, problem = nb_kinds(name)
    assert problem == "unparseable" and found == set()


def test_every_notebook_file_appears_in_the_scan_even_when_clean(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "n.ipynb").write_text(json.dumps(NOTEBOOKS["clean"]), encoding="utf-8")
    scans = rs.scan_tree(tmp_path)
    assert list(scans) == ["scripts/n.ipynb"] and scans["scripts/n.ipynb"].is_notebook and scans["scripts/n.ipynb"].findings == []


# ---- file discovery ---------------------------------------------------------------------------------------------
def test_discovery_covers_python_shell_and_shebang_files_and_prunes_environments(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.py").write_text(CASES["import_requests"], encoding="utf-8")
    (tmp_path / "a" / "run.sh").write_text(CASES["sh_curl"], encoding="utf-8")
    (tmp_path / "a" / "tool").write_text(CASES["sh_wget"], encoding="utf-8")        # no extension, shell shebang
    (tmp_path / "a" / "pytool").write_text("#!/usr/bin/env python3\nimport socket\n", encoding="utf-8")
    (tmp_path / "a" / "notes").write_text("curl http://x.invalid\n", encoding="utf-8")   # no shebang: not source
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "v.py").write_text(CASES["import_requests"], encoding="utf-8")
    assert sorted(rs.scan_tree(tmp_path)) == ["a/pytool", "a/run.sh", "a/tool", "a/x.py"]


def test_unscanned_languages_are_reported_so_they_need_a_listing(tmp_path):
    (tmp_path / "fetch.js").write_text("fetch('x')\n", encoding="utf-8")
    scans = rs.scan_tree(tmp_path)
    assert {f.kind for f in scans["fetch.js"].findings} == {"unscanned_source"}


def test_env_files_are_never_opened(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".env.local.py").write_text(CASES["import_requests"], encoding="utf-8")
    opened = []
    real_open = Path.open

    def spy(self, *args, **kwargs):
        opened.append(self.name)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy)
    assert rs.scan_tree(tmp_path) == {}
    assert not [name for name in opened if name.startswith(".env")]


def test_symlinked_source_is_a_problem_not_followed(tmp_path):
    target = tmp_path / "real.py"
    target.write_text(CASES["plain"], encoding="utf-8")
    (tmp_path / "link.py").symlink_to(target)
    scans = rs.scan_tree(tmp_path)
    assert scans["link.py"].problem == "symlink"


def test_findings_never_carry_file_content_beyond_fixed_labels():
    for source in CASES.values():
        try:
            findings = rs.scan_python_source(source)
        except SyntaxError:
            continue
        for finding in findings:
            assert finding.detail in {
                "requests", "urllib", "http", "socket", "httpx", "maps.llm_client", "llm_client", "relative", "from-import",
                "OpenRouterClient", ".complete(", "getattr complete", "url-or-provider-literal", "curl-or-wget",
                "__import__", "exec", "eval", "compile", "import_module", "spec_from_file_location", "exec_module",
            } or finding.detail.startswith("maps"), finding
