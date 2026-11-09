# MAPS environment and reproducibility

Status: updated in the v2.3.13 hardening batch. Commands below that create or change an environment,
or that contact a package index, were **not executed**; only the read-only commands marked "verified"
were run.

## Python policy

- Supported range: `>=3.12,<3.13` (set in `pyproject.toml`).
- `.python-version` records `3.12.16`, the patch version used so far. It is a record, not an
  enforced pin: any 3.12.x is accepted, and every test run should report the exact patch version.
- The synthetic golden manifest additionally fails closed on a Python major.minor mismatch and only
  warns on a patch difference.

## Files

| File | Purpose |
|---|---|
| `requirements.in` | The **direct** dependencies (11 names, unpinned), copied from the original `requirements.txt`. |
| `requirements.lock` | Version snapshot from a local `pip freeze` (see limitations). Direct and transitive pins are not marked in the file; the report classifies them using `requirements.in`. |
| `requirements.txt` | Original unpinned list; left unchanged (it duplicates `requirements.in`). |
| `.python-version` | Recorded interpreter version, `3.12.16`. |
| `scripts/env/report_environment.py` | Prints Python, platform, package and file-hash provenance as JSON (report format 2). Standard library only. |
| `scripts/env/setup_env.sh` | Creates a **new** virtual environment from `requirements.lock`. Requires an explicit install source (see below). |

## Provenance recorded when the report was last run

Taken with `python scripts/env/report_environment.py` (read-only, output to the terminal; verified in v2.3.13):

- Python 3.12.16 (CPython), macOS arm64, inside `/Users/aryapatel/arya/Programming/MAPS/.venv`.
- 41 installed distributions: the 40 pinned packages plus `pip` 26.3. `setuptools` and `wheel` are not installed.
  The 40 pins are 11 direct (all of `requirements.in`) and 29 transitive. The report lists no pin missing,
  no unpinned package other than the bootstrap ones, and no version difference.
- sha256: `requirements.lock` `f1e7ca9d17bc06d1beadd265ebd633c83bd78c29b3c7fac412def0568bb0b09c`,
  `requirements.in` `885faa5e772f0698c1fd2724eb9c84d6fe53a1d8ad97980a6af56a1da85055f4`,
  `.python-version` `a05e0074505ce29f25abf3aebe4f7218d28e98411822f199e3272740be4e363c`,
  `pyproject.toml` `98ba7cb94fb8d209296a76ba2455332b2d74847301372087963fc38edd413cdf`.

### What the report's fields mean

- `versions_match_lock_snapshot` (renamed from `lockfile_in_sync`): true only if every pin is installed at
  the pinned version, nothing unpinned is installed (bootstrap packages excepted) and every direct dependency
  is pinned. **It is a version comparison, not hash verification and not a portability check.**
- `bootstrap_packages`: versions of `pip`, `setuptools` and `wheel`, reported separately. They are not in the
  lock (`pip freeze` omits them) and are not compared with any pin.
- `pinned_packages`: each pin with `kind` = `direct` (named in `requirements.in`) or `transitive`.
- `not_checked`: the things the report does not verify (installed-file hashes, platform/ABI compatibility,
  bootstrap versions, duplicate distributions, transitive resolution, extras/markers/editable installs).

## Running the tests (reproducible invocation)

Use the environment's interpreter with `python -m pytest` or the wrapper, never the `pytest` launcher in
`.venv/bin` (see the stale launcher below). Disable bytecode and the cache so runs leave nothing behind.

```bash
# synthetic fixture suite: guarded launcher for collection AND execution, scope check, no cache
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/synthetic/tools/run_synthetic.py

# analysis-only suite (synthetic planted-effect datasets)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/analysis_synthetic -p no:cacheprovider
```

A bare `pytest` or `python -m pytest` with no path collects every test under `tests/`, including
truth-bearing tests, and is **not** the routine synthetic invocation. The synthetic wrapper installs a
Python-level write guard before pytest is imported; it protects the golden and audit directories and is not
filesystem security (see `tests/synthetic/data/README_SYNTHETIC.md` for its limits).

## Separation of outputs

- Test runs write only to pytest temporary directories; fixtures and goldens are read-only for routine runs.
- Golden recording, manifest refresh and replacement are separate operations
  (`tests/synthetic/tools/record_goldens.py`, each needs `--confirm-authorized`). They never run under pytest.
- Environment reports (`--out`) refuse to write inside `experiments/`, `data/`, `configs/` or `tests/synthetic/`,
  and never overwrite an existing file.

## Creating a fresh environment (not executed)

`setup_env.sh` needs exactly one explicit install source; with neither it exits with a usage error before
creating anything:

```bash
# offline: only local wheels, --no-index --only-binary=:all:
bash scripts/env/setup_env.sh /path/to/new-venv --wheelhouse /path/to/wheels

# contacts a package index; the flag is the explicit opt-in
bash scripts/env/setup_env.sh /path/to/new-venv --allow-network
```

Safeguards: the target directory must not exist; the wheelhouse must be an existing local directory (URLs are
rejected); pip's version check is disabled and pip never prompts; a Python outside 3.12 is refused; if a step
fails after the directory was created, the directory is removed. The script does not alter `.venv` and does not
use Git. It was checked with `bash -n` only (verified); it has never been executed. Even offline installs from
a wheelhouse cannot be hash-verified, because the lock carries no hashes.

## Regenerating the lockfile

The current snapshot came from `PIP_NO_INDEX=1 python -m pip freeze` inside the working environment.
To refresh it deliberately: install or upgrade packages in a *new* environment, run `python -m pip freeze`,
keep the header comment, review the diff, rerun the environment report, then rerun both test suites.
Do not upgrade packages silently, and do not regenerate the lock to make a failing test pass.

## Limitations of the lockfile

- It is a `pip freeze` snapshot: exact versions, **no hashes**, not resolved against an index, and specific to
  this Python version and platform (macOS arm64). Wheels for other platforms may differ or be unavailable.
- Transitive pins are whatever was installed, so the file cannot say *why* a package is present; use
  `requirements.in` and the report's `kind` field.
- Future path to a stronger lockfile (each needs a separate decision and network access): `pip-compile
  --generate-hashes` from `requirements.in`, or `uv lock`.

## Stale launcher in `.venv/bin` (unresolved)

The virtual environment was created at `/Users/aryapatel/MAPS/.venv`, but the project now lives at
`/Users/aryapatel/arya/Programming/MAPS`. 16 of the 20 non-symlink files in `.venv/bin` (including `pytest`,
`pip` and `jsonschema`) start with `#!/Users/aryapatel/MAPS/.venv/bin/python`, which no longer exists, and
`.venv/pyvenv.cfg` records the old creation command (verified in v2.3.12). `.venv/bin/python` works, which is
why `python -m pytest` and `python -m pip` work. Whether `activate` is also stale was not checked.

Options, none of them applied: (1) create a new environment with `setup_env.sh` and switch to it, keeping
`.venv` until the new one passes both suites; (2) recreate `.venv` in place (destructive; avoid unless the new
environment has been verified). A virtual environment is not relocatable, so moving the project directory again
will recreate the problem.

## Recovery

- Tests fail with "bad interpreter": use `python -m pytest` or the wrapper instead of the launcher.
- Environment drift: run `report_environment.py`; compare `snapshot_comparison` and rebuild in a new environment.
- Golden provenance failure: a production source, fixture or helper file changed. Do not edit the golden
  files. Investigate the change; re-issuing the manifest requires explicit authorization and
  `record_goldens.py --refresh-manifest`, which never rewrites a golden.
