"""The downstream live flow after a passed preflight, driven ONLY through an injected fake client factory (v2.3.74, Stage 4E).

``run_live_after_preflight`` is not reachable from ``main`` (the final refusal stands); these tests call it directly.
Covers every approved exit code, the report's policy provenance, sticky-stop semantics and diagnostic-only partial runs.
Offline: socket tripwire, patched client constructor and key lookup, fake dotenv, scripted fake clients, synthetic data.
"""

from __future__ import annotations

import json
import socket
import sys
import types
from types import SimpleNamespace

import pytest

import maps.config as maps_config
import maps.experiments.receiver as receiver
import maps.llm_client as maps_llm_client
import maps.runs.lifecycle as lifecycle
from maps.experiments.receiver import live_exit_code, run_live_after_preflight
from maps.runs.endpoint_policy import APPROVED_HOSTS, APPROVED_PATH
from maps.runs.integrity_gate import IntegrityGateError, Verdict, check_run_integrity, load_eligible_run, load_for_diagnostics
from maps.schemas import LLMResult

from lc_support import SECRET, client_factory, prepare


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    events: list[str] = []

    def refuse(label):
        def _raise(*a, **k):
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
    yield events
    assert events == []


def run(tmp_path, *, limits=None, enabled=True, **client_kwargs):
    cfg, scenarios, specs, loaded, endpoint = prepare(tmp_path, enabled=enabled, limits=limits)
    factory = client_factory(**client_kwargs)
    run_dir = tmp_path / "runs" / "live-flow"
    code = run_live_after_preflight(
        cfg=cfg, scenarios=scenarios, specs=specs, loaded=loaded, endpoint=endpoint, client_factory=factory,
        run_dir=run_dir, run_id="live-flow", redaction_values=[SECRET],
    )
    return code, run_dir, factory, specs, loaded


def report_of(run_dir) -> dict:
    return json.loads((run_dir / "run_integrity.json").read_text(encoding="utf-8"))


def error(status: str = "http_503: busy") -> LLMResult:
    return LLMResult(error=status, attempts=1, latency_s=0.0)


# ---- exit code 0: complete and eligible ------------------------------------------------------------------------------
def test_a_complete_run_exits_zero_and_is_admitted_by_the_gate(tmp_path, capsys):
    code, run_dir, factory, specs, loaded = run(tmp_path)
    out = capsys.readouterr().out
    assert code == 0 and "run complete and eligible" in out and factory.calls == 1 and factory.client.calls == 96
    report = report_of(run_dir)
    assert report["execution_mode"] == "live" and report["analysis_eligible"] is True and report["failure_stage"] is None
    ids = [s.episode_id for s in specs]
    assert check_run_integrity(run_dir, expected_episode_ids=ids).verdict is Verdict.ELIGIBLE
    assert len(load_eligible_run(run_dir, expected_episode_ids=ids).records) == 96


# ---- provenance (PS-15 option A) ------------------------------------------------------------------------------------------
def test_the_report_records_the_policy_and_the_validated_endpoint(tmp_path):
    code, run_dir, _factory, _specs, loaded = run(tmp_path)
    record = report_of(run_dir)["live"]["policy_source"]
    assert record["schema"] == "maps-live-policy" and record["schema_version"] == 1 and record["profile"] == loaded.profile
    assert record["policy_id"] == loaded.policy_id and record["policy_digest"] == loaded.policy_digest
    assert record["effective_digest"] == loaded.effective_digest and record["design_digest"] == loaded.design_digest
    assert record["planned_episodes"] == 96 and record["max_tokens_per_request"] == loaded.max_tokens_per_request
    assert record["content_bound"] is True and record["expected_digest_checked"] is True
    assert record["endpoint"] == {"scheme": "https", "host": APPROVED_HOSTS[0], "path": APPROVED_PATH, "validated": True,
                                  "limitation": "hostname validation does not prevent DNS or proxy redirection"}
    assert "not authenticated" in record["trust"] and "not proof of owner approval" in record["trust"]
    assert record["owner_authentication"].startswith("none")


