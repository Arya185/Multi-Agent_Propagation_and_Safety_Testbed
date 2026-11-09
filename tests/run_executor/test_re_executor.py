"""The mock-only run executor (SYNTHETIC runner doubles, temporary directories, no network)."""

from __future__ import annotations

import ast
import inspect
import json
import socket
from pathlib import Path

import pytest

import maps.runs.executor as executor_module
import maps.runs.integrity_report as report_module
from maps.runs.executor import ExecutionOutcome, RunNotEligibleError, execute_mock_run, provenance_drift
from maps.runs.integrity_report import ELIGIBILITY_CONDITIONS, EVENT_TYPES, FAILURE_STAGES

from re_support import (
    MOCK, SENTINEL, SOURCE_REL, LOCK_REL, Runner, append_line, cfg_double, duplicate_first_line, episode_ids, make_repo,
    provenance_options, read_events, reverse_lines, schema_invalid_line, tree_hashes, truncate,
)

SUCCESS_FILES = {".maps_run_claim", "episodes.jsonl", "run_events.jsonl", "run_integrity.json", "run_provenance.json"}
SUCCESS_EVENTS = ["run_claimed", "provenance_recorded", "runner_started", "runner_finished", "post_run_validation_finished"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during an executor test")

    monkeypatch.setattr(socket, "socket", refuse)


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


def go(tmp_path, repo, runner=None, *, run_id="run-001", out=None, **kw) -> ExecutionOutcome:
    kw.setdefault("provenance_options", provenance_options())
    return execute_mock_run(
        run_fn=runner or Runner(), cfg=kw.pop("cfg", cfg_double()), scenarios=[], client=kw.pop("client", MOCK),
        run_dir=out or (tmp_path / "run"), run_id=run_id, repo_root=repo, **kw,
    )


def report_of(out: Path) -> dict:
    return json.loads((out / "run_integrity.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------
def test_successful_run_is_complete_and_eligible_with_one_runner_call(tmp_path, repo):
    runner, out = Runner(3), tmp_path / "run"
    outcome = go(tmp_path, repo, runner)
    assert runner.calls == 1
    assert (outcome.status, outcome.failed_stage, outcome.detail, outcome.claimed) == ("complete", None, "", True)
    assert outcome.analysis_eligible and len(outcome.require_eligible()) == 3
    assert {p.name for p in out.iterdir()} == SUCCESS_FILES
    report = outcome.report
    assert (report.overall_status, report.failure_stage, report.execution_mode, report.directory_initialization) == ("complete", None, "mock", "claimed")
    assert report.pre_run_provenance["status"] == "recorded" and report.post_run_provenance["status"] == "collected"
    assert report.runner == {"status": "completed", "results_returned": 3, "exception_class": None}
    assert report.provenance_drift["status"] == "none_detected" and report.loader["status"] == "passed"
    assert report.loader["records_loaded"] == 3 and report.loader["order_matches_runner"] is True
    assert tuple(report.eligibility) == ELIGIBILITY_CONDITIONS and all(report.eligibility.values())
    assert report.statistical_validity_claimed is False
    assert report_of(out) == report.to_dict() | {"warnings": list(report.warnings), "notes": list(report.notes)}
    assert outcome.report_path == out / "run_integrity.json" and outcome.events_path == out / "run_events.jsonl"


def test_inventory_validation_is_recorded_as_not_performed_when_none_is_supplied(tmp_path, repo):
    outcome = go(tmp_path, repo)
    assert outcome.report.inventory_validation == {"performed": False, "status": "not_performed", "missing": None, "unexpected": None, "invalid_expected": None}
    assert outcome.analysis_eligible


def test_a_matching_explicit_inventory_is_recorded_as_performed(tmp_path, repo):
    outcome = go(tmp_path, repo, expected_episode_ids=episode_ids(3))
    assert outcome.report.inventory_validation == {"performed": True, "status": "matched", "missing": 0, "unexpected": 0, "invalid_expected": 0}
    assert outcome.analysis_eligible


def test_lifecycle_events_are_ordered_numbered_and_use_the_injected_clock(tmp_path, repo):
    outcome = go(tmp_path, repo, clock=lambda: "2026-02-03T04:05:06Z")
    events = read_events(tmp_path / "run")
    assert [e["event"] for e in events] == SUCCESS_EVENTS and [e["seq"] for e in events] == [1, 2, 3, 4, 5]
    assert {e["utc"] for e in events} == {"2026-02-03T04:05:06Z"} and {e["run_id"] for e in events} == {"run-001"}
    assert events[3] == {"seq": 4, "event": "runner_finished", "utc": "2026-02-03T04:05:06Z", "run_id": "run-001", "results_returned": 3}
    assert events[4]["passed"] is True and set(e["event"] for e in events) <= set(EVENT_TYPES)
    assert outcome.analysis_eligible


def test_the_single_pre_run_provenance_file_describes_the_run(tmp_path, repo):
    outcome = go(tmp_path, repo, run_id="prov-1")
    record = json.loads((tmp_path / "run" / "run_provenance.json").read_text(encoding="utf-8"))
    assert record["run_id"] == "prov-1" and "not an independent trust anchor" in record["note"]
    assert outcome.provenance_record == record and outcome.provenance_path == tmp_path / "run" / "run_provenance.json"


def test_partial_provenance_is_a_warning_not_a_failure(tmp_path, repo):
    outcome = go(tmp_path, repo, provenance_options=provenance_options(lock_file="no-such.lock"))
    assert outcome.analysis_eligible and outcome.report.pre_run_provenance["partial"] is True
    assert "lock_file(missing)" in outcome.report.pre_run_provenance["unavailable_fields"]


# ---------------------------------------------------------------------------
# Inputs, directory, collisions (nothing may be written)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["", "../escape", "a/b", "x" * 129, ".", "..", None])
def test_an_invalid_run_id_is_refused_before_any_directory_is_created(tmp_path, repo, bad):
    runner, out = Runner(), tmp_path / "run"
    outcome = go(tmp_path, repo, runner, run_id=bad)
    assert (outcome.status, outcome.failed_stage, outcome.claimed) == ("refused", "inputs", False)
    assert runner.calls == 0 and not out.exists() and not outcome.analysis_eligible and outcome.report is None


@pytest.mark.parametrize(
    "kwargs",
    [dict(client=type("Live", (), {"name": "openrouter"})()), dict(client=None), dict(cfg=cfg_double(enabled=True)),
     dict(expected_episode_ids=["ok", ""]), dict(provenance_options={"environment": "x"})],
    ids=["live-client", "no-client", "live-config", "bad-inventory", "bad-option"],
)
def test_non_mock_or_malformed_inputs_are_refused_without_writing(tmp_path, repo, kwargs):
    runner, out = Runner(), tmp_path / "run"
    outcome = go(tmp_path, repo, runner, **kwargs)
    assert (outcome.status, outcome.failed_stage) == ("refused", "inputs") and runner.calls == 0 and not out.exists()
    with pytest.raises(RunNotEligibleError):
        outcome.require_eligible()


def test_a_non_empty_directory_is_refused_and_left_untouched(tmp_path, repo):
    out = tmp_path / "used"
    out.mkdir()
    (out / "episodes.jsonl").write_text("an earlier record\n", encoding="utf-8")
    before, runner = tree_hashes(out), Runner()
    outcome = go(tmp_path, repo, runner, out=out)
    assert (outcome.status, outcome.failed_stage, outcome.claimed) == ("refused", "run_directory", False)
    assert "episodes.jsonl" in outcome.detail and runner.calls == 0 and tree_hashes(out) == before


def test_a_second_run_into_the_same_directory_is_refused_with_no_regeneration_or_alternate_directory(tmp_path, repo):
    first = go(tmp_path, repo)
    before, siblings = tree_hashes(tmp_path / "run"), sorted(p.name for p in tmp_path.iterdir())
    runner = Runner()
    second = go(tmp_path, repo, runner, run_id="run-002")
    assert first.status == "complete" and (second.status, second.failed_stage) == ("refused", "run_directory")
    assert runner.calls == 0 and tree_hashes(tmp_path / "run") == before and sorted(p.name for p in tmp_path.iterdir()) == siblings


def test_a_symbolic_link_directory_is_refused(tmp_path, repo):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    runner = Runner()
    outcome = go(tmp_path, repo, runner, out=link)
    assert outcome.failed_stage == "run_directory" and runner.calls == 0 and list(real.iterdir()) == []


# ---------------------------------------------------------------------------
# Runner failure and partial output
# ---------------------------------------------------------------------------
def test_a_runner_exception_is_recorded_safely_and_partial_output_is_preserved(tmp_path, repo):
    runner = Runner(3, raise_after=(2, RuntimeError(f"boom {SENTINEL}")))
    out = tmp_path / "run"
    outcome = go(tmp_path, repo, runner)
    assert runner.calls == 1                                      # no automatic retry
    assert (outcome.status, outcome.failed_stage, outcome.detail) == ("failed", "runner", "RuntimeError (message withheld)")
    assert outcome.results is None and not outcome.analysis_eligible
    assert (out / "episodes.jsonl").read_text(encoding="utf-8").count("\n") == 2     # the partial records stay
    assert {p.name for p in out.iterdir()} == SUCCESS_FILES                         # claim, provenance, events, report
    report = outcome.report
    assert report.runner == {"status": "failed", "results_returned": None, "exception_class": "RuntimeError"}
    assert report.post_run_provenance["status"] == "not_run" and report.provenance_drift["status"] == "not_checked"
    assert report.loader["status"] == "not_run" and report.analysis_eligible is False and report.overall_status == "failed"
    assert [e["event"] for e in read_events(out)] == ["run_claimed", "provenance_recorded", "runner_started", "runner_failed"]
    assert read_events(out)[-1]["exception_class"] == "RuntimeError"
    for path in out.iterdir():
        assert SENTINEL not in path.read_text(encoding="utf-8"), path.name
    with pytest.raises(RunNotEligibleError):
        outcome.require_eligible()


def test_a_runner_that_returns_nothing_usable_is_a_runner_failure(tmp_path, repo):
    outcome = go(tmp_path, repo, Runner(returns=None))
    assert (outcome.status, outcome.failed_stage) == ("failed", "runner") and outcome.report.runner["exception_class"] == "TypeError"


def test_a_failed_run_is_never_resumed_appended_or_overwritten(tmp_path, repo):
    out = tmp_path / "run"
    go(tmp_path, repo, Runner(3, raise_after=(1, RuntimeError("x"))))
    before, runner = tree_hashes(out), Runner()
    again = go(tmp_path, repo, runner)
    assert again.failed_stage == "run_directory" and runner.calls == 0 and tree_hashes(out) == before


# ---------------------------------------------------------------------------
# Provenance lifecycle
# ---------------------------------------------------------------------------
def test_pre_run_provenance_that_cannot_be_collected_stops_before_the_runner(tmp_path, repo, monkeypatch):
    def refuse(**kwargs):
        raise OSError(f"disk problem {SENTINEL}")

    monkeypatch.setattr(executor_module, "collect_provenance", refuse)
    runner, out = Runner(), tmp_path / "run"
    outcome = go(tmp_path, repo, runner)
    assert runner.calls == 0 and (outcome.status, outcome.failed_stage) == ("failed", "pre_run_provenance")
    assert outcome.detail == "OSError (message withheld)" and outcome.claimed and not outcome.analysis_eligible
    assert outcome.report.pre_run_provenance["status"] == "failed" and outcome.report.runner["status"] == "not_started"
    assert {p.name for p in out.iterdir()} == {".maps_run_claim", "run_events.jsonl", "run_integrity.json"}
    assert [e["event"] for e in read_events(out)] == ["run_claimed", "provenance_failed"]
    for path in out.iterdir():
        assert SENTINEL not in path.read_text(encoding="utf-8")


def test_pre_run_provenance_write_failure_prevents_the_runner(tmp_path, repo, monkeypatch):
    def refuse(run_dir, record):
        raise FileExistsError("run_provenance.json")

    monkeypatch.setattr(executor_module, "write_provenance", refuse)
    runner = Runner()
    outcome = go(tmp_path, repo, runner)
    assert runner.calls == 0 and outcome.failed_stage == "pre_run_provenance" and not outcome.analysis_eligible


def test_post_run_provenance_failure_blocks_eligibility(tmp_path, repo, monkeypatch):
    real, calls = executor_module.collect_provenance, []

    def second_fails(**kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError(f"post {SENTINEL}")
        return real(**kwargs)

    monkeypatch.setattr(executor_module, "collect_provenance", second_fails)
    runner = Runner()
    outcome = go(tmp_path, repo, runner)
    assert runner.calls == 1 and (outcome.status, outcome.failed_stage) == ("failed", "post_run_provenance")
    assert outcome.report.post_run_provenance["status"] == "failed" and outcome.report.provenance_drift["status"] == "not_checked"
    assert outcome.report.loader["status"] == "passed"           # the rest is still evaluated and recorded
    assert not outcome.analysis_eligible and outcome.report.eligibility["post_run_provenance_collected"] is False
    assert SENTINEL not in (tmp_path / "run" / "run_integrity.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda path, repo: (repo / SOURCE_REL).write_text("VALUE = 2\n", encoding="utf-8"), f"source_files:{SOURCE_REL}"),
        (lambda path, repo: (repo / LOCK_REL).write_text("pkg==2\n", encoding="utf-8"), "lock_file"),
        (lambda path, repo: (repo / "src" / "maps" / "late.py").write_text("x = 1\n", encoding="utf-8"), None),
    ],
    ids=["source-changed", "lock-changed", "new-unlisted-file-with-explicit-source-list"],
)
def test_drift_in_sources_or_lock_is_detected_and_blocks_eligibility(tmp_path, repo, mutate, expected):
    outcome = go(tmp_path, repo, Runner(after=mutate))
    if expected is None:                                           # an unlisted file is outside an explicit source list
        assert outcome.analysis_eligible and outcome.report.provenance_drift["status"] == "none_detected"
        return
    assert (outcome.status, outcome.failed_stage) == ("failed", "provenance_drift")
    assert outcome.report.provenance_drift["status"] == "detected" and outcome.report.provenance_drift["changed"] == [expected]
    assert outcome.report.eligibility["no_provenance_drift"] is False and not outcome.analysis_eligible


def test_package_drift_is_detected(tmp_path, repo):
    state = {"n": 0}

    def provider():
        state["n"] += 1
        return [("pkg", "1" if state["n"] == 1 else "2")]

    outcome = go(tmp_path, repo, provenance_options=provenance_options(package_provider=provider))
    assert outcome.failed_stage == "provenance_drift" and outcome.report.provenance_drift["changed"] == ["packages"]


def test_drift_comparison_ignores_timestamps_and_reports_added_and_removed_files():
    def record(files, lock="a", packages=()):
        return {"source_files": {"files": [{"path": p, "sha256": h, "status": "ok"} for p, h in files]},
                "lock_file": {"path": "l", "sha256": lock, "status": "ok"}, "packages": {"items": list(packages)}, "created_utc": "x"}

    pre = record([("a.py", "1"), ("b.py", "2")])
    assert provenance_drift(pre, {**record([("a.py", "1"), ("b.py", "2")]), "created_utc": "y"}) == []
    assert provenance_drift(pre, record([("a.py", "1"), ("c.py", "3")])) == ["source_files:b.py", "source_files:c.py"]


# ---------------------------------------------------------------------------
# Loader, structure, inventory
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "damage,field,expected",
    [(duplicate_first_line, "duplicate_ids", 1), (append_line("{broken json"), "invalid_json", 1), (schema_invalid_line, "schema_invalid", 1)],
    ids=["duplicate", "malformed", "schema-invalid"],
)
def test_damaged_results_fail_structural_validation_and_block_analysis(tmp_path, repo, damage, field, expected):
    runner, out = Runner(3, after=damage), tmp_path / "run"
    outcome = go(tmp_path, repo, runner)
    assert runner.calls == 1 and (outcome.status, outcome.failed_stage) == ("failed", "structural_validation")
    assert outcome.report.loader[field] == expected and outcome.report.structural_validation["status"] == "failed"
    assert outcome.report.loader["status"] == "failed" and not outcome.analysis_eligible
    assert (out / "episodes.jsonl").read_text(encoding="utf-8").count("\n") == 4          # damaged output preserved
    with pytest.raises(RunNotEligibleError):
        outcome.require_eligible()


def test_an_empty_result_file_fails_structural_validation(tmp_path, repo):
    outcome = go(tmp_path, repo, Runner(3, after=truncate))
    assert outcome.failed_stage == "structural_validation" and not outcome.analysis_eligible


def test_a_missing_result_file_fails_structural_validation(tmp_path, repo):
    outcome = go(tmp_path, repo, Runner(3, write=False))
    assert outcome.failed_stage == "structural_validation" and outcome.report.loader["records_loaded"] == 0


def test_a_reordered_file_is_caught_by_comparison_with_the_runner_return(tmp_path, repo):
    outcome = go(tmp_path, repo, Runner(3, after=reverse_lines))
    assert (outcome.failed_stage, outcome.report.loader["order_matches_runner"]) == ("loader", False)
    assert "order" in outcome.detail and not outcome.analysis_eligible


@pytest.mark.parametrize("inventory,missing,unexpected", [(episode_ids(4), 1, 0), (episode_ids(2), 0, 1)], ids=["missing", "unexpected"])
def test_an_explicit_inventory_mismatch_blocks_eligibility(tmp_path, repo, inventory, missing, unexpected):
    outcome = go(tmp_path, repo, Runner(3), expected_episode_ids=inventory)
    assert (outcome.status, outcome.failed_stage) == ("failed", "inventory")
    assert outcome.report.inventory_validation == {"performed": True, "status": "mismatch", "missing": missing, "unexpected": unexpected, "invalid_expected": 0}
    assert outcome.report.structural_validation["status"] == "passed" and not outcome.analysis_eligible


def test_the_loader_never_changes_the_run_files(tmp_path, repo):
    out = tmp_path / "run"
    go(tmp_path, repo, Runner(3, after=duplicate_first_line))
    after_run = {k: v for k, v in tree_hashes(out).items() if k not in ("run_events.jsonl", "run_integrity.json")}
    from maps.adapters.run_loader import load_episode_results

    load_episode_results(out)
    assert {k: v for k, v in tree_hashes(out).items() if k not in ("run_events.jsonl", "run_integrity.json")} == after_run


# ---------------------------------------------------------------------------
# Final report and event log failures
# ---------------------------------------------------------------------------
def test_a_run_whose_final_report_cannot_be_written_is_ineligible(tmp_path, repo):
    def squat(path, repo_root):
        (path.parent / "run_integrity.json").write_text("not a report\n", encoding="utf-8")

    out = tmp_path / "run"
    outcome = go(tmp_path, repo, Runner(3, after=squat))
    assert (outcome.status, outcome.failed_stage, outcome.report_path) == ("failed", "report", None)
    assert not outcome.analysis_eligible and (out / "run_integrity.json").read_text(encoding="utf-8") == "not a report\n"
    assert any("incomplete" in w for w in outcome.warnings)


def test_an_unwritable_event_log_stops_the_run_before_the_runner(tmp_path, repo, monkeypatch):
    class Broken:
        def __init__(self, *a, **k):
            self.complete, self.path = False, tmp_path / "run" / "run_events.jsonl"

        def emit(self, *a, **k):
            return False

    monkeypatch.setattr(executor_module, "EventLog", Broken)
    runner = Runner()
    outcome = go(tmp_path, repo, runner)
    assert runner.calls == 0 and outcome.failed_stage == "event_log" and not outcome.analysis_eligible


def test_an_event_log_failure_after_the_run_is_a_warning(tmp_path, repo, monkeypatch):
    real = executor_module.EventLog

    class Flaky(real):
        def emit(self, event, **fields):
            if event == "runner_finished":
                self.complete = False
                return False
            return super().emit(event, **fields)

    monkeypatch.setattr(executor_module, "EventLog", Flaky)
    outcome = go(tmp_path, repo)
    assert outcome.analysis_eligible and "lifecycle event log is incomplete" in outcome.warnings
    assert outcome.report.event_log["status"] == "incomplete"


def test_report_and_events_hold_no_secrets_labels_or_record_content(tmp_path, repo):
    go(tmp_path, repo, Runner(3, after=schema_invalid_line))
    out = tmp_path / "run"
    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield str(key).lower()
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)

    documents = [report_of(out), *read_events(out)]
    for name in ("run_integrity.json", "run_events.jsonl"):
        text = (out / name).read_text(encoding="utf-8").lower()
        for word in ("api_key", "secret", "password", "reasoning", "synthetic/alpha", "bearer", "sk-"):
            assert word not in text, (name, word)
    for key in set().union(*(set(keys(d)) for d in documents)):
        assert not any(w in key for w in ("truth", "label", "key", "secret", "token", "reasoning", "response", "scenario", "evidence")), key
    data = report_of(out)
    assert data["statistical_validity_claimed"] is False and any("not an independent trust anchor" in n for n in data["notes"])
    assert any("structural validity only" in n for n in data["notes"]) and any("does not prove completion" in n for n in data["notes"])


def test_every_failure_stage_name_is_documented():
    assert {"event_log", "pre_run_provenance", "runner", "post_run_provenance", "provenance_drift", "loader", "structural_validation", "inventory"} == set(FAILURE_STAGES)


# ---------------------------------------------------------------------------
# Boundaries: mock-only, no live client, no network, no CLI dependency
# ---------------------------------------------------------------------------
def test_the_executor_signature_has_no_live_option_and_requires_an_injected_runner():
    parameters = inspect.signature(execute_mock_run).parameters
    assert "run_fn" in parameters and parameters["run_fn"].default is inspect.Parameter.empty
    assert not any("live" in name or "allow" in name or "secret" in name or "key" in name for name in parameters)
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())


def test_the_executor_modules_import_no_cli_live_client_network_or_process_code():
    for module in (executor_module, report_module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        flat = {name.split(".")[0] for name in imported}
        assert not flat & {"socket", "urllib", "http", "requests", "subprocess", "os", "shutil", "dotenv"}, module.__name__
        assert not imported & {"maps.experiments.receiver", "maps.experiments", "maps.llm_client", "maps.mock_client"}, module.__name__
        assert "OpenRouter" not in source and "os.environ" not in source and "getenv" not in source


def test_a_live_looking_client_is_never_called(tmp_path, repo):
    class Live:
        name = "openrouter"

        def complete(self, request):
            raise AssertionError("must never be called")

    runner = Runner()
    outcome = go(tmp_path, repo, runner, client=Live())
    assert outcome.status == "refused" and runner.calls == 0
