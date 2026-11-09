"""Guarded pytest launcher for the SYNTHETIC suite (NOT a test; pytest never collects this file).

It installs the preventive write guard (tools/write_guard.py) BEFORE pytest is imported, so that
test collection (module imports) and test execution are both covered, then calls pytest.main with
the given arguments. Around the run it snapshots the golden and audit directories and verifies
afterwards that nothing changed and that the goldens still match the manifest (detection-only
second layer). It refuses to run without an explicit path argument, so it cannot start a
repository-wide run by accident; tools/run_synthetic.py is the supported entry point.

Usage: python tests/synthetic/tools/guarded_pytest.py tests/synthetic [pytest options]
Exit codes: pytest's own code, 2 for a missing path argument, 5 when post-run verification fails.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
SYN_ROOT = HERE.parent
GOLDEN_DIR = SYN_ROOT / "data" / "golden"
AUDIT_DIR = SYN_ROOT / "audit"
EXIT_USAGE, EXIT_VERIFY = 2, 5

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import write_guard  # noqa: E402  (must come before pytest is imported)


def _has_path_argument(args: list[str]) -> bool:
    value_options = {"-k", "-m", "-p", "-c", "-o", "--rootdir", "--basetemp", "--maxfail", "--tb"}
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in value_options:
            skip = True
        elif not arg.startswith("-"):
            return True
    return False


def _manifest_problems() -> list[str]:
    manifest_path = GOLDEN_DIR / "golden_manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        recorded = json.loads(manifest_path.read_text(encoding="utf-8")).get("goldens", {})
    except ValueError as exc:
        return [f"manifest is not valid JSON: {exc}"]
    problems = []
    for name, digest in sorted(recorded.items()):
        path = GOLDEN_DIR / name
        if not path.is_file():
            problems.append(f"golden missing: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"golden differs from the manifest: {name}")
    return problems


def main(argv: list[str]) -> int:
    if not _has_path_argument(argv):
        print("refusing: give an explicit test path (this launcher never runs the whole repository)")
        return EXIT_USAGE
    guard = write_guard.install_for_repository(SYN_ROOT)
    before = write_guard.snapshot([GOLDEN_DIR, AUDIT_DIR])
    import pytest  # imported only after the guard is installed

    code = int(pytest.main(argv))
    after = write_guard.snapshot([GOLDEN_DIR, AUDIT_DIR])
    problems = write_guard.compare_snapshots(before, after) + _manifest_problems()
    print(
        f"write guard: {len(guard.violations)} blocked attempt(s) in this run "
        f"(deliberate ones from the guard's own tests are included); post-run verification: "
        f"{'FAILED' if problems else 'golden and audit files unchanged, goldens match the manifest'}"
    )
    for problem in problems:
        print(f"  {problem}")
    return EXIT_VERIFY if problems else code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