def test_the_record_holds_no_secret_no_local_path_and_no_policy_file_name(tmp_path):
    code, run_dir, _factory, _specs, _loaded = run(tmp_path, leak=SECRET)
    text = json.dumps(report_of(run_dir)["live"]["policy_source"])
    assert str(tmp_path) not in text and "policy.json" not in text and SECRET not in text
    assert not any(SECRET in p.read_text(encoding="utf-8", errors="replace") for p in run_dir.rglob("*") if p.is_file())


def test_the_policy_file_is_not_copied_into_the_run_artifacts(tmp_path):
    _code, run_dir, *_ = run(tmp_path)
    assert sorted(p.name for p in run_dir.iterdir()) == sorted(
        ["calls.jsonl", "contrast_gaps.json", "episodes.jsonl", "manifest.json", "run_events.jsonl", "run_integrity.json",
         "run_provenance.json", "summary.json", ".maps_run_claim"])
    report = report_of(run_dir)
    assert {f["name"] for f in report["artifacts"]["files"]} <= {"episodes.jsonl", ".maps_run_claim", "calls.jsonl", "manifest.json", "run_provenance.json"}


# ---- exit code 3: policy stop; sticky-stop semantics (PS-10) and diagnostic-only partial runs (PS-14) ------------------------
def stop_run(tmp_path):
    script = {1: error(), 2: error()}                      # two nonfatal errors in a row reach the threshold of 2
    return run(tmp_path, limits={"max_consecutive_nonfatal_errors": 2}, script=script)


