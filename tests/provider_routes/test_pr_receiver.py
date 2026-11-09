"""receiver --live is refused before anything else (v2.3.56, Stage 4C, PR3). Offline, with tripwires.

This complements tests/cli_safety: it patches the real sources (key lookup, client class, dotenv, run guard, runner,
executors), blocks sockets, watches every file open for ``.env*`` names, and checks that nothing is created.
"""

from __future__ import annotations

import ast
import builtins
import json
import socket
import sys
import types
from pathlib import Path

import pytest

import maps.config as maps_config
import maps.experiments.receiver as receiver
import maps.llm_client as maps_llm_client
import maps.runs.executor as maps_executor
import maps.runs.guard as maps_guard

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_CONFIG = REPO_ROOT / "tests" / "synthetic" / "data" / "config_synthetic.json"
KEY_ENV = "MAPS_RECEIVER_REFUSAL_KEY_ENV"
sys.path.insert(0, str(REPO_ROOT / "tests" / "policy_source"))     # the policy builders live with the policy-source tests


def approved_base_url() -> str:
    from maps.runs.endpoint_policy import APPROVED_HOSTS, APPROVED_PATH

    return f"https://{APPROVED_HOSTS[0]}{APPROVED_PATH}"


def policy_arguments(tmp_path, config) -> list[str]:
    import ps_support
    from maps.runs.policy_source import policy_digest

    cfg, _scenarios, specs, digests = ps_support.load_inputs(config)
    doc = ps_support.make_doc(cfg, specs, digests)
    path = ps_support.write_policy(tmp_path, doc)
    return ["--policy", str(path), "--profile", ps_support.PROFILE, "--expected-policy-digest", policy_digest(doc)]


def make_config(tmp_path, *, enabled=True) -> Path:
    config = json.loads(SYNTHETIC_CONFIG.read_text(encoding="utf-8"))
    config["api"].update({"enabled": enabled, "api_key_env": KEY_ENV, "base_url": approved_base_url()})
    config["output"]["results_dir"] = str(tmp_path / "results")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.fixture
def trip(monkeypatch, capsys):
    events: list[str] = []

    def tripwire(label):
        def _raise(*args, **kwargs):
            events.append(label)
            raise AssertionError(f"{label} was reached")
        return _raise

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *a, **k: events.append("load_dotenv")
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setattr(maps_config, "get_api_key", tripwire("get_api_key"))
    monkeypatch.setattr(maps_llm_client.OpenRouterClient, "__init__", tripwire("OpenRouterClient()"))
    monkeypatch.setattr(maps_guard, "initialize_run_dir", tripwire("initialize_run_dir"))
    monkeypatch.setattr(maps_guard, "check_run_dir", tripwire("check_run_dir"))
    monkeypatch.setattr(maps_executor, "execute_mock_run", tripwire("execute_mock_run"))
    monkeypatch.setattr(receiver, "execute_live_run", tripwire("execute_live_run"))
    monkeypatch.setattr(receiver, "run_live_after_preflight", tripwire("run_live_after_preflight"))
    monkeypatch.setattr(receiver, "run_experiment", tripwire("run_experiment"))
    monkeypatch.setattr(receiver, "execute_mock_run", tripwire("execute_mock_run (receiver)"))
    monkeypatch.setattr(socket, "socket", tripwire("socket.socket"))
    monkeypatch.setattr(socket, "create_connection", tripwire("socket.create_connection"))
    real_open = builtins.open

    def watching_open(file, *args, **kwargs):
        if Path(str(file)).name.startswith(".env"):
            events.append(f"open({Path(str(file)).name})")
            raise AssertionError("an .env file was opened")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watching_open)
    monkeypatch.setenv(KEY_ENV, "DUMMY-NOT-A-SECRET")
    return events


