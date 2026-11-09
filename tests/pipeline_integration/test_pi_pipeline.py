"""Mock end-to-end pipeline (SYNTHETIC fixtures, temporary directories, test doubles named 'mock').

These tests show that synthetic mock records pass through the software pipeline and that failures stop
it safely. They prove nothing about model behaviour or experimental results.
"""

from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest

import maps.pipeline.mock_pipeline as pipeline_module
import maps.pipeline.report as report_module
from maps.pipeline.mock_pipeline import run_mock_pipeline
from maps.pipeline.report import STAGES, PipelineFailed

from pi_support import (
    Recorder, append_line, duplicate_first_line, file_hash, grid_ids, load_inputs, reverse_lines,
    schema_invalid_line, tree_hashes,
)

EXPECTED_FILES = {
    ".maps_run_claim", "calls.jsonl", "contrast_gaps.json", "episodes.jsonl", "manifest.json",
    "pipeline_report.json", "run_events.jsonl", "run_integrity.json", "run_provenance.json", "summary.json",
}


@pytest.fixture(scope="module")
def inputs():
    return load_inputs()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during a mock pipeline test")

    monkeypatch.setattr(socket, "socket", refuse)


def run(inputs, out, run_id="mock-001", **kw):
    cfg, scenarios = inputs
    return run_mock_pipeline(cfg, scenarios, out, run_id, **kw)


def spy_analysis(monkeypatch):
    calls = []
    for name in ("validate_rows", "invalid_response_report", "stratified_summary", "aggregate_to_scenario", "paired_scenario_diffs"):
        monkeypatch.setattr(pipeline_module, name, lambda *a, _n=name, **k: calls.append(_n))
    return calls


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------
def test_successful_mock_pipeline_runs_every_stage(tmp_path, inputs):
    out = tmp_path / "run"
    report = run(inputs, out)
    assert report.pipeline_execution_status == "success" and report.failed_stage is None
    assert [s.stage for s in report.stages] == list(STAGES) and all(s.status == "ok" for s in report.stages)
    assert (report.records_written, report.records_loaded, report.invalid_records, report.duplicate_identifier_count) == (96, 96, 0, 0)
    assert report.loader_status == "passed" and report.adapter_status == "ok" and report.structural_validation_passed
    assert report.descriptive_analysis_status == "completed" and report.descriptive_analysis_completed
    assert report.mock_only and report.client_name == "mock" and report.provenance_status in ("complete", "partial")
    assert {p.name for p in out.iterdir()} == EXPECTED_FILES
    report.raise_for_failure()


def test_descriptive_analysis_hand_counts(tmp_path, inputs):
    analysis = run(inputs, tmp_path / "run").descriptive_analysis
    assert analysis["row_validation"] == {"ok": True, "n_rows": 96}
    table = analysis["invalid_response_report"]
    assert len(table) == 24 and all(r["n_total"] == 4 and r["n_invalid"] == 0 for r in table)   # 2 models x 2 variants x 6 conditions, 4 scenarios each
    for outcome, rows in analysis["stratified_summaries"].items():
        assert len(rows) == 24 and all(r["n_scenarios_total"] == 4 and r["n_episodes_valid"] == 4 for r in rows), outcome
    assert analysis["contrasts"] == [] and "not a statistical result" in analysis["interpretation"]
    assert any("hypothesis tests" in item for item in analysis["omitted"])


def test_statistical_protocol_is_never_reported_complete(tmp_path, inputs):
    ok = run(inputs, tmp_path / "ok")
    assert ok.statistical_protocol_complete is False and "NOT COMPLETE" in ok.statistical_protocol_status
    used = tmp_path / "used"
    used.mkdir()
    (used / "f.txt").write_text("x", encoding="utf-8")
    failed = run(inputs, used)
    assert failed.statistical_protocol_complete is False and failed.descriptive_analysis_completed is False


