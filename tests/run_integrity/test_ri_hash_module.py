"""The artifact-hash module on its own (temporary files only; offline)."""

from __future__ import annotations

import ast
import copy
import hashlib
import os
from pathlib import Path

import pytest

import maps.runs.artifact_hashes as ah
from maps.runs.artifact_hashes import (
    ALGORITHM, ARTIFACT_REASONS, DIGEST_FORMAT, HASHED_ARTIFACTS, NOT_HASHED, ArtifactError, artifact_set_digest, build_artifact_block,
    list_unlisted, missing_required, read_artifact, validate_artifact_block, verify_entry,
)


def make_run(tmp_path: Path, **files: bytes) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    defaults = {"episodes.jsonl": b'{"a": 1}\n{"a": 2}\n', ".maps_run_claim": b'{"run_id": "r1"}\n'}
    for name, data in {**defaults, **files}.items():
        (run / name).write_bytes(data)
    return run


def hex_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- allow-list ---------------------------------------------------------------------------------------------
def test_the_allow_list_and_exclusions_are_exactly_the_approved_ones():
    assert dict(HASHED_ARTIFACTS) == {"episodes.jsonl": True, ".maps_run_claim": True, "calls.jsonl": False, "manifest.json": False, "run_provenance.json": False}
    assert set(NOT_HASHED) == {"run_events.jsonl", "run_integrity.json", "summary.json", "contrast_gaps.json", "pipeline_report.json"}
    assert not {n for n, _ in HASHED_ARTIFACTS} & set(NOT_HASHED) and ALGORITHM == "sha256"


# ---- reading and hashing --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("data", [b"", b"x", b"line\n" * 10, bytes(range(256)), "héllo wörld\n".encode()], ids=["empty", "one", "lines", "binary", "unicode"])
def test_the_hash_and_size_are_those_of_the_exact_bytes_read(tmp_path, data):
    path = tmp_path / "f"
    path.write_bytes(data)
    read = read_artifact(path, keep_bytes=True)
    assert (read.size, read.sha256, read.data) == (len(data), hex_of(data), data)
    assert read_artifact(path).data is None


def test_multi_chunk_files_hash_correctly(tmp_path):
    data = os.urandom(int(ah.CHUNK_BYTES * 2.5))
    path = tmp_path / "big"
    path.write_bytes(data)
    assert read_artifact(path).sha256 == hex_of(data) and read_artifact(path, keep_bytes=True).data == data


def test_a_missing_file_a_directory_a_symlink_and_a_special_file_are_refused(tmp_path):
    with pytest.raises(ArtifactError) as missing:
        read_artifact(tmp_path / "nope")
    assert missing.value.reason == "artifact_missing"
    (tmp_path / "d").mkdir()
    real = tmp_path / "real"
    real.write_bytes(b"x")
    os.symlink(real, tmp_path / "link")
    os.symlink(tmp_path / "d", tmp_path / "dirlink")
    os.symlink(tmp_path / "gone", tmp_path / "dangling")
    for name in ("d", "link", "dirlink", "dangling"):
        with pytest.raises(ArtifactError) as caught:
            read_artifact(tmp_path / name)
        assert caught.value.reason == "artifact_not_regular_file", name
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ArtifactError) as caught:
        read_artifact(fifo)
    assert caught.value.reason == "artifact_not_regular_file"


