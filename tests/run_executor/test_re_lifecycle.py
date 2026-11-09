"""Shared lifecycle extraction (v2.3.48) and hash binding (v2.3.53): the mock executor must behave exactly as before.

Two snapshots (see ``re_scenarios.py``): ``data/lifecycle_snapshot_pre_hash.json`` was generated from the PRE-extraction
executor (reports at schema version 1); ``data/lifecycle_snapshot.json`` was regenerated in v2.3.53 with the hash block
and normalized hash values. The current code must match the second, and must differ from the first ONLY by the report
``version`` and the ``artifacts`` block. Offline only: fake runners, temporary directories, network and client tripwires.
"""

from __future__ import annotations

import ast
import inspect
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

import maps.runs.executor as executor_module
import maps.runs.lifecycle as lifecycle_module
from maps.runs.executor import execute_mock_run
from maps.runs.lifecycle import run_lifecycle

from re_scenarios import SCENARIOS, run_scenario
from re_support import MOCK, Runner, cfg_double, make_repo, provenance_options

SNAPSHOT_PATH = Path(__file__).parent / "data" / "lifecycle_snapshot.json"
SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
PRE_HASH = json.loads((Path(__file__).parent / "data" / "lifecycle_snapshot_pre_hash.json").read_text(encoding="utf-8"))
CLOCK = lambda: "2026-01-01T00:00:00Z"  # noqa: E731


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    import maps.llm_client as llm_client

    def refuse(*args, **kwargs):
        raise AssertionError("network access or provider-client construction attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(llm_client.OpenRouterClient, "__init__", refuse)


# ---- behavioral equivalence with the pre-extraction executor ---------------------------------------
def test_the_snapshots_cover_exactly_the_scenario_table():
    assert sorted(SNAPSHOT) == sorted(SCENARIOS) == sorted(PRE_HASH) and len(SNAPSHOT) == 32


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_current_executor_matches_the_regenerated_snapshot(name, tmp_path):
    assert run_scenario(name, tmp_path.resolve()) == SNAPSHOT[name]


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_current_results_differ_from_the_pre_hash_snapshot_only_by_the_report_version_and_the_hash_block(name, tmp_path):
    current = run_scenario(name, tmp_path.resolve())
    report = current["report"]
    if report is not None:
        assert report["version"] == 2 and set(report["artifacts"]) >= {"hash_algorithm", "files", "artifact_digest", "digest_format", "not_hashed"}
        report.pop("artifacts")
        report["version"] = 1
    assert current == PRE_HASH[name]             # every status, stage, event, file name, count and eligibility value is unchanged


def test_the_hash_block_lists_exactly_the_files_that_existed_and_never_the_excluded_ones():
    excluded = {"run_events.jsonl", "run_integrity.json", "summary.json", "contrast_gaps.json", "pipeline_report.json"}
    for name, scenario in SNAPSHOT.items():
        report = scenario["report"]
        if report is None:
            continue
        listed = [f["name"] for f in report["artifacts"]["files"]]
        assert not set(listed) & excluded and set(listed) <= {"episodes.jsonl", ".maps_run_claim", "calls.jsonl", "manifest.json", "run_provenance.json"}, name
        assert ".maps_run_claim" in listed and ("run_provenance.json" in listed) == (report["pre_run_provenance"]["status"] == "recorded"), name
        assert ("episodes.jsonl" in listed) == ("episodes.jsonl" in scenario["files"]), name
        assert report["artifacts"].get("errors") is None, name


def test_the_snapshot_spans_every_outcome_category():
    outcomes = {(v["status"], v["failed_stage"]) for v in SNAPSHOT.values()}
    expected = {
        ("complete", None), ("refused", "inputs"), ("refused", "run_directory"), ("failed", "event_log"),
        ("failed", "pre_run_provenance"), ("failed", "runner"), ("failed", "post_run_provenance"),
        ("failed", "provenance_drift"), ("failed", "loader"), ("failed", "structural_validation"),
        ("failed", "inventory"), ("failed", "report"),
    }
    assert expected <= outcomes
    assert all(v["analysis_eligible"] is (v["status"] == "complete") for v in SNAPSHOT.values())
    full = ("run_claimed", "provenance_recorded", "runner_started", "runner_finished", "post_run_validation_finished")
    complete = {k: tuple(e["event"] for e in v["events"]) for k, v in SNAPSHOT.items() if v["status"] == "complete"}
    assert complete.pop("event_log_flaky_after_run") == tuple(e for e in full if e != "runner_finished")   # that event failed to write
    assert set(complete.values()) == {full}


# ---- delegation and ordering -----------------------------------------------------------------------
def test_the_mock_executor_delegates_to_the_shared_lifecycle_exactly_once(tmp_path, monkeypatch):
    calls = []
    real = lifecycle_module.run_lifecycle

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(executor_module, "run_lifecycle", spy)
    repo, runner, options = make_repo(tmp_path), Runner(3), provenance_options()
    outcome = execute_mock_run(run_fn=runner, cfg=cfg_double(), scenarios=[], client=MOCK, run_dir=tmp_path / "run", run_id="d-1",
                               repo_root=repo, provenance_options=options, clock=CLOCK)
    (call,) = calls
    assert outcome.status == "complete" and runner.calls == 1
    assert call["execution_mode"] == "mock" and call["run_id"] == "d-1" and call["inventory"] is None
    assert call["clock"] is CLOCK and call["options"] == options
    assert call["collect_provenance_fn"] is executor_module.collect_provenance and call["event_log_factory"] is executor_module.EventLog


def test_the_injected_runner_is_called_by_the_lifecycle_with_the_original_arguments(tmp_path):
    seen = []

    def run_fn(cfg, scenarios, client, out_dir, secrets, repo_root):
        seen.append((cfg, scenarios, client, Path(out_dir), secrets, repo_root))
        return Runner(2)(cfg, scenarios, client, out_dir, secrets, repo_root)

    cfg, scenarios, repo = cfg_double(), ["sentinel-scenario"], make_repo(tmp_path)
    out = tmp_path / "run"
    execute_mock_run(run_fn=run_fn, cfg=cfg, scenarios=scenarios, client=MOCK, run_dir=out, run_id="d-2", repo_root=repo,
                     provenance_options=provenance_options(), clock=CLOCK)
    ((got_cfg, got_scenarios, got_client, got_out, got_secrets, got_root),) = seen
    assert got_cfg is cfg and got_scenarios == scenarios and got_scenarios is not scenarios      # a copy, as before
    assert got_client is MOCK and got_out == out and got_secrets is None and got_root == Path(repo)


def test_refused_inputs_never_reach_the_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_module, "run_lifecycle", lambda **kw: pytest.fail("the lifecycle must not run for refused inputs"))
    repo = make_repo(tmp_path)
    for kwargs in (dict(run_id="../x"), dict(client=SimpleNamespace(name="openrouter")), dict(cfg=cfg_double(enabled=True)),
                   dict(expected_episode_ids=[""]), dict(provenance_options={"bogus": 1})):
        base = dict(run_fn=Runner(), cfg=cfg_double(), scenarios=[], client=MOCK, run_dir=tmp_path / "run", run_id="ok-1", repo_root=repo)
        outcome = execute_mock_run(**{**base, **kwargs})
        assert (outcome.status, outcome.failed_stage) == ("refused", "inputs") and not (tmp_path / "run").exists()


