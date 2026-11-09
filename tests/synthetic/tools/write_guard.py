"""Preventive in-process write guard for the SYNTHETIC suite (best effort; NOT filesystem security).

The guard is a Python audit hook (sys.addaudithook). When armed it raises WriteBlocked *before* a
supported mutating operation runs on a protected path, so the operation does not happen. It is
installed by tools/guarded_pytest.py before pytest imports anything, so test collection and test
execution are both covered, including test modules that import no guard themselves.

What it blocks (in this process only):
  * open()/os.open() with a write, append, create or read-write intent on a protected path;
  * rename/replace, remove/unlink, rmdir, mkdir/makedirs, chmod, chown, utime, link, symlink,
    setxattr, truncate and the shutil copy/move/rmtree/unpack/make_archive family, by path;
  * the same calls with dir_fd arguments, when the descriptor's directory can be resolved
    (otherwise the call is blocked because it cannot be proven safe);
  * subprocess creation (Popen, os.system, exec, spawn, fork), unless allow_subprocess() is active.

How paths are matched: the path is canonicalised with realpath (symlinks and ".." resolved), then
compared by file identity (device and inode) of every existing ancestor against the protected
directories, so symlinks, case variants on case-insensitive filesystems and relative paths match.
Inodes of files that already exist under a protected directory are recorded too, so a hard link
created *before* protection is still recognised. A protected directory that does not exist yet is
matched by canonical path text (case-sensitive).

KNOWN LIMITS - this is not filesystem-level security. Not covered:
  * os.open(name, flags, dir_fd=fd): the audit event carries no dir_fd, so the target is unknown;
  * writes through a file descriptor that was opened before protection began (inherited or earlier);
  * native extensions, ctypes, direct system calls, memory-mapped writes;
  * other processes, including children that are started while allow_subprocess() is active;
  * hard links created before protection to files created later, and a file moved out of a
    protected directory by an unrelated process;
  * anything the hook cannot see because the event is not audited by this Python version.
The hook cannot be removed once installed; disarm() only stops it from blocking. Post-run hash and
stat verification (snapshot / compare) is retained as a second, detection-only layer.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
from pathlib import Path

try:  # macOS: resolve a directory descriptor to its path
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

MODULE_NAME = "write_guard"
GUARD_ENV = "MAPS_SYN_GUARD"


class WriteBlocked(PermissionError):
    """Raised by the guard instead of performing a blocked operation."""


_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

# event -> indexes of the path arguments that the operation modifies or creates
_PATH_EVENTS = {
    "os.remove": (0,), "os.rmdir": (0,), "os.mkdir": (0,), "os.chmod": (0,), "os.chown": (0,),
    "os.truncate": (0,), "os.utime": (0,), "os.rename": (0, 1), "os.link": (0, 1), "os.symlink": (1,),
    "os.setxattr": (0,), "os.removexattr": (0,),
    "shutil.copyfile": (1,), "shutil.copymode": (1,), "shutil.copystat": (1,), "shutil.copytree": (1,),
    "shutil.move": (0, 1), "shutil.rmtree": (0,), "shutil.unpack_archive": (1,), "shutil.make_archive": (0,),
}
# event -> (path argument index, dir_fd argument index) pairs
_DIR_FD_ARGS = {
    "os.remove": ((0, 1),), "os.rmdir": ((0, 1),), "os.mkdir": ((0, 2),), "os.chmod": ((0, 2),),
    "os.chown": ((0, 3),), "os.utime": ((0, 3),), "os.rename": ((0, 2), (1, 3)),
    "os.link": ((0, 2), (1, 3)), "os.symlink": ((1, 2),), "shutil.rmtree": ((0, 1),),
}
_PROCESS_EVENTS = frozenset(
    {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty"}
)


def _is_pathlike(value: object) -> bool:
    return isinstance(value, (str, bytes, os.PathLike))


def _fd_path(fd: int) -> str | None:
    """Best-effort path of an open directory descriptor (None if it cannot be resolved)."""
    try:
        if fcntl is not None and hasattr(fcntl, "F_GETPATH"):
            raw = fcntl.fcntl(fd, fcntl.F_GETPATH, b"\0" * 1024)
            return os.fsdecode(raw.split(b"\0", 1)[0]) or None
        return os.readlink(f"/proc/self/fd/{fd}")
    except (OSError, ValueError, TypeError):
        return None


def _write_intent(mode: object, flags: object) -> bool:
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


class WriteGuard:
    def __init__(self) -> None:
        self.enabled = True
        self.block_processes = False
        self.violations: list[str] = []
        self._roots: list[Path] = []
        self._real: list[str] = []
        self._ids: set[tuple[int, int]] = set()
        self._installed = False
        self._process_allowed = 0

    # -- configuration -------------------------------------------------------------------------
    def install(self) -> None:
        """Add the audit hook (idempotent). Hooks cannot be removed; use disarm()."""
        if not self._installed:
            sys.addaudithook(self._hook)
            self._installed = True

    def protect(self, path: str | os.PathLike) -> None:
        root = Path(os.path.realpath(path))
        if root not in self._roots:
            self._roots.append(root)
        self._rebuild()

    def unprotect(self, path: str | os.PathLike) -> None:
        root = Path(os.path.realpath(path))
        self._roots = [r for r in self._roots if r != root]
        self._rebuild()

    def refresh_identities(self) -> None:
        """Re-record inodes (call after protected directories gain files)."""
        self._rebuild()

    def disarm(self) -> None:
        self.enabled = False

    def arm(self) -> None:
        self.enabled = True

    @property
    def roots(self) -> tuple[Path, ...]:
        return tuple(self._roots)

    def _rebuild(self) -> None:
        self._real = [str(r) for r in self._roots]
        ids: set[tuple[int, int]] = set()
        for root in self._roots:
            for current, dirs, files in os.walk(root):
                for name in [*dirs, *files, ""]:
                    target = os.path.join(current, name) if name else current
                    try:
                        st = os.stat(target)
                    except OSError:
                        continue
                    ids.add((st.st_dev, st.st_ino))
        self._ids = ids

    @contextlib.contextmanager
    def allow_subprocess(self):
        """Explicitly permit subprocess creation (the guard does not follow the children)."""
        self._process_allowed += 1
        try:
            yield
        finally:
            self._process_allowed -= 1

    # -- matching ------------------------------------------------------------------------------
    def is_protected(self, target: object, dir_fd: int | None = None) -> bool:
        if not _is_pathlike(target):
            return False
        text = os.fsdecode(target)
        if dir_fd is not None and not os.path.isabs(text):
            base = _fd_path(dir_fd)
            if base is None:
                raise WriteBlocked("directory descriptor cannot be resolved; blocked as unsafe")
            text = os.path.join(base, text)
        real = os.path.realpath(text)
        for root in self._real:
            if real == root or real.startswith(root + os.sep):
                return True
        current = real
        while True:
            try:
                st = os.stat(current)
                if (st.st_dev, st.st_ino) in self._ids:
                    return True
            except OSError:
                pass
            parent = os.path.dirname(current)
            if parent == current:
                return False
            current = parent

    # -- the hook ------------------------------------------------------------------------------
    def _block(self, message: str) -> None:
        self.violations.append(message)
        raise WriteBlocked(f"write guard: {message}")

    def _hook(self, event: str, args: tuple) -> None:
        if not self.enabled:
            return
        if event in _PROCESS_EVENTS:
            if self.block_processes and not self._process_allowed:
                self._block(f"{event} blocked (subprocess creation is not allowed in the guarded process)")
            return
        if event == "open":
            if args and _is_pathlike(args[0]) and _write_intent(args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else None):
                if self.is_protected(args[0]):
                    self._block(f"open for write/create/append of {os.fsdecode(args[0])}")
            return
        indexes = _PATH_EVENTS.get(event)
        if indexes is None:
            return
        fd_args = dict(_DIR_FD_ARGS.get(event, ()))
        for i in indexes:
            if i >= len(args) or not _is_pathlike(args[i]):
                continue
            dir_fd = args[fd_args[i]] if i in fd_args and fd_args[i] < len(args) else None
            try:
                protected = self.is_protected(args[i], dir_fd if isinstance(dir_fd, int) else None)
            except WriteBlocked as exc:
                self.violations.append(f"{event}: {exc}")
                raise
            if protected:
                self._block(f"{event} on {os.fsdecode(args[i])}")


GUARD = WriteGuard()


def install_for_repository(syn_root: str | os.PathLike) -> WriteGuard:
    """Protect the golden and audit directories of the synthetic suite and block subprocesses."""
    syn_root = Path(syn_root)
    GUARD.install()
    GUARD.protect(syn_root / "data" / "golden")
    GUARD.protect(syn_root / "audit")
    GUARD.block_processes = True
    os.environ[GUARD_ENV] = "1"
    return GUARD


# -- post-run verification (detection only) ----------------------------------------------------
def snapshot(directories: list[str | os.PathLike]) -> dict[str, tuple[int, int, int, str]]:
    """(size, mtime_ns, inode, sha256) of every file under the directories."""
    result: dict[str, tuple[int, int, int, str]] = {}
    for directory in directories:
        for path in sorted(Path(directory).rglob("*")) if Path(directory).exists() else []:
            if path.is_file():
                st = path.stat()
                result[str(path)] = (st.st_size, st.st_mtime_ns, st.st_ino, hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def compare_snapshots(before: dict, after: dict) -> list[str]:
    problems = []
    for path in sorted(set(before) | set(after)):
        if path not in after:
            problems.append(f"removed: {path}")
        elif path not in before:
            problems.append(f"added: {path}")
        elif before[path] != after[path]:
            problems.append(f"changed: {path}")
    return problems
