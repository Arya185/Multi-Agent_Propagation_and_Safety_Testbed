"""Run provenance recorder (SYNTHETIC temporary repositories only; no network, no Git commands)."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

import maps.runs.provenance as prov
from maps.runs.provenance import (
    collect_provenance,
    discover_source_files,
    read_git_commit,
    serialize,
    sha256_file,
    write_provenance,
)

from ri_support import tree_hashes

FIXED_TIME = "2030-01-02T03:04:05Z"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def packages():
    return [("zeta-pkg", "2.0"), ("Alpha_Pkg", "1.5"), ("beta.pkg", "0.1")]


def make_repo(tmp_path: Path, *, with_lock=True, with_git=True) -> Path:
    repo = tmp_path / "repo"
    (repo / "src" / "maps" / "sub").mkdir(parents=True)
    (repo / "src" / "maps" / "a.py").write_text("print('a')\n", encoding="utf-8")
    (repo / "src" / "maps" / "sub" / "b.py").write_text("print('b')\n", encoding="utf-8")
    (repo / "src" / "maps" / "__pycache__").mkdir()
    (repo / "src" / "maps" / "__pycache__" / "skip.py").write_text("x", encoding="utf-8")
    if with_lock:
        (repo / "requirements.lock").write_text("pkg==1.0\n", encoding="utf-8")
    if with_git:
        (repo / ".git" / "refs" / "heads").mkdir(parents=True)
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (repo / ".git" / "refs" / "heads" / "main").write_text(COMMIT + "\n", encoding="utf-8")
    return repo


def collect(repo, **kw):
    kw.setdefault("run_id", "run-001")
    kw.setdefault("created_utc", FIXED_TIME)
    kw.setdefault("package_provider", packages)
    return collect_provenance(repo_root=repo, **kw)


def test_serialization_is_stable_sorted_and_round_trips(tmp_path):
    repo = make_repo(tmp_path)
    first, second = serialize(collect(repo)), serialize(collect(repo))
    assert first == second and first.endswith("\n")
    parsed = json.loads(first)
    assert json.dumps(parsed, sort_keys=True, indent=2, ensure_ascii=False) + "\n" == first
    assert parsed["schema"] == "maps-run-provenance" and parsed["version"] == 1
    assert parsed["created_utc"] == FIXED_TIME and parsed["run_id"] == "run-001"
    # key insertion order does not matter
    shuffled = dict(reversed(list(collect(repo).items())))
    assert serialize(shuffled) == first


def test_source_file_digests_are_generated_and_combined(tmp_path):
    repo = make_repo(tmp_path)
    record = collect(repo)
    sources = record["source_files"]
    expected = {
        "src/maps/a.py": hashlib.sha256(b"print('a')\n").hexdigest(),
        "src/maps/sub/b.py": hashlib.sha256(b"print('b')\n").hexdigest(),
    }
    assert {e["path"]: e["sha256"] for e in sources["files"]} == expected
    assert [e["path"] for e in sources["files"]] == sorted(expected)          # sorted, __pycache__ skipped
    assert all(e["status"] == "ok" for e in sources["files"]) and sources["complete"] is True
    lines = "\n".join(f"{p}:{d}" for p, d in sorted(expected.items()))
    assert sources["combined_sha256"] == hashlib.sha256(lines.encode()).hexdigest()
    assert record["unavailable_fields"] == []
    assert discover_source_files(repo) == sorted(expected)


def test_lock_file_digest(tmp_path):
    repo = make_repo(tmp_path)
    lock = collect(repo)["lock_file"]
    assert lock == {"path": "requirements.lock", "sha256": hashlib.sha256(b"pkg==1.0\n").hexdigest(), "status": "ok"}
    assert sha256_file(repo / "requirements.lock") == lock["sha256"]


def test_a_missing_source_file_is_reported_not_hidden(tmp_path):
    repo = make_repo(tmp_path)
    record = collect(repo, source_files=["src/maps/a.py", "src/maps/gone.py"])
    entries = {e["path"]: e for e in record["source_files"]["files"]}
    assert entries["src/maps/gone.py"] == {"path": "src/maps/gone.py", "sha256": None, "status": "missing"}
    assert record["source_files"]["complete"] is False and record["source_files"]["combined_sha256"] is None
    assert "source_files:src/maps/gone.py(missing)" in record["unavailable_fields"]


def test_a_missing_lock_file_and_unsafe_paths_are_reported(tmp_path):
    repo = make_repo(tmp_path, with_lock=False)
    record = collect(repo, source_files=["src/maps/a.py", "../outside.py", "/etc/hosts"])
    assert record["lock_file"]["status"] == "missing" and record["lock_file"]["sha256"] is None
    assert "lock_file(missing)" in record["unavailable_fields"]
    statuses = {e["path"]: e["status"] for e in record["source_files"]["files"]}
    assert statuses["../outside.py"] == statuses["/etc/hosts"] == "invalid_path"
    assert collect(repo, lock_file=None)["lock_file"]["status"] == "not_requested"
    empty = collect(repo, source_files=[])
    assert empty["source_files"]["complete"] is False and "source_files:none_supplied" in empty["unavailable_fields"]


def test_unavailable_or_partial_package_metadata_is_reported(tmp_path):
    repo = make_repo(tmp_path)

    def broken():
        raise RuntimeError("metadata backend failed")

    down = collect(repo, package_provider=broken)["packages"]
    assert down == {"status": "unavailable", "reason": "RuntimeError", "n_unreadable": 0, "items": []}
    partial = collect(repo, package_provider=lambda: [("ok-pkg", "1.0"), (None, "9.9"), ("no-version", None)])
    assert partial["packages"]["status"] == "partial" and partial["packages"]["n_unreadable"] == 1
    assert partial["packages"]["items"] == [{"name": "no-version", "version": None}, {"name": "ok-pkg", "version": "1.0"}]
    assert "packages(partial)" in partial["unavailable_fields"]
    ordered = collect(repo)["packages"]
    assert ordered["status"] == "ok" and [i["name"] for i in ordered["items"]] == ["Alpha_Pkg", "beta.pkg", "zeta-pkg"]


def test_environment_variables_and_secrets_are_never_recorded(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "SYN-SECRET-VALUE-1")
    monkeypatch.setenv("MAPS_FAKE_TOKEN", "SYN-SECRET-VALUE-2")
    text = serialize(collect(repo))
    assert "SYN-SECRET-VALUE" not in text and "OPENROUTER" not in text and "MAPS_FAKE_TOKEN" not in text
    tree = ast.parse(Path(prov.__file__).read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"environ", "getenv", "environb"}          # the recorder never touches the environment


_ACTIVE = False
_OPENED: list[str] = []


def _audit(event, args):
    """Inert unless a test switches it on: records every path opened while a collection runs."""
    if _ACTIVE and event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        _OPENED.append(os.fsdecode(args[0]))


sys.addaudithook(_audit)


def test_git_commit_is_read_from_head_without_git_config_or_remotes(tmp_path):
    global _ACTIVE
    repo = make_repo(tmp_path)
    (repo / ".git" / "config").write_text('[remote "origin"]\n  url = https://example.invalid/secret.git\n', encoding="utf-8")
    _OPENED.clear()
    _ACTIVE = True
    try:
        record = collect(repo)
    finally:
        _ACTIVE = False
    assert record["git"] == {"commit": COMMIT, "ref": "refs/heads/main", "status": "ok", "dirty": "unknown"}
    git_paths = [p for p in _OPENED if "/.git/" in p]
    assert sorted(Path(p).name for p in git_paths) == ["HEAD", "main"]      # only HEAD and the loose ref were opened
    assert "example.invalid" not in serialize(record)


def test_git_unavailable_cases_are_explicit(tmp_path):
    no_git = make_repo(tmp_path / "a", with_git=False)
    assert read_git_commit(no_git)["status"] == "unavailable" and "git.commit" in collect(no_git)["unavailable_fields"]
    detached = make_repo(tmp_path / "b")
    (detached / ".git" / "HEAD").write_text(COMMIT + "\n", encoding="utf-8")
    assert read_git_commit(detached) == {"commit": COMMIT, "ref": "detached", "status": "ok", "dirty": "unknown"}
    packed = make_repo(tmp_path / "c")
    (packed / ".git" / "refs" / "heads" / "main").unlink()
    result = read_git_commit(packed)
    assert result["status"] == "unavailable" and "packed refs are deliberately not read" in result["reason"]
    odd = make_repo(tmp_path / "d")
    (odd / ".git" / "HEAD").write_text("ref: refs/remotes/origin/main\n", encoding="utf-8")
    assert read_git_commit(odd)["status"] == "unavailable"
    assert collect(no_git, include_git=False)["git"]["status"] == "not_requested"


def test_write_provenance_is_beside_the_run_exclusive_and_touches_nothing_else(tmp_path):
    repo = make_repo(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "episodes.jsonl").write_text("existing\n", encoding="utf-8")
    before = tree_hashes(run_dir)
    record = collect(repo)
    target = write_provenance(run_dir, record)
    assert target == run_dir / "run_provenance.json" and target.read_text(encoding="utf-8") == serialize(record)
    after = tree_hashes(run_dir)
    assert {k: v for k, v in after.items() if k != "run_provenance.json"} == before
    with pytest.raises(FileExistsError):
        write_provenance(run_dir, record)
    assert target.read_text(encoding="utf-8") == serialize(record)
    with pytest.raises(NotADirectoryError):
        write_provenance(tmp_path / "missing", record)
    with pytest.raises(ValueError):
        write_provenance(run_dir, record, filename="../escape.json")


def test_invalid_run_ids_are_rejected_and_the_record_states_its_limits(tmp_path):
    repo = make_repo(tmp_path)
    for bad in ("", "has space", "../x", "a/b", "x" * 129, None):
        with pytest.raises(ValueError):
            collect_provenance(run_id=bad, repo_root=repo)
    record = collect(repo)
    assert "not an independent trust anchor" in record["note"]
    assert record["python"]["version"] and record["platform"]["system"]


def test_the_recorder_uses_no_network_or_subprocess_modules():
    tree = ast.parse(Path(prov.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert not imported & {"socket", "urllib", "http", "requests", "subprocess", "os"}