def test_lifecycle_operations_happen_in_the_original_order(tmp_path, monkeypatch):
    order = []
    real_collect, real_write = executor_module.collect_provenance, executor_module.write_provenance

    monkeypatch.setattr(executor_module, "collect_provenance", lambda **kw: (order.append("collect"), real_collect(**kw))[1])
    monkeypatch.setattr(executor_module, "write_provenance", lambda d, r: (order.append("write_provenance"), real_write(d, r))[1])
    # since v2.3.53 the lifecycle reads episodes.jsonl once and parses those bytes (parse_episode_results), at the same
    # position in the sequence where it used to call the path loader
    real_init, real_load, real_report = lifecycle_module.initialize_run_dir, lifecycle_module.parse_episode_results, lifecycle_module.write_integrity_report
    monkeypatch.setattr(lifecycle_module, "initialize_run_dir", lambda *a, **k: (order.append("claim"), real_init(*a, **k))[1])
    monkeypatch.setattr(lifecycle_module, "parse_episode_results", lambda *a, **k: (order.append("load"), real_load(*a, **k))[1])
    monkeypatch.setattr(lifecycle_module, "write_integrity_report", lambda *a, **k: (order.append("report"), real_report(*a, **k))[1])

    def run_fn(*args):
        order.append("runner")
        return Runner(3)(*args)

    execute_mock_run(run_fn=run_fn, cfg=cfg_double(), scenarios=[], client=MOCK, run_dir=tmp_path / "run", run_id="o-1",
                     repo_root=make_repo(tmp_path), provenance_options=provenance_options(), clock=CLOCK)
    assert order == ["claim", "collect", "write_provenance", "runner", "collect", "load", "report"]


def test_the_runner_is_not_started_when_pre_run_provenance_fails_and_is_never_called_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_module, "collect_provenance", lambda **kw: (_ for _ in ()).throw(OSError("x")))
    runner = Runner(3)
    outcome = execute_mock_run(run_fn=runner, cfg=cfg_double(), scenarios=[], client=MOCK, run_dir=tmp_path / "run", run_id="p-1",
                               repo_root=make_repo(tmp_path), provenance_options=provenance_options(), clock=CLOCK)
    assert outcome.failed_stage == "pre_run_provenance" and runner.calls == 0


