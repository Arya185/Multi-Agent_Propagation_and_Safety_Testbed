"""Hash binding at the integrity gate (v2.3.53): every listed file must still be what the report recorded (offline)."""

from __future__ import annotations

import ast
import hashlib
import inspect
import os
from pathlib import Path

import pytest

import maps.runs.artifact_hashes as ah
import maps.runs.integrity_gate as gate_module
from maps.runs.integrity_gate import IntegrityGateError, Verdict, check_run_integrity, load_eligible_run, load_for_diagnostics

from ri_gate_support import FULL_EXTRAS, REPORT, build_live_run, build_mock_run, edit_report, rebuild_block, read_report
from ri_support import make_result, raw_line
from maps.schemas import LLMResult

SRC = Path(gate_module.__file__).resolve().parents[1]


def verdict(run, **kw):
    r = check_run_integrity(run, **kw)
    return r.verdict, r.reason


def full_run(tmp_path, name="run", **kw):
    return build_mock_run(tmp_path, name=name, extra_files=FULL_EXTRAS, **kw)


def flip_last_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-2] ^= 0x01                                                  # one bit of one byte (the last byte is a newline, keep it)
    path.write_bytes(bytes(data))


# ---- 1-2. accepted / one byte ------------------------------------------------------------------------------------------------
def test_correct_hashes_are_accepted_for_mock_and_live_runs_and_the_digest_is_exposed(tmp_path):
    mock_run, _ = full_run(tmp_path, "mock")
    live_run, _ = build_live_run(tmp_path, name="live")
    for run in (mock_run, live_run):
        result = check_run_integrity(run)
        assert result.verdict is Verdict.ELIGIBLE and result.artifact_digest == read_report(run)["artifacts"]["artifact_digest"]
        assert len(load_eligible_run(run).records) >= 3


def test_a_one_byte_change_to_the_episode_file_is_rejected(tmp_path):
    run, _ = full_run(tmp_path)
    flip_last_byte(run / "episodes.jsonl")
    assert verdict(run) == (Verdict.MISMATCH, "artifact_hash_differs")


def test_an_equal_length_valid_file_replacement_is_rejected(tmp_path):
    run, _ = full_run(tmp_path)
    original = (run / "episodes.jsonl").read_text(encoding="utf-8")
    replacement = original.replace('"confidence": 80', '"confidence": 79')       # different content, identical length, still valid records
    assert len(replacement) == len(original) and replacement != original
    (run / "episodes.jsonl").write_text(replacement, encoding="utf-8")
    assert verdict(run) == (Verdict.MISMATCH, "artifact_hash_differs")


# ---- 7-9. missing / omitted -----------------------------------------------------------------------------------------------------
def test_a_missing_required_or_listed_optional_file_is_rejected(tmp_path):
    run, _ = full_run(tmp_path, "a")
    (run / "episodes.jsonl").unlink()
    assert verdict(run) == (Verdict.MISMATCH, "artifact_missing")
    for i, name in enumerate(("calls.jsonl", "manifest.json", "run_provenance.json")):
        run, _ = full_run(tmp_path, f"opt{i}")
        (run / name).unlink()
        assert verdict(run) == (Verdict.MISMATCH, "artifact_missing"), name
    run, _ = full_run(tmp_path, "claim")
    (run / ".maps_run_claim").unlink()
    assert verdict(run) == (Verdict.MALFORMED, "claim_missing")                  # the claim is checked before the hashes


def test_a_required_artifact_omitted_from_the_report_is_rejected(tmp_path):
    for name in ("episodes.jsonl", ".maps_run_claim"):
        run, _ = full_run(tmp_path, name.strip("."))
        rebuild_block(run, lambda b, name=name: b.update(files=[f for f in b["files"] if f["name"] != name]))
        assert verdict(run) == (Verdict.MALFORMED, "artifacts_malformed"), name


def test_a_listed_optional_artifact_cannot_be_dropped_from_the_report_without_leaving_it_unbound(tmp_path):
    run, _ = full_run(tmp_path)
    rebuild_block(run, lambda b: b.update(files=[f for f in b["files"] if f["name"] != "calls.jsonl"]))
    (run / "calls.jsonl").write_bytes(b"forged\n")
    result = check_run_integrity(run)
    assert result.verdict is Verdict.ELIGIBLE and "calls.jsonl" in result.notes     # an unlisted file is noted, not bound or rejected (HB4)


