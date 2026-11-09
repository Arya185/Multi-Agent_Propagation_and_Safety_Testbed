"""Helpers for the SYNTHETIC WP2 fixtures (software tests only; not research data).

Rules for this module:
- Every path is explicit and lives under this directory. Nothing here reads production data.
- Importing this module performs no file reads (paths are computed, never opened).
- Routine tests only READ golden files. Recording is a separate, explicitly authorized
  operation (tools/record_goldens.py); nothing in this module writes golden files.

Provenance specification (digest_format_version 1):
- Algorithm: SHA-256.
- Per-file digest: sha256 of the raw file bytes (no newline, BOM or whitespace normalization).
- Combined digest: sha256 of the UTF-8 text made of the lines "<posix relative path>:<hex digest>",
  sorted by path and joined with "\\n" (no trailing newline).
- Source set: SOURCE_FILES, relative to src/maps (the import closure of the mock run, plus the
  empty package __init__ files). Fixture set: every file under tests/synthetic/data except the
  golden directory. Helper set: HELPER_FILES, relative to tests/synthetic.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sys
from pathlib import Path

import pytest

from maps.config import ExperimentConfig, load_config
from maps.experiments.receiver import build_grid, grid_tsv, run_experiment
from maps.mock_client import MockClient
from maps.scenarios import REPO_ROOT, load_scenario_dir
from maps.schemas import Scenario

# ---------------------------------------------------------------------------
# Paths (all under this directory)
# ---------------------------------------------------------------------------
SYN_ROOT = Path(__file__).resolve().parent
DATA_DIR = SYN_ROOT / "data"
SCEN_DIR = DATA_DIR / "scenarios"
EVID_DIR = DATA_DIR / "evidence"
GOLDEN_DIR = DATA_DIR / "golden"
CONFIG_PATH = DATA_DIR / "config_synthetic.json"
README_PATH = DATA_DIR / "README_SYNTHETIC.md"
TOOLS_DIR = SYN_ROOT / "tools"

EXPECTED_SCENARIO_IDS = ("syn-p1-a", "syn-p1-b", "syn-p2-a", "syn-p2-b")
EVIDENCE_REF_PREFIX = EVID_DIR.relative_to(REPO_ROOT).as_posix() + "/"

GOLDEN_FILE_NAMES = {"grid": "grid.tsv", "episodes": "episodes.jsonl", "summary": "run_summary.json"}
MANIFEST_NAME = "golden_manifest.json"
GOLDEN_FILES = {key: GOLDEN_DIR / fname for key, fname in GOLDEN_FILE_NAMES.items()}
MANIFEST_PATH = GOLDEN_DIR / MANIFEST_NAME

# Audit directory (outside the golden and fixture digest sets): archived manifests and the receipt.
AUDIT_DIR = SYN_ROOT / "audit"
ARCHIVE_DIR = AUDIT_DIR / "manifests"
RECEIPT_NAME = "manifest_receipt.json"
RECEIPT_PATH = AUDIT_DIR / RECEIPT_NAME

# ---------------------------------------------------------------------------
# Provenance specification
# ---------------------------------------------------------------------------
DIGEST_FORMAT_VERSION = 1
DIGEST_ALGORITHM = "sha256"
MANIFEST_FORMAT = 1

# Production sources whose digests are recorded (relative to src/maps). Completeness was checked
# by static import inspection; see test_source_set_covers_the_static_import_closure.
SOURCE_FILES = (
    "__init__.py",
    "adapters/__init__.py",
    "adapters/run_loader.py",
    "config.py",
    "experiments/__init__.py",
    "experiments/metrics.py",
    "experiments/receiver.py",
    "llm_client.py",
    "logging_utils.py",
    "mock_client.py",
    "prompts/__init__.py",
    "prompts/receiver.py",
    "registry.py",
    "runs/__init__.py",
    "runs/artifact_hashes.py",
    "runs/endpoint_policy.py",
    "runs/executor.py",
    "runs/guard.py",
    "runs/ids.py",
    "runs/integrity_report.py",
    "runs/lifecycle.py",
    "runs/live_budget.py",
    "runs/live_executor.py",
    "runs/live_policy.py",
    "runs/policy_source.py",
    "runs/provenance.py",
    "scenarios.py",
    "schemas.py",
    "validation.py",
)
# The nine files covered by the provenance embedded in the originally accepted run_summary.json.
LEGACY_SOURCE_FILES = (
    "config.py",
    "experiments/metrics.py",
    "experiments/receiver.py",
    "llm_client.py",
    "logging_utils.py",
    "mock_client.py",
    "prompts/receiver.py",
    "scenarios.py",
    "schemas.py",
)
HELPER_FILES = ("synthetic_support.py",)
DEPENDENCY_NAMES = ("pydantic", "pydantic_core", "pytest", "requests", "python-dotenv")
CANONICALIZATION = (
    "sha256 over raw file bytes; combined digest = sha256 of UTF-8 lines '<posix relpath>:<hex>' "
    "sorted by path, joined by LF, no trailing LF; digest_format_version 1"
)
REQUIRED_RECEIPT_KEYS = (
    "receipt_format", "note", "manifest_sha256", "goldens_digest", "source_digest", "fixture_digest",
    "helper_digest", "previous_manifest_sha256", "reason", "recorded_by",
)

REQUIRED_PROVENANCE_KEYS = (
    "digest_format_version",
    "digest_algorithm",
    "source_files",
    "source_digest",
    "fixture_files",
    "fixture_digest",
    "helper_files",
    "helper_digest",
    "python_version",
    "dependencies",
)
REQUIRED_MANIFEST_KEYS = ("manifest_format", "canonicalization", "goldens", "goldens_digest", "provenance")

NON_DETERMINISTIC_MANIFEST_KEYS = ("started_utc", "python")
NON_DETERMINISTIC_CALL_KEYS = ("timestamp_utc",)


# ---------------------------------------------------------------------------
# Loaders and fixtures
# ---------------------------------------------------------------------------
def load_syn_config() -> ExperimentConfig:
    return load_config(CONFIG_PATH)


def load_syn_scenarios() -> list[Scenario]:
    return load_scenario_dir(SCEN_DIR)


@pytest.fixture(scope="module")
def syn_cfg() -> ExperimentConfig:
    return load_syn_config()


@pytest.fixture(scope="module")
def syn_scenarios() -> list[Scenario]:
    return load_syn_scenarios()


def fixture_hashes() -> dict[str, str]:
    """sha256 of every file under the synthetic data directory (used to prove immutability)."""
    return {
        p.relative_to(DATA_DIR).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(DATA_DIR.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# Independent oracles (re-implemented here on purpose; they must not import the recipe)
# ---------------------------------------------------------------------------
def _digest(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def expected_episode_id(
    experiment_id: str, model_id: str, scenario_id: str, variant: str, condition_id: str, repetition: int
) -> str:
    return "ep_" + _digest(experiment_id, model_id, scenario_id, variant, condition_id, repetition)[:12]


def expected_seed(cfg_seed: int, episode_id: str) -> int:
    return int(_digest(cfg_seed, episode_id)[:8], 16)


# ---------------------------------------------------------------------------
# Normalization (only the non-deterministic fields named in the specification)
# ---------------------------------------------------------------------------
def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def round_floats(obj: object, ndigits: int = 12) -> object:
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, ndigits) for v in obj]
    return obj


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_manifest(manifest: dict) -> dict:
    return {k: v for k, v in manifest.items() if k not in NON_DETERMINISTIC_MANIFEST_KEYS}


def normalize_call(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in NON_DETERMINISTIC_CALL_KEYS}


def calls_digest(path: Path) -> dict:
    lines = [canonical_json(normalize_call(r)) for r in read_jsonl(path)]
    return {"count": len(lines), "normalized_digest": hashlib.sha256("\n".join(lines).encode()).hexdigest()}


def first_difference(expected: str, actual: str, width: int = 100) -> str:
    """Describe the first difference between two texts (synthetic content only)."""
    if expected == actual:
        return "identical"
    for i, (x, y) in enumerate(zip(expected.splitlines(), actual.splitlines()), start=1):
        if x != y:
            return f"first difference at line {i}: expected {x[:width]!r}, got {y[:width]!r}"
    if len(expected.splitlines()) != len(actual.splitlines()):
        return f"line counts differ: expected {len(expected.splitlines())}, got {len(actual.splitlines())}"
    return "texts differ only in line endings or the trailing newline"


def json_first_difference(a: object, b: object, path: str = "$") -> str | None:
    """First structural difference between two JSON values (None if identical, int vs float counts)."""
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        if set(a) != set(b):
            return f"{path}: keys differ ({sorted(set(a) ^ set(b))[:5]})"
        for k in sorted(a):
            d = json_first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = json_first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} vs {b!r}"


# ---------------------------------------------------------------------------
# Mock run and golden artifacts
# ---------------------------------------------------------------------------
def run_mock_experiment(out_dir: Path, client=None, cfg=None, scenarios=None, secrets=None):
    cfg = cfg or load_syn_config()
    scenarios = scenarios or load_syn_scenarios()
    client = client or MockClient()
    results = run_experiment(cfg, scenarios, client, out_dir, secrets)
    return cfg, scenarios, results


# ---------------------------------------------------------------------------
# Digests and provenance
# ---------------------------------------------------------------------------
def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def combined_digest(files: dict[str, str]) -> str:
    text = "\n".join(f"{rel}:{digest}" for rel, digest in sorted(files.items()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_files(base: Path, rels) -> dict:
    files = {rel: file_sha256(Path(base) / rel) for rel in rels}
    return {"files": files, "digest": combined_digest(files)}


def source_provenance(rels=SOURCE_FILES) -> dict:
    d = digest_files(REPO_ROOT / "src" / "maps", rels)
    return {"source_files": d["files"], "source_digest": d["digest"]}


def fixture_file_list() -> list[str]:
    """Every file under the synthetic data directory except the golden directory (posix, sorted)."""
    return sorted(
        p.relative_to(DATA_DIR).as_posix()
        for p in DATA_DIR.rglob("*")
        if p.is_file() and GOLDEN_DIR not in p.parents
    )


def fixture_provenance() -> dict:
    d = digest_files(DATA_DIR, fixture_file_list())
    return {"fixture_files": d["files"], "fixture_digest": d["digest"]}


def helper_provenance() -> dict:
    d = digest_files(SYN_ROOT, HELPER_FILES)
    return {"helper_files": d["files"], "helper_digest": d["digest"]}


def dependency_versions() -> dict[str, str]:
    out = {}
    for name in DEPENDENCY_NAMES:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = "unavailable"
    return out


def current_provenance() -> dict:
    return {
        "digest_format_version": DIGEST_FORMAT_VERSION,
        "digest_algorithm": DIGEST_ALGORITHM,
        **source_provenance(),
        **fixture_provenance(),
        **helper_provenance(),
        "python_version": platform.python_version(),
        "dependencies": dependency_versions(),
    }


def golden_hashes(golden_dir: Path = GOLDEN_DIR) -> dict[str, str]:
    return {fname: file_sha256(Path(golden_dir) / fname) for fname in GOLDEN_FILE_NAMES.values()}


def build_run_summary(out_dir: Path, include_provenance: bool) -> dict:
    manifest = normalize_manifest(json.loads((out_dir / "manifest.json").read_text(encoding="utf-8")))
    doc: dict = {
        "golden_format": 1,
        "synthetic": True,
        "note": "SYNTHETIC golden output of a mock run; values are arbitrary and show stability only.",
        "manifest": round_floats(manifest),
        "summary": round_floats(json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))),
        "contrast_gaps": round_floats(json.loads((out_dir / "contrast_gaps.json").read_text(encoding="utf-8"))),
        "calls": calls_digest(out_dir / "calls.jsonl"),
    }
    if include_provenance:
        doc["provenance"] = {
            **source_provenance(LEGACY_SOURCE_FILES),
            "python_version": platform.python_version(),
            "recorded_by": "legacy embedded provenance",
        }
    return doc


def comparable_summary(doc: dict) -> dict:
    """The summary without the legacy embedded provenance (provenance lives in the manifest)."""
    return {k: v for k, v in doc.items() if k != "provenance"}


def dump_summary(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def compute_golden_artifacts(workdir: Path, include_provenance: bool = False) -> dict:
    cfg = load_syn_config()
    scenarios = load_syn_scenarios()
    grid_text = grid_tsv(build_grid(cfg, scenarios))
    out = Path(workdir) / "golden_run"
    run_mock_experiment(out, cfg=cfg, scenarios=scenarios)
    return {
        "grid": grid_text,
        "episodes": (out / "episodes.jsonl").read_text(encoding="utf-8"),
        "summary": dump_summary(build_run_summary(out, include_provenance)),
    }


def compare_golden(name: str, expected: str, actual: str) -> str | None:
    """Return a description of the first difference, or None if the texts agree for this golden.

    grid and episodes are compared as exact text. The summary is compared as JSON (floats rounded
    to 12 digits, int vs float distinguished, legacy embedded provenance ignored)."""
    if name in ("grid", "episodes"):
        return None if expected == actual else first_difference(expected, actual)
    if name == "summary":
        try:
            e = comparable_summary(json.loads(expected))
            a = comparable_summary(json.loads(actual))
        except ValueError as exc:
            return f"summary is not valid JSON: {exc}"
        return json_first_difference(round_floats(e), round_floats(a))
    raise KeyError(name)


def read_golden(name: str) -> str:
    path = GOLDEN_FILES[name]
    if not path.is_file():
        pytest.fail(f"golden file '{name}' has not been recorded", pytrace=False)
    return path.read_text(encoding="utf-8")


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    if not Path(path).is_file():
        pytest.fail("golden manifest has not been recorded", pytrace=False)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_provenance(manifest: object, golden_dir: Path = GOLDEN_DIR) -> list[str]:
    """Fail-closed provenance check. Returns the list of problems (empty means verified).

    Problems: a missing required field, an unknown manifest or digest format version, an unsupported
    algorithm, a canonicalization declaration that differs from the implemented one, a Python
    major.minor that differs from the recorded one, a source / fixture / helper file added or removed,
    any changed per-file or combined digest, or a golden file whose hash differs from the recorded
    one. A Python patch difference and changed dependency versions are not problems; see
    provenance_warnings()."""
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]
    problems = [f"missing manifest field: {k}" for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    prov = manifest.get("provenance")
    if "provenance" in manifest and not isinstance(prov, dict):
        problems.append("provenance is not an object")
    if isinstance(prov, dict):
        problems += [f"missing provenance field: {k}" for k in REQUIRED_PROVENANCE_KEYS if k not in prov]
    if problems:
        return problems
    if manifest["manifest_format"] != MANIFEST_FORMAT:
        return [f"unknown manifest format: {manifest['manifest_format']!r}"]
    if prov["digest_format_version"] != DIGEST_FORMAT_VERSION:
        return [f"unknown digest format version: {prov['digest_format_version']!r}"]
    if prov["digest_algorithm"] != DIGEST_ALGORITHM:
        return [f"unsupported digest algorithm: {prov['digest_algorithm']!r}"]
    if manifest["canonicalization"] != CANONICALIZATION:
        return ["canonicalization declaration differs from the implemented canonicalization"]
    if not isinstance(prov["python_version"], str) or not isinstance(prov["dependencies"], dict):
        problems.append("python_version / dependencies have the wrong type")
    else:
        recorded_minor = prov["python_version"].split(".")[:2]
        if recorded_minor != platform.python_version().split(".")[:2]:
            problems.append(
                f"Python major.minor differs: recorded {prov['python_version']}, current {platform.python_version()}"
            )

    current = current_provenance()
    for label, files_key, digest_key in (
        ("source", "source_files", "source_digest"),
        ("fixture", "fixture_files", "fixture_digest"),
        ("helper", "helper_files", "helper_digest"),
    ):
        recorded, now = prov[files_key], current[files_key]
        if not isinstance(recorded, dict) or not all(isinstance(v, str) for v in recorded.values()):
            problems.append(f"{label} file record is malformed")
            continue
        added = sorted(set(now) - set(recorded))
        removed = sorted(set(recorded) - set(now))
        if added:
            problems.append(f"{label} file(s) added since recording: {added}")
        if removed:
            problems.append(f"{label} file(s) removed since recording: {removed}")
        changed = sorted(k for k in set(now) & set(recorded) if recorded[k] != now[k])
        if changed:
            problems.append(f"{label} file digest(s) differ: {changed}")
        if combined_digest(recorded) != prov[digest_key]:
            problems.append(f"recorded {label} digest is inconsistent with the recorded file digests")
        if prov[digest_key] != current[digest_key]:
            problems.append(f"{label} digest differs from the current {label} files")

    goldens = manifest["goldens"]
    expected_names = set(GOLDEN_FILE_NAMES.values())
    if not isinstance(goldens, dict) or set(goldens) != expected_names:
        problems.append(f"golden record must name exactly {sorted(expected_names)}")
        return problems
    for fname, recorded_hash in sorted(goldens.items()):
        path = Path(golden_dir) / fname
        if not path.is_file():
            problems.append(f"golden file missing: {fname}")
        elif file_sha256(path) != recorded_hash:
            problems.append(f"golden file hash differs from the manifest: {fname}")
    if combined_digest(goldens) != manifest["goldens_digest"]:
        problems.append("goldens_digest is inconsistent with the recorded golden hashes")
    return problems


def provenance_warnings(manifest: object) -> list[str]:
    """Non-fatal differences: a Python patch-version difference and changed dependency versions."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("provenance"), dict):
        return []
    prov = manifest["provenance"]
    warnings_out = []
    recorded, current = prov.get("python_version"), platform.python_version()
    if isinstance(recorded, str) and recorded != current and recorded.split(".")[:2] == current.split(".")[:2]:
        warnings_out.append(f"Python patch version differs: recorded {recorded}, current {current}")
    recorded_deps = prov.get("dependencies")
    if isinstance(recorded_deps, dict):
        now = dependency_versions()
        for name in sorted(set(recorded_deps) & set(now)):
            if recorded_deps[name] != now[name]:
                warnings_out.append(f"dependency {name} differs: recorded {recorded_deps[name]}, current {now[name]}")
    return warnings_out


