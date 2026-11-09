"""SYNTHETIC tests of the preventive write guard (tools/write_guard.py) and its launcher.

All blocked and permitted writes below happen in pytest temporary directories that are protected
only for the duration of one test. The few checks against the real golden and audit directories use
operations that are harmless even if the guard failed (append-open without writing, renaming or
creating something that cannot exist). The guard is a Python audit hook, not filesystem security.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import types

import pytest

from synthetic_support import AUDIT_DIR, GOLDEN_DIR, GOLDEN_FILES, TOOLS_DIR, golden_write_guard  # noqa: F401


def _guard_module():
    module = sys.modules.get("write_guard")
    if module is None:
        spec = importlib.util.spec_from_file_location("write_guard", TOOLS_DIR / "write_guard.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["write_guard"] = module
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard(tmp_path):
    wg = _guard_module()
    g = wg.GUARD
    g.install()
    protected, other = tmp_path / "protected", tmp_path / "other"
    protected.mkdir()
    other.mkdir()
    (protected / "existing.txt").write_text("original", encoding="utf-8")
    (other / "a.txt").write_text("a", encoding="utf-8")
    saved = (g.enabled, g.block_processes)
    g.enabled = True
    g.protect(protected)
    yield types.SimpleNamespace(wg=wg, g=g, protected=protected, other=other, tmp=tmp_path)
    g.unprotect(protected)
    g.enabled, g.block_processes = saved


def _unchanged(guard):
    assert (guard.protected / "existing.txt").read_text(encoding="utf-8") == "original"
    assert sorted(p.name for p in guard.protected.iterdir()) == ["existing.txt"]


# ---------------------------------------------------------------------------
# Blocked writes (before the operation happens) and permitted writes
# ---------------------------------------------------------------------------
def test_open_for_write_create_append_and_update_is_blocked(guard):
    wb = guard.wg.WriteBlocked
    target = guard.protected / "new.txt"
    for action in (
        lambda: target.write_text("x"),
        lambda: target.write_bytes(b"x"),
        lambda: open(guard.protected / "existing.txt", "w"),
        lambda: open(guard.protected / "existing.txt", "a"),
        lambda: open(guard.protected / "existing.txt", "r+"),
        lambda: open(target, "x"),
        lambda: os.open(target, os.O_WRONLY | os.O_CREAT),
    ):
        with pytest.raises(wb):
            action()
    _unchanged(guard)


def test_reads_of_protected_files_are_allowed(guard):
    assert (guard.protected / "existing.txt").read_text(encoding="utf-8") == "original"
    with open(guard.protected / "existing.txt", "rb") as handle:
        assert handle.read() == b"original"
    assert [p.name for p in guard.protected.iterdir()] == ["existing.txt"]


def test_writes_outside_the_protected_directory_are_permitted(guard):
    (guard.other / "b.txt").write_text("b", encoding="utf-8")
    shutil.copyfile(guard.protected / "existing.txt", guard.other / "copy.txt")  # protected file is only read
    os.mkdir(guard.other / "dir")
    os.rename(guard.other / "a.txt", guard.other / "renamed.txt")
    os.makedirs(guard.other / "x" / "y")
    shutil.rmtree(guard.other / "x")
    os.remove(guard.other / "b.txt")
    assert sorted(p.name for p in guard.other.iterdir()) == ["copy.txt", "dir", "renamed.txt"]
    _unchanged(guard)


def test_mutating_operations_are_blocked(guard):
    wb = guard.wg.WriteBlocked
    p, o = guard.protected, guard.other
    operations = {
        "rename out": lambda: os.rename(p / "existing.txt", o / "moved.txt"),
        "rename in": lambda: os.rename(o / "a.txt", p / "in.txt"),
        "replace": lambda: os.replace(o / "a.txt", p / "existing.txt"),
        "remove": lambda: os.remove(p / "existing.txt"),
        "unlink": lambda: (p / "existing.txt").unlink(),
        "mkdir": lambda: os.mkdir(p / "d"),
        "makedirs": lambda: os.makedirs(p / "x" / "y"),
        "chmod": lambda: os.chmod(p / "existing.txt", 0o600),
        "utime": lambda: os.utime(p / "existing.txt", (1, 1)),
        "truncate": lambda: os.truncate(p / "existing.txt", 0),
        "link from": lambda: os.link(p / "existing.txt", o / "hard.txt"),
        "link into": lambda: os.link(o / "a.txt", p / "hard.txt"),
        "symlink into": lambda: os.symlink("target", p / "sym"),
        "copyfile into": lambda: shutil.copyfile(o / "a.txt", p / "copy.txt"),
        "move out": lambda: shutil.move(str(p / "existing.txt"), str(o / "m.txt")),
        "move in": lambda: shutil.move(str(o / "a.txt"), str(p / "m.txt")),
        "copytree into": lambda: shutil.copytree(o, p / "tree"),
        "rmtree": lambda: shutil.rmtree(p),
    }
    for name, action in operations.items():
        with pytest.raises(wb):
            action()
    _unchanged(guard)
    assert (guard.other / "a.txt").read_text(encoding="utf-8") == "a"
    assert len(guard.g.violations) >= len(operations)


def _helper_that_writes(path):
    path.write_text("via helper", encoding="utf-8")


def test_helper_mediated_writes_are_blocked(guard):
    with pytest.raises(guard.wg.WriteBlocked):
        _helper_that_writes(guard.protected / "helper.txt")
    _helper_that_writes(guard.other / "helper.txt")  # the same helper is fine elsewhere
    _unchanged(guard)


def test_relative_and_dotdot_paths_are_canonicalised(guard, monkeypatch):
    wb = guard.wg.WriteBlocked
    monkeypatch.chdir(guard.tmp)
    with pytest.raises(wb):
        open("protected/rel.txt", "w")
    with pytest.raises(wb):
        open("other/../protected/dotdot.txt", "w")
    monkeypatch.chdir(guard.protected)
    with pytest.raises(wb):
        open("here.txt", "w")
    with pytest.raises(wb):
        open("../protected/./again.txt", "w")
    monkeypatch.chdir(guard.other)
    open("fine.txt", "w").close()
    _unchanged(guard)


def test_symlink_aliases_resolve_to_the_protected_directory(guard):
    wb = guard.wg.WriteBlocked
    alias = guard.tmp / "alias"
    os.symlink(guard.protected, alias)
    with pytest.raises(wb):
        (alias / "via_link.txt").write_text("x")
    with pytest.raises(wb):
        os.rename(guard.other / "a.txt", alias / "b.txt")
    with pytest.raises(wb):
        open(alias / "existing.txt", "a")
    _unchanged(guard)


def test_case_variants_match_on_case_insensitive_filesystems(guard):
    variant = guard.tmp / "PROTECTED"
    if not variant.exists():
        pytest.skip("this filesystem is case-sensitive: case variants are different directories")
    with pytest.raises(guard.wg.WriteBlocked):
        (variant / "case.txt").write_text("x")
    _unchanged(guard)


def test_hard_link_created_before_protection_is_recognised(tmp_path):
    wg = _guard_module()
    g = wg.GUARD
    g.install()
    protected, other = tmp_path / "protected", tmp_path / "other"
    protected.mkdir()
    other.mkdir()
    (protected / "file.txt").write_text("original", encoding="utf-8")
    os.link(protected / "file.txt", other / "alias.txt")  # alias exists before protection starts
    g.protect(protected)
    try:
        with pytest.raises(wg.WriteBlocked):
            open(other / "alias.txt", "a")
        with pytest.raises(wg.WriteBlocked):
            (other / "alias.txt").write_text("changed")
    finally:
        g.unprotect(protected)
    assert (protected / "file.txt").read_text(encoding="utf-8") == "original"


def test_dir_fd_relative_operations_are_blocked_when_the_directory_resolves(guard):
    fd = os.open(guard.protected, os.O_RDONLY)
    try:
        with pytest.raises(guard.wg.WriteBlocked):
            os.rename("existing.txt", "moved.txt", src_dir_fd=fd, dst_dir_fd=fd)
        with pytest.raises(guard.wg.WriteBlocked):
            os.remove("existing.txt", dir_fd=fd)
        with pytest.raises(guard.wg.WriteBlocked):
            os.mkdir("sub", dir_fd=fd)
    finally:
        os.close(fd)
    _unchanged(guard)


def test_documented_limit_os_open_with_dir_fd_is_not_seen(guard):
    """KNOWN BYPASS: the open audit event carries no dir_fd, so this write is not blocked."""
    fd = os.open(guard.protected, os.O_RDONLY)
    try:
        leak = os.open("leak.txt", os.O_WRONLY | os.O_CREAT, dir_fd=fd)
        os.close(leak)
    finally:
        os.close(fd)
    assert (guard.protected / "leak.txt").exists()  # demonstrates the limitation; do not rely on the guard here


def test_documented_limit_descriptor_opened_before_protection(tmp_path):
    """KNOWN BYPASS: writes through a descriptor opened before protection are not intercepted."""
    wg = _guard_module()
    g = wg.GUARD
    g.install()
    early = tmp_path / "early"
    early.mkdir()
    handle = open(early / "pre.txt", "w", encoding="utf-8")
    g.protect(early)
    try:
        handle.write("still works")
        handle.flush()
        with pytest.raises(wg.WriteBlocked):
            open(early / "fresh.txt", "w")
    finally:
        handle.close()
        g.unprotect(early)
    assert (early / "pre.txt").read_text(encoding="utf-8") == "still works"


def test_subprocess_creation_is_blocked_unless_explicitly_allowed(guard):
    guard.g.block_processes = True
    with pytest.raises(guard.wg.WriteBlocked):
        subprocess.run([sys.executable, "-c", "pass"])
    with pytest.raises(guard.wg.WriteBlocked):
        os.system("true")
    with guard.g.allow_subprocess():
        assert subprocess.run([sys.executable, "-c", "pass"]).returncode == 0
    with pytest.raises(guard.wg.WriteBlocked):
        subprocess.run([sys.executable, "-c", "pass"])


def test_unprotect_and_disarm_stop_blocking(guard):
    guard.g.unprotect(guard.protected)
    (guard.protected / "free.txt").write_text("x", encoding="utf-8")
    guard.g.protect(guard.protected)
    guard.g.disarm()
    (guard.protected / "free2.txt").write_text("x", encoding="utf-8")
    guard.g.arm()
    with pytest.raises(guard.wg.WriteBlocked):
        (guard.protected / "blocked.txt").write_text("x")


def test_blocked_attempts_are_recorded(guard):
    before = len(guard.g.violations)
    with pytest.raises(guard.wg.WriteBlocked):
        (guard.protected / "x.txt").write_text("x")
    assert len(guard.g.violations) == before + 1 and "x.txt" in guard.g.violations[-1]


def test_snapshot_comparison_detects_changes_removals_and_additions(tmp_path):
    wg = _guard_module()
    directory = tmp_path / "watched"
    directory.mkdir()
    (directory / "a.txt").write_text("1", encoding="utf-8")
    (directory / "b.txt").write_text("2", encoding="utf-8")
    before = wg.snapshot([directory])
    assert wg.compare_snapshots(before, wg.snapshot([directory])) == []
    (directory / "a.txt").write_text("changed", encoding="utf-8")
    (directory / "b.txt").unlink()
    (directory / "c.txt").write_text("3", encoding="utf-8")
    problems = wg.compare_snapshots(before, wg.snapshot([directory]))
    assert sorted(p.split(": ")[0] for p in problems) == ["added", "changed", "removed"]
    (directory / "a.txt").write_text("1", encoding="utf-8")  # modify-then-restore keeps the hash but not the mtime/inode record
    restored = wg.snapshot([directory])
    assert restored[str(directory / "a.txt")][3] == before[str(directory / "a.txt")][3]


# ---------------------------------------------------------------------------
# The launcher: installed before pytest, covers collection, refuses broad runs
# ---------------------------------------------------------------------------
def _load_launcher():
    spec = importlib.util.spec_from_file_location("syn_guarded_pytest", TOOLS_DIR / "guarded_pytest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_installs_the_guard_before_pytest_is_imported():
    source = (TOOLS_DIR / "guarded_pytest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [n for n in tree.body if isinstance(n, ast.Import) and any(a.name == "pytest" for a in n.names)]
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    lines = {}
    for node in ast.walk(main):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "install_for_repository":
            lines["install"] = node.lineno
        if isinstance(node, ast.Import) and any(a.name == "pytest" for a in node.names):
            lines["import"] = node.lineno
    assert lines["install"] < lines["import"]


def test_launcher_refuses_to_run_without_an_explicit_path():
    launcher = _load_launcher()
    assert launcher._has_path_argument([]) is False
    assert launcher._has_path_argument(["-q", "-p", "no:cacheprovider"]) is False
    assert launcher._has_path_argument(["-k", "expression"]) is False
    assert launcher._has_path_argument(["tests/synthetic", "-q"]) is True
    assert launcher._has_path_argument(["-k", "expr", "tests/synthetic"]) is True


def _write_module(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run_launcher(workdir, test_dir):
    wg = _guard_module()
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, str(TOOLS_DIR / "guarded_pytest.py"), str(test_dir), "-p", "no:cacheprovider", "-q"]
    with wg.GUARD.allow_subprocess():  # explicitly required: the launcher itself is under test
        return subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True, timeout=120)


def _hashes(paths):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def test_writes_during_collection_are_blocked_by_the_launcher(tmp_path):
    outside_target = GOLDEN_DIR / "no_such_subdirectory" / "import_time.txt"  # cannot exist even if unguarded
    before = _hashes(GOLDEN_FILES.values())
    _write_module(
        tmp_path / "suite" / "test_import_time_write.py",
        f"open({str(outside_target)!r}, 'w')\n\ndef test_never_reached():\n    pass\n",
    )
    proc = _run_launcher(tmp_path, tmp_path / "suite")
    output = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "WriteBlocked" in output and "FileNotFoundError" not in output
    assert "post-run verification: golden and audit files unchanged" in output
    assert _hashes(GOLDEN_FILES.values()) == before
    assert not (GOLDEN_DIR / "no_such_subdirectory").exists()


def test_a_clean_module_runs_under_the_launcher_and_may_write_to_temporary_directories(tmp_path):
    _write_module(
        tmp_path / "suite" / "test_clean.py",
        "def test_tmp_write(tmp_path):\n    (tmp_path / 'ok.txt').write_text('fine')\n    assert (tmp_path / 'ok.txt').read_text() == 'fine'\n",
    )
    proc = _run_launcher(tmp_path, tmp_path / "suite")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 passed" in proc.stdout and "golden and audit files unchanged" in proc.stdout


# ---------------------------------------------------------------------------
# The real golden and audit directories (only when launched through the guard)
# ---------------------------------------------------------------------------
def _try_append_nothing(path):
    open(path, "ab").close()  # appends no bytes: harmless even if the guard failed


def _try_rename(src, dst):
    os.rename(src, dst)


def _try_mkdir(path):
    os.mkdir(path)


def _try_open_for_write(path):
    open(path, "w")


@pytest.mark.skipif(os.environ.get("MAPS_SYN_GUARD") != "1", reason="only meaningful when run through tools/guarded_pytest.py")
def test_the_launcher_guard_protects_the_real_golden_and_audit_directories(tmp_path):
    wg = _guard_module()
    roots = {str(r) for r in wg.GUARD.roots}
    assert {str(GOLDEN_DIR.resolve()), str(AUDIT_DIR.resolve())} <= roots
    before = _hashes(GOLDEN_FILES.values())
    for golden in GOLDEN_FILES.values():
        with pytest.raises(wg.WriteBlocked):
            _try_append_nothing(golden)
    with pytest.raises(wg.WriteBlocked):
        _try_rename(tmp_path / "does_not_exist", GOLDEN_DIR / "zz_target")
    with pytest.raises(wg.WriteBlocked):
        _try_mkdir(GOLDEN_DIR / "no_such_parent" / "child")
    with pytest.raises(wg.WriteBlocked):
        _try_open_for_write(AUDIT_DIR / "no_such_parent" / "file.txt")
    assert wg.GUARD.block_processes is True
    assert _hashes(GOLDEN_FILES.values()) == before
    assert not (GOLDEN_DIR / "zz_target").exists()