# ---- 10. unexpected ---------------------------------------------------------------------------------------------------------------------
def test_unexpected_files_are_recorded_as_a_note_and_not_rejected(tmp_path):
    run, _ = full_run(tmp_path)
    for name in ("episodes-copy.jsonl", "notes.txt", ".DS_Store"):
        (run / name).write_bytes(b"x")
    result = check_run_integrity(run)
    assert result.verdict is Verdict.ELIGIBLE and result.notes == (".DS_Store", "episodes-copy.jsonl", "notes.txt")
    assert "summary.json" not in result.notes and "run_events.jsonl" not in result.notes and "pipeline_report.json" not in result.notes
    assert len(load_eligible_run(run).records) == 3


# ---- 11-12. symlink / directory ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["episodes.jsonl", "calls.jsonl", "manifest.json", "run_provenance.json"])
def test_a_symlink_in_place_of_a_listed_file_is_rejected(tmp_path, name):
    run, _ = full_run(tmp_path)
    copy = tmp_path / "copy-of-original"
    copy.write_bytes((run / name).read_bytes())                         # byte-identical content, but behind a link
    (run / name).unlink()
    os.symlink(copy, run / name)
    assert verdict(run) == (Verdict.MISMATCH, "artifact_not_regular_file")


@pytest.mark.parametrize("name", ["episodes.jsonl", "calls.jsonl", "manifest.json", "run_provenance.json"])
def test_a_directory_in_place_of_a_listed_file_is_rejected(tmp_path, name):
    run, _ = full_run(tmp_path)
    (run / name).unlink()
    (run / name).mkdir()
    assert verdict(run) == (Verdict.MISMATCH, "artifact_not_regular_file")


def test_a_symlinked_claim_record_is_rejected(tmp_path):
    run, _ = full_run(tmp_path)
    copy = tmp_path / "claim-copy"
    copy.write_bytes((run / ".maps_run_claim").read_bytes())
    (run / ".maps_run_claim").unlink()
    os.symlink(copy, run / ".maps_run_claim")
    assert check_run_integrity(run).verdict is Verdict.MALFORMED


# ---- 13-18. malformed hash blocks --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["", "ABC", "A" * 64, "g" * 64, "a" * 63, "a" * 65, 5, None, ["a" * 64]])
def test_an_invalid_hash_string_is_malformed(tmp_path, bad):
    run, _ = full_run(tmp_path)
    edit_report(run, lambda r: r["artifacts"]["files"][0].update(sha256=bad))
    assert verdict(run) == (Verdict.MALFORMED, "artifacts_malformed")


@pytest.mark.parametrize("algorithm", ["md5", "sha1", "sha512", "SHA256", "sha-256", ""])
def test_an_unsupported_hash_algorithm_is_malformed(tmp_path, algorithm):
    run, _ = full_run(tmp_path)
    edit_report(run, lambda r: r["artifacts"].update(hash_algorithm=algorithm))
    assert verdict(run) == (Verdict.MALFORMED, "unsupported_hash_algorithm")


def test_a_missing_or_non_object_hash_block_is_malformed(tmp_path):
    run, _ = full_run(tmp_path, "gone")
    edit_report(run, lambda r: r.pop("artifacts"))
    assert verdict(run) == (Verdict.MALFORMED, "artifacts_missing")
    for i, bad in enumerate((None, [], "block", 5, True, {})):
        run, _ = full_run(tmp_path, f"bad{i}")
        edit_report(run, lambda r, bad=bad: r.update(artifacts=bad))
        assert check_run_integrity(run).verdict is Verdict.MALFORMED, bad


def test_duplicate_names_and_path_separators_in_names_are_malformed(tmp_path):
    run, _ = full_run(tmp_path, "dup")
    rebuild_block(run, lambda b: b["files"].append(dict(b["files"][0])))
    assert verdict(run) == (Verdict.MALFORMED, "artifacts_malformed")
    for i, bad in enumerate(("../episodes.jsonl", "sub/episodes.jsonl", "sub\\episodes.jsonl", "/etc/passwd", "..")):
        run, _ = full_run(tmp_path, f"sep{i}")
        rebuild_block(run, lambda b, bad=bad: b["files"][0].update(name=bad))
        assert verdict(run) == (Verdict.MALFORMED, "artifacts_malformed"), bad


