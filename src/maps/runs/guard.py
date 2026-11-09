"""Safe run-directory guard (standalone).

``initialize_run_dir`` accepts only a new path or an existing EMPTY directory, checks it immediately
before use, and then claims it by exclusively creating a small claim file, so a second initialization
of the same directory is refused. ``check_run_dir`` performs the same checks without writing anything.

What it never does: delete, overwrite, truncate or rename existing files, or change existing outputs.

LIMITATIONS (read before relying on it):
  * It only protects executions that actually call it. The existing runner (``run_experiment``) does
    NOT call it, so the runner is not protected until a future, separately authorized integration.
  * The claim file is created with exclusive creation, which prevents two cooperating callers from
    claiming the same empty directory, but it cannot stop a process that ignores the guard from
    writing into the directory, and a check-then-use window remains for such processes.
  * Hidden files (for example ``.DS_Store``) count as content, so a Finder-visited directory is
    refused; choose a new directory.
  * A symbolic link is refused rather than followed.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

CLAIM_FILENAME = ".maps_run_claim"
_MAX_NAMES_SHOWN = 10


class UnsafeRunDirectoryError(RuntimeError):
    """The requested run directory cannot be used safely."""


def _entry_names(path: Path) -> list[str]:
    with os.scandir(path) as entries:
        return sorted(entry.name for entry in entries)


def _refuse_non_empty(path: Path, names: list[str]) -> None:
    shown = ", ".join(names[:_MAX_NAMES_SHOWN]) + (", ..." if len(names) > _MAX_NAMES_SHOWN else "")
    raise UnsafeRunDirectoryError(
        f"Refusing to use run directory {path}: it already contains {len(names)} entr"
        f"{'y' if len(names) == 1 else 'ies'} ({shown}). "
        "Choose a new run directory (for example a new run id). Existing files are never deleted, "
        "overwritten, truncated or renamed by this guard."
    )


def check_run_dir(path: str | os.PathLike) -> Path:
    """Check without writing. Returns the path if it is new or an empty directory, otherwise raises."""
    p = Path(path)
    if p.is_symlink():
        raise UnsafeRunDirectoryError(f"Refusing to use run directory {p}: it is a symbolic link. Use a real directory path.")
    if not p.exists():
        return p
    if not p.is_dir():
        raise UnsafeRunDirectoryError(f"Refusing to use run directory {p}: the path exists and is not a directory.")
    names = _entry_names(p)
    if names:
        _refuse_non_empty(p, names)
    return p


def initialize_run_dir(path: str | os.PathLike, *, run_id: str | None = None) -> Path:
    """Check, create if needed, and claim the run directory. See the module docstring for limits."""
    p = check_run_dir(path)  # checked immediately before initialization
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.mkdir()  # atomic; fails if another creator got there first
        except FileExistsError:
            p = check_run_dir(p)
    names = _entry_names(p)  # re-check right before claiming
    if names:
        _refuse_non_empty(p, names)
    claim = {
        "claimed_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
        "note": "Created by maps.runs.guard. Its presence makes this directory non-empty so it cannot be initialized twice.",
    }
    try:
        with open(p / CLAIM_FILENAME, "x", encoding="utf-8") as handle:  # exclusive creation
            handle.write(json.dumps(claim, sort_keys=True, indent=2) + "\n")
    except FileExistsError:
        _refuse_non_empty(p, _entry_names(p))
    return p
