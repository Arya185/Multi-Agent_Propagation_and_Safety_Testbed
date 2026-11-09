"""PR6 (v2.3.56, Stage 4C): tests may build the real OpenRouterClient only with a fake transport, a literal dummy
credential and a socket tripwire. The detector is tested on synthetic sources, then run over every test in the repo.
Offline; nothing is imported or executed from the scanned files.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from pr6_check import check_source, construction_calls

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((Path(__file__).parent / "snippets" / "cases.json").read_text(encoding="utf-8"))

# the test files that build the real client today; every one must satisfy the rules
EXPECTED_CONSTRUCTORS = {
    "tests/endpoint_policy/test_ep_validator.py",
    "tests/live_executor/test_le_accounting.py",
    "tests/live_policy/test_lp_redirect_hardening.py",
    "tests/provider_routes/test_pr_script.py",
    "tests/test_client.py",
}


def test_a_protected_construction_passes():
    assert check_source(CASES["pr6_good"]) == []


@pytest.mark.parametrize("name,fragment", [
    ("pr6_no_session", "fake session"),
    ("pr6_none_session", "fake session"),
    ("pr6_no_tripwire", "autouse fixture"),
    ("pr6_tripwire_not_autouse", "autouse fixture"),
    ("pr6_env_key", "literal dummy"),
    ("pr6_getenv_key", "literal dummy"),
    ("pr6_param_key", "literal dummy"),
    ("pr6_dotenv", "environment or .env"),
    ("pr6_real_host", "real provider host"),
    ("pr6_alias", "fake session"),
    ("pr6_alias_import", "fake session"),
    ("pr6_getattr_construct", "fake session"),
    ("pr6_attribute_construct", "fake session"),
])
def test_an_unprotected_construction_is_detected(name, fragment):
    problems = check_source(CASES[name])
    assert problems and any(fragment in p for p in problems), problems


def test_a_default_session_inspection_test_that_never_calls_complete_is_allowed():
    assert check_source(CASES["pr6_default_session_ok"]) == []


@pytest.mark.parametrize("name,fragment", [
    ("pr6_default_session_wrong_name", "fake session"),
    ("pr6_default_session_calls_complete", "fake session"),
    ("pr6_default_session_no_tripwire", "autouse fixture"),
])
def test_the_default_session_allowance_is_narrow(name, fragment):
    problems = check_source(CASES[name])
    assert problems and any(fragment in p for p in problems), problems


@pytest.mark.parametrize("name", ["pr6_refuse_only", "pr6_no_use"])
def test_a_test_that_only_refuses_or_never_mentions_the_client_has_no_requirements(name):
    assert check_source(CASES[name]) == []


def test_alias_and_attribute_and_getattr_constructions_are_all_found():
    for name in ("pr6_alias", "pr6_alias_import", "pr6_getattr_construct", "pr6_attribute_construct", "pr6_good"):
        assert len(construction_calls(ast.parse(CASES[name]))) == 1, name
    assert construction_calls(ast.parse(CASES["pr6_refuse_only"])) == []


def _test_sources():
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path.relative_to(REPO_ROOT).as_posix(), path.read_text(encoding="utf-8")


def test_every_test_in_the_repository_that_builds_the_real_client_is_protected():
    constructors, problems = set(), {}
    for rel, source in _test_sources():
        if construction_calls(ast.parse(source)):
            constructors.add(rel)
            found = check_source(source)
            if found:
                problems[rel] = found
    assert problems == {}
    assert constructors == EXPECTED_CONSTRUCTORS


def test_no_other_test_names_the_real_provider_host():
    offenders = [rel for rel, source in _test_sources() if "openrouter" + ".ai" in source.lower() and not rel.startswith("tests/provider_routes/")]
    assert offenders == []