def test_an_inconsistent_set_digest_is_rejected(tmp_path):
    run, _ = full_run(tmp_path)
    edit_report(run, lambda r: r["artifacts"].update(artifact_digest="0" * 64))
    assert verdict(run) == (Verdict.MALFORMED, "artifact_digest_inconsistent")
    run, _ = full_run(tmp_path, "b")
    edit_report(run, lambda r: r["artifacts"]["files"][0].update(sha256="1" * 64))        # changed hash, digest left alone
    assert verdict(run) == (Verdict.MALFORMED, "artifact_digest_inconsistent")


def test_wrongly_typed_lengths_are_malformed_and_a_wrong_length_is_a_mismatch(tmp_path):
    for i, bad in enumerate(("5", True, -1, 1.5, None)):
        run, _ = full_run(tmp_path, f"t{i}")
        edit_report(run, lambda r, bad=bad: r["artifacts"]["files"][0].update(bytes=bad))
        assert check_run_integrity(run).verdict is Verdict.MALFORMED, bad
    run, _ = full_run(tmp_path, "len")
    rebuild_block(run, lambda b: b["files"][0].update(bytes=b["files"][0]["bytes"] + 1))
    assert verdict(run) == (Verdict.MISMATCH, "artifact_size_differs")


# ---- 19-20. claim, calls, manifest, provenance ---------------------------------------------------------------------------------------------
def test_modifying_the_claim_record_without_changing_its_run_id_is_rejected(tmp_path):
    run, _ = full_run(tmp_path)
    claim = (run / ".maps_run_claim").read_text(encoding="utf-8")
    (run / ".maps_run_claim").write_text(claim.replace("Created by", "Edited  by"), encoding="utf-8")
    assert verdict(run) == (Verdict.MISMATCH, "artifact_hash_differs")


@pytest.mark.parametrize("name", ["calls.jsonl", "manifest.json", "run_provenance.json"])
def test_modifying_a_listed_optional_artifact_is_rejected(tmp_path, name):
    run, _ = full_run(tmp_path)
    flip_last_byte(run / name) if name != "manifest.json" else (run / name).write_bytes(b'{"manifest": fals3}')
    assert verdict(run)[0] is Verdict.MISMATCH and check_run_integrity(run).reason in ("artifact_hash_differs", "artifact_size_differs")


# ---- 21-22. modification during verification; exact bytes -----------------------------------------------------------------------------------
def test_a_file_that_changes_while_it_is_being_verified_is_a_mismatch(tmp_path, monkeypatch):
    run, _ = full_run(tmp_path)
    real, state = ah.hashlib.sha256, {"done": False}
    episode_size = (run / "episodes.jsonl").stat().st_size         # the hook fires while the EPISODE file is being hashed

    class Changing:
        def __init__(self, initial=b""):
            self._h = real(initial)

        def update(self, chunk):
            if not state["done"] and len(chunk) == episode_size:
                state["done"] = True
                with open(run / "episodes.jsonl", "ab") as handle:
                    handle.write(b"\n")
            self._h.update(chunk)

        def hexdigest(self):
            return self._h.hexdigest()

    monkeypatch.setattr(ah.hashlib, "sha256", Changing)
    assert verdict(run) == (Verdict.MISMATCH, "artifact_changed_during_verification")


def test_the_bytes_that_are_parsed_are_the_bytes_whose_hash_was_checked_and_the_file_is_read_once(tmp_path, monkeypatch):
    run, _ = full_run(tmp_path)
    recorded = next(f for f in read_report(run)["artifacts"]["files"] if f["name"] == "episodes.jsonl")["sha256"]
    reads, parsed = [], []
    real_read, real_parse = ah.read_artifact, gate_module.parse_episode_results
    monkeypatch.setattr(ah, "read_artifact", lambda path, **kw: (reads.append(Path(path).name), real_read(path, **kw))[1])

    def parse_then_tamper(raw, **kw):
        parsed.append(raw)
        (run / "episodes.jsonl").write_bytes(b"TAMPERED AFTER VERIFICATION\n")        # the file changes between verification and parsing
        return real_parse(raw, **kw)

    monkeypatch.setattr(gate_module, "parse_episode_results", parse_then_tamper)
    loaded = load_eligible_run(run)
    assert hashlib.sha256(parsed[0]).hexdigest() == recorded and reads.count("episodes.jsonl") == 1
    assert len(loaded.records) == 3 and [r.spec.episode_id for r in loaded.records] == ["ep_000000000001", "ep_000000000002", "ep_000000000003"]   # verified content, not the tampered file
    assert (run / "episodes.jsonl").read_bytes() == b"TAMPERED AFTER VERIFICATION\n"      # and the gate never repaired or rewrote it


