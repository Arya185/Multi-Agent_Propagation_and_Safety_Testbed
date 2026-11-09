"""KeyboardInterrupt handling: best-effort recording, then the ORIGINAL interrupt is re-raised (offline)."""

from __future__ import annotations

import socket

import pytest

import maps.runs.live_executor as live_executor_module
from maps.runs.executor import execute_mock_run
from maps.runs.integrity_report import EventLog

from le_support import (
    CLOCK, PLANNED, Factory, FakeClock, RunnerSpy, ScriptedClient, event_names, line_count, make_policy, read_report, run_live,
)
from re_support_bridge import MOCK_RUN


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    import maps.llm_client as llm_client

    def refuse(*args, **kwargs):
        raise AssertionError("network access or provider-client construction attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(llm_client.OpenRouterClient, "__init__", refuse)


def interrupt_at(call: int):
    first = KeyboardInterrupt()
    return first, ScriptedClient({call: first})


def test_an_interrupt_is_recorded_and_the_original_is_re_raised(tmp_path):
    original, inner = interrupt_at(6)
    with pytest.raises(KeyboardInterrupt) as caught:
        run_live(tmp_path, factory=Factory(inner))
    assert caught.value is original                                                          # the same object, not a replacement
    out = tmp_path / "run"
    outcome = caught.value.maps_outcome
    assert (outcome.status, outcome.failed_stage) == ("failed", "interrupted") and not outcome.analysis_eligible
    report = read_report(out)
    assert report["runner"] == {"status": "interrupted", "results_returned": None, "exception_class": "KeyboardInterrupt"}
    assert report["failure_stage"] == "interrupted" and report["analysis_eligible"] is False and report["overall_status"] == "failed"
    assert report["live"]["wrapper_stop_reason"] == "unexpected_client_exception" and not report["live"]["policy_stop_recorded"]
    assert not hasattr(caught.value, "__notes__")                                            # nothing failed while recording


def test_completed_output_is_preserved_and_the_incomplete_inventory_is_recorded_as_evidence(tmp_path):
    original, inner = interrupt_at(6)
    with pytest.raises(KeyboardInterrupt):
        run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    report = read_report(out)
    assert line_count(out / "episodes.jsonl") == 5 == line_count(out / "calls.jsonl")        # calls 1-5 completed; the interrupted call recorded nothing
    assert report["inventory_validation"]["status"] == "mismatch" and report["inventory_validation"]["missing"] == PLANNED - 5
    assert report["loader"]["records_loaded"] == 5 and report["loader"]["order_matches_runner"] is None
    assert not (out / "summary.json").exists() and not (out / "contrast_gaps.json").exists()


def test_the_interruption_events_are_recorded_in_order(tmp_path):
    original, inner = interrupt_at(3)
    with pytest.raises(KeyboardInterrupt):
        run_live(tmp_path, factory=Factory(inner))
    names = event_names(tmp_path / "run")
    assert names == ["run_claimed", "provenance_recorded", "runner_started", "runner_interrupted", "post_run_validation_finished", "integrity_report_written"]
    assert "runner_finished" not in names and "policy_stop" not in names


def test_an_interrupt_raised_by_the_runner_itself_is_handled_the_same_way(tmp_path):
    class InterruptingRunner(RunnerSpy):
        def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=None):
            self.calls += 1
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt) as caught:
        run_live(tmp_path, runner=InterruptingRunner())
    assert caught.value.maps_outcome.failed_stage == "interrupted" and read_report(tmp_path / "run")["runner"]["status"] == "interrupted"


def test_a_failure_while_recording_does_not_replace_the_interrupt_and_is_disclosed(tmp_path, monkeypatch):
    class LoudLog(EventLog):
        def emit(self, event, **fields):
            if event == "runner_interrupted":
                raise RuntimeError("log trouble")
            return super().emit(event, **fields)

    monkeypatch.setattr(live_executor_module, "EventLog", LoudLog)
    original, inner = interrupt_at(4)
    with pytest.raises(KeyboardInterrupt) as caught:
        run_live(tmp_path, factory=Factory(inner))
    assert caught.value is original
    assert any("recording the interruption failed (RuntimeError)" in note for note in caught.value.__notes__)
    assert not hasattr(caught.value, "maps_outcome")
    out = tmp_path / "run"
    assert not (out / "run_integrity.json").exists()                                         # no report, so the run is incomplete
    assert line_count(out / "episodes.jsonl") == 3                                           # completed output is untouched


def test_nothing_resumes_or_recovers_after_an_interrupt(tmp_path):
    original, inner = interrupt_at(2)
    with pytest.raises(KeyboardInterrupt):
        run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    again, factory, runner = run_live(tmp_path, run_id="live-002")
    assert (again.status, again.failed_stage) == ("refused", "run_directory") and factory.calls == 0 and runner.calls == 0
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


def test_an_interrupt_before_the_runner_starts_is_not_intercepted_and_leaves_no_report(tmp_path):
    class InterruptingFactory(Factory):
        def __call__(self):
            self.calls += 1
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_live(tmp_path, factory=InterruptingFactory())
    out = tmp_path / "run"
    assert not (out / "run_integrity.json").exists() and event_names(out) == ["run_claimed", "provenance_recorded"]   # incomplete by rule


def test_the_mock_executor_does_not_intercept_an_interrupt(tmp_path):
    with pytest.raises(KeyboardInterrupt) as caught:
        MOCK_RUN(tmp_path, KeyboardInterrupt())
    assert not hasattr(caught.value, "maps_outcome")
    assert not (tmp_path / "run" / "run_integrity.json").exists()
    assert event_names(tmp_path / "run") == ["run_claimed", "provenance_recorded", "runner_started"]