def test_optional_contrast_pairs_give_plain_mean_differences_only(tmp_path, inputs):
    report = run(inputs, tmp_path / "run", contrast_pairs=[("C4", "C2")])
    contrasts = report.descriptive_analysis["contrasts"]
    assert len(contrasts) == 12                                    # 3 outcomes x 2 models x 2 variants
    assert all(set(c) == {"model_alias", "prompt_variant", "outcome", "condition_a", "condition_b", "n_scenarios_total", "n_scenarios_used", "n_dropped", "mean_diff"} for c in contrasts)
    assert all(c["n_scenarios_total"] == 4 and c["n_scenarios_used"] == 4 and c["n_dropped"] == 0 for c in contrasts)
    assert not {"p_value", "interval", "effect_size", "label", "significant"} & set().union(*(set(c) for c in contrasts))


def test_bad_contrast_pairs_fail_at_inputs_without_touching_the_directory(tmp_path, inputs):
    out = tmp_path / "run"
    report = run(inputs, out, contrast_pairs=[("C4", "C4")])
    assert report.failed_stage == "inputs" and not out.exists()


# ---------------------------------------------------------------------------
# Run directory, provenance, report file
# ---------------------------------------------------------------------------
def test_a_non_empty_directory_is_refused_before_any_execution(tmp_path, inputs, monkeypatch):
    out = tmp_path / "used"
    out.mkdir()
    (out / "episodes.jsonl").write_text("an earlier record\n", encoding="utf-8")
    before = tree_hashes(out)
    recorder = Recorder()
    monkeypatch.setattr(pipeline_module, "run_experiment", recorder)
    report = run(inputs, out)
    assert report.pipeline_execution_status == "failed" and report.failed_stage == "run_directory"
    assert recorder.calls == 0 and report.report_path is None
    assert tree_hashes(out) == before                             # nothing written, not even a report
    assert "episodes.jsonl" in report.stages[1].detail
    assert [s.status for s in report.stages[2:]] == ["skipped"] * 6
    assert report.records_written is None and report.loader_status == "not_run"


def test_a_second_run_into_the_same_directory_is_refused_and_records_are_unchanged(tmp_path, inputs):
    out = tmp_path / "run"
    first = run(inputs, out)
    before = tree_hashes(out)
    second = run(inputs, out, run_id="mock-002")
    assert first.pipeline_execution_status == "success" and second.failed_stage == "run_directory"
    assert tree_hashes(out) == before                             # no append, no resume, no overwrite


def test_provenance_file_is_created_beside_the_run(tmp_path, inputs):
    out = tmp_path / "run"
    report = run(inputs, out, run_id="prov-run")
    record = json.loads((out / "run_provenance.json").read_text(encoding="utf-8"))
    assert report.provenance_path == str(out / "run_provenance.json")
    assert record["schema"] == "maps-run-provenance" and record["run_id"] == "prov-run"
    assert "not an independent trust anchor" in record["note"]


def test_unavailable_provenance_fields_become_warnings_not_failures(tmp_path, inputs):
    report = run(inputs, tmp_path / "run", provenance_options={"lock_file": "no-such.lock"})
    assert report.pipeline_execution_status == "success" and report.provenance_status == "partial"
    assert "lock_file(missing)" in report.unavailable_provenance_fields
    assert any("provenance is partial" in w for w in report.warnings)
    bad = run(inputs, tmp_path / "other", run_id="r2", provenance_options={"environment": "x"})
    assert bad.failed_stage == "inputs"


def test_pipeline_report_file_matches_the_returned_report(tmp_path, inputs):
    out = tmp_path / "run"
    report = run(inputs, out)
    on_disk = (out / "pipeline_report.json").read_text(encoding="utf-8")
    assert on_disk == report.to_json() and report.report_path == str(out / "pipeline_report.json")
    data = json.loads(on_disk)
    for key in ("run_id", "pipeline_execution_status", "output_dir", "provenance_status", "loader_status", "records_written",
                "records_loaded", "invalid_records", "duplicate_identifier_count", "adapter_status", "descriptive_analysis_status",
                "failed_stage", "warnings", "statistical_protocol_complete"):
        assert key in data
    assert "SYNTHETIC MOCK RUN" in data["notes"][0]