def verify_receipt(
    manifest_path: Path = MANIFEST_PATH, receipt_path: Path = RECEIPT_PATH, archive_dir: Path = ARCHIVE_DIR
) -> list[str]:
    """Consistency check between the manifest, its receipt and the archived previous manifest.

    The receipt is an in-repository consistency aid, not an independent trust anchor: anyone who can
    edit the manifest can edit the receipt too. Stronger anchoring means recording the manifest's
    sha256 somewhere outside the repository."""
    manifest_path, receipt_path, archive_dir = Path(manifest_path), Path(receipt_path), Path(archive_dir)
    if not manifest_path.is_file():
        return ["manifest is missing"]
    if not receipt_path.is_file():
        return ["manifest receipt is missing"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"manifest or receipt is not valid JSON: {exc}"]
    if not isinstance(receipt, dict) or not isinstance(manifest, dict) or not isinstance(manifest.get("provenance"), dict):
        return ["manifest or receipt has the wrong shape"]
    problems = [f"missing receipt field: {k}" for k in REQUIRED_RECEIPT_KEYS if k not in receipt]
    if problems:
        return problems
    if receipt["manifest_sha256"] != file_sha256(manifest_path):
        problems.append("receipt manifest_sha256 differs from the manifest file")
    prov = manifest["provenance"]
    for key, value in (
        ("goldens_digest", manifest.get("goldens_digest")),
        ("source_digest", prov.get("source_digest")),
        ("fixture_digest", prov.get("fixture_digest")),
        ("helper_digest", prov.get("helper_digest")),
    ):
        if receipt[key] != value:
            problems.append(f"receipt {key} differs from the manifest")
    previous = receipt["previous_manifest_sha256"]
    if previous is not None:
        archived = archive_dir / f"golden_manifest.{previous}.json"
        if not archived.is_file():
            problems.append("archived previous manifest is missing")
        elif file_sha256(archived) != previous:
            problems.append("archived previous manifest does not match its recorded sha256")
    return problems


