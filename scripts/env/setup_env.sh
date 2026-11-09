#!/usr/bin/env bash
# Create a NEW Python 3.12 virtual environment for MAPS from requirements.lock.
#
# Usage (exactly one install source is required):
#   bash scripts/env/setup_env.sh <new-venv-dir> --wheelhouse <dir>   # offline: only local wheels, no package index
#   bash scripts/env/setup_env.sh <new-venv-dir> --allow-network      # contacts a package index
#
# Safety:
#   * Nothing is installed and no network is used unless one of the two options above is given;
#     without them the script exits with a usage error before touching anything.
#   * --allow-network is the only way to reach a package index. --wheelhouse must name an existing
#     LOCAL directory (URLs are rejected) and is installed with --no-index --only-binary=:all:.
#   * pip's own version check (which contacts the index) is disabled, and pip never prompts.
#   * It refuses an existing target directory (it never recreates or modifies .venv in place).
#   * If anything fails after the environment directory was created, that directory is removed again.
#   * It never edits requirements files and does not use Git.
# The PYTHON environment variable selects the interpreter (default: python3.12).
set -euo pipefail

usage() {
  echo "usage: $0 <new-venv-dir> (--wheelhouse <local-dir> | --allow-network)" >&2
  exit 2
}

[[ $# -ge 2 ]] || usage
target="$1"; shift
wheelhouse=""
allow_network=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --wheelhouse) [[ $# -ge 2 ]] || usage; wheelhouse="$2"; shift 2 ;;
    --allow-network) allow_network=1; shift ;;
    *) echo "unexpected argument: $1" >&2; usage ;;
  esac
done
if [[ -n "$wheelhouse" && $allow_network -eq 1 ]]; then
  echo "choose either --wheelhouse (offline) or --allow-network, not both" >&2
  exit 2
fi
if [[ -z "$wheelhouse" && $allow_network -eq 0 ]]; then
  echo "refusing: no install source selected (use --wheelhouse <dir> for an offline install or --allow-network)" >&2
  usage
fi
if [[ -n "$wheelhouse" ]]; then
  if [[ "$wheelhouse" == *"://"* ]]; then
    echo "refusing: --wheelhouse must be a local directory, not a URL: $wheelhouse" >&2
    exit 3
  fi
  if [[ ! -d "$wheelhouse" ]]; then
    echo "refusing: wheelhouse is not an existing local directory: $wheelhouse" >&2
    exit 3
  fi
  wheelhouse="$(cd "$wheelhouse" && pwd)"
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON:-python3.12}"

if [[ -e "$target" ]]; then
  echo "refusing: $target already exists (this script only creates new environments)" >&2
  exit 3
fi
if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "interpreter not found: $python_bin (install Python 3.12 or set PYTHON)" >&2
  exit 3
fi
version="$("$python_bin" -c 'import platform; print(platform.python_version())')"
case "$version" in
  3.12.*) ;;
  *) echo "unsupported Python $version: MAPS supports >=3.12,<3.13" >&2; exit 3 ;;
esac
echo "Python $version ($python_bin); recorded in .python-version: $(cat "$repo_root/.python-version")"

created=0
cleanup() {
  status=$?
  if [[ $status -ne 0 && $created -eq 1 && -n "$target" && "$target" != "/" ]]; then
    echo "setup failed (exit $status): removing the partially created environment $target" >&2
    rm -rf -- "$target"
  fi
}
trap cleanup EXIT

export PYTHONDONTWRITEBYTECODE=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1

"$python_bin" -m venv "$target"
created=1
if [[ -n "$wheelhouse" ]]; then
  echo "installing offline from the local wheelhouse $wheelhouse (no package index)" >&2
  "$target/bin/python" -m pip install --no-index --find-links "$wheelhouse" --only-binary=:all: -r "$repo_root/requirements.lock"
else
  echo "installing from the package index (network access explicitly allowed)" >&2
  "$target/bin/python" -m pip install -r "$repo_root/requirements.lock"
fi
"$target/bin/python" "$repo_root/scripts/env/report_environment.py"
created=0