# ---------------------------------------------------------------------------
# Failure handling: fail closed, preserve, report the stage, never analyse
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "damage,field,expected",
    [
        (duplicate_first_line, "duplicate_identifier_count", 1),
        (append_line("{broken json"), "invalid_json_records", 1),
        (schema_invalid_line, "schema_invalid_records", 1),
    ],
    ids=["duplicate", "malformed", "schema-invalid"],
)
def test_damaged_results_stop_the_pipeline_before_analysis(tmp_path, inputs, monkeypatch, damage, field, expected):
    recorder = Recorder(after=damage)
    monkeypatch.setattr(pipeline_module, "run_experiment", recorder)
    analysis_calls = spy_analysis(monkeypatch)
    out = tmp_path / "run"
    report = run(inputs, out)
    assert report.pipeline_execution_status == "failed" and report.failed_stage == "loader_validation"
    assert getattr(report, field) == expected and report.loader_status == "failed"
    assert report.structural_validation_passed is False and report.adapter_status == "not_run"
    assert report.descriptive_analysis_status == "blocked" and report.descriptive_analysis is None
    assert analysis_calls == []                                   # no analysis function was reached
    assert recorder.calls == 1                                    # no automatic retry
    assert (out / "episodes.jsonl").read_text(encoding="utf-8").count("\n") == 97   # the damaged output is preserved
    assert (out / "pipeline_report.json").is_file() and (out / "run_provenance.json").is_file()
    assert [s.status for s in report.stages].count("failed") == 1


def test_expected_inventory_mismatch_fails_the_loader_stage(tmp_path, inputs):
    cfg, scenarios = inputs
    ids = grid_ids(cfg, scenarios)
    ok = run(inputs, tmp_path / "ok", expected_episode_ids=ids)
    assert ok.pipeline_execution_status == "success" and ok.inventory_supplied and (ok.missing_expected_count, ok.unexpected_count) == (0, 0)
    extra = run(inputs, tmp_path / "extra", run_id="r2", expected_episode_ids=[*ids, "ep_not_in_the_run"])
    assert extra.failed_stage == "loader_validation" and extra.missing_expected_count == 1
    short = run(inputs, tmp_path / "short", run_id="r3", expected_episode_ids=ids[:-1])
    assert short.failed_stage == "loader_validation" and short.unexpected_count == 1
    assert run(inputs, tmp_path / "none", run_id="r4").inventory_supplied is False


