"""Harness for the CLI safety-gate tests (SYNTHETIC configuration, temporary directories, test doubles).

The CLI under test is ``maps.experiments.receiver.main``. Every external boundary it can reach is
replaced by a recording double, and the network is blocked, so an invocation that should have been
refused fails loudly if it gets anywhere near execution. Nothing here uses a real credential, a real
API client or a live service.
"""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import maps.config as maps_config
import maps.experiments.receiver as receiver
import maps.llm_client as maps_llm_client

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "policy_source"))      # the policy builders live with the policy-source tests
SYNTHETIC_CONFIG = REPO_ROOT / "tests" / "synthetic" / "data" / "config_synthetic.json"
FAKE_KEY_ENV = "MAPS_CLI_TEST_KEY_ENV_NAME"   # a variable name only; the tests never set a value except the empty string


def approved_base_url() -> str:
    from maps.runs.endpoint_policy import APPROVED_HOSTS, APPROVED_PATH

    return f"https://{APPROVED_HOSTS[0]}{APPROVED_PATH}"


def write_config(tmp_path: Path, *, enabled: bool = False, stage: str | None = None, mutate=None) -> Path:
    """A copy of the synthetic configuration with an absolute temporary results directory."""
    config = json.loads(SYNTHETIC_CONFIG.read_text(encoding="utf-8"))
    config["api"]["enabled"] = enabled
    config["api"]["api_key_env"] = FAKE_KEY_ENV
    config["api"]["base_url"] = approved_base_url()      # a string only; the live preflight validates it and nothing connects
    config["output"]["results_dir"] = str(tmp_path / "results")      # absolute, so REPO_ROOT / results_dir is the temp path
    if stage:
        config["output"]["stage"] = stage
    if mutate:
        mutate(config)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@dataclass
class Calls:
    run_experiment: list = field(default_factory=list)     # clients passed to the experiment runner
    live_client: list = field(default_factory=list)        # constructions of the live client class
    get_api_key: list = field(default_factory=list)
    load_dotenv: list = field(default_factory=list)
    load_config: list = field(default_factory=list)        # configuration files the CLI tried to load
    load_scenarios: list = field(default_factory=list)     # scenario directories the CLI tried to load


class Harness:
    def __init__(self, tmp_path: Path, calls: Calls, capsys):
        self.tmp_path, self.calls, self._capsys = tmp_path, calls, capsys
        self.results_dir = tmp_path / "results"

    def invoke(self, *args: str, config: Path | None = None) -> tuple[int, str, str]:
        code = receiver.main(["--config", str(config or write_config(self.tmp_path)), *args])
        captured = self._capsys.readouterr()
        return code, captured.out, captured.err

    def assert_nothing_executed(self, *, key_lookup: bool = False, dotenv: bool = False) -> None:
        assert self.calls.run_experiment == [], "an experiment run was reached"
        assert self.calls.live_client == [], "a live client was constructed"
        assert bool(self.calls.get_api_key) is key_lookup
        assert bool(self.calls.load_dotenv) is dotenv

    def assert_no_inputs_loaded(self) -> None:
        assert self.calls.load_config == [] and self.calls.load_scenarios == [], "inputs were loaded"

    def assert_no_output(self) -> None:
        assert not self.results_dir.exists(), "output that could be mistaken for a run was created"


@pytest.fixture
def harness(tmp_path, monkeypatch, capsys):
    calls = Calls()
    real_run = receiver.run_experiment
    real_key = maps_config.get_api_key

    def run_spy(cfg, scenarios, client, out_dir, secrets=None, *args, **kwargs):
        calls.run_experiment.append(client)
        if getattr(client, "name", None) != "mock":      # only the mock path may ever execute
            raise AssertionError("the runner was reached with a non-mock client")
        return real_run(cfg, scenarios, client, out_dir, secrets, *args, **kwargs)

    class LiveClientDouble:
        name = "openrouter"

        def __init__(self, *args, **kwargs):
            calls.live_client.append((args, kwargs))
            raise AssertionError("the live client must never be constructed in these tests")

    def key_spy(cfg, environ=None):
        calls.get_api_key.append(cfg.api.api_key_env)
        return real_key(cfg, environ)

    real_load_config, real_load_scenarios = receiver.load_config, receiver.load_scenario_dir

    def load_config_spy(path):
        calls.load_config.append(str(path))
        return real_load_config(path)

    def load_scenarios_spy(directory, *args, **kwargs):
        calls.load_scenarios.append(str(directory))
        return real_load_scenarios(directory, *args, **kwargs)

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *a, **k: calls.load_dotenv.append(a) or False     # never reads a real .env file
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setattr(receiver, "run_experiment", run_spy)
    # receiver no longer imports the live client or the key lookup (Stage 4C), so the doubles sit at their sources:
    # anything that reached them, by any route, is recorded (and the client double refuses to be constructed).
    monkeypatch.setattr(maps_llm_client, "OpenRouterClient", LiveClientDouble)
    monkeypatch.setattr(maps_config, "get_api_key", key_spy)
    monkeypatch.setattr(receiver, "load_config", load_config_spy)
    monkeypatch.setattr(receiver, "load_scenario_dir", load_scenarios_spy)
    monkeypatch.delenv(FAKE_KEY_ENV, raising=False)

    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during a CLI safety test")

    monkeypatch.setattr(socket, "socket", refuse)
    return Harness(tmp_path, calls, capsys)


# ---------------------------------------------------------------------------
# Live-path inputs (Stage 4E): a synthetic policy file, its digest and the three CLI arguments
# ---------------------------------------------------------------------------
def policy_args(tmp_path: Path, config: Path, *, profile=None, digest=None, mutate=None, name="policy.json") -> list[str]:
    """``--policy/--profile/--expected-policy-digest`` for the synthetic configuration. All values are synthetic test data."""
    import ps_support
    from maps.runs.policy_source import policy_digest

    cfg, _scenarios, specs, digests = ps_support.load_inputs(config)
    doc = ps_support.make_doc(cfg, specs, digests)
    if mutate:
        mutate(doc)
    path = ps_support.write_policy(tmp_path, doc, name)
    return [
        "--policy", str(path), "--profile", ps_support.PROFILE if profile is None else profile,
        "--expected-policy-digest", policy_digest(doc) if digest is None else digest,
    ]
