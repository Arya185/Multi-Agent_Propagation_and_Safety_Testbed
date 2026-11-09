"""Allow-list validation and comparison against a scan (v2.3.56, Stage 4C). Pure functions; offline; no file content in messages."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from allowlist import CATEGORIES, CLASSIFICATION_ROOTS, CLASSIFICATIONS, FIELDS
from route_scanner import KINDS, NEVER_ALLOWLISTABLE, scan_tree

_WILDCARD = re.compile(r"[*?\[\]{}]")
MIN_TEXT = 20   # a purpose or justification must be a real sentence, not a placeholder
_CLASS_CATEGORIES = {
    "guarded_experiment": {"source"},
    "diagnostic_only": {"script", "notebook"},
    "test_only": {"test", "test_support", "notebook"},
    "non_provider_network": {"source", "script", "notebook"},
}


def validate_entries(entries, root: Path) -> list[str]:
    """Problems with the allow-list itself (empty when it is well-formed). Fails closed on any malformed entry."""
    problems: list[str] = []
    if not isinstance(entries, (list, tuple)):
        return ["allow-list is not a sequence"]
    seen: dict[str, int] = {}
    for index, entry in enumerate(entries):
        where = f"entry #{index}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: not a mapping")
            continue
        if set(entry) != set(FIELDS):
            problems.append(f"{where}: fields must be exactly {sorted(FIELDS)} (missing {sorted(set(FIELDS) - set(entry))}, extra {sorted(set(entry) - set(FIELDS))})")
            continue
        path = entry["path"]
        if type(path) is not str or not path:
            problems.append(f"{where}: path must be a non-empty string")
            continue
        where = f"entry {path!r}"
        posix = PurePosixPath(path)
        if (path.startswith("/") or "\\" in path or ".." in posix.parts or path.endswith("/") or _WILDCARD.search(path)
                or posix.as_posix() != path or "\x00" in path or path.startswith("./")):
            problems.append(f"{where}: path must be a plain relative POSIX file path (no wildcard, directory, '..', absolute or backslash)")
            continue
        if path in seen:
            problems.append(f"{where}: duplicate entry (also #{seen[path]})")
        seen[path] = index
        target = root / path
        if target.is_dir():
            problems.append(f"{where}: names a directory; entries are per file")
        elif not target.is_file():
            problems.append(f"{where}: file does not exist (stale entry)")
        if entry["classification"] not in CLASSIFICATIONS:
            problems.append(f"{where}: classification must be one of {list(CLASSIFICATIONS)}")
        if entry["category"] not in CATEGORIES:
            problems.append(f"{where}: category must be one of {list(CATEGORIES)}")
        for text_field in ("purpose", "justification"):
            value = entry[text_field]
            if type(value) is not str or len(value.strip()) < MIN_TEXT:
                problems.append(f"{where}: {text_field} must be a descriptive string of at least {MIN_TEXT} characters")
        kinds = entry["kinds"]
        if not isinstance(kinds, (list, tuple)) or any(type(k) is not str for k in kinds) or len(set(kinds)) != len(kinds):
            problems.append(f"{where}: kinds must be a sequence of distinct strings")
            continue
        unknown = sorted(set(kinds) - set(KINDS))
        if unknown:
            problems.append(f"{where}: unknown kinds {unknown} (never-allowlistable problems such as {list(NEVER_ALLOWLISTABLE)} cannot be listed)")
        is_notebook = path.endswith(".ipynb")
        if entry["category"] == "notebook" and not is_notebook or is_notebook and entry["category"] != "notebook":
            problems.append(f"{where}: category 'notebook' and the .ipynb extension must go together")
        if not kinds and not is_notebook:
            problems.append(f"{where}: kinds is empty; only a notebook may be listed without findings")
        cls = entry["classification"]
        if cls in CLASSIFICATION_ROOTS and not path.startswith(CLASSIFICATION_ROOTS[cls]):
            problems.append(f"{where}: classification {cls!r} is only valid under {list(CLASSIFICATION_ROOTS[cls])}")
        if cls in _CLASS_CATEGORIES and entry["category"] in CATEGORIES and entry["category"] not in _CLASS_CATEGORIES[cls]:
            problems.append(f"{where}: category {entry['category']!r} does not fit classification {cls!r}")
    return problems


def compare(scans, entries) -> list[str]:
    """Violations of the allow-list by a scan result (a mapping path -> FileScan). Assumes the entries are well-formed."""
    by_path = {e["path"]: e for e in entries if isinstance(e, dict) and "path" in e}
    problems: list[str] = []
    for path, scan in sorted(scans.items()):
        if scan.problem:
            problems.append(f"{path}: cannot be analysed ({scan.problem}); this is never allow-listable")
            continue
        entry = by_path.get(path)
        if entry is None:
            shown = sorted(scan.kinds) or ["notebook without findings"]
            problems.append(f"{path}: not in the provider-route allow-list (findings: {shown})")
            continue
        allowed, found = set(entry["kinds"]), set(scan.kinds)
        if found - allowed:
            problems.append(f"{path}: has findings not in its entry: {sorted(found - allowed)}")
        if allowed - found:
            problems.append(f"{path}: entry lists kinds the file no longer has: {sorted(allowed - found)} (tighten the entry)")
    for path in sorted(set(by_path) - set(scans)):
        problems.append(f"{path}: listed but the scan found nothing in it (stale entry)")
    return problems


def check_tree(root: Path, entries) -> list[str]:
    """Everything wrong with the tree under ``root`` against ``entries``: malformed entries first, then violations."""
    problems = validate_entries(entries, root)
    if problems:
        return problems   # fail closed: a malformed list is not used to judge the tree
    return compare(scan_tree(root), entries)
