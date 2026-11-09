"""The mock pipeline after delegation to the executor (SYNTHETIC inputs, temporary directories, no network)."""

from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest

import maps.pipeline.mock_pipeline as pipeline_module
from maps.config import load_config
from maps.experiments.receiver import run_experiment as real_run_experiment
from maps.pipeline.mock_pipeline import run_mock_pipeline
from maps.pipeline.report import STAGES
from maps.scenarios import load_scenario_dir

from re_support import REPO_ROOT, SYNTHETIC_DATA, tree_hashes


@pytest.fixture(scope="module")
def inputs():
    return load_config(SYNTHETIC_DATA / "config_synthetic.json"), load_scenario_dir(SYNTHETIC_DATA / "scenarios", REPO_ROOT)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during a pipeline test")

    monkeypatch.setattr(socket, "socket", refuse)


class Counting:
    def __init__(self, after=None):
        self.calls, self.after = 0, after

    def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=REPO_ROOT):
        self.calls += 1
        results = real_run_experiment(cfg, scenarios, client, out_dir, secrets, repo_root)
        if self.after:
            self.after(Path(out_dir) / "episodes.jsonl")
        return results


def spy_analysis(monkeypatch):
    calls = []
    for name in ("validate_rows", "invalid_response_report", "stratified_summary", "aggregate_to_scenario", "paired_scenario_diffs"):
        monkeypatch.setattr(pipeline_module, name, lambda *a, _n=name, **k: calls.append(_n))
    return calls


def run(inputs, out, run_id="mock-001", **kw):
    cfg, scenarios = inputs
    return run_mock_pipeline(cfg, scenarios, out, run_id, **kw)


def test_the_pipeline_report_references_the_integrity_report(tmp_path, inputs):
    out = tmp_path / "run"
    report = run(inputs, out)
    assert report.pipeline_execution_status == "success" and report.analysis_eligible is True
    assert report.integrity_overall_status == "complete" and report.integrity_report_path == str(out / "run_integrity.json")
    integrity = json.loads((out / "run_integrity.json").read_text(encoding="utf-8"))
    assert integrity["analysis_eligible"] is True and integrity["run_id"] == "mock-001" and integrity["execution_mode"] == "mock"
    on_disk = json.loads((out / "pipeline_report.json").read_text(encoding="utf-8"))
    assert on_disk["analysis_eligible"] is True and on_disk["statistical_protocol_complete"] is False
    assert [json.loads(l)["event"] for l in (out / "run_events.jsonl").read_text(encoding="utf-8").splitlines()][:3] == [
        "run_claimed", "provenance_recorded", "runner_started"]


def test_a_generated_run_id_is_accepted_by_the_pipeline(tmp_path, inputs):
    from maps.runs.ids import generate_run_id

    run_id = generate_run_id()
    report = run(inputs, tmp_path / run_id, run_id=run_id)
    assert report.pipeline_execution_status == "success" and report.run_id == run_id


def test_pre_run_provenance_failure_stops_before_the_runner_and_the_stages_stay_in_fixed_order(tmp_path, inputs, monkeypatch):
    import maps.runs.executor as executor_module

    def refuse(**kwargs):
        raise OSError("disk")

    monkeypatch.setattr(executor_module, "collect_provenance", refuse)
    runner = Counting()
    monkeypatch.setattr(pipeline_module, "run_experiment", runner)
    analysis = spy_analysis(monkeypatch)
    out = tmp_path / "run"
    report = run(inputs, out)
    assert runner.calls == 0 and analysis == []
    assert report.failed_stage == "provenance" and report.provenance_status == "failed" and report.records_written is None
    assert [s.stage for s in report.stages] == list(STAGES)
    assert [(s.stage, s.status) for s in report.stages][:4] == [("inputs", "ok"), ("run_directory", "ok"), ("mock_execution", "skipped"), ("provenance", "failed")]
    assert report.analysis_eligible is False and (out / "pipeline_report.json").is_file() and not (out / "episodes.jsonl").exists()


def test_provenance_drift_blocks_analysis(tmp_path, inputs, monkeypatch):
    state = {"n": 0}

    def provider():
        state["n"] += 1
        return [("pkg", str(state["n"]))]

    runner = Counting()
    monkeypatch.setattr(pipeline_module, "run_experiment", runner)
    analysis = spy_analysis(monkeypatch)
    out = tmp_path / "run"
    report = run(inputs, out, provenance_options={"package_provider": provider})
    assert runner.calls == 1 and analysis == []
    assert report.failed_stage == "provenance" and "packages" in report.stages[3].detail
    assert report.descriptive_analysis_status == "blocked" and report.analysis_eligible is False
    assert report.records_written == 96 and report.loader_status == "passed"        # recorded, but no analysis
    assert json.loads((out / "run_integrity.json").read_text(encoding="utf-8"))["provenance_drift"]["status"] == "detected"


def test_a_damaged_run_is_ineligible_and_leaves_its_files(tmp_path, inputs, monkeypatch):
    def damage(path):
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("{broken\n")

    monkeypatch.setattr(pipeline_module, "run_experiment", Counting(after=damage))
    analysis = spy_analysis(monkeypatch)
    out = tmp_path / "run"
    report = run(inputs, out)
    assert report.failed_stage == "loader_validation" and report.analysis_eligible is False and analysis == []
    assert report.integrity_overall_status == "failed"
    assert (out / "episodes.jsonl").read_text(encoding="utf-8").count("\n") == 97
    assert json.loads((out / "run_integrity.json").read_text(encoding="utf-8"))["failure_stage"] == "structural_validation"


def test_a_missing_integrity_report_means_no_analysis(tmp_path, inputs, monkeypatch):
    def squat(path):
        (path.parent / "run_integrity.json").write_text("occupied\n", encoding="utf-8")

    monkeypatch.setattr(pipeline_module, "run_experiment", Counting(after=squat))
    analysis = spy_analysis(monkeypatch)
    report = run(inputs, tmp_path / "run")
    assert report.failed_stage == "report" and report.analysis_eligible is False and analysis == []
    assert report.integrity_report_path is None


def test_a_refused_directory_is_not_touched_even_with_the_executor(tmp_path, inputs):
    out = tmp_path / "used"
    out.mkdir()
    (out / "note.txt").write_text("keep\n", encoding="utf-8")
    before = tree_hashes(out)
    report = run(inputs, out)
    assert report.failed_stage == "run_directory" and report.report_path is None and tree_hashes(out) == before
    assert [s.stage for s in report.stages] == list(STAGES)


def test_the_pipeline_delegates_claiming_provenance_and_execution_to_the_executor():
    tree = ast.parse(Path(pipeline_module.__file__).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"initialize_run_dir", "check_run_dir", "collect_provenance", "write_provenance", "load_episode_results"}
    called = {c.func.id for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "run_experiment" not in called and "execute_mock_run" in called       # the runner is only passed to the executor
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "maps.runs.executor" in imports and "maps.llm_client" not in imports
