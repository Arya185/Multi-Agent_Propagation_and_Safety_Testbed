"""Hash binding in the lifecycle (v2.3.53): the report's artifact block describes the exact final bytes (offline)."""

from __future__ import annotations

import hashlib
import json
import os
import socket
from pathlib import Path

import pytest

import maps.runs.artifact_hashes as ah
import maps.runs.lifecycle as lifecycle_module
from maps.runs.executor import execute_mock_run
from maps.runs.integrity_report import REPORT_VERSION, REPORT_VERSION_HASHED

from le_bridge import live_report_keys   # imported before any socket patch is applied (requests/ssl need the real class)
from re_support import MOCK, Runner, cfg_double, make_repo, provenance_options

CLOCK = lambda: "2026-01-01T00:00:00Z"  # noqa: E731


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def go(tmp_path, runner, name="run"):
    out = tmp_path / name
    outcome = execute_mock_run(run_fn=runner, cfg=cfg_double(), scenarios=[], client=MOCK, run_dir=out, run_id="h-1",
                               repo_root=make_repo(tmp_path), provenance_options=provenance_options(), clock=CLOCK)
    return out, outcome


class FullRunner(Runner):
    """Also writes the optional artifacts and the legacy summaries, as the real runner does."""

    def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=None):
        results = super().__call__(cfg, scenarios, client, out_dir, secrets, repo_root)
        out = Path(out_dir)
        (out / "calls.jsonl").write_text('{"call": 1}\n', encoding="utf-8")
        (out / "manifest.json").write_text('{"manifest": true}', encoding="utf-8")
        (out / "summary.json").write_text("{}", encoding="utf-8")
        (out / "contrast_gaps.json").write_text("[]", encoding="utf-8")
        return results


def test_every_report_is_schema_version_2_with_a_hash_block(tmp_path):
    out, outcome = go(tmp_path, Runner(3))
    report = json.loads((out / "run_integrity.json").read_text(encoding="utf-8"))
    assert REPORT_VERSION == 1 and REPORT_VERSION_HASHED == 2 and report["version"] == 2 and report["schema"] == "maps-run-integrity"
    assert ah.validate_artifact_block(report["artifacts"]) is None and outcome.report.artifacts == report["artifacts"]


def test_the_listed_hashes_equal_independent_hashes_of_the_files_on_disk(tmp_path):
    out, outcome = go(tmp_path, FullRunner(3))
    report = json.loads((out / "run_integrity.json").read_text(encoding="utf-8"))
    files = {f["name"]: f for f in report["artifacts"]["files"]}
    assert set(files) == {"episodes.jsonl", ".maps_run_claim", "calls.jsonl", "manifest.json", "run_provenance.json"}
    for name, entry in files.items():
        assert entry["sha256"] == sha(out / name) and entry["bytes"] == (out / name).stat().st_size, name
        assert entry["required"] == (name in ("episodes.jsonl", ".maps_run_claim"))
    assert report["artifacts"]["artifact_digest"] == ah.artifact_set_digest(report["artifacts"]["files"])
    listed = set(files)
    assert not listed & {"run_events.jsonl", "run_integrity.json", "summary.json", "contrast_gaps.json"}        # present on disk, deliberately unhashed
    assert {"summary.json", "contrast_gaps.json", "run_events.jsonl"} <= {p.name for p in out.iterdir()}


def test_the_episode_file_is_read_exactly_once_and_the_hash_covers_the_bytes_that_were_parsed(tmp_path, monkeypatch):
    reads, parsed = [], []
    real_read = ah.read_artifact
    counting = lambda path, **kw: (reads.append(Path(path).name), real_read(path, **kw))[1]  # noqa: E731
    monkeypatch.setattr(ah, "read_artifact", counting)
    monkeypatch.setattr(lifecycle_module, "read_artifact", counting)
    real_parse = lifecycle_module.parse_episode_results

    def parse_then_tamper(raw, **kw):
        parsed.append(raw)
        result = real_parse(raw, **kw)
        (tmp_path / "run" / "episodes.jsonl").write_bytes(b"TAMPERED AFTER VALIDATION\n")          # changes between validation and the report
        return result

    monkeypatch.setattr(lifecycle_module, "parse_episode_results", parse_then_tamper)
    out, outcome = go(tmp_path, Runner(3))
    entry = next(f for f in outcome.report.artifacts["files"] if f["name"] == "episodes.jsonl")
    assert reads.count("episodes.jsonl") == 1                                                      # never re-read for the report
    assert entry["sha256"] == hashlib.sha256(parsed[0]).hexdigest() != sha(out / "episodes.jsonl")  # it describes the validated bytes, not the later file
    assert entry["bytes"] == len(parsed[0])


