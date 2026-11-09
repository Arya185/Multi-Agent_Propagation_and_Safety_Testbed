"""Gated (primary-analysis) versus diagnostic access to persisted runs (offline, read-only)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import maps.analysis as analysis_package
import maps.runs.integrity_gate as gate_module
from maps.adapters.episode_results import episode_results_to_rows
from maps.adapters.run_loader import load_episode_results
from maps.runs.integrity_gate import DiagnosticRun, IntegrityGateError, Verdict, check_run_integrity, load_eligible_run, load_for_diagnostics
from maps.schemas import LLMResult

from ri_gate_support import REPORT, build_live_run, build_mock_run, edit_report, ids
from ri_support import tree_hashes

SRC = Path(gate_module.__file__).resolve().parents[1]


def one_of_each(tmp_path):
    """One persisted run per verdict (keys are the expected verdicts)."""
    eligible, _ = build_mock_run(tmp_path, name="eligible")
    ineligible, _ = build_mock_run(tmp_path, name="ineligible", fail_after=2)
    missing, _ = build_mock_run(tmp_path, name="missing")
    (missing / REPORT).unlink()
    malformed, _ = build_mock_run(tmp_path, name="malformed")
    (malformed / REPORT).write_bytes(b"{broken")
    mismatch, _ = build_mock_run(tmp_path, name="mismatch")
    edit_report(mismatch, lambda r: r.update(run_id="another-valid-id"))
    return {Verdict.ELIGIBLE: eligible, Verdict.INELIGIBLE: ineligible, Verdict.MISSING: missing, Verdict.MALFORMED: malformed, Verdict.MISMATCH: mismatch}


def test_the_fixture_runs_really_produce_the_five_verdicts(tmp_path):
    for expected, run in one_of_each(tmp_path).items():
        assert check_run_integrity(run).verdict is expected


def test_primary_access_returns_the_records_only_for_an_eligible_run(tmp_path):
    runs = one_of_each(tmp_path)
    loaded = load_eligible_run(runs[Verdict.ELIGIBLE])
    assert len(loaded.records) == 3 and loaded.report.safe_for_analysis
    assert [r.spec.episode_id for r in loaded.records] == ids(3)
    assert [r.spec.episode_id for r in loaded.records] == [r.spec.episode_id for r in load_episode_results(runs[Verdict.ELIGIBLE]).records]


@pytest.mark.parametrize("verdict", [Verdict.INELIGIBLE, Verdict.MISSING, Verdict.MALFORMED, Verdict.MISMATCH])
def test_primary_access_refuses_every_other_verdict_with_a_clear_safe_error(tmp_path, verdict):
    run = one_of_each(tmp_path)[verdict]
    with pytest.raises(IntegrityGateError) as caught:
        load_eligible_run(run)
    assert caught.value.result.verdict is verdict and verdict.value in str(caught.value) and caught.value.result.reason in str(caught.value)
    assert "SYNTHETIC" not in str(caught.value) and str(tmp_path) not in str(caught.value)       # no record content, no paths


def test_a_refused_run_never_falls_back_to_the_raw_loader(tmp_path, monkeypatch):
    path_calls, byte_calls = [], []
    real_path, real_bytes = gate_module.load_episode_results, gate_module.parse_episode_results
    monkeypatch.setattr(gate_module, "load_episode_results", lambda *a, **k: (path_calls.append(1), real_path(*a, **k))[1])
    monkeypatch.setattr(gate_module, "parse_episode_results", lambda *a, **k: (byte_calls.append(1), real_bytes(*a, **k))[1])
    runs = one_of_each(tmp_path)
    for verdict in (Verdict.INELIGIBLE, Verdict.MISSING, Verdict.MALFORMED, Verdict.MISMATCH):
        with pytest.raises(IntegrityGateError):
            load_eligible_run(runs[verdict])
    assert path_calls == [] and byte_calls == []                         # no data were even parsed for a report that is already refused
    load_eligible_run(runs[Verdict.ELIGIBLE])
    assert byte_calls == [1] and path_calls == []                        # the eligible path parses the verified bytes once, and never reopens the file


def test_a_data_mismatch_is_refused_by_the_file_hashes(tmp_path):
    run, _ = build_mock_run(tmp_path)
    lines = (run / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
    (run / "episodes.jsonl").write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityGateError) as caught:
        load_eligible_run(run)
    assert caught.value.result.verdict is Verdict.MISMATCH and caught.value.result.reason == "artifact_size_differs"


def test_expected_inventory_is_enforced_on_the_primary_path(tmp_path):
    run, _ = build_mock_run(tmp_path)
    assert len(load_eligible_run(run, expected_episode_ids=ids(3)).records) == 3
    with pytest.raises(IntegrityGateError) as caught:
        load_eligible_run(run, expected_episode_ids=ids(4))
    assert caught.value.result.reason == "inventory_differs_from_expected"


def test_gated_records_feed_the_existing_analysis_adapter(tmp_path):
    run, _ = build_mock_run(tmp_path)
    rows = episode_results_to_rows(load_eligible_run(run).records)
    assert len(rows) == 3


# ---- diagnostics ------------------------------------------------------------------------------------------------------------
def test_diagnostic_access_reads_partial_and_unreported_runs_without_admitting_them(tmp_path):
    runs = one_of_each(tmp_path)
    for verdict in (Verdict.INELIGIBLE, Verdict.MISSING, Verdict.MALFORMED, Verdict.MISMATCH):
        diag = load_for_diagnostics(runs[verdict])
        assert isinstance(diag, DiagnosticRun) and diag.analysis_admitted is False and diag.purpose == "diagnostic"
        assert diag.gate.verdict is verdict and not diag.gate.eligible
        assert len(diag.loaded.records) >= 2                                      # the partial or unreported output is still readable


def test_a_policy_stopped_and_an_interrupted_run_stay_inspectable_but_are_not_admitted(tmp_path):
    stopped, _ = build_live_run(tmp_path, n=6, script={3: LLMResult(error="http_401: nope", attempts=1)}, name="stopped")
    with pytest.raises(KeyboardInterrupt):
        build_live_run(tmp_path, n=6, script={4: KeyboardInterrupt()}, name="interrupted")
    for run, count in ((stopped, 3), (tmp_path / "interrupted", 3)):
        diag = load_for_diagnostics(run)
        assert len(diag.loaded.records) == count and diag.analysis_admitted is False and diag.gate.verdict is Verdict.INELIGIBLE
        with pytest.raises(IntegrityGateError):
            load_eligible_run(run)


def test_even_an_eligible_run_read_for_diagnostics_is_not_marked_as_admitted(tmp_path):
    run, _ = build_mock_run(tmp_path)
    diag = load_for_diagnostics(run)
    assert diag.gate.verdict is Verdict.ELIGIBLE and diag.analysis_admitted is False       # admission only comes from load_eligible_run
    with pytest.raises(Exception):
        diag.purpose = "analysis"                                                           # type: ignore[misc]


def test_a_run_directory_that_does_not_exist_gives_an_empty_diagnostic_read(tmp_path):
    diag = load_for_diagnostics(tmp_path / "nothing-here")
    assert diag.gate.verdict is Verdict.MISSING and diag.loaded.records == () and diag.analysis_admitted is False


def test_neither_access_path_modifies_the_run_data(tmp_path):
    runs = one_of_each(tmp_path)
    before = {v: tree_hashes(run) for v, run in runs.items() if run.exists()}
    for verdict, run in runs.items():
        check_run_integrity(run)
        load_for_diagnostics(run)
        try:
            load_eligible_run(run)
        except IntegrityGateError:
            pass
    assert {v: tree_hashes(run) for v, run in runs.items()} == before


# ---- structure of the code base --------------------------------------------------------------------------------------------------
def test_only_the_lifecycle_and_the_gate_call_the_raw_loader_inside_src():
    callers = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "load_episode_results" for n in ast.walk(tree)):
            callers.add(path.relative_to(SRC).as_posix())
    assert callers == {"runs/lifecycle.py", "runs/integrity_gate.py"}             # a new unguarded reader of persisted runs fails here


def test_no_analysis_module_reads_a_run_directory():
    for path in Path(analysis_package.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "") for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not calls & {"open", "read_text", "read_bytes", "iterdir", "glob", "rglob", "load_episode_results"}, path.name


def test_the_gate_is_read_only_and_has_no_network_process_hash_or_dynamic_import_code():
    tree = ast.parse(Path(gate_module.__file__).read_text(encoding="utf-8"))
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not attributes & {"write_text", "write_bytes", "unlink", "rename", "replace", "mkdir", "rmdir", "touch", "chmod", "symlink_to", "truncate", "write"}
    assert not calls & {"open", "exec", "eval", "__import__"}
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not {i.split(".")[0] for i in imported} & {"os", "shutil", "subprocess", "socket", "urllib", "http", "requests", "hashlib", "importlib", "dotenv"}
    assert {i for i in imported if i.startswith("maps")} == {
        "maps.adapters.run_loader", "maps.runs.artifact_hashes", "maps.runs.guard", "maps.runs.ids", "maps.runs.integrity_report"}


def test_the_mock_pipeline_and_the_cli_do_not_use_the_gate():
    for rel in ("pipeline/mock_pipeline.py", "experiments/receiver.py", "runs/lifecycle.py", "runs/executor.py", "runs/live_executor.py"):
        assert "integrity_gate" not in (SRC / rel).read_text(encoding="utf-8"), rel
