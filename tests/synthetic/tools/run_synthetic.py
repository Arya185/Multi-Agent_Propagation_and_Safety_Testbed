"""Dedicated wrapper for the SYNTHETIC test directory (NOT a test; pytest never collects this file).

Both collection and execution go through tools/guarded_pytest.py, which installs the preventive
write guard before pytest is imported. The wrapper (1) collects tests/synthetic only, (2) verifies
that every collected node id lies inside that directory and stops before running anything
otherwise, then (3) runs pytest on tests/synthetic with `-p no:cacheprovider` and
PYTHONDONTWRITEBYTECODE=1. It accepts no paths, no config-file or rootdir overrides, and it never
records or replaces goldens or runs the full suite.

Usage:
  python tests/synthetic/tools/run_synthetic.py [-v|-q] [-x] [-s] [-k EXPRESSION] [--verify-only]

Exit codes: pytest's own code, 4 when collection verification fails, 5 when the launcher's
post-run verification of the golden and audit files fails.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = Path(__file__).resolve().parent / "guarded_pytest.py"
SCOPE = "tests/synthetic"
EXIT_SCOPE = 4
NODE_ID = re.compile(r"^\S+\.py::\S")
COUNT_LINE = re.compile(r"(\d+) tests? collected")


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _launch(pytest_args: list[str], capture: bool = False):
    return subprocess.run(
        [sys.executable, str(LAUNCHER), SCOPE, *pytest_args], cwd=ROOT, env=_env(), capture_output=capture, text=True
    )


def collect_and_verify() -> tuple[int, list[str]]:
    """Return (exit code, node ids). Non-zero exit means the scope check failed."""
    proc = _launch(["--collect-only", "-q", "-p", "no:cacheprovider"], capture=True)
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr)
        print("STOP: collection failed; nothing was executed.")
        return (proc.returncode if proc.returncode == 5 else EXIT_SCOPE), []
    ids = [ln.strip() for ln in proc.stdout.splitlines() if NODE_ID.match(ln.strip())]
    stated = COUNT_LINE.search(proc.stdout)
    outside = [i for i in ids if not i.startswith(SCOPE + "/")]
    if not ids or outside:
        print(f"STOP: out-of-scope or no tests collected: {outside[:5] or 'none collected'}; nothing was executed.")
        return EXIT_SCOPE, ids
    if stated and int(stated.group(1)) != len(ids):
        print(f"STOP: collected count {stated.group(1)} does not match the {len(ids)} node ids parsed; nothing was executed.")
        return EXIT_SCOPE, ids
    return 0, ids


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_synthetic.py", description="Run only the SYNTHETIC tests with collection verification.")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("-x", "--exitfirst", action="store_true")
    p.add_argument("-s", "--show-output", action="store_true", help="do not capture test output")
    p.add_argument("-k", dest="expression", help="pytest -k expression (selects within tests/synthetic)")
    p.add_argument("--verify-only", action="store_true", help="verify collection scope and stop")
    args = p.parse_args(argv)

    print(f"python: {sys.executable} ({platform.python_version()})")
    code, ids = collect_and_verify()
    if code:
        return code
    print(f"collection verified (guarded launcher): {len(ids)} tests, all under {SCOPE}/")
    if args.verify_only:
        return 0

    extra = ["-p", "no:cacheprovider"]
    if args.verbose:
        extra.append("-v")
    if args.quiet:
        extra.append("-q")
    if args.exitfirst:
        extra.append("-x")
    if args.show_output:
        extra.append("-s")
    if args.expression:
        extra += ["-k", args.expression]
    print("running: " + " ".join([sys.executable, str(LAUNCHER), SCOPE, *extra]), flush=True)
    return _launch(extra).returncode


if __name__ == "__main__":
    sys.exit(main())
