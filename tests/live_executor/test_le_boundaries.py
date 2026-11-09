"""Boundaries of the live executor: no client construction here, no bypass, no CLI integration, mock untouched (offline)."""

from __future__ import annotations

import ast
import inspect
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

import maps.runs.executor as executor_module
import maps.runs.live_executor as live_executor_module
from maps.runs.executor import execute_mock_run
from maps.runs.live_budget import BudgetedClient
from maps.runs.live_executor import execute_live_run

from le_support import (
    CLOCK, PLANNED, REPO_ROOT, Factory, RunnerSpy, ScriptedClient, event_names, grid_ids, live_cfg, load_inputs, make_policy,
    provenance_options, run_live,
)


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    import maps.llm_client as llm_client

    def refuse(*args, **kwargs):
        raise AssertionError("network access or provider-client construction attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(llm_client.OpenRouterClient, "__init__", refuse)


def imports_of(module) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(Path(module.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


# ---- static structure of the live executor -------------------------------------------------------------------------
def test_the_live_executor_depends_only_on_the_lifecycle_policy_budget_ids_and_provenance_modules():
    imported = imports_of(live_executor_module)
    assert {n for n in imported if n.startswith("maps")} == {
        "maps.runs.ids", "maps.runs.integrity_report", "maps.runs.lifecycle", "maps.runs.live_budget", "maps.runs.live_policy", "maps.runs.provenance"}
    assert not {n.split(".")[0] for n in imported} & {"socket", "urllib", "http", "requests", "subprocess", "os", "shutil", "dotenv", "importlib", "runpy", "pkgutil", "imp", "ssl"}


def test_the_live_executor_never_constructs_a_provider_client_or_reads_credentials():
    source = Path(live_executor_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {c.func.id for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert not called & {"OpenRouterClient", "MockClient", "exec", "eval", "__import__", "open", "getenv"}
    assert not {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} & {"environ", "getenv", "post", "get", "send", "request"}
    assert "OpenRouter" not in source and ".env" not in source and "api_key" not in source.lower() and "getenv" not in source


def test_there_is_exactly_one_runner_call_and_it_passes_the_wrapper_not_the_inner_client():
    tree = ast.parse(Path(live_executor_module.__file__).read_text(encoding="utf-8"))
    run_calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "run_fn"]
    assert len(run_calls) == 1 and ast.unparse(run_calls[0].args[2]) == "state.wrapper"
    factory_calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "client_factory"]
    wrappers = [c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "BudgetedClient"]
    assert len(factory_calls) == 1 and len(wrappers) == 1 and not factory_calls[0].args and not factory_calls[0].keywords
    assert not [c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "complete"]   # it never calls the client itself


def test_the_runner_receives_the_wrapper_and_the_inner_client_is_reachable_only_through_it(tmp_path):
    inner = ScriptedClient()
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    (given,) = runner.clients
    assert isinstance(given, BudgetedClient) and given is not inner and inner.calls == PLANNED


def test_the_signature_is_keyword_only_with_no_credential_environment_or_bypass_parameters():
    parameters = inspect.signature(execute_live_run).parameters
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    assert not [n for n in parameters if any(w in n for w in ("env", "token", "api_key", "password", "allow", "bypass", "force", "resume", "retry"))]
    assert {"client_factory", "policy", "expected_episode_ids", "run_fn"} <= set(parameters)
    required = {n for n, p in parameters.items() if p.default is inspect.Parameter.empty}
    assert {"policy", "client_factory", "expected_episode_ids"} <= required                 # nothing about the policy or the grid is optional


# ---- the factory is called only after every precondition ---------------------------------------------------------------
def base_kwargs(tmp_path):
    cfg, scenarios = load_inputs()
    cfg = live_cfg(cfg)
    factory, runner = Factory(), RunnerSpy()
    return dict(run_fn=runner, cfg=cfg, scenarios=scenarios, client_factory=factory, policy=make_policy(), run_dir=tmp_path / "run",
                run_id="live-001", repo_root=REPO_ROOT, expected_episode_ids=grid_ids(cfg, scenarios), provenance_options=provenance_options(),
                clock=CLOCK), factory, runner


@pytest.mark.parametrize(
    "mutate",
    [
        lambda k: k.update(run_id="../escape"),
        lambda k: k.update(run_id=".."),
        lambda k: k.update(run_fn="not callable"),
        lambda k: k.update(client_factory=None),
        lambda k: k.update(policy={"max_retries": 0}),
        lambda k: k.update(policy=None),
        lambda k: k.update(cfg=live_cfg(k["cfg"], enabled=False)),
        lambda k: k.update(cfg=live_cfg(k["cfg"], max_retries=2)),
        lambda k: k.update(expected_episode_ids=None),
        lambda k: k.update(expected_episode_ids=5),
        lambda k: k.update(expected_episode_ids=k["expected_episode_ids"][:-1]),
        lambda k: k.update(expected_episode_ids=k["expected_episode_ids"][:-1] + [k["expected_episode_ids"][0]]),
        lambda k: k.update(expected_episode_ids=["", *k["expected_episode_ids"][1:]]),
        lambda k: k.update(redaction_values=["ok", ""]),
        lambda k: k.update(provenance_options={"environment": "x"}),
    ],
    ids=["bad-id", "dot-id", "runner-not-callable", "no-factory", "policy-dict", "no-policy", "api-disabled", "retries-mismatch",
         "no-inventory", "inventory-not-iterable", "inventory-too-short", "inventory-duplicate", "inventory-empty-id", "bad-redaction", "bad-option"],
)
def test_invalid_inputs_are_refused_before_the_factory_and_before_anything_is_written(tmp_path, mutate):
    kwargs, factory, runner = base_kwargs(tmp_path)
    mutate(kwargs)
    outcome = execute_live_run(**kwargs)
    assert (outcome.status, outcome.failed_stage, outcome.claimed) == ("refused", "inputs", False)
    assert factory.calls == 0 and runner.calls == 0 and not (tmp_path / "run").exists()


def test_a_failed_claim_does_not_call_the_factory(tmp_path):
    kwargs, factory, runner = base_kwargs(tmp_path)
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "old.txt").write_text("keep", encoding="utf-8")
    outcome = execute_live_run(**kwargs)
    assert (outcome.status, outcome.failed_stage) == ("refused", "run_directory") and factory.calls == 0 and runner.calls == 0
    assert [p.name for p in (tmp_path / "run").iterdir()] == ["old.txt"]


def test_failed_pre_run_provenance_does_not_call_the_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(live_executor_module, "collect_provenance", lambda **kw: (_ for _ in ()).throw(OSError("disk")))
    kwargs, factory, runner = base_kwargs(tmp_path)
    outcome = execute_live_run(**kwargs)
    assert (outcome.status, outcome.failed_stage) == ("failed", "pre_run_provenance") and factory.calls == 0 and runner.calls == 0
    assert event_names(tmp_path / "run") == ["run_claimed", "provenance_failed", "integrity_report_written"]


def test_an_unwritable_event_log_does_not_call_the_factory(tmp_path, monkeypatch):
    class Broken:
        def __init__(self, *a, **k):
            self.complete, self.path = False, tmp_path / "run" / "run_events.jsonl"

        def emit(self, *a, **k):
            return False

    monkeypatch.setattr(live_executor_module, "EventLog", Broken)
    kwargs, factory, runner = base_kwargs(tmp_path)
    outcome = execute_live_run(**kwargs)
    assert outcome.failed_stage == "event_log" and factory.calls == 0 and runner.calls == 0


def test_the_factory_is_called_with_no_arguments_and_exactly_once_after_provenance(tmp_path, monkeypatch):
    order = []

    def factory():                                   # a factory taking parameters would fail here
        order.append("factory")
        return ScriptedClient()

    real = live_executor_module.write_provenance
    monkeypatch.setattr(live_executor_module, "write_provenance", lambda d, r: (order.append("provenance_written"), real(d, r))[1])
    kwargs, _, runner = base_kwargs(tmp_path)
    kwargs["client_factory"] = factory
    outcome = execute_live_run(**kwargs)
    assert outcome.status == "complete" and order == ["provenance_written", "factory"]


def test_a_factory_failure_is_a_client_construction_failure_and_the_runner_never_starts(tmp_path):
    outcome, factory, runner = run_live(tmp_path, factory=Factory(raises=RuntimeError("cannot build")))
    assert (outcome.status, outcome.failed_stage) == ("failed", "client_construction") and outcome.detail == "RuntimeError (message withheld)"
    assert factory.calls == 1 and runner.calls == 0 and not outcome.analysis_eligible
    assert event_names(tmp_path / "run") == ["run_claimed", "provenance_recorded", "client_construction_failed", "integrity_report_written"]


def test_strict_physical_refuses_a_client_that_does_not_declare_redirects_disabled_before_the_runner(tmp_path):
    from maps.runs.live_policy import AccountingBasis

    outcome, factory, runner = run_live(tmp_path, factory=Factory(ScriptedClient()), policy=make_policy(accounting_basis=AccountingBasis.STRICT_PHYSICAL))
    assert (outcome.failed_stage, factory.calls, runner.calls) == ("client_construction", 1, 0)
    ok_dir = tmp_path / "ok"
    ok_dir.mkdir()
    ok, _, ok_runner = run_live(ok_dir, factory=Factory(ScriptedClient(redirects_disabled=True)), policy=make_policy(accounting_basis=AccountingBasis.STRICT_PHYSICAL))
    assert ok.status == "complete" and ok_runner.calls == 1


# ---- the mock executor and the CLI are untouched ------------------------------------------------------------------------
def test_the_mock_executor_is_unchanged_in_signature_imports_and_refusals(tmp_path):
    assert list(inspect.signature(execute_mock_run).parameters) == [
        "run_fn", "cfg", "scenarios", "client", "run_dir", "run_id", "repo_root", "expected_episode_ids", "provenance_options", "clock"]
    assert {n for n in imports_of(executor_module) if n.startswith("maps")} == {"maps.runs.ids", "maps.runs.integrity_report", "maps.runs.lifecycle", "maps.runs.provenance"}
    assert "live_" not in Path(executor_module.__file__).read_text(encoding="utf-8")
    refused = execute_mock_run(run_fn=lambda *a: [], cfg=SimpleNamespace(api=SimpleNamespace(enabled=False)), scenarios=[], client=SimpleNamespace(name="fake-live"),
                               run_dir=tmp_path / "m", run_id="m-1", repo_root=REPO_ROOT)
    assert (refused.status, refused.failed_stage) == ("refused", "inputs") and not (tmp_path / "m").exists()


def test_only_the_cli_imports_the_live_executor_and_only_for_the_downstream_flow():
    """v2.3.74 (Stage 4E, authorized): the CLI module imports the executor for ``run_live_after_preflight``, which ``main`` never calls
    (the final refusal stands). Nothing else in the source tree knows the executor."""
    importers = []
    for path in (REPO_ROOT / "src" / "maps").rglob("*.py"):
        if path.name != "live_executor.py" and "live_executor" in path.read_text(encoding="utf-8"):
            importers.append(path.relative_to(REPO_ROOT / "src" / "maps").as_posix())
    assert importers == ["experiments/receiver.py"]


def test_the_scripts_directory_is_not_part_of_the_executor_path():
    source = Path(live_executor_module.__file__).read_text(encoding="utf-8")
    assert "scripts" not in source and "test_openrouter" not in source