def test_a_policy_stop_exits_three_keeps_the_triggering_call_and_refuses_the_next(tmp_path, capsys):
    code, run_dir, factory, specs, _loaded = stop_run(tmp_path)
    assert code == 3 and "exit 3" in capsys.readouterr().err
    assert factory.client.calls == 2                                           # the call after the stop never reached the client
    episodes = [json.loads(line) for line in (run_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(episodes) == 2 and all(e["status"] == "call_error" for e in episodes)   # the triggering call is retained
    report = report_of(run_dir)
    assert report["failure_stage"] == "policy_stop" and report["analysis_eligible"] is False
    assert report["live"]["policy_stop_recorded"] is True and report["live"]["wrapper_stop_reason"] == "consecutive_errors"
    assert not (run_dir / "summary.json").exists() and not (run_dir / "contrast_gaps.json").exists()


def test_a_stopped_run_is_diagnostic_only_and_never_admitted(tmp_path):
    _code, run_dir, _factory, specs, _loaded = stop_run(tmp_path)
    ids = [s.episode_id for s in specs]
    with pytest.raises(IntegrityGateError) as e:
        load_eligible_run(run_dir, expected_episode_ids=ids)
    assert e.value.result.verdict is not Verdict.ELIGIBLE and e.value.result.reason == "policy_stop_recorded"
    diagnostic = load_for_diagnostics(run_dir, expected_episode_ids=ids)
    assert diagnostic.analysis_admitted is False and diagnostic.gate.verdict is not Verdict.ELIGIBLE
    assert len(diagnostic.loaded.records) == 2                                  # the partial records are readable, but not admitted


def test_a_finished_run_directory_is_never_reused_or_resumed(tmp_path):
    _code, run_dir, _factory, _specs, _loaded = stop_run(tmp_path)
    again = tmp_path / "again"
    again.mkdir()
    cfg, scenarios, specs, loaded, endpoint = prepare(again, limits={"max_consecutive_nonfatal_errors": 2})
    factory = client_factory()
    before = sorted(p.name for p in run_dir.iterdir())
    code = run_live_after_preflight(cfg=cfg, scenarios=scenarios, specs=specs, loaded=loaded, endpoint=endpoint, client_factory=factory,
                                    run_dir=run_dir, run_id="live-flow")
    assert code == 2 and factory.calls == 0 and sorted(p.name for p in run_dir.iterdir()) == before     # refused; nothing appended


# ---- exit code 1: lifecycle failure ------------------------------------------------------------------------------------------
def test_an_ordinary_runner_failure_exits_one_and_keeps_the_report(tmp_path):
    code, run_dir, factory, *_ = run(tmp_path, script={1: RuntimeError("boom")})
    report = report_of(run_dir)
    assert code == 1 and report["failure_stage"] == "runner" and report["analysis_eligible"] is False and factory.client.calls == 1


# ---- exit code 2: refused ------------------------------------------------------------------------------------------------------
def test_an_executor_refusal_exits_two_and_creates_nothing(tmp_path, capsys):
    code, run_dir, factory, *_ = run(tmp_path, enabled=False)
    assert code == 2 and "refused:" in capsys.readouterr().err and factory.calls == 0 and not run_dir.exists()


def test_the_policy_record_is_validated_before_anything_is_written(tmp_path, monkeypatch):
    cfg, scenarios, specs, loaded, endpoint = prepare(tmp_path)
    factory = client_factory()
    monkeypatch.setattr(receiver, "build_policy_record", lambda *a: {"api_key": "x"})
    run_dir = tmp_path / "runs" / "bad-record"
    code = run_live_after_preflight(cfg=cfg, scenarios=scenarios, specs=specs, loaded=loaded, endpoint=endpoint, client_factory=factory,
                                    run_dir=run_dir, run_id="bad-record")
    assert code == 2 and factory.calls == 0 and not run_dir.exists()


# ---- exit code 4: report unwritable -------------------------------------------------------------------------------------------
def test_an_unwritable_report_exits_four(tmp_path, monkeypatch, capsys):
    def fail(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(lifecycle, "write_integrity_report", fail)
    code, run_dir, *_ = run(tmp_path)
    assert code == 4 and not (run_dir / "run_integrity.json").exists() and (run_dir / "episodes.jsonl").exists()
    assert "stage: report" in capsys.readouterr().err


# ---- exit code 130: interrupted -------------------------------------------------------------------------------------------------
def test_an_interrupt_exits_130_records_the_interruption_and_keeps_partial_files(tmp_path, capsys):
    code, run_dir, factory, specs, _loaded = run(tmp_path, script={3: KeyboardInterrupt()})
    assert code == 130 and "interrupted" in capsys.readouterr().err
    report = report_of(run_dir)
    assert report["failure_stage"] == "interrupted" and report["analysis_eligible"] is False and report["runner"]["status"] == "interrupted"
    assert len((run_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()) == 2        # partial output preserved
    with pytest.raises(IntegrityGateError):
        load_eligible_run(run_dir, expected_episode_ids=[s.episode_id for s in specs])


# ---- exit code 5 and the mapping itself ----------------------------------------------------------------------------------------
def outcome(**kw):
    base = dict(status="complete", failed_stage=None, report_path="r", analysis_eligible=True, detail="", run_dir="d")
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("kw,expected", [
    (dict(), 0),
    (dict(analysis_eligible=False), 5),
    (dict(status="failed", failed_stage="runner", analysis_eligible=False), 1),
    (dict(status="failed", failed_stage="loader", analysis_eligible=False), 1),
    (dict(status="failed", failed_stage="client_construction", analysis_eligible=False), 1),
    (dict(status="failed", failed_stage="artifact_hashing", analysis_eligible=False), 1),
    (dict(status="refused", failed_stage="inputs", report_path=None, analysis_eligible=False), 2),
    (dict(status="failed", failed_stage="policy_stop", analysis_eligible=False), 3),
    (dict(status="failed", failed_stage="report", report_path=None, analysis_eligible=False), 4),
    (dict(status="failed", failed_stage="policy_stop", report_path=None, analysis_eligible=False), 4),
    (dict(status="failed", failed_stage="interrupted", analysis_eligible=False), 130),
])
def test_the_exit_code_mapping(kw, expected):
    assert live_exit_code(outcome(**kw)) == expected


def test_the_exit_code_constants_are_the_approved_table():
    assert (receiver.OK, receiver.LIFECYCLE_FAILED, receiver.REFUSED, receiver.POLICY_STOP, receiver.REPORT_UNWRITABLE,
            receiver.NOT_ELIGIBLE, receiver.INTERRUPTED) == (0, 1, 2, 3, 4, 5, 130)


# ---- the executor interface -------------------------------------------------------------------------------------------------------
def test_mock_and_live_flows_do_not_read_credentials_or_construct_the_provider_client(tmp_path, tripwires):
    run(tmp_path)
    assert tripwires == []