def test_an_oversized_file_is_refused_without_being_read_into_memory(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(b"x" * 100)
    with pytest.raises(ArtifactError) as caught:
        read_artifact(path, max_bytes=99)
    assert caught.value.reason == "artifact_too_large"
    assert read_artifact(path, max_bytes=100).size == 100


def test_an_unreadable_file_is_refused(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(b"secret-ish")
    path.chmod(0)
    try:
        try:
            path.read_bytes()
            pytest.skip("permissions are not enforced for this user")
        except OSError:
            pass
        with pytest.raises(ArtifactError) as caught:
            read_artifact(path)
        assert caught.value.reason == "artifact_unreadable"
    finally:
        path.chmod(0o644)


def test_a_file_that_changes_while_it_is_read_is_detected(tmp_path, monkeypatch):
    path = tmp_path / "f"
    path.write_bytes(b"original\n")
    real, calls = ah.hashlib.sha256, []

    class Changing:
        def __init__(self):
            self._h = real()

        def update(self, chunk):
            if not calls:
                calls.append(1)
                with open(path, "ab") as handle:                       # the file is modified mid-verification
                    handle.write(b"tampered\n")
            self._h.update(chunk)

        def hexdigest(self):
            return self._h.hexdigest()

    monkeypatch.setattr(ah.hashlib, "sha256", Changing)
    with pytest.raises(ArtifactError) as caught:
        read_artifact(path)
    assert caught.value.reason == "artifact_changed_during_verification"


def test_errors_carry_a_fixed_message_and_never_file_content(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(b"SENTINEL-CONTENT")
    with pytest.raises(ArtifactError) as caught:
        read_artifact(path, max_bytes=3)
    assert "SENTINEL" not in str(caught.value) and str(caught.value) == ARTIFACT_REASONS["artifact_too_large"]


# ---- the set digest -------------------------------------------------------------------------------------------------------
def test_the_set_digest_follows_the_documented_format_independently(tmp_path):
    files = [{"name": "b.json", "bytes": 3, "sha256": "b" * 64, "required": False}, {"name": "a.json", "bytes": 1, "sha256": "a" * 64, "required": False}]
    expected = hashlib.sha256(f"a.json:1:{'a' * 64}\nb.json:3:{'b' * 64}".encode()).hexdigest()
    assert artifact_set_digest(files) == artifact_set_digest(list(reversed(files))) == expected
    assert "LF" in DIGEST_FORMAT


def test_changing_any_listed_value_changes_the_set_digest():
    files = [{"name": "episodes.jsonl", "bytes": 3, "sha256": "a" * 64, "required": True}]
    base = artifact_set_digest(files)
    for change in ({"bytes": 4}, {"sha256": "b" * 64}, {"name": "calls.jsonl"}):
        assert artifact_set_digest([{**files[0], **change}]) != base


# ---- building the block ---------------------------------------------------------------------------------------------------------
def test_the_block_lists_the_present_allow_listed_files_in_allow_list_order(tmp_path):
    run = make_run(tmp_path, **{"calls.jsonl": b"c\n", "manifest.json": b"{}", "summary.json": b"{}", "run_events.jsonl": b"e\n", "stray.txt": b"s"})
    block, errors = build_artifact_block(run)
    assert errors == [] and [f["name"] for f in block["files"]] == ["episodes.jsonl", ".maps_run_claim", "calls.jsonl", "manifest.json"]
    assert validate_artifact_block(block) is None and block["hash_algorithm"] == "sha256" and block["not_hashed"] == list(NOT_HASHED)
    for entry in block["files"]:
        data = (run / entry["name"]).read_bytes()
        assert (entry["bytes"], entry["sha256"], entry["required"]) == (len(data), hex_of(data), entry["name"] in ("episodes.jsonl", ".maps_run_claim"))
    assert "errors" not in block and block["artifact_digest"] == artifact_set_digest(block["files"])


def test_a_missing_file_is_not_listed_and_an_unhashable_one_is_reported_never_skipped(tmp_path):
    run = make_run(tmp_path)
    (run / "manifest.json").mkdir()
    os.symlink(run / "episodes.jsonl", run / "calls.jsonl")
    block, errors = build_artifact_block(run)
    assert {e["name"]: e["reason"] for e in errors} == {"manifest.json": "artifact_not_regular_file", "calls.jsonl": "artifact_not_regular_file"}
    assert block["errors"] == errors and "calls.jsonl" not in [f["name"] for f in block["files"]]
    assert validate_artifact_block(block) is None


def test_precomputed_reads_are_used_instead_of_rereading(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    reads = []
    real = ah.read_artifact
    monkeypatch.setattr(ah, "read_artifact", lambda path, **kw: (reads.append(Path(path).name), real(path, **kw))[1])
    precomputed = {"episodes.jsonl": ah.FileRead("episodes.jsonl", 5, "c" * 64)}
    block, _ = build_artifact_block(run, precomputed=precomputed)
    assert "episodes.jsonl" not in reads and ".maps_run_claim" in reads        # the precomputed file is never re-read; the others are looked up
    assert block["files"][0] == {"name": "episodes.jsonl", "bytes": 5, "sha256": "c" * 64, "required": True}


def test_verify_entry_checks_size_then_hash(tmp_path):
    run = make_run(tmp_path)
    data = (run / "episodes.jsonl").read_bytes()
    good = {"name": "episodes.jsonl", "bytes": len(data), "sha256": hex_of(data), "required": True}
    assert verify_entry(run, good, keep_bytes=True).data == data
    for entry, reason in (({**good, "bytes": len(data) + 1}, "artifact_size_differs"), ({**good, "sha256": "0" * 64}, "artifact_hash_differs")):
        with pytest.raises(ArtifactError) as caught:
            verify_entry(run, entry)
        assert caught.value.reason == reason
    (run / "episodes.jsonl").write_bytes(data[:-1] + b"X")                      # one byte changed, same length
    with pytest.raises(ArtifactError) as caught:
        verify_entry(run, good)
    assert caught.value.reason == "artifact_hash_differs"


# ---- validation of a block's format ------------------------------------------------------------------------------------------------------
def good_block(tmp_path):
    return build_artifact_block(make_run(tmp_path))[0]


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda b: b.update(hash_algorithm="md5"), "unsupported_hash_algorithm"),
        (lambda b: b.update(hash_algorithm="SHA256"), "unsupported_hash_algorithm"),
        (lambda b: b.update(hash_algorithm=256), "artifacts_malformed"),
        (lambda b: b.pop("hash_algorithm"), "artifacts_malformed"),
        (lambda b: b.update(files="none"), "artifacts_malformed"),
        (lambda b: b.pop("files"), "artifacts_malformed"),
        (lambda b: b["files"].append(dict(b["files"][0])), "artifacts_malformed"),
        (lambda b: b["files"][0].update(name="../episodes.jsonl"), "artifacts_malformed"),
        (lambda b: b["files"][0].update(name="sub/episodes.jsonl"), "artifacts_malformed"),
        (lambda b: b["files"][0].update(name="evil\\episodes.jsonl"), "artifacts_malformed"),
        (lambda b: b["files"][0].update(name=".."), "artifacts_malformed"),
        (lambda b: b["files"][0].update(name=""), "artifacts_malformed"),
        (lambda b: b["files"][0].update(name="summary.json"), "artifacts_malformed"),
        (lambda b: b["files"][0].update(name="unknown.bin"), "artifacts_malformed"),
        (lambda b: b["files"][0].update(sha256="A" * 64), "artifacts_malformed"),
        (lambda b: b["files"][0].update(sha256="a" * 63), "artifacts_malformed"),
        (lambda b: b["files"][0].update(sha256="g" * 64), "artifacts_malformed"),
        (lambda b: b["files"][0].update(sha256=5), "artifacts_malformed"),
        (lambda b: b["files"][0].update(bytes="5"), "artifacts_malformed"),
        (lambda b: b["files"][0].update(bytes=True), "artifacts_malformed"),
        (lambda b: b["files"][0].update(bytes=-1), "artifacts_malformed"),
        (lambda b: b["files"][0].update(bytes=1.0), "artifacts_malformed"),
        (lambda b: b["files"][0].update(required="yes"), "artifacts_malformed"),
        (lambda b: b["files"][0].update(required=False), "artifacts_malformed"),
        (lambda b: b["files"][0].update(extra=1), "artifacts_malformed"),
        (lambda b: b["files"][0].pop("sha256"), "artifacts_malformed"),
        (lambda b: b.update(artifact_digest="0" * 64), "artifact_digest_inconsistent"),
        (lambda b: b.update(artifact_digest="XYZ"), "artifacts_malformed"),
        (lambda b: b.pop("artifact_digest"), "artifacts_malformed"),
        (lambda b: b["files"][0].update(sha256="1" * 64), "artifact_digest_inconsistent"),
        (lambda b: b.update(digest_format="something else"), "artifacts_malformed"),
        (lambda b: b.update(not_hashed=["run_events.jsonl"]), "artifacts_malformed"),
        (lambda b: b.update(errors="x"), "artifacts_malformed"),
        (lambda b: b.update(errors=[{"name": "x", "reason": "made_up"}]), "artifacts_malformed"),
    ],
)
def test_malformed_blocks_are_rejected_with_a_bounded_reason(tmp_path, mutate, reason):
    block = good_block(tmp_path)
    mutated = copy.deepcopy(block)
    mutate(mutated)
    assert validate_artifact_block(mutated) == reason


@pytest.mark.parametrize("bad", [None, [], "block", 5, True])
def test_a_non_object_block_is_malformed(bad):
    assert validate_artifact_block(bad) == "artifacts_malformed"


def test_required_artifacts_must_be_listed(tmp_path):
    block = good_block(tmp_path)
    assert missing_required(block) == []
    block["files"] = [f for f in block["files"] if f["name"] != "episodes.jsonl"]
    block["artifact_digest"] = artifact_set_digest(block["files"])
    assert validate_artifact_block(block) is None and missing_required(block) == ["episodes.jsonl"]
    block["files"] = []
    assert missing_required(block) == [".maps_run_claim", "episodes.jsonl"]


def test_unlisted_files_are_noted_but_known_unhashed_files_are_not(tmp_path):
    run = make_run(tmp_path, **{"run_events.jsonl": b"e", "run_integrity.json": b"{}", "summary.json": b"{}", "contrast_gaps.json": b"{}", "pipeline_report.json": b"{}", "stray.txt": b"s", ".DS_Store": b"d"})
    block, _ = build_artifact_block(run)
    assert list_unlisted(run, block) == (".DS_Store", "stray.txt")
    assert list_unlisted(tmp_path / "no-such-dir", block) == ()


def test_the_note_list_is_bounded(tmp_path):
    run = make_run(tmp_path)
    for i in range(50):
        (run / f"{'x' * 150}{i:02d}").write_bytes(b"")
    block, _ = build_artifact_block(run)
    notes = list_unlisted(run, block)
    assert len(notes) == ah.MAX_UNLISTED_NOTES and all(len(n) <= 100 for n in notes)


# ---- structure of the module -----------------------------------------------------------------------------------------------------------------
def test_the_module_has_no_network_process_environment_or_dynamic_import_code():
    tree = ast.parse(Path(ah.__file__).read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not {i.split(".")[0] for i in imported} & {"os", "shutil", "subprocess", "socket", "urllib", "http", "requests", "importlib", "dotenv"}
    assert {i for i in imported if i.startswith("maps")} == {"maps.runs.guard"}
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not calls & {"exec", "eval", "__import__"}
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attributes & {"write_text", "write_bytes", "unlink", "rename", "replace", "mkdir", "environ", "getenv"}


@pytest.mark.parametrize("name", ["unknown.bin", "summary.json", "run_events.jsonl", "run_integrity.json", "pipeline_report.json", "contrast_gaps.json"])
def test_an_extra_entry_with_a_name_outside_the_allow_list_is_malformed_even_with_valid_values(tmp_path, name):
    block = good_block(tmp_path)
    block["files"].append({"name": name, "bytes": 1, "sha256": "e" * 64, "required": False})        # well-formed in every other respect
    block["artifact_digest"] = artifact_set_digest(block["files"])
    assert validate_artifact_block(block) == "artifacts_malformed"