@pytest.mark.parametrize("flags,enabled", [
    ([], False), ([], True), (["--confirm-spend"], False), (["--confirm-spend"], True), (["--confirm-spend", "--run-id", "refusal-test"], True),
])
def test_live_with_a_passing_preflight_ends_in_the_final_refusal_and_touches_nothing(trip, capsys, tmp_path, flags, enabled):
    config = make_config(tmp_path, enabled=enabled)
    code = receiver.main(["--config", str(config), "--live", *flags, *policy_arguments(tmp_path, config)])
    captured = capsys.readouterr()
    assert code == 2 and "FINAL REFUSAL" in captured.err and "done:" not in captured.out
    assert trip == []                                                       # no dotenv, key, client, guard, runner, socket, .env open
    assert not (tmp_path / "results").exists()                              # no run directory, no claim
    assert "DUMMY-NOT-A-SECRET" not in captured.out + captured.err


def test_the_mock_path_is_unchanged_by_the_refusal(tmp_path, monkeypatch, capsys):
    """Without tripwires on the executor: the mock path still runs and writes its artifacts, and no live module is touched."""
    monkeypatch.setattr(maps_llm_client.OpenRouterClient, "__init__", lambda *a, **k: (_ for _ in ()).throw(AssertionError("client built")))
    monkeypatch.setattr(maps_config, "get_api_key", lambda *a, **k: (_ for _ in ()).throw(AssertionError("key read")))
    code = receiver.main(["--config", str(make_config(tmp_path, enabled=False)), "--mock", "--run-id", "mock-still-works"])
    out = capsys.readouterr().out
    assert code == 0 and "MOCK RUN" in out and "done: 96/96 valid" in out
    assert (tmp_path / "results" / "mock" / "mock-still-works" / "run_integrity.json").is_file()


def test_receiver_source_has_no_credential_or_client_machinery():
    source = (REPO_ROOT / "src" / "maps" / "experiments" / "receiver.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not imported & {"OpenRouterClient", "get_api_key", "check_run_dir", "initialize_run_dir", "UnsafeRunDirectoryError", "load_dotenv"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"OpenRouterClient", "get_api_key", "load_dotenv", "check_run_dir"}
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not [v for v in strings if ".env" in v and "\n" not in v]       # no code string names the .env file (docstrings excepted)


def test_the_executor_call_is_only_inside_the_downstream_function_which_main_never_calls():
    tree = ast.parse((REPO_ROOT / "src" / "maps" / "experiments" / "receiver.py").read_text(encoding="utf-8"))
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    def names_called(fn):
        return {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "execute_live_run" in names_called(functions["run_live_after_preflight"])
    assert "run_live_after_preflight" not in names_called(functions["main"]) and "execute_live_run" not in names_called(functions["main"])
    others = [name for name, fn in functions.items() if name not in ("run_live_after_preflight",) and "execute_live_run" in names_called(fn)]
    assert others == []
    assert "run_live_after_preflight" not in {n.id for n in ast.walk(functions["main"]) if isinstance(n, ast.Name)}   # not even referenced


def test_the_final_refusal_is_the_last_statement_of_main_after_the_preflight():
    main = next(n for n in ast.walk(ast.parse((REPO_ROOT / "src/maps/experiments/receiver.py").read_text(encoding="utf-8")))
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    assert ast.unparse(main.body[-1]) == "return REFUSED"
    assert "FINAL_REFUSAL_TEXT" in ast.unparse(main.body[-2]) and "file=sys.stderr" in ast.unparse(main.body[-2])
    preflight = ast.unparse(main.body[-3])
    assert preflight.index("compute_content_digests") < preflight.index("load_policy") < preflight.index("validate_base_url")
    assert "FINAL_REFUSAL_TEXT" not in preflight


def test_no_flag_or_environment_variable_can_disable_the_final_refusal():
    tree = ast.parse((REPO_ROOT / "src/maps/experiments/receiver.py").read_text(encoding="utf-8"))
    main = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")
    flags = {a.args[0].value for a in ast.walk(main) if isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute) and a.func.attr == "add_argument"}
    assert flags == {"--config", "--mock", "--live", "--confirm-spend", "--export-grid", "--export-balance", "--run-id",
                     "--policy", "--profile", "--expected-policy-digest", "--registry"}
    text = ast.unparse(main)
    assert "environ" not in text and "getenv" not in text and "os." not in text
