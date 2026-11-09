SYNTHETIC FIXTURES - NOT RESEARCH DATA

# Synthetic fixtures for MAPS software tests (WP2)

Everything under `tests/synthetic/` is invented from scratch for software testing. None of it is
derived from, copied from, or paraphrased from any real MAPS scenario, evidence document, truth
assignment, identifier, result or reviewer record. The truth labels in these fixtures are
arbitrary and have no relation to any real scenario. Nothing here is research evidence, pilot
output, or a model result.

## Contents

- `scenarios/` - four synthetic scenarios (`syn-p1-a`, `syn-p1-b`, `syn-p2-a`, `syn-p2-b`), two matched pairs.
- `evidence/` - one synthetic evidence document per scenario.
- `config_synthetic.json` - synthetic experiment configuration (synthetic model ids, API disabled).
- `golden/` - the three accepted golden files (`grid.tsv`, `episodes.jsonl`, `run_summary.json`) and
  `golden_manifest.json`, which records their hashes and the provenance they were verified against.
- `../audit/` - archived previous manifests and `manifest_receipt.json` (outside the digest sets).
- `../tools/` - the golden recorder, the write guard, the guarded pytest launcher and the wrapper.
  None of these files is collected by pytest.

## Rules

1. Tests in this directory use explicit paths under this directory only. They never read any
   production data, results, review material, key or secret.
2. Execution is mock-only. There are no API calls and no network access.
3. Run outputs go to temporary directories only.
4. Routine tests only READ the golden files. Recording, manifest refresh and replacement are
   separate, explicitly authorized operations performed by `tools/record_goldens.py` (see its
   docstring). Nothing in a pytest run regenerates or overwrites a golden file. To change a golden
   file, an approved interface change and a reviewed diff are required.
5. Goldens characterize current behaviour (stability); they do not show that behaviour is correct.
   Correctness-relevant facts are asserted separately against independently derived values.

## Provenance

`golden/golden_manifest.json` is the authoritative provenance record (digest format version 1,
SHA-256). It lists the golden hashes and the digests of three input sets:

- the source files (the 12 `src/maps` files in the import closure of a mock run),
- the fixture files (every file under `tests/synthetic/data` except `golden/`, including this README),
- the helper file `tests/synthetic/synthetic_support.py`.

Routine verification fails closed when a required field is missing, the digest format version or the
canonicalization declaration is unknown, a file is added, removed or changed, a golden hash differs,
or the Python major.minor version differs from the recorded one. A Python patch-version difference or
a changed dependency version only produces a warning. The summary golden still carries a legacy
embedded provenance block (nine source files); it is ignored by verification and is not authoritative.

Known limits of the import-closure check: it follows absolute and relative `maps` imports by static
inspection and rejects `__import__`, `importlib`-style loading and similar markers, but it cannot see
runtime file reads, environment variables, third-party package contents (only their versions are
recorded) or code reached by other dynamic means.

`../audit/manifest_receipt.json` repeats the manifest's digests and its own sha256. It is an
in-repository consistency aid, not an independent trust anchor. For stronger anchoring, record the
manifest sha256 outside the repository.

Because this README is part of the fixture digest, editing it (or the helper file) makes verification
fail until the manifest is re-issued with `record_goldens.py --refresh-manifest`. That operation never
rewrites a golden file.

## Invocation

Routine synthetic verification (guarded launcher for collection and execution, scope check, no cache):

    PYTHONDONTWRITEBYTECODE=1 python tests/synthetic/tools/run_synthetic.py

Do not use `.venv/bin/pytest` (its launcher is stale); a bare `pytest` is not the synthetic invocation.
Setting `PYTHONDONTWRITEBYTECODE=1` keeps bytecode files out of the tree.

## Write protection and its limits

The launcher installs a preventive in-process guard before pytest is imported. It blocks supported
mutating operations on the golden and audit directories, and subprocess creation, before they run,
and it verifies the hashes afterwards. This is a Python-level guard, not filesystem security: native
extensions, ctypes, inherited file descriptors, `os.open` with `dir_fd`, other processes and other
bypasses remain outside its protection. A bare `pytest` run is not guarded.