# ---------------------------------------------------------------------------
# Audit hook: file-access recording and the golden write guard
# ---------------------------------------------------------------------------
_WATCHERS: list = []
_HOOK_INSTALLED = False
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_MUTATING_EVENTS = frozenset(
    {
        "os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate",
        "os.utime", "os.link", "os.symlink", "shutil.copyfile", "shutil.copymode", "shutil.copystat",
        "shutil.copytree", "shutil.move", "shutil.rmtree",
    }
)


def _audit_hook(event: str, args: tuple) -> None:
    if _WATCHERS:
        for watcher in tuple(_WATCHERS):
            watcher(event, args)


def _install_hook() -> None:
    global _HOOK_INSTALLED
    if not _HOOK_INSTALLED:
        sys.addaudithook(_audit_hook)
        _HOOK_INSTALLED = True


@contextlib.contextmanager
def record_file_opens():
    """Record every path opened (any mode) while the context is active."""
    _install_hook()
    paths: list[str] = []

    def watcher(event: str, args: tuple) -> None:
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            paths.append(os.fsdecode(args[0]))

    _WATCHERS.append(watcher)
    try:
        yield paths
    finally:
        _WATCHERS.remove(watcher)


def _is_write_open(args: tuple) -> bool:
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 else None
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _under_golden_dir(arg: object) -> bool:
    if not isinstance(arg, (str, bytes, os.PathLike)):
        return False
    ap = Path(os.path.abspath(os.fsdecode(arg)))
    return any(ap == root or root in ap.parents for root in (GOLDEN_DIR, AUDIT_DIR))


