"""Run-directory guard (SYNTHETIC; temporary directories only)."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

import maps.runs.guard as guard_module
from maps.runs.guard import CLAIM_FILENAME, UnsafeRunDirectoryError, check_run_dir, initialize_run_dir

from ri_support import tree_hashes


def test_a_new_directory_is_created_and_claimed(tmp_path):
    target = tmp_path / "runs" / "run-001"          # the parent does not exist yet
    result = initialize_run_dir(target, run_id="run-001")
    assert result == target and target.is_dir()
    assert [p.name for p in target.iterdir()] == [CLAIM_FILENAME]
    assert '"run_id": "run-001"' in (target / CLAIM_FILENAME).read_text(encoding="utf-8")


def test_an_existing_empty_directory_is_allowed(tmp_path):
    target = tmp_path / "empty"
    target.mkdir()
    assert initialize_run_dir(target) == target
    assert (target / CLAIM_FILENAME).is_file()


def test_a_non_empty_directory_is_refused_and_left_untouched(tmp_path):
    target = tmp_path / "used"
    target.mkdir()
    (target / "episodes.jsonl").write_text("existing result\n", encoding="utf-8")
    before = tree_hashes(target)
    with pytest.raises(UnsafeRunDirectoryError) as exc:
        initialize_run_dir(target)
    message = str(exc.value)
    assert "episodes.jsonl" in message and "Choose a new run directory" in message and "never deleted" in message
    assert tree_hashes(target) == before and [p.name for p in target.iterdir()] == ["episodes.jsonl"]


def test_unrelated_and_hidden_files_also_make_a_directory_unsafe(tmp_path):
    target = tmp_path / "notes"
    target.mkdir()
    (target / "notes.txt").write_text("unrelated", encoding="utf-8")
    (target / ".hidden").write_text("x", encoding="utf-8")
    with pytest.raises(UnsafeRunDirectoryError, match="2 entries"):
        initialize_run_dir(target)
    with pytest.raises(UnsafeRunDirectoryError):
        check_run_dir(target)
    assert sorted(p.name for p in target.iterdir()) == [".hidden", "notes.txt"]


def test_repeated_initialization_is_refused(tmp_path):
    target = tmp_path / "once"
    initialize_run_dir(target)
    claim_before = (target / CLAIM_FILENAME).read_bytes()
    with pytest.raises(UnsafeRunDirectoryError, match=CLAIM_FILENAME):
        initialize_run_dir(target)
    assert (target / CLAIM_FILENAME).read_bytes() == claim_before   # the first claim is not overwritten


def test_a_long_listing_is_truncated_in_the_message(tmp_path):
    target = tmp_path / "many"
    target.mkdir()
    for i in range(15):
        (target / f"f{i:02d}.txt").write_text("x", encoding="utf-8")
    with pytest.raises(UnsafeRunDirectoryError) as exc:
        check_run_dir(target)
    assert "15 entries" in str(exc.value) and ", ..." in str(exc.value) and "f14.txt" not in str(exc.value)


def test_check_run_dir_never_writes(tmp_path):
    new = tmp_path / "not-created"
    assert check_run_dir(new) == new and not new.exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert check_run_dir(empty) == empty and list(empty.iterdir()) == []


def test_a_file_path_and_a_symlink_are_refused(tmp_path):
    a_file = tmp_path / "file.txt"
    a_file.write_text("x", encoding="utf-8")
    with pytest.raises(UnsafeRunDirectoryError, match="not a directory"):
        initialize_run_dir(a_file)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(real, link)
    with pytest.raises(UnsafeRunDirectoryError, match="symbolic link"):
        initialize_run_dir(link)
    assert list(real.iterdir()) == []


def test_the_claim_cannot_be_created_twice_even_if_the_pre_check_is_bypassed(tmp_path, monkeypatch):
    target = tmp_path / "raced"
    target.mkdir()
    monkeypatch.setattr(guard_module, "check_run_dir", lambda path: Path(path))   # simulate a stale pre-check
    initialize_run_dir(target)
    with pytest.raises(UnsafeRunDirectoryError):
        initialize_run_dir(target)


def test_the_guard_documents_its_limits_and_uses_no_network_or_subprocess():
    doc = " ".join(guard_module.__doc__.split())
    assert "only protects executions that actually call it" in doc and "does NOT call it" in doc
    tree = ast.parse(Path(guard_module.__file__).read_text(encoding="utf-8"))
    imported = {
        (n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
        for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    assert imported <= {"__future__", "json", "os", "datetime", "pathlib"}
