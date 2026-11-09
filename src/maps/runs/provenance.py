"""Run provenance recorder (standalone; writes a separate file beside a run).

The record is a LOCAL snapshot produced by the process that creates it. It is not an independent
trust anchor: whoever can edit the run directory can edit the record. Stronger anchoring means
recording a digest outside the repository.

Collected where possible: run id, UTC creation time, Python and platform information, a Git commit id
read directly from ``.git/HEAD`` and a loose ref file (no Git command, no remotes, no Git config),
SHA-256 digests of source files and of the dependency lock file, and installed package names and
versions. Every field that could not be collected is listed under ``unavailable_fields`` and has an
explicit status; nothing is silently omitted. Environment variables are never read or recorded, and
there are no network calls.

Serialization is deterministic (sorted keys, fixed indentation, trailing newline).
"""

from __future__ import annotations

import hashlib
import json
import platform
import posixpath
import re
import sys
import textwrap
import zipfile
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path, PurePosixPath

from maps.runs.ids import validate_run_id

RECORD_SCHEMA = "maps-run-provenance"
RECORD_VERSION = 1
DEFAULT_FILENAME = "run_provenance.json"
NOT_A_TRUST_ANCHOR = (
    "Local provenance snapshot written by the process that produced it. It is not an independent trust "
    "anchor; record digests outside the repository for stronger anchoring."
)
_HEX_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_source_files(repo_root: str | Path) -> list[str]:
    """Every ``*.py`` under ``src/maps`` (posix paths relative to the repository root, sorted)."""
    root = Path(repo_root)
    base = root / "src" / "maps"
    if not base.is_dir():
        return []
    return sorted(p.relative_to(root).as_posix() for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _file_entry(repo_root: Path, rel: str) -> dict:
    pure = PurePosixPath(rel)
    if not rel or pure.is_absolute() or ".." in pure.parts:
        return {"path": rel, "sha256": None, "status": "invalid_path"}
    try:
        return {"path": pure.as_posix(), "sha256": sha256_file(repo_root / pure), "status": "ok"}
    except FileNotFoundError:
        return {"path": pure.as_posix(), "sha256": None, "status": "missing"}
    except OSError:
        return {"path": pure.as_posix(), "sha256": None, "status": "unreadable"}


def _combined(entries: list[dict]) -> str:
    lines = "\n".join(f"{e['path']}:{e['sha256']}" for e in sorted(entries, key=lambda e: e["path"]))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def read_git_commit(repo_root: str | Path) -> dict:
    """Commit id from ``.git/HEAD`` and a loose ref file only. Never runs Git, never reads Git config,
    remotes or packed refs, and never inspects the working tree (so ``dirty`` is always 'unknown')."""
    unavailable = {"commit": None, "ref": None, "status": "unavailable", "dirty": "unknown"}
    git_dir = Path(repo_root) / ".git"
    if not git_dir.is_dir():
        return {**unavailable, "reason": "no .git directory (or a gitdir indirection, which is not followed)"}
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return {**unavailable, "reason": "HEAD is not readable"}
    if _HEX_COMMIT.fullmatch(head):
        return {"commit": head, "ref": "detached", "status": "ok", "dirty": "unknown"}
    if head.startswith("ref: "):
        ref = head[5:].strip()
        pure = PurePosixPath(ref)
        if not ref.startswith("refs/heads/") or ".." in pure.parts:
            return {**unavailable, "reason": "HEAD names a ref outside refs/heads"}
        try:
            commit = (git_dir / pure).read_text(encoding="utf-8").strip()
        except OSError:
            return {**unavailable, "ref": ref, "reason": "the ref is not a loose ref file; packed refs are deliberately not read"}
        if _HEX_COMMIT.fullmatch(commit):
            return {"commit": commit, "ref": ref, "status": "ok", "dirty": "unknown"}
        return {**unavailable, "ref": ref, "reason": "the ref file does not contain a commit id"}
    return {**unavailable, "reason": "HEAD has an unrecognized format"}


_SUPPRESSED_READ_ERRORS = (FileNotFoundError, IsADirectoryError, KeyError, NotADirectoryError, PermissionError)
_INFO_SUFFIXES = (".dist-info", ".egg-info")


def _redent(value):
    """Undo RFC 822 folding indentation in a multi-line header value (as the standard library does)."""
    if not value or "\n" not in value:
        return value
    return textwrap.dedent(" " * 8 + value)


def _open_root(root: str):
    """Names of the entries directly under one search-path entry, plus a ``read(child, rel)`` function that
    returns the UTF-8 text of ``child/rel`` (``rel == ""`` means ``child`` itself) or None if it is absent
    or unreadable for the usual reasons. A directory is listed first; anything that is not a listable
    directory is tried as a zip archive; anything else yields nothing."""
    base = Path(root or ".")
    try:
        names = sorted(entry.name for entry in base.iterdir())
    except Exception:
        names = None
    if names is not None:
        def read_directory(child: str, rel: str) -> str | None:
            try:
                return (base / child / rel).read_text(encoding="utf-8")
            except _SUPPRESSED_READ_ERRORS:
                return None

        return names, read_directory
    try:
        with zipfile.ZipFile(root) as archive:
            members = archive.namelist()
    except Exception:
        return [], None
    names = sorted(dict.fromkeys(member.split("/", 1)[0] for member in members))

    def read_archive(child: str, rel: str) -> str | None:
        if not rel:   # the standard library resolves "the entry itself" inside an archive as a directory, so a
            return None  # single-file egg-info in a zip has no readable metadata there; matched deliberately
        try:
            with zipfile.ZipFile(root) as archive:
                return archive.read(f"{child}/{rel}").decode("utf-8")
        except _SUPPRESSED_READ_ERRORS:
            return None

    return names, read_archive


def _name_and_version(read) -> tuple[str | None, str | None]:
    """``Name`` and ``Version`` from METADATA, else PKG-INFO, else the entry itself (old single-file
    egg-info). Any failure (for example non-UTF-8 text) gives (None, None), which the caller reports as an
    unreadable entry. A missing header gives None for that field."""
    try:
        text = read("METADATA") or read("PKG-INFO") or read("")
        values: dict[str, str] = {}
        for key, value in Parser().parsestr(text or "").raw_items():
            values.setdefault(key.lower(), _redent(value))
        return values.get("name"), values.get("version")
    except Exception:
        return None, None


def default_package_provider(paths: Sequence[str | Path] | None = None) -> list[tuple[str | None, str | None]]:
    """Installed distributions as (name, version) pairs, read directly from package metadata on disk.

    Replaces ``importlib.metadata`` so that no dynamic-loading module is imported (the static import-closure
    check rejects those). It follows the Python 3.12 standard-library discovery rules: for every entry of
    ``paths`` (default ``sys.path``; ``''`` means the current directory) it lists directories, or else zip
    archives, and treats every child named ``*.dist-info`` or ``*.egg-info`` (directory or file) as a
    distribution, plus an ``EGG-INFO`` child of a ``*.egg`` entry. Duplicates are kept, as in the standard
    library, and ordering is left to ``collect_packages``. No code is executed or imported and nothing is
    written. Not covered: custom finders on ``sys.meta_path`` (the standard library asks them too), and
    path separators other than ``/`` in the egg check.
    """
    items: list[tuple[str | None, str | None]] = []
    for entry in sys.path if paths is None else paths:
        if not isinstance(entry, (str, Path)):
            continue
        root = str(entry)
        names, read = _open_root(root)
        if read is None:
            continue
        is_egg = posixpath.basename(root).lower().endswith(".egg")
        infos = [name for name in names if name.lower().endswith(_INFO_SUFFIXES)]
        eggs = [name for name in names if is_egg and name.lower() == "egg-info"]
        for child in (*infos, *eggs):
            items.append(_name_and_version(lambda rel, child=child: read(child, rel)))
    return items


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def collect_packages(provider: Callable[[], Iterable[tuple[str | None, str | None]]]) -> dict:
    try:
        raw = list(provider())
    except Exception as exc:
        return {"status": "unavailable", "reason": type(exc).__name__, "n_unreadable": 0, "items": []}
    items, unreadable = [], 0
    for name, version in raw:
        if not isinstance(name, str) or not name:
            unreadable += 1
            continue
        items.append({"name": name, "version": version if isinstance(version, str) and version else None})
    items.sort(key=lambda i: (_normalized(i["name"]), i["name"], i["version"] or ""))
    partial = unreadable > 0 or any(i["version"] is None for i in items)
    return {"status": "partial" if partial else "ok", "n_unreadable": unreadable, "items": items}


def collect_provenance(
    *,
    run_id: str,
    repo_root: str | Path,
    source_files: Sequence[str] | None = None,
    lock_file: str | None = "requirements.lock",
    created_utc: str | None = None,
    package_provider: Callable[[], Iterable[tuple[str | None, str | None]]] | None = None,
    include_git: bool = True,
) -> dict:
    """Collect the provenance snapshot as a plain dict (see the module docstring)."""
    validate_run_id(run_id)  # InvalidRunIdError is a ValueError
    root = Path(repo_root)
    rels = list(source_files) if source_files is not None else discover_source_files(root)
    entries = sorted((_file_entry(root, rel) for rel in rels), key=lambda e: e["path"])
    complete = bool(entries) and all(e["status"] == "ok" for e in entries)
    lock = _file_entry(root, lock_file) if lock_file else {"path": None, "sha256": None, "status": "not_requested"}
    git = read_git_commit(root) if include_git else {"commit": None, "ref": None, "status": "not_requested", "dirty": "unknown"}
    packages = collect_packages(package_provider or default_package_provider)

    unavailable: list[str] = []
    unavailable += [f"source_files:{e['path']}({e['status']})" for e in entries if e["status"] != "ok"]
    if not entries:
        unavailable.append("source_files:none_supplied")
    if lock["status"] not in ("ok", "not_requested"):
        unavailable.append(f"lock_file({lock['status']})")
    if git["status"] == "unavailable":
        unavailable.append("git.commit")
    if packages["status"] != "ok":
        unavailable.append(f"packages({packages['status']})")
    return {
        "schema": RECORD_SCHEMA,
        "version": RECORD_VERSION,
        "note": NOT_A_TRUST_ANCHOR,
        "run_id": run_id,
        "created_utc": created_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "in_virtualenv": sys.prefix != sys.base_prefix,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "git": git,
        "source_files": {
            "files": entries,
            "complete": complete,
            "combined_sha256": _combined(entries) if complete else None,
        },
        "lock_file": lock,
        "packages": packages,
        "unavailable_fields": sorted(unavailable),
    }


def serialize(record: dict) -> str:
    return json.dumps(record, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_provenance(run_dir: str | Path, record: dict, filename: str = DEFAULT_FILENAME) -> Path:
    """Write the record beside the run with exclusive creation (an existing file is never overwritten)."""
    directory = Path(run_dir)
    if not directory.is_dir():
        raise NotADirectoryError(f"run directory does not exist: {directory}")
    if Path(filename).name != filename:
        raise ValueError("filename must not contain path separators")
    target = directory / filename
    with open(target, "x", encoding="utf-8") as handle:
        handle.write(serialize(record))
    return target