@pytest.fixture(scope="module", autouse=True)
def golden_write_guard():
    """Module-wide DETECTION (imported into the covered routine test modules): any write-mode open or
    mutating filesystem call on the golden or audit directory makes the module fail at teardown. It
    does not prevent the write; prevention is the launcher-installed guard in tools/write_guard.py.
    Limits: path strings are compared lexically (no symlink, case or dir_fd handling), and it only
    runs while a covered module's tests run."""
    _install_hook()
    violations: list[str] = []

    def watcher(event: str, args: tuple) -> None:
        if not args:
            return
        if event == "open" and _under_golden_dir(args[0]) and _is_write_open(args):
            violations.append(f"open for write: {os.fsdecode(args[0])}")
        elif event in _MUTATING_EVENTS:
            # copying FROM a protected path only reads it: for copy events the destination alone matters
            checked = args[1:2] if event.startswith("shutil.copy") else args
            if any(_under_golden_dir(a) for a in checked):
                violations.append(f"{event}: {[os.fsdecode(a) for a in args if isinstance(a, (str, bytes, os.PathLike))]}")

    _WATCHERS.append(watcher)
    yield violations
    _WATCHERS.remove(watcher)
    assert not violations, f"routine tests must not modify the golden directory: {violations}"


def forbidden_roots() -> list[Path]:
    """Repository areas that synthetic tests must never open (top level only; our own data
    directory lives under tests/ and is not affected)."""
    return [REPO_ROOT / "data", REPO_ROOT / "experiments", REPO_ROOT / "configs", REPO_ROOT / ".env"]


def forbidden_opened(paths: list[str]) -> list[str]:
    roots = forbidden_roots()
    bad = []
    for p in paths:
        ap = Path(os.path.abspath(p))
        if any(ap == r or r in ap.parents for r in roots):
            bad.append(p)
    return bad


def forbidden_source_patterns() -> list[re.Pattern]:
    """Fragments that must not appear in WP2 Python sources (built from parts so this file
    does not contain them literally)."""
    literal_parts = [
        ("answer", "_key"),
        ("experiments", "/plans"),
        ("experiments", "/results"),
        ("configs", "/receiver"),
        ("data", "/review"),
    ]
    patterns = [re.compile(re.escape(a + b)) for a, b in literal_parts]
    patterns.append(re.compile(r"(?<!synthetic/)" + "data" + r"/(?:scenarios|evidence)"))
    return patterns