# ---- 23. interrupted / policy stopped -----------------------------------------------------------------------------------------------------------
def test_interrupted_and_policy_stopped_runs_carry_a_hash_snapshot_but_stay_ineligible(tmp_path):
    stopped, _ = build_live_run(tmp_path, n=6, script={3: LLMResult(error="http_401: nope", attempts=1)}, name="stopped")
    with pytest.raises(KeyboardInterrupt):
        build_live_run(tmp_path, n=6, script={4: KeyboardInterrupt()}, name="interrupted")
    for run in (stopped, tmp_path / "interrupted"):
        block = read_report(run)["artifacts"]
        assert ah.validate_artifact_block(block) is None and "episodes.jsonl" in [f["name"] for f in block["files"]]
        assert check_run_integrity(run).verdict is Verdict.INELIGIBLE
        flip_last_byte(run / "episodes.jsonl")                                     # tampering with an ineligible run changes nothing: still refused
        assert check_run_integrity(run).verdict is Verdict.INELIGIBLE
        with pytest.raises(IntegrityGateError):
            load_eligible_run(run)


# ---- 24. legacy -----------------------------------------------------------------------------------------------------------------------------------
def test_a_legacy_version_1_report_is_diagnostic_only(tmp_path):
    run, _ = full_run(tmp_path)
    edit_report(run, lambda r: (r.pop("artifacts"), r.update(version=1)))
    assert verdict(run) == (Verdict.INELIGIBLE, "legacy_report_without_hashes")
    with pytest.raises(IntegrityGateError) as caught:
        load_eligible_run(run)
    assert caught.value.result.reason == "legacy_report_without_hashes"
    diag = load_for_diagnostics(run)
    assert len(diag.loaded.records) == 3 and diag.analysis_admitted is False and diag.gate.verdict is Verdict.INELIGIBLE


def test_a_version_1_report_is_never_silently_treated_as_hash_verified(tmp_path):
    run, _ = full_run(tmp_path)
    edit_report(run, lambda r: r.update(version=1))                                # a v1 report that still carries a hash block is malformed
    assert verdict(run) == (Verdict.MALFORMED, "artifacts_malformed")
    run2, _ = full_run(tmp_path, "b")
    edit_report(run2, lambda r: (r.pop("artifacts"), r.update(version=1, analysis_eligible=False)))
    assert verdict(run2) == (Verdict.INELIGIBLE, "legacy_report_without_hashes")


def test_a_version_2_report_cannot_be_downgraded_to_skip_verification(tmp_path):
    run, _ = full_run(tmp_path)
    flip_last_byte(run / "episodes.jsonl")
    edit_report(run, lambda r: (r.pop("artifacts"), r.update(version=1)))
    assert verdict(run)[0] is Verdict.INELIGIBLE                                     # legacy: refused, never admitted


# ---- 25-26. schema sharing and diagnostics ---------------------------------------------------------------------------------------------------------
def test_mock_and_live_reports_share_one_hash_schema(tmp_path):
    mock_run, _ = full_run(tmp_path, "mock")
    live_run, _ = build_live_run(tmp_path, name="live")
    mock_block, live_block = read_report(mock_run)["artifacts"], read_report(live_run)["artifacts"]
    assert set(mock_block) == set(live_block) and mock_block["hash_algorithm"] == live_block["hash_algorithm"] == "sha256"
    assert mock_block["not_hashed"] == live_block["not_hashed"] and read_report(mock_run)["version"] == read_report(live_run)["version"] == 2


