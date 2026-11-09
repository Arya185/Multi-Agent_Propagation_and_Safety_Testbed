"""Builders and tripwires for the policy-source tests (v2.3.66, Stage 4D).

OFFLINE ONLY. Inputs are the SYNTHETIC configuration and scenarios under tests/synthetic/data (96 episodes). Every policy
here is generated in a temporary directory with obviously synthetic values; no live policy file exists anywhere. Nothing reads
a credential or ``.env`` file, builds a client, or reaches a network.
"""

from __future__ import annotations

import builtins
import copy
import json
import socket
import sys
import types
from pathlib import Path

import pytest

import maps.config as maps_config
import maps.llm_client as maps_llm_client
import maps.runs.guard as maps_guard
from maps.config import load_config
from maps.experiments.receiver import build_grid
from maps.runs.policy_source import compute_content_digests, design_digest
from maps.scenarios import load_scenario_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
SYN = REPO_ROOT / "tests" / "synthetic" / "data"
SYN_CONFIG = SYN / "config_synthetic.json"
PROFILE = "synthetic-test-profile"
SENTINEL = "SENTINEL-VALUE-4242"


def load_inputs(config_path: Path = SYN_CONFIG):
    cfg = load_config(config_path)
    scenarios = load_scenario_dir(REPO_ROOT / cfg.design.scenario_dir)
    specs = build_grid(cfg, scenarios)
    digests = compute_content_digests(REPO_ROOT / cfg.design.scenario_dir, REPO_ROOT)
    return cfg, scenarios, specs, digests


def make_doc(cfg, specs, digests, **scope_overrides) -> dict:
    """A valid policy document (plain dict) for the synthetic inputs. The numbers are test values, not proposals."""
    scenario_ids = sorted(digests)
    scope = {
        "experiment_id": cfg.experiment_id, "config_version": cfg.config_version, "prompt_version": cfg.prompt_version,
        "stage": cfg.output.stage, "seed": cfg.seed,
        "models": sorted(({"alias": m.alias, "family": m.family, "model_id": m.model_id} for m in cfg.models), key=lambda m: m["alias"]),
        "conditions": sorted(({"id": c.id, "n_messages": c.n_messages, "n_roots": c.n_roots} for c in cfg.design.conditions), key=lambda c: c["id"]),
        "prompt_variants": sorted(cfg.design.prompt_variants), "scenario_ids": scenario_ids,
        "repetitions": cfg.design.repetitions, "rotate_templates_and_roots": cfg.design.rotate_templates_and_roots,
        "planned_episodes": len(specs), "max_tokens_per_request": cfg.sampling.max_tokens,
        "design_digest": design_digest(cfg), "content": {sid: dict(digests[sid]) for sid in scenario_ids},
    }
    scope.update(scope_overrides)
    return {
        "schema": "maps-live-policy", "schema_version": 1, "policy_id": "synthetic-test-policy", "scope": scope,
        "profiles": {PROFILE: make_limits(len(specs), cfg.api.max_retries)},
        "approval": {"approval_reference": "synthetic-test-only"},
    }


def make_limits(planned: int, retries: int, **overrides) -> dict:
    limits = {
        "max_episodes": planned, "max_request_attempts": planned * (1 + retries), "max_retries": retries, "deadline_seconds": 3600,
        "max_consecutive_nonfatal_errors": 5, "accounting_basis": "client_attempts", "nonfatal_4xx_statuses": [408, 429],
        "fatal_3xx": True,
    }
    limits.update(overrides)
    return limits


def write_policy(directory: Path, doc, name: str = "policy.json") -> Path:
    path = directory / name
    path.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    return path


def mutated(doc: dict, mutate) -> dict:
    out = copy.deepcopy(doc)
    mutate(out)
    return out


def listing(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    """Any network use, client construction, key lookup, .env open or run-directory call during these tests fails loudly."""
    events: list[str] = []

    def refuse(label):
        def _raise(*args, **kwargs):
            events.append(label)
            raise AssertionError(f"{label} was reached")
        return _raise

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = refuse("load_dotenv")
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setattr(socket, "socket", refuse("socket.socket"))
    monkeypatch.setattr(socket, "create_connection", refuse("socket.create_connection"))
    monkeypatch.setattr(maps_llm_client.OpenRouterClient, "__init__", refuse("OpenRouterClient()"))
    monkeypatch.setattr(maps_config, "get_api_key", refuse("get_api_key"))
    monkeypatch.setattr(maps_guard, "initialize_run_dir", refuse("initialize_run_dir"))
    monkeypatch.setattr(maps_guard, "check_run_dir", refuse("check_run_dir"))
    real_open = builtins.open

    def watching_open(file, *args, **kwargs):
        if Path(str(file)).name.startswith(".env"):
            events.append("open(.env)")
            raise AssertionError("an .env file was opened")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watching_open)
    yield events
    assert events == []