def test_a_failed_run_still_records_a_hash_snapshot_of_what_exists_and_stays_ineligible(tmp_path):
    out, outcome = go(tmp_path, Runner(3, raise_after=(2, RuntimeError("boom"))))
    assert outcome.failed_stage == "runner" and not outcome.analysis_eligible
    names = [f["name"] for f in outcome.report.artifacts["files"]]
    assert names == ["episodes.jsonl", ".maps_run_claim", "run_provenance.json"]
    entry = next(f for f in outcome.report.artifacts["files"] if f["name"] == "episodes.jsonl")
    assert entry["sha256"] == sha(out / "episodes.jsonl")


def test_a_run_that_produced_no_episode_file_lists_no_episode_entry(tmp_path):
    out, outcome = go(tmp_path, Runner(3, write=False))
    assert [f["name"] for f in outcome.report.artifacts["files"]] == [".maps_run_claim", "run_provenance.json"] and not outcome.analysis_eligible


def test_an_optional_file_that_cannot_be_hashed_makes_the_run_ineligible_instead_of_being_skipped(tmp_path):
    class LinkingRunner(Runner):
        def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=None):
            results = super().__call__(cfg, scenarios, client, out_dir, secrets, repo_root)
            os.symlink(Path(out_dir) / "episodes.jsonl", Path(out_dir) / "calls.jsonl")
            return results

    out, outcome = go(tmp_path, LinkingRunner(3))
    assert (outcome.status, outcome.failed_stage) == ("failed", "artifact_hashing") and not outcome.analysis_eligible
    assert outcome.report.artifacts["errors"] == [{"name": "calls.jsonl", "reason": "artifact_not_regular_file"}]
    assert "calls.jsonl" not in [f["name"] for f in outcome.report.artifacts["files"]]
    assert json.loads((out / "run_integrity.json").read_text(encoding="utf-8"))["failure_stage"] == "artifact_hashing"


def test_an_existing_failure_stage_is_not_replaced_by_a_hashing_failure(tmp_path):
    class LinkingRunner(Runner):
        def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=None):
            results = super().__call__(cfg, scenarios, client, out_dir, secrets, repo_root)
            os.symlink(Path(out_dir) / "episodes.jsonl", Path(out_dir) / "manifest.json")
            return results

    out, outcome = go(tmp_path, LinkingRunner(3, after=lambda path, repo: path.write_text(path.read_text(encoding="utf-8") + "{broken\n", encoding="utf-8")))
    assert outcome.failed_stage == "structural_validation"                 # the first failure stays primary
    assert outcome.report.artifacts["errors"][0]["name"] == "manifest.json"


def test_the_hash_block_survives_a_report_write_failure_fallback(tmp_path):
    out, outcome = go(tmp_path, Runner(3, after=lambda path, repo: (path.parent / "run_integrity.json").write_text("occupied\n", encoding="utf-8")))
    assert outcome.failed_stage == "report" and outcome.report.artifacts is not None and outcome.report.version == 2


def test_hashing_never_modifies_the_run_files(tmp_path):
    out, outcome = go(tmp_path, FullRunner(3))
    hashes = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name not in ("run_integrity.json", "run_events.jsonl")}
    ah.build_artifact_block(out)
    assert {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name not in ("run_integrity.json", "run_events.jsonl")} == hashes


def test_mock_and_live_reports_share_one_hash_schema(tmp_path):
    out, outcome = go(tmp_path, FullRunner(3))
    mock_keys = set(outcome.report.artifacts)
    (tmp_path / "live-case").mkdir()
    assert live_report_keys(tmp_path / "live-case") == mock_keys
