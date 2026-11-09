"""The optional ``policy_record`` of ``execute_live_run`` (v2.3.74, Stage 4E, PS-15 option A). Offline, fake client."""

from __future__ import annotations

import json
import socket

import pytest

from le_support import SENTINEL, Factory, ScriptedClient, read_report, run_live

GOOD = {
    "schema": "maps-live-policy", "schema_version": 1, "profile": "synthetic", "policy_digest": "a" * 64, "planned_episodes": 96,
    "max_tokens_per_request": 800, "content_bound": True, "expected_digest_checked": False,
    "endpoint": {"scheme": "https", "host": "example.invalid", "path": "/v", "validated": True},
}


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    import maps.llm_client as llm_client

    def refuse(*args, **kwargs):
        raise AssertionError("network access or provider-client construction attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(llm_client.OpenRouterClient, "__init__", refuse)


def test_without_a_record_the_live_block_is_unchanged(tmp_path):
    outcome, _factory, _runner = run_live(tmp_path)
    assert outcome.analysis_eligible and "policy_source" not in read_report(tmp_path / "run")["live"]


def test_a_valid_record_is_stored_under_policy_source_and_the_run_stays_eligible(tmp_path):
    outcome, _factory, _runner = run_live(tmp_path, policy_record=GOOD)
    assert outcome.analysis_eligible
    assert read_report(tmp_path / "run")["live"]["policy_source"] == GOOD


def test_the_stored_record_is_a_copy_not_the_callers_object(tmp_path):
    record = json.loads(json.dumps(GOOD))
    outcome, _factory, _runner = run_live(tmp_path, policy_record=record)
    record["profile"] = "changed-afterwards"
    assert read_report(tmp_path / "run")["live"]["policy_source"]["profile"] == "synthetic" and outcome.analysis_eligible


@pytest.mark.parametrize("bad", [
    "text", ["a"], 5, {"api_key": "x"}, {"API_KEY": "x"}, {"secret": "x"}, {"password": "x"}, {"authorization": "x"},
    {"bearer_value": "x"}, {"token": "x"}, {"access_token": "x"}, {"x y": "z"}, {"1abc": "z"}, {"a": 1.5}, {"a": None}, {"a": [1]},
    {"a": {"b": {"c": {"d": 1}}}}, {"a": "x" * 5000},
])
def test_an_invalid_record_is_refused_before_anything_is_written(tmp_path, bad):
    outcome, factory, _runner = run_live(tmp_path, policy_record=bad)
    assert outcome.status == "refused" and outcome.failed_stage == "inputs" and not outcome.claimed
    assert factory.calls == 0 and not (tmp_path / "run").exists()


def test_a_record_containing_a_redaction_value_is_refused(tmp_path):
    outcome, factory, _runner = run_live(tmp_path, policy_record={**GOOD, "profile": f"x-{SENTINEL}-y"}, redaction_values=[SENTINEL])
    assert outcome.status == "refused" and factory.calls == 0 and not (tmp_path / "run").exists()


def test_a_non_string_key_is_refused(tmp_path):
    outcome, factory, _runner = run_live(tmp_path, policy_record={1: "x"})
    assert outcome.status == "refused" and factory.calls == 0


def test_field_names_that_merely_contain_token_are_allowed(tmp_path):
    outcome, _factory, _runner = run_live(tmp_path, policy_record={"max_tokens_per_request": 800, "expected_digest_checked": True})
    assert outcome.analysis_eligible


def test_the_executor_signature_keeps_every_existing_parameter_and_adds_only_the_optional_record():
    import inspect

    from maps.runs.live_executor import execute_live_run

    params = inspect.signature(execute_live_run).parameters
    assert list(params) == ["run_fn", "cfg", "scenarios", "client_factory", "policy", "run_dir", "run_id", "repo_root", "expected_episode_ids",
                            "redaction_values", "provenance_options", "clock", "budget_clock", "policy_record"]
    assert params["policy_record"].default is None and params["policy_record"].kind is inspect.Parameter.KEYWORD_ONLY
