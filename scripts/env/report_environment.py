#!/usr/bin/env python3
"""Report runtime and dependency provenance for MAPS (standard library only; no network, no Git).

Prints one JSON document to stdout: Python version and executable, platform, the bootstrap packages
(pip, setuptools, wheel) reported separately, every pinned package marked direct or transitive, the
sha256 of the environment files, and how the installed *versions* compare with requirements.lock.
With --out PATH the document is written to a new file instead; existing files are never
overwritten, and paths inside experiment-result or data directories are refused so that
environment reports stay separate from experiment results and synthetic fixtures.

The comparison is a version-snapshot comparison only. requirements.lock is a local `pip freeze`
snapshot, not a hash-verified or portable lockfile; the `not_checked` list states what is not
verified. Direct dependencies are the names in requirements.in; every other pin is transitive.

Usage: python scripts/env/report_environment.py [--out PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

REPORT_FORMAT = 2
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = ("requirements.in", "requirements.lock", ".python-version", "pyproject.toml")
BOOTSTRAP = ("pip", "setuptools", "wheel")  # present in a venv but not listed by `pip freeze`
PROTECTED = ("experiments", "data", "configs", "tests/synthetic")
NOT_CHECKED = (
    "hashes or file contents of installed packages",
    "platform / ABI compatibility of installed wheels",
    "versions of the bootstrap packages (pip, setuptools, wheel): reported separately, not compared with any pin",
    "duplicate distributions: a name found more than once on sys.path is not detected (the last one read wins)",
    "transitive pins are whatever was installed; they were not resolved against a package index",
    "extras, environment markers and editable installs",
)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def read_lock(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    if not path.is_file():
        return pins
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, version = line.partition("==")
        if sep:
            pins[_normalize(name)] = version.split("#")[0].strip()
    return pins


def read_direct(path: Path) -> list[str]:
    """Names listed in requirements.in (specifiers, extras, markers and comments stripped)."""
    names: list[str] = []
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("-"):
            names.append(_normalize(re.split(r"[<>=!~;\[\s]", line)[0]))
    return names


def installed_packages() -> dict[str, str]:
    return {_normalize(d.metadata["Name"]): d.version for d in importlib.metadata.distributions() if d.metadata["Name"]}


def build_report() -> dict:
    installed = installed_packages()
    pins = read_lock(REPO_ROOT / "requirements.lock")
    direct = read_direct(REPO_ROOT / "requirements.in")
    wanted = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip() if (REPO_ROOT / ".python-version").is_file() else None
    current = platform.python_version()
    exempt = set(BOOTSTRAP)
    comparison = {
        "pinned_but_not_installed": sorted(set(pins) - set(installed)),
        "installed_but_not_pinned": sorted(set(installed) - set(pins) - exempt),
        "version_differs": {k: {"lock": pins[k], "installed": installed[k]} for k in sorted(set(pins) & set(installed)) if pins[k] != installed[k]},
    }
    return {
        "report_format": REPORT_FORMAT,
        "python": {
            "version": current,
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
            "prefix": sys.prefix,
            "in_virtualenv": sys.prefix != sys.base_prefix,
            "recorded_version": wanted,
            "minor_matches_recorded": bool(wanted) and current.split(".")[:2] == wanted.split(".")[:2],
            "patch_matches_recorded": wanted == current,
        },
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "platform": platform.platform()},
        "files_sha256": {name: _sha256(REPO_ROOT / name) for name in ENV_FILES},
        "bootstrap_packages": {name: installed.get(name) for name in BOOTSTRAP},
        "direct_dependencies": sorted(direct),
        "direct_dependencies_missing_from_lock": sorted(d for d in direct if d not in pins),
        "direct_dependencies_not_installed": sorted(d for d in direct if d not in installed),
        "pinned_packages": {
            name: {"locked": version, "installed": installed.get(name), "kind": "direct" if name in direct else "transitive"}
            for name, version in sorted(pins.items())
        },
        "packages_installed": dict(sorted(installed.items())),
        "snapshot_comparison": comparison,
        "versions_match_lock_snapshot": not any(comparison.values()) and not [d for d in direct if d not in pins],
        "versions_match_lock_snapshot_meaning": (
            "True only if every pin is installed at the pinned version, nothing unpinned is installed "
            "(bootstrap packages excepted) and every direct dependency is pinned. It says nothing about hashes, "
            "platform portability or the bootstrap packages."
        ),
        "not_checked": list(NOT_CHECKED),
        "note": "requirements.lock is a local pip-freeze snapshot, not a hash-verified or portable lockfile; see docs/ENVIRONMENT.md.",
    }


def _refuse_if_protected(out: Path) -> None:
    resolved = out.resolve()
    for part in PROTECTED:
        root = (REPO_ROOT / part).resolve()
        if resolved == root or root in resolved.parents:
            raise SystemExit(f"refusing to write inside {part}/: environment reports must stay separate from results and fixtures")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report MAPS runtime and dependency provenance.")
    parser.add_argument("--out", type=Path, help="write the report to this new file instead of stdout")
    args = parser.parse_args(argv)
    text = json.dumps(build_report(), indent=2, sort_keys=True) + "\n"
    if args.out is None:
        sys.stdout.write(text)
        return 0
    _refuse_if_protected(args.out)
    with open(args.out, "x", encoding="utf-8") as handle:  # "x": fail if the file exists
        handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
