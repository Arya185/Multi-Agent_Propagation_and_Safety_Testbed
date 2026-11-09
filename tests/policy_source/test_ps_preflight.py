"""Loading and refusing a policy has no side effects, and the module's boundaries are static facts (v2.3.66, Stage 4D). Offline.

Every invalid policy is refused with exit-code-2 semantics BEFORE credentials, a client, a run directory, a claim or any
network use could be reached: here that means the loader itself touches none of them (the tripwire fixture fails any
test in which one is reached). The CLI ordering is wired in Stage 4E; the Stage 4C refusal is untouched.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import maps.runs.policy_source as policy_source
from maps.runs.policy_source import REFUSAL_EXIT_CODE, PolicySourceError, load_policy

from ps_support import PROFILE, SENTINEL, listing, load_inputs, make_doc, make_limits, mutated, tripwires, write_policy  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(policy_source.__file__)
ALLOWED_IMPORTS = {
    "__future__", "hashlib", "itertools", "json", "re", "collections.abc", "dataclasses", "pathlib", "maps.config",
    "maps.runs.artifact_hashes", "maps.runs.live_policy", "maps.scenarios",
}
FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "socket", "ssl", "http", "urllib", "requests", "dotenv", "shutil", "tempfile", "importlib",
    "runpy", "argparse", "getpass", "environ", "getenv", "OpenRouterClient", "get_api_key", "initialize_run_dir", "check_run_dir",
    "execute_live_run", "load_dotenv",
}
FORBIDDEN_BARE_CALLS = {"open", "exec", "eval", "compile", "__import__"}     # as bare names; ``re.compile`` is an attribute and is fine


@pytest.fixture(scope="module")
def inputs():
    return load_inputs()


def good_doc(inputs):
    cfg, _s, specs, digests = inputs
    return make_doc(cfg, specs, digests)


INVALID = {
    "schema": lambda d: d.update(schema_version=2),
    "unknown-field": lambda d: d.update(extra=1),
    "missing-field": lambda d: d.pop("approval"),
    "type": lambda d: d["scope"].update(seed="x"),
    "scope": lambda d: d["scope"].update(experiment_id="other"),
    "grid": lambda d: d["scope"].update(planned_episodes=95),
    "content": lambda d: next(iter(d["scope"]["content"].values())).update(scenario_sha256="0" * 64),
    "limits": lambda d: d["profiles"][PROFILE].update(max_request_attempts=1),
    "config": lambda d: d["profiles"][PROFILE].update(make_limits(96, 1)),
}


@pytest.mark.parametrize("name", sorted(INVALID))
def test_an_invalid_policy_is_refused_with_no_side_effects(tmp_path, inputs, name):
    cfg, _s, specs, digests = inputs
    work = tmp_path / "work"
    work.mkdir()
    path = write_policy(work, mutated(good_doc(inputs), INVALID[name]))
    before = listing(tmp_path)
    with pytest.raises(PolicySourceError) as e:
        load_policy(path, cfg=cfg, specs=specs, content_digests=digests, profile=PROFILE)
    assert isinstance(e.value, ValueError) and e.value.reason in policy_source.REASONS
    assert listing(tmp_path) == before                                    # no run directory, claim, results or any other file
    assert not (tmp_path / "results").exists()


def test_a_missing_policy_is_refused_with_no_side_effects(tmp_path, inputs):
    cfg, _s, specs, digests = inputs
    before = listing(tmp_path)
    with pytest.raises(PolicySourceError):
        load_policy(tmp_path / "nope.json", cfg=cfg, specs=specs, content_digests=digests, profile=PROFILE)
    assert listing(tmp_path) == before


def test_a_valid_load_also_has_no_side_effects(tmp_path, inputs):
    cfg, _s, specs, digests = inputs
    path = write_policy(tmp_path, good_doc(inputs))
    before = listing(tmp_path)
    load_policy(path, cfg=cfg, specs=specs, content_digests=digests, profile=PROFILE)
    assert listing(tmp_path) == before and path.read_bytes() == path.read_bytes()


def test_the_refusal_exit_code_is_two():
    assert REFUSAL_EXIT_CODE == 2


def test_error_messages_never_contain_policy_values(tmp_path, inputs):
    cfg, _s, specs, digests = inputs
    for mutate in (
        lambda d: d.update(policy_id=SENTINEL + " bad"), lambda d: d["scope"].update(experiment_id=SENTINEL),
        lambda d: d["scope"].update({SENTINEL: 1}), lambda d: d["approval"].update(approval_reference=3),
        lambda d: d["profiles"][PROFILE].update(accounting_basis=SENTINEL), lambda d: d["scope"]["models"][0].update(model_id=SENTINEL),
    ):
        path = write_policy(tmp_path, mutated(good_doc(inputs), mutate))
        with pytest.raises(PolicySourceError) as e:
            load_policy(path, cfg=cfg, specs=specs, content_digests=digests, profile=PROFILE)
        assert SENTINEL not in str(e.value) and SENTINEL not in repr(e.value)


# ---- static boundaries of the module ------------------------------------------------------------------------------------------
def imports_of_module() -> set[str]:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


def test_the_module_imports_only_the_reviewed_set():
    assert imports_of_module() <= ALLOWED_IMPORTS, imports_of_module() - ALLOWED_IMPORTS


def test_the_module_has_no_environment_network_process_client_or_dynamic_loading_names():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    bare = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names = bare | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & FORBIDDEN_NAMES, names & FORBIDDEN_NAMES
    assert not bare & FORBIDDEN_BARE_CALLS, bare & FORBIDDEN_BARE_CALLS


def test_the_module_names_no_url_no_env_file_and_no_client_text():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and "\n" not in n.value]
    assert not [s for s in strings if "://" in s or s.endswith(".env") or "OpenRouter" in s or "openrouter" in s]


def _importers(module_name: str) -> list[str]:
    found = []
    for path in sorted((REPO_ROOT / "src" / "maps").rglob("*.py")):
        if path.name == f"{module_name}.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            if any(n.split(".")[-1] == module_name for n in names):
                found.append(path.relative_to(REPO_ROOT / "src" / "maps").as_posix())
                break
    return found


def test_only_the_cli_imports_the_policy_source():
    """v2.3.74 (Stage 4E): the CLI preflight loads the policy; no executor, pipeline or other module imports it."""
    assert _importers("policy_source") == ["experiments/receiver.py"]


def test_the_live_branch_still_ends_in_the_final_refusal():
    source = (REPO_ROOT / "src" / "maps" / "experiments" / "receiver.py").read_text(encoding="utf-8")
    assert "FINAL REFUSAL" in source and "get_api_key" not in source and "load_dotenv" not in source and "OpenRouterClient" not in source


def test_the_live_policy_module_is_unchanged_in_shape():
    import dataclasses

    from maps.runs.live_policy import LivePolicy

    assert [f.name for f in dataclasses.fields(LivePolicy)] == [
        "approval_reference", "planned_episodes", "max_episodes", "max_request_attempts", "max_retries", "deadline_seconds",
        "max_consecutive_nonfatal_errors", "accounting_basis", "nonfatal_4xx_statuses", "fatal_3xx",
    ]
    assert "max_tokens_per_request" not in {f.name for f in dataclasses.fields(LivePolicy)}      # stripped by the loader, not stored


def test_loading_the_real_class_never_constructs_the_provider_client_even_when_patched_to_raise(tmp_path, inputs):
    cfg, _s, specs, digests = inputs
    path = write_policy(tmp_path, good_doc(inputs))
    assert load_policy(path, cfg=cfg, specs=specs, content_digests=digests, profile=PROFILE).policy.max_retries == cfg.api.max_retries