def test_diagnostic_access_of_a_tampered_run_works_and_never_admits_it(tmp_path):
    run, _ = full_run(tmp_path)
    flip_last_byte(run / "episodes.jsonl")
    diag = load_for_diagnostics(run)
    assert diag.analysis_admitted is False and diag.gate.verdict is Verdict.MISMATCH and diag.gate.reason == "artifact_hash_differs"
    assert diag.loaded.records == () or len(diag.loaded.records) <= 3


# ---- 27. static bypass protection ---------------------------------------------------------------------------------------------------------------
def _callers(name: str) -> set[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name for n in ast.walk(tree)):
            found.add(path.relative_to(SRC).as_posix())
    return found


def test_only_the_lifecycle_and_the_gate_call_either_loader_and_the_gate_reaches_the_path_loader_only_for_diagnostics():
    assert _callers("load_episode_results") == {"runs/lifecycle.py", "runs/integrity_gate.py"}
    assert _callers("parse_episode_results") == {"runs/lifecycle.py", "runs/integrity_gate.py"}
    # v2.3.66 (Stage 4D, authorized): policy_source.py reads the one POLICY file (not a run file) through the same bounded,
    # link-refusing reader instead of duplicating it. No other module reads run files through it.
    assert _callers("read_artifact") == {"runs/lifecycle.py", "runs/artifact_hashes.py", "runs/policy_source.py"}
    tree = ast.parse(Path(gate_module.__file__).read_text(encoding="utf-8"))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    def calls_in(fn, name):
        return [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == name]
    for primary in ("_gate", "check_run_integrity", "load_eligible_run"):
        assert not calls_in(functions[primary], "load_episode_results"), primary           # the primary path never uses the path-based loader
    assert len(calls_in(functions["_gate"], "parse_episode_results")) == 1                   # exactly one parse site, fed by verified bytes
    assert len(calls_in(functions["load_for_diagnostics"], "load_episode_results")) == 1      # diagnostics keep the path loader
    assert not calls_in(functions["load_for_diagnostics"], "parse_episode_results")
    assert not any(calls_in(fn, "read_artifact") for fn in functions.values())                  # the gate reads files only through verify_entry


def test_the_gate_reads_the_episode_file_only_through_the_hash_verifying_helper():
    source = Path(gate_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    direct = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in ("read_bytes", "read_text", "open")]
    assert len(direct) == 1                                                                   # only the small report/claim reader opens files itself
    assert "EPISODES_NAME" in source and source.count("verify_entry(") == 1


def test_diagnostic_access_cannot_become_an_admission_path():
    from maps.runs.integrity_gate import DiagnosticRun

    assert DiagnosticRun(loaded=None, gate=None).analysis_admitted is False                    # type: ignore[arg-type]
    assert "analysis_admitted" not in DiagnosticRun.__dataclass_fields__                       # a property, not a settable field
    assert not any(name in inspect.signature(load_for_diagnostics).parameters for name in ("admit", "force", "eligible"))


# ---- 28. deferred (HB9) ----------------------------------------------------------------------------------------------------------------------------
def test_the_externally_anchored_digest_argument_is_deliberately_not_implemented():
    for fn in (check_run_integrity, load_eligible_run, load_for_diagnostics):
        assert "expected_artifact_digest" not in inspect.signature(fn).parameters


# ---- the claim is checked against the report again on the bytes whose hash was verified --------------------------------------------------
def test_the_claim_bytes_that_were_hash_verified_must_still_name_the_run(tmp_path, monkeypatch):
    """Simulates the claim record differing between its first read and the hash-verified read (a race): the first read
    agrees with the report, the verified bytes do not. The run must be refused, not admitted on the first read's say-so."""
    run, _ = full_run(tmp_path)
    claim_path = run / ".maps_run_claim"
    claim_path.write_text(claim_path.read_text(encoding="utf-8").replace('"run_id": "gate-001"', '"run_id": "gate-002"'), encoding="utf-8")
    rebuild_block(run)                                                    # hashes consistent with the changed claim
    real = gate_module._read_json_object

    def first_read_looks_fine(path, *a, **k):
        data, reason = real(path, *a, **k)
        if Path(path).name == ".maps_run_claim" and data is not None:
            data = {**data, "run_id": "gate-001"}                         # the earlier read saw a claim that matched the report
        return data, reason

    monkeypatch.setattr(gate_module, "_read_json_object", first_read_looks_fine)
    assert verdict(run) == (Verdict.MISMATCH, "run_id_differs_from_claim")
