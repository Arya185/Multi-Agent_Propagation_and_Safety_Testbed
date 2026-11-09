"""Routing: every request of the run passes through ONE budget wrapper (real runner, fake client, offline)."""

from __future__ import annotations

import json
import socket

import pytest

import maps.experiments.receiver as receiver
import maps.runs.live_executor as live_executor_module
from maps.runs.live_budget import BudgetedClient

from le_support import (
    PLANNED, SENTINEL, Factory, FakeClock, RunnerSpy, ScriptedClient, event_names, make_policy, read_report, run_live,
)


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    import maps.llm_client as llm_client

    def refuse(*args, **kwargs):
        raise AssertionError("network access or provider-client construction attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(llm_client.OpenRouterClient, "__init__", refuse)


def test_the_runner_receives_one_budgeted_client_and_the_factory_is_called_once(tmp_path):
    inner = ScriptedClient()
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    assert (outcome.status, outcome.failed_stage) == ("complete", None) and outcome.analysis_eligible
    assert factory.calls == 1 and runner.calls == 1
    (wrapper,) = runner.clients
    assert isinstance(wrapper, BudgetedClient) and wrapper is not inner and wrapper.name == inner.name == "fake-live"


def test_the_same_wrapper_serves_every_episode_of_the_grid(tmp_path, monkeypatch):
    seen = []
    real = receiver.run_episode

    def spy(spec, scenario, client, cfg, call_writer=None):
        seen.append((id(client), client.summary().logical_calls_started, spec.model_alias, spec.prompt_variant, spec.condition_id))
        return real(spec, scenario, client, cfg, call_writer)

    monkeypatch.setattr(receiver, "run_episode", spy)
    outcome, factory, runner = run_live(tmp_path)
    assert outcome.status == "complete" and len(seen) == PLANNED
    assert len({entry[0] for entry in seen}) == 1                                            # one wrapper object throughout
    assert [entry[1] for entry in seen] == list(range(PLANNED))                              # the count never resets
    assert len({e[2] for e in seen}) == 2 and len({e[3] for e in seen}) == 2 and len({e[4] for e in seen}) == 6   # models, variants, conditions


def test_every_model_request_passes_through_the_wrapper(tmp_path):
    inner = ScriptedClient()
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    summary = runner.clients[0].summary()
    assert inner.calls == summary.logical_calls_started == summary.calls_returned == summary.attempts_charged == PLANNED
    assert len(outcome.results) == PLANNED and len({r.model for r in inner.requests}) == 2
    assert (tmp_path / "run" / "calls.jsonl").read_text(encoding="utf-8").count("\n") == PLANNED


def test_the_deadline_starts_when_the_wrapper_is_built_not_during_setup(tmp_path, monkeypatch):
    clock = FakeClock()
    real = live_executor_module.collect_provenance

    def slow_provenance(**kwargs):
        clock.advance(50_000)                                                               # pre- and post-run provenance take a long time
        return real(**kwargs)

    monkeypatch.setattr(live_executor_module, "collect_provenance", slow_provenance)
    inner = ScriptedClient()

    class SlowFactory(Factory):
        def __call__(self):
            clock.advance(50_000)                                                           # so does building the client
            return super().__call__()

    outcome, factory, runner = run_live(tmp_path, factory=SlowFactory(inner), policy=make_policy(deadline_seconds=100), budget_clock=clock)
    assert outcome.status == "complete" and outcome.analysis_eligible
    assert runner.clients[0].summary().elapsed_seconds_at_last_check < 1
    assert runner.clients[0].summary().stop_reason is None


def test_time_spent_in_the_runner_counts_against_the_deadline(tmp_path):
    clock = FakeClock()
    inner = ScriptedClient(advance=lambda: clock.advance(1.0))
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner), policy=make_policy(deadline_seconds=10), budget_clock=clock)
    assert outcome.failed_stage == "policy_stop" and read_report(tmp_path / "run")["live"]["policy_stop_reason"] == "deadline"
    assert inner.calls == 10


def test_a_successful_run_reports_the_live_mode_budget_and_event_sequence(tmp_path):
    outcome, factory, runner = run_live(tmp_path)
    report = read_report(tmp_path / "run")
    assert report["execution_mode"] == "live" and report["analysis_eligible"] is True and report["overall_status"] == "complete"
    assert report["eligibility"]["no_policy_stop"] is True and report["statistical_validity_claimed"] is False
    live = report["live"]
    assert live["client_factory_called"] and live["budget_wrapper_created"] and live["wrapper_stop_reason"] is None and not live["policy_stop_recorded"]
    assert live["policy"]["max_request_attempts"] == PLANNED and live["policy"]["accounting_basis"] == "client_attempts"
    assert live["budget"]["attempts_charged"] == PLANNED and live["budget"]["redirect_exposure"] == "not_counted"
    assert event_names(tmp_path / "run") == [
        "run_claimed", "provenance_recorded", "runner_started", "runner_finished", "post_run_validation_finished", "integrity_report_written"]
    assert report["inventory_validation"] == {"performed": True, "status": "matched", "missing": 0, "unexpected": 0, "invalid_expected": 0}


def test_the_runner_gets_the_redaction_values_and_nothing_secret_is_stored(tmp_path):
    inner = ScriptedClient(leak=SENTINEL)
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner), redaction_values=[SENTINEL])
    assert outcome.status == "complete" and runner.secrets == [[SENTINEL]]
    for path in (tmp_path / "run").iterdir():
        assert SENTINEL not in path.read_text(encoding="utf-8"), path.name                  # redacted from every output, never in the report
    assert SENTINEL not in json.dumps(read_report(tmp_path / "run"))


def test_a_run_into_an_existing_directory_is_refused_without_calling_the_factory(tmp_path):
    first, factory1, _ = run_live(tmp_path)
    second, factory2, runner2 = run_live(tmp_path, run_id="live-002")
    assert first.status == "complete" and (second.status, second.failed_stage) == ("refused", "run_directory")
    assert factory2.calls == 0 and runner2.calls == 0