# ---- the shared module is mode-agnostic and self-contained -----------------------------------------------
def test_the_lifecycle_can_be_called_directly_and_records_its_mode_label_without_judging_it(tmp_path):
    out = tmp_path / "run"
    outcome = run_lifecycle(run_dir=out, run_id="direct-1", execution_mode="label-only", repo_root=make_repo(tmp_path),
                            invoke_runner=lambda: Runner(2)(None, [], None, out, None, tmp_path), inventory=None,
                            options=provenance_options(), clock=CLOCK)
    assert outcome.status == "complete" and outcome.report.execution_mode == "label-only"


def test_default_collaborators_are_resolved_from_the_lifecycle_module_at_call_time(tmp_path, monkeypatch):
    seen = []
    real = lifecycle_module.collect_provenance
    monkeypatch.setattr(lifecycle_module, "collect_provenance", lambda **kw: (seen.append(1), real(**kw))[1])
    out = tmp_path / "run"
    run_lifecycle(run_dir=out, run_id="direct-2", execution_mode="m", repo_root=make_repo(tmp_path),
                  invoke_runner=lambda: Runner(1)(None, [], None, out, None, tmp_path), inventory=None, options=provenance_options(), clock=CLOCK)
    assert len(seen) == 2                                                         # pre-run and post-run


def test_the_lifecycle_signature_has_no_client_configuration_scenario_secret_or_policy_parameters():
    parameters = inspect.signature(run_lifecycle).parameters
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    assert not {"client", "cfg", "scenarios", "secrets", "api_key"} & set(parameters)
    assert not [n for n in parameters if any(w in n for w in ("live", "allow", "policy", "budget", "key"))]


def _imports(module) -> set[str]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


def test_the_lifecycle_module_has_no_executor_cli_client_policy_network_or_process_imports():
    imported = _imports(lifecycle_module)
    assert {n for n in imported if n.startswith("maps")} == {
        "maps.adapters.run_loader", "maps.runs.artifact_hashes", "maps.runs.guard", "maps.runs.integrity_report", "maps.runs.provenance"}
    assert not {n.split(".")[0] for n in imported} & {"socket", "urllib", "http", "requests", "subprocess", "os", "shutil", "dotenv", "importlib", "runpy", "pkgutil", "imp", "ssl"}
    source = Path(lifecycle_module.__file__).read_text(encoding="utf-8")
    assert "OpenRouter" not in source and "os.environ" not in source and "getenv" not in source and "A-Za-z0-9._-" not in source
    tree = ast.parse(source)
    assert not {c.func.id for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)} & {"exec", "eval", "__import__"}


def test_the_executor_no_longer_contains_the_lifecycle_logic():
    tree = ast.parse(Path(executor_module.__file__).read_text(encoding="utf-8"))
    called = {c.func.id for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert not called & {"load_episode_results", "initialize_run_dir", "write_integrity_report", "EventLog", "collect_provenance", "write_provenance", "IntegrityReport"}
    assert "run_lifecycle" in called
    assert not {n for n in _imports(executor_module) if n.startswith("maps.adapters") or n == "maps.runs.guard"}


def test_the_public_names_of_the_executor_are_unchanged_and_shared_with_the_lifecycle():
    for name in ("ExecutionOutcome", "RunNotEligibleError", "provenance_drift", "ALLOWED_PROVENANCE_OPTIONS"):
        assert getattr(executor_module, name) is getattr(lifecycle_module, name), name
    assert executor_module.MODE == "mock" and set(executor_module.__all__) == {
        "ALLOWED_PROVENANCE_OPTIONS", "MODE", "ExecutionOutcome", "RunNotEligibleError", "execute_mock_run", "provenance_drift"}


def test_the_mock_executor_still_refuses_live_clients_and_live_configurations(tmp_path):
    repo = make_repo(tmp_path)
    runner = Runner()
    live_client = execute_mock_run(run_fn=runner, cfg=cfg_double(), scenarios=[], client=SimpleNamespace(name="openrouter"),
                                   run_dir=tmp_path / "a", run_id="r-1", repo_root=repo)
    live_config = execute_mock_run(run_fn=runner, cfg=cfg_double(enabled=True), scenarios=[], client=MOCK, run_dir=tmp_path / "b",
                                   run_id="r-2", repo_root=repo)
    assert (live_client.status, live_client.failed_stage, live_client.claimed) == ("refused", "inputs", False)
    assert (live_config.status, live_config.failed_stage, live_config.claimed) == ("refused", "inputs", False)
    assert runner.calls == 0 and not (tmp_path / "a").exists() and not (tmp_path / "b").exists()