def test_record_order_is_preserved_and_a_reordered_file_is_caught(tmp_path, inputs, monkeypatch):
    cfg, scenarios = inputs
    out = tmp_path / "ok"
    run(inputs, out)
    written = [json.loads(line)["spec"]["episode_id"] for line in (out / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert written == grid_ids(cfg, scenarios)                    # grid order is the file order
    monkeypatch.setattr(pipeline_module, "run_experiment", Recorder(after=reverse_lines))
    report = run(inputs, tmp_path / "reordered", run_id="r2")
    assert report.failed_stage == "loader_validation" and "order" in report.stages[4].detail


def test_an_execution_failure_is_reported_with_a_safe_description(tmp_path, inputs, monkeypatch):
    recorder = Recorder(before_error=RuntimeError("boom SENTINEL-CONTENT"))
    monkeypatch.setattr(pipeline_module, "run_experiment", recorder)
    out = tmp_path / "run"
    report = run(inputs, out)
    assert report.failed_stage == "mock_execution" and recorder.calls == 1
    assert report.stages[2].detail == "RuntimeError (message withheld)"
    assert "SENTINEL-CONTENT" not in report.to_json() and "SENTINEL-CONTENT" not in (out / "pipeline_report.json").read_text(encoding="utf-8")
    assert (out / ".maps_run_claim").is_file() and report.records_written is None
    with pytest.raises(PipelineFailed, match="mock_execution"):
        report.raise_for_failure()


def test_failure_stage_is_recorded_exactly_once_and_later_stages_are_skipped(tmp_path, inputs, monkeypatch):
    monkeypatch.setattr(pipeline_module, "run_experiment", Recorder(after=append_line("{broken")))
    report = run(inputs, tmp_path / "run")
    assert [(s.stage, s.status) for s in report.stages] == [
        ("inputs", "ok"), ("run_directory", "ok"), ("mock_execution", "ok"), ("provenance", "ok"),
        ("loader_validation", "failed"), ("adapter", "skipped"), ("descriptive_analysis", "skipped"), ("report", "skipped"),
    ]


def test_existing_run_records_are_not_modified_by_loading_or_reporting(tmp_path, inputs):
    out = tmp_path / "run"
    run(inputs, out)
    episodes, manifest = file_hash(out / "episodes.jsonl"), file_hash(out / "manifest.json")
    from maps.adapters.run_loader import load_episode_results

    assert load_episode_results(out).report.safe_for_analysis
    assert (file_hash(out / "episodes.jsonl"), file_hash(out / "manifest.json")) == (episodes, manifest)


# ---------------------------------------------------------------------------
# Mock-only guarantees and report content
# ---------------------------------------------------------------------------
def test_only_a_mock_client_and_a_non_live_configuration_are_accepted(tmp_path, inputs):
    cfg, scenarios = inputs

    class LiveLooking:
        name = "openrouter"

        def complete(self, request):
            raise AssertionError("must never be called")

    out = tmp_path / "live-client"
    report = run_mock_pipeline(cfg, scenarios, out, "r1", client=LiveLooking())
    assert report.failed_stage == "inputs" and not out.exists()
    live_cfg = cfg.model_copy(update={"api": cfg.api.model_copy(update={"enabled": True})})
    out2 = tmp_path / "live-config"
    assert run_mock_pipeline(live_cfg, scenarios, out2, "r2").failed_stage == "inputs" and not out2.exists()
    assert run(inputs, tmp_path / "bad-id", run_id="../escape").failed_stage == "inputs"
    assert not (tmp_path / "bad-id").exists()


def test_a_mock_test_double_named_mock_is_accepted_and_failed_mock_episodes_are_valid_records(tmp_path, inputs):
    from maps.mock_client import MockClient

    report = run(inputs, tmp_path / "run", client=MockClient("malformed"))
    assert report.pipeline_execution_status == "success" and report.records_loaded == 96
    rows = report.descriptive_analysis["invalid_response_report"]
    assert all(r["n_parse_error"] == 4 and r["n_invalid"] == 4 for r in rows)      # failed episodes are data, not load errors


def test_the_adapter_is_called_with_labels_disabled_and_the_report_has_no_label_fields(tmp_path, inputs, monkeypatch):
    seen = []
    original = pipeline_module.episode_results_to_rows
    monkeypatch.setattr(pipeline_module, "episode_results_to_rows", lambda results, **kw: (seen.append(kw), original(results, **kw))[1])
    out = tmp_path / "run"
    report = run(inputs, out)
    assert seen == [{"include_truth_labels": False}]
    for text in (report.to_json(), (out / "pipeline_report.json").read_text(encoding="utf-8")):
        assert "truth" not in text.lower() and "secret" not in text.lower() and "api_key" not in text.lower()


def test_pipeline_modules_import_no_network_or_subprocess_code_and_name_no_live_client():
    for module in (pipeline_module, report_module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        assert not imported & {"socket", "urllib", "http", "requests", "subprocess", "os", "shutil"}, module.__name__
        assert "OpenRouter" not in source and "environ" not in source
