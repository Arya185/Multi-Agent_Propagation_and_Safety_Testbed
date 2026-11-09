"""Policy stops, provider errors, runner failures and partial runs (real runner, fake client, offline)."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from maps.llm_client import ApiDisabledError
from maps.runs.lifecycle import RunNotEligibleError
from maps.schemas import LLMResult

from le_support import (
    PLANNED, SENTINEL, CallingRunner, Factory, FakeClock, RunnerSpy, ScriptedClient, event_names, line_count, make_policy, read_events,
    read_report, run_live, small_ids,
)


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    import maps.llm_client as llm_client

    def refuse(*args, **kwargs):
        raise AssertionError("network access or provider-client construction attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(llm_client.OpenRouterClient, "__init__", refuse)


def err(text, attempts=1):
    return LLMResult(error=text, attempts=attempts)


def assert_partial_stop(outcome, out: Path, *, episodes: int, reason: str, raised: bool = True, runner_wrote_summaries: bool = False):
    assert (outcome.status, outcome.failed_stage) == ("failed", "policy_stop") and not outcome.analysis_eligible
    assert f"{reason}" in outcome.detail
    assert line_count(out / "episodes.jsonl") == episodes and line_count(out / "calls.jsonl") == episodes     # nothing fabricated or lost
    # an incomplete run gets no summaries; after a normal return the RUNNER itself wrote its legacy summaries (the executor never adds any)
    assert (out / "summary.json").exists() is runner_wrote_summaries and (out / "contrast_gaps.json").exists() is runner_wrote_summaries
    report = read_report(out)
    assert report["analysis_eligible"] is False and report["overall_status"] == "failed" and report["failure_stage"] == "policy_stop"
    assert report["live"]["policy_stop_reason"] == reason and report["live"]["policy_stop_raised_by_wrapper"] is raised
    assert report["eligibility"]["no_policy_stop"] is False
    with pytest.raises(RunNotEligibleError):
        outcome.require_eligible()
    return report


# ---- BudgetAbort ------------------------------------------------------------------------------------------
def test_a_fatal_error_stops_the_run_at_the_next_call_and_keeps_every_completed_record(tmp_path):
    inner = ScriptedClient({10: err("http_401: nope")})
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    report = assert_partial_stop(outcome, out, episodes=10, reason="fatal_error")
    assert inner.calls == 10                                                                 # the 11th call never reached the client
    assert report["runner"] == {"status": "failed", "results_returned": None, "exception_class": "BudgetAbort"}
    assert report["inventory_validation"]["status"] == "mismatch" and report["inventory_validation"]["missing"] == PLANNED - 10
    assert report["structural_validation"]["status"] == "passed" and report["loader"]["records_loaded"] == 10
    names = event_names(out)
    assert "policy_stop" in names and "runner_failed" not in names and names[-1] == "integrity_report_written"
    stop = next(e for e in read_events(out) if e["event"] == "policy_stop")
    assert stop["reason"] == "fatal_error" and stop["raised"] is True
    assert outcome.loaded.report.valid_records == 10 and len(outcome.results or ()) == 0


def test_the_failing_call_is_recorded_as_an_ordinary_call_error_episode_not_dropped(tmp_path):
    inner = ScriptedClient({4: err("http_404: gone")})
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    records = [json.loads(line) for line in (tmp_path / "run" / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 4 and [r["status"] for r in records] == ["ok", "ok", "ok", "call_error"]
    assert outcome.failed_stage == "policy_stop"


def test_consecutive_nonfatal_errors_stop_the_run_at_exactly_n(tmp_path):
    inner = ScriptedClient({4: err("http_503: x"), 5: err("http_503: x"), 6: err("http_503: x")})
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner), policy=make_policy(max_consecutive_nonfatal_errors=3))
    assert_partial_stop(outcome, tmp_path / "run", episodes=6, reason="consecutive_errors")
    assert inner.calls == 6


def test_the_disabled_client_exception_is_a_policy_stop_with_no_episodes(tmp_path):
    inner = ScriptedClient({1: ApiDisabledError("disabled")})
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    assert (outcome.status, outcome.failed_stage) == ("failed", "policy_stop") and "disabled_client" in outcome.detail
    assert read_report(out)["live"]["policy_stop_reason"] == "disabled_client" and not (out / "episodes.jsonl").exists()
    assert read_report(out)["live"]["budget"]["exception_class_counts"] == {"ApiDisabledError": 1}


def test_the_request_budget_and_the_episode_cap_stop_a_runner_that_makes_extra_calls(tmp_path):
    for overrides, reason in ((dict(max_episodes=10, max_request_attempts=3), "request_budget"), (dict(max_episodes=3, max_request_attempts=10), "episode_cap")):
        policy = make_policy(planned_episodes=3, max_consecutive_nonfatal_errors=3, **overrides)
        inner = ScriptedClient()
        sub = tmp_path / reason
        sub.mkdir()
        runner = CallingRunner(n_calls=5)
        outcome, factory, spied = run_live(sub, factory=Factory(inner), policy=policy, runner=runner, ids=small_ids(3))
        out = sub / "run"
        assert (outcome.status, outcome.failed_stage) == ("failed", "policy_stop") and inner.calls == 3 and not outcome.analysis_eligible
        report = read_report(out)
        assert report["live"]["policy_stop_reason"] == reason and report["inventory_validation"]["status"] == "matched"   # grid complete, still ineligible
        assert report["analysis_eligible"] is False and report["eligibility"]["no_policy_stop"] is False


def test_the_deadline_is_enforced_between_calls_and_an_inflight_call_is_not_called_cancelled(tmp_path):
    clock = FakeClock()
    inner = ScriptedClient(advance=lambda: clock.advance(60))
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner), policy=make_policy(deadline_seconds=100), budget_clock=clock)
    report = assert_partial_stop(outcome, tmp_path / "run", episodes=2, reason="deadline")
    budget = report["live"]["budget"]
    assert budget["deadline_crossed_by_inflight_call"] is True and "not cancelled" in budget["in_flight_note"]
    assert budget["calls_returned"] == 2 and budget["calls_raised"] == 0 and inner.calls == 2


# ---- a stop on the final call -------------------------------------------------------------------------------
def test_a_stop_recorded_on_the_final_call_is_detected_even_though_the_runner_returned_normally(tmp_path):
    inner = ScriptedClient({PLANNED: err("http_401: late")})
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    assert len(outcome.results) == PLANNED and inner.calls == PLANNED                       # the whole grid ran
    report = assert_partial_stop(outcome, out, episodes=PLANNED, reason="fatal_error", raised=False, runner_wrote_summaries=True)
    assert "returned normally" in outcome.detail
    assert report["runner"]["status"] == "completed" and report["inventory_validation"]["status"] == "matched"
    assert event_names(out)[3:5] == ["runner_finished", "policy_stop"]
    assert "owner decision" in report["live"]["eligibility_note"]                           # flagged, conservative answer applied


# ---- provider errors and runner failures are distinct --------------------------------------------------------
def test_isolated_provider_errors_are_ordinary_results_not_policy_stops(tmp_path):
    inner = ScriptedClient({3: err("http_503: x"), 8: err("http_429: y")})
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    assert (outcome.status, outcome.failed_stage) == ("complete", None)
    records = [json.loads(line) for line in (out / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["status"] for r in records].count("call_error") == 2 and len(records) == PLANNED
    live = read_report(out)["live"]
    assert live["budget"]["calls_nonfatal"] == 2 and not live["policy_stop_recorded"] and live["wrapper_stop_reason"] is None
    assert dict((k, v) for k, v in live["budget"]["error_category_counts"].items()) == {"http_503": 1, "http_429": 1}


def test_an_ordinary_runner_exception_is_a_runner_failure_not_a_policy_stop(tmp_path):
    inner = ScriptedClient({5: RuntimeError(f"client bug {SENTINEL}")})
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    assert (outcome.status, outcome.failed_stage) == ("failed", "runner") and outcome.detail == "RuntimeError (message withheld)"
    report = read_report(out)
    assert report["runner"] == {"status": "failed", "results_returned": None, "exception_class": "RuntimeError"}
    assert report["live"]["wrapper_stop_reason"] == "unexpected_client_exception" and not report["live"]["policy_stop_recorded"]
    assert "policy_stop" not in event_names(out) and "runner_failed" in event_names(out)
    assert line_count(out / "episodes.jsonl") == 4 and not outcome.analysis_eligible
    for path in out.iterdir():
        assert SENTINEL not in path.read_text(encoding="utf-8"), path.name


def test_a_stopped_run_is_never_resumed_or_rerun_into_the_same_directory(tmp_path):
    inner = ScriptedClient({2: err("http_401: x")})
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    again, factory2, runner2 = run_live(tmp_path, run_id="live-002")
    assert (again.status, again.failed_stage) == ("refused", "run_directory") and factory2.calls == 0 and runner2.calls == 0
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


def test_a_policy_stop_leaves_every_evidence_file_in_place(tmp_path):
    inner = ScriptedClient({7: err("http_403: x")})
    run_live(tmp_path, factory=Factory(inner))
    names = {p.name for p in (tmp_path / "run").iterdir()}
    assert names == {".maps_run_claim", "calls.jsonl", "episodes.jsonl", "manifest.json", "run_events.jsonl", "run_integrity.json", "run_provenance.json"}


# ---- the lifecycle itself: any recorded failure stage is ineligible, even when every condition holds -----------------
def test_any_recorded_failure_stage_makes_a_run_ineligible_even_if_every_eligibility_condition_is_true(tmp_path):
    from maps.runs.lifecycle import LifecycleHooks, RunnerFailure, run_lifecycle

    from le_support import CLOCK, provenance_options, small_ids
    from re_support_bridge import REPO_ROOT

    out = tmp_path / "run"
    runner = CallingRunner(n_calls=3)
    client = ScriptedClient()
    hooks = LifecycleHooks(post_runner_check=lambda: RunnerFailure(stage="policy_stop", event="policy_stop", detail="flagged", event_fields={"reason": "x"}))
    outcome = run_lifecycle(
        run_dir=out, run_id="hook-1", execution_mode="live", repo_root=REPO_ROOT,
        invoke_runner=lambda: runner(None, [], client, out, None, REPO_ROOT), inventory=small_ids(3), options=provenance_options(),
        clock=CLOCK, hooks=hooks,
    )
    report = read_report(out)
    assert all(report["eligibility"].values())                    # every named condition holds ...
    assert (outcome.status, outcome.failed_stage) == ("failed", "policy_stop") and report["analysis_eligible"] is False   # ... yet the run is ineligible
    assert not outcome.analysis_eligible and report["failure_stage"] == "policy_stop"


def test_redaction_values_never_appear_in_stop_or_interruption_records(tmp_path):
    stopped = ScriptedClient({3: err("http_401: nope")}, leak=SENTINEL)
    outcome, _, runner = run_live(tmp_path, factory=Factory(stopped), redaction_values=[SENTINEL])
    assert outcome.failed_stage == "policy_stop" and runner.secrets == [[SENTINEL]]
    interrupted_dir = tmp_path / "interrupted"
    interrupted_dir.mkdir()
    interrupted = ScriptedClient({3: KeyboardInterrupt()}, leak=SENTINEL)
    with pytest.raises(KeyboardInterrupt) as caught:
        run_live(interrupted_dir, factory=Factory(interrupted), redaction_values=[SENTINEL])
    assert caught.value.maps_outcome.failed_stage == "interrupted"
    for run_dir in (tmp_path / "run", interrupted_dir / "run"):
        for path in run_dir.iterdir():
            assert SENTINEL not in path.read_text(encoding="utf-8"), (run_dir.name, path.name)    # events, report, provenance, outputs alike
