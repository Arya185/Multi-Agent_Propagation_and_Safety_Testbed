"""Boundary audit: no client construction, no network/process/environment access, no sensitive text,
no dynamic-import markers, no coupling to the CLI/executor, and the closure is untouched (static + fake client)."""

from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest

import maps.runs.live_budget as budget_module
import maps.runs.live_policy as policy_module
from maps.runs.live_budget import BudgetAbort, BudgetedClient

from lp_support import FakeClient, FakeClock, SENTINEL, err, make_policy, make_request, ok

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES = (policy_module, budget_module)
FORBIDDEN_IMPORTS = {"socket", "urllib", "http", "requests", "subprocess", "os", "shutil", "dotenv", "importlib", "runpy", "pkgutil", "imp", "ssl"}
FORBIDDEN_FIRST_PARTY = ("maps.experiments", "maps.runs.executor", "maps.pipeline", "maps.mock_client", "maps.runs.guard", "maps.runs.provenance")
SUMMARY_FIELDS = {
    "accounting_basis", "accounting_claim", "redirect_exposure", "attempts_cap", "reserved_attempts_per_call", "attempts_charged",
    "attempt_count_untrusted", "logical_calls_started", "calls_returned", "calls_success", "calls_fatal", "calls_nonfatal",
    "calls_raised", "error_category_counts", "consecutive_errors_current", "consecutive_errors_peak",
    "max_consecutive_nonfatal_errors", "stop_reason", "deadline_seconds", "elapsed_seconds_at_last_check",
    "deadline_crossed_by_inflight_call", "in_flight_note", "usage_complete", "usage_partial", "usage_missing", "usage_invalid",
    "provider_reported_prompt_tokens", "provider_reported_completion_tokens", "provider_reported_total_tokens",
    "usage_totals_basis", "requested_completion_ceiling_tokens", "requested_ceiling_basis", "exception_class_counts",
}


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    """Any network access or live-client construction during these tests fails loudly."""
    import maps.llm_client as llm_client

    def refuse(*args, **kwargs):
        raise AssertionError("network or live-client access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(llm_client.OpenRouterClient, "__init__", refuse)


def imports_of(module) -> set[str]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_network_process_environment_or_dynamic_loading_imports(module):
    imported = imports_of(module)
    assert not {name.split(".")[0] for name in imported} & FORBIDDEN_IMPORTS
    assert not [name for name in imported if name.startswith(FORBIDDEN_FIRST_PARTY)]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_client_construction_environment_sleep_or_execution_mechanisms(module):
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {c.func.id for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert not calls & {"exec", "eval", "__import__", "open", "OpenRouterClient", "MockClient"}
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attributes & {"environ", "getenv", "sleep", "system", "Popen", "run", "urlopen", "post", "get"}
    assert "OpenRouterClient" not in source and ".env" not in source and "api_key" not in source.lower()


def test_the_only_first_party_dependencies_are_the_schemas_the_disabled_client_exception_and_the_policy():
    first_party = {name for name in imports_of(budget_module) if name.startswith("maps")}
    assert first_party == {"maps.llm_client", "maps.runs.live_policy", "maps.schemas"}
    assert not [name for name in imports_of(policy_module) if name.startswith("maps")]


def test_only_the_live_executor_imports_the_new_modules_and_the_recorded_closure_is_the_pinned_size():
    importers = []
    for path in (REPO_ROOT / "src" / "maps").rglob("*.py"):
        if path.name in ("live_policy.py", "live_budget.py"):
            continue
        text = path.read_text(encoding="utf-8")
        if "live_policy" in text or "live_budget" in text:
            importers.append(path.name)
    # v2.3.66 (Stage 4D, authorized): policy_source.py builds a LivePolicy from the policy file, so it also names live_policy.
    assert sorted(importers) == ["live_executor.py", "policy_source.py"]   # not the CLI, the mock executor, the lifecycle or the pipeline
    support = ast.parse((REPO_ROOT / "tests" / "synthetic" / "synthetic_support.py").read_text(encoding="utf-8"))
    recorded = next(ast.literal_eval(n.value) for n in ast.walk(support) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SOURCE_FILES")
    # pinned size: 20 after v2.3.46; 21 after v2.3.48 (runs/lifecycle.py); 24 after v2.3.49 (runs/live_executor.py plus the
    # live_policy and live_budget modules it imports); 25 after v2.3.53 (runs/artifact_hashes.py); 27 after v2.3.74 (Stage 4E: the
    # CLI now imports runs/policy_source.py and runs/endpoint_policy.py); 29 after Stage 4J.3 (owner-authorized: the CLI now imports
    # registry.py, which imports validation.py). Update only for an authorized change.
    assert {"runs/lifecycle.py", "runs/live_executor.py", "runs/live_budget.py", "runs/live_policy.py", "runs/artifact_hashes.py"} <= set(recorded) and len(recorded) == 29


def test_summaries_and_abort_messages_hold_no_prompts_outputs_secrets_or_provider_bodies():
    policy = make_policy(max_consecutive_nonfatal_errors=2, max_retries=1, max_request_attempts=40)
    client = FakeClient(
        [ok(content=f"model output {SENTINEL}"), err(f"http_503: {SENTINEL}"), err(f"api_error: {SENTINEL}"), RuntimeError(SENTINEL)],
        max_retries=1,
    )
    budget = BudgetedClient(client, policy, clock=FakeClock())
    request = make_request()
    request.messages[0].content = f"prompt {SENTINEL}"
    budget.complete(request)
    budget.complete(request)
    budget.complete(request)
    with pytest.raises(BudgetAbort) as caught:
        budget.complete(request)
    assert SENTINEL not in str(caught.value) and SENTINEL not in repr(caught.value)
    summary = budget.summary()
    assert SENTINEL not in repr(summary) and SENTINEL not in json.dumps(summary.to_dict())
    assert "prompt" not in json.dumps(summary.to_dict()).replace("provider_reported_prompt_tokens", "")


def test_the_summary_has_exactly_the_documented_fields():
    summary = BudgetedClient(FakeClient([ok()]), make_policy(), clock=FakeClock()).summary()
    assert set(summary.to_dict()) == SUMMARY_FIELDS


def test_the_summary_values_are_plain_bounded_types():
    budget = BudgetedClient(FakeClient([ok(), err("http_503: x")]), make_policy(), clock=FakeClock())
    budget.complete(make_request())
    budget.complete(make_request())
    for key, value in budget.summary().to_dict().items():
        assert isinstance(value, (str, int, float, bool, dict, type(None))), key
        if isinstance(value, str):
            assert len(value) < 200, key


def test_the_wrapper_never_reads_the_wrapped_clients_credentials():
    client = FakeClient([ok()])
    client._api_key = SENTINEL
    budget = BudgetedClient(client, make_policy(), clock=FakeClock())
    budget.complete(make_request())
    assert SENTINEL not in repr(budget) and SENTINEL not in repr(budget.summary())
    assert not hasattr(budget, "_api_key")


def test_the_executor_and_cli_do_not_know_about_the_new_modules():
    import maps.runs.executor as executor

    assert "live_" not in Path(executor.__file__).read_text(encoding="utf-8")
    assert "live_policy" not in Path(REPO_ROOT / "src/maps/experiments/receiver.py").read_text(encoding="utf-8")
