"""SYNTHETIC mock-run tests: output structure, goldens, provenance, reproducibility, isolation (no real data).

Routine tests only READ golden files. Recording is a separate, explicitly authorized operation
(tools/record_goldens.py), and the module-wide write guard fails any test module that modifies the
golden directory.
"""

from __future__ import annotations

import ast
import hashlib
import json
import warnings
from pathlib import Path

import pytest

from maps.config import config_hash
from maps.experiments.receiver import build_grid
from maps.mock_client import MockClient
from maps.prompts.receiver import PROMPT_VERSION
from maps.schemas import CallRecord, EpisodeResult

from synthetic_support import (  # noqa: F401
    EVID_DIR,
    GOLDEN_DIR,
    GOLDEN_FILE_NAMES,
    HELPER_FILES,
    SOURCE_FILES,
    SYN_ROOT,
    TOOLS_DIR,
    build_run_summary,
    compare_golden,
    dump_summary,
    fixture_hashes,
    forbidden_opened,
    golden_write_guard,
    load_manifest,
    provenance_warnings,
    read_golden,
    read_jsonl,
    record_file_opens,
    run_mock_experiment,
    syn_cfg,
    syn_scenarios,
    verify_provenance,
)
from maps.scenarios import REPO_ROOT

FAKE_SECRET = "SYN-FAKE-SECRET-NOT-A-KEY-0001"


@pytest.fixture(scope="module")
def mock_run(tmp_path_factory, syn_cfg, syn_scenarios):
    before = fixture_hashes()
    out = tmp_path_factory.mktemp("syn_run_a")
    _, _, results = run_mock_experiment(out, cfg=syn_cfg, scenarios=syn_scenarios)
    after = fixture_hashes()
    return {"out": out, "results": results, "before": before, "after": after}


# ---------------------------------------------------------------------------
# Structure of one mock run
# ---------------------------------------------------------------------------
def test_run_writes_the_expected_files_and_counts(mock_run):
    out = mock_run["out"]
    for name in ("manifest.json", "calls.jsonl", "episodes.jsonl", "summary.json", "contrast_gaps.json"):
        assert (out / name).is_file(), name
    assert len(read_jsonl(out / "calls.jsonl")) == 96
    assert len(read_jsonl(out / "episodes.jsonl")) == 96
    assert all(r.status == "ok" for r in mock_run["results"])


def test_manifest_fields(mock_run, syn_cfg, syn_scenarios):
    m = json.loads((mock_run["out"] / "manifest.json").read_text(encoding="utf-8"))
    assert m["client"] == "mock" and m["synthetic_mock_data"] is True
    assert m["stage"] == "pilot" and m["n_episodes"] == 96
    assert m["evidence_visible_to_receiver"] is False
    assert m["prompt_version"] == PROMPT_VERSION
    assert m["model_ids"] == [mm.model_id for mm in syn_cfg.models]
    assert m["config_hash"] == config_hash(syn_cfg)
    assert set(m["scenarios"]) == {s.scenario_id for s in syn_scenarios}
    for s in syn_scenarios:
        entry = m["scenarios"][s.scenario_id]
        assert entry["status"] == "draft" and entry["evidence_verification"] == "unverified"
        doc = (EVID_DIR / f"{s.scenario_id}.md").read_bytes()
        assert entry["evidence_sha256_actual"] == hashlib.sha256(doc).hexdigest()


def test_call_records_are_complete_and_consistent(mock_run, syn_cfg):
    model_ids = {m.model_id for m in syn_cfg.models}
    for line in read_jsonl(mock_run["out"] / "calls.jsonl"):
        rec = CallRecord.model_validate(line)
        assert rec.client == "mock" and rec.requested_model_id in model_ids
        assert rec.response_model_id == rec.requested_model_id
        assert rec.prompt_version == PROMPT_VERSION
        assert rec.total_tokens == rec.prompt_tokens + rec.completion_tokens
        assert rec.latency_s == 0.0 and rec.attempts == 1 and rec.error is None
        assert [m.role for m in rec.messages] == ["system", "user"]
        assert set(rec.params) == {"temperature", "max_tokens", "seed"}


def test_episode_rows_validate_and_follow_grid_order(mock_run, syn_cfg, syn_scenarios):
    rows = [EpisodeResult.model_validate(r) for r in read_jsonl(mock_run["out"] / "episodes.jsonl")]
    grid = build_grid(syn_cfg, syn_scenarios)
    assert [r.spec.episode_id for r in rows] == [s.episode_id for s in grid]


def test_summary_and_contrast_gap_shapes(mock_run):
    summary = json.loads((mock_run["out"] / "summary.json").read_text(encoding="utf-8"))
    gaps = json.loads((mock_run["out"] / "contrast_gaps.json").read_text(encoding="utf-8"))
    assert len(summary) == 2 * 2 * 6 * 2 == 48
    for row in summary:
        assert row["n_episodes"] == 2 and row["n_valid"] == 2 and row["n_invalid"] == 0
        if row["condition_id"] == "C0":
            assert row["mean_corroboration_inflation"] is None and row["mean_root_count_error"] is None
        assert (row["false_claim_acceptance_rate"] is None) == (row["truth_status"] == "true")
        assert (row["correct_claim_rejection_rate"] is None) == (row["truth_status"] == "false")
    assert len(gaps) == 2 * 2 * 2 * 2 == 16
    assert {g["contrast"] for g in gaps} == {"C4-C2", "C5-C3"}
    assert all(g["n_pairs"] == 2 and g["n_unmatched"] == 0 for g in gaps)


def test_fixtures_are_unchanged_by_a_run(mock_run):
    assert mock_run["before"] == mock_run["after"]


def test_outputs_stay_in_the_temporary_directory(mock_run):
    out = mock_run["out"]
    assert SYN_ROOT.resolve() not in out.resolve().parents
    assert all(out.resolve() in p.resolve().parents for p in out.iterdir())


# ---------------------------------------------------------------------------
# Goldens: read-only comparison against the accepted files
# ---------------------------------------------------------------------------
def test_episodes_match_recorded_golden(mock_run):
    actual = (mock_run["out"] / "episodes.jsonl").read_text(encoding="utf-8")
    diff = compare_golden("episodes", read_golden("episodes"), actual)
    assert diff is None, diff


def test_run_summary_matches_recorded_golden(mock_run):
    actual = dump_summary(build_run_summary(mock_run["out"], include_provenance=False))
    diff = compare_golden("summary", read_golden("summary"), actual)
    assert diff is None, diff


def test_two_runs_are_identical_after_normalization(mock_run, tmp_path):
    run_mock_experiment(tmp_path / "second")
    first, second = mock_run["out"], tmp_path / "second"
    assert (first / "episodes.jsonl").read_text(encoding="utf-8") == (second / "episodes.jsonl").read_text(encoding="utf-8")
    a = build_run_summary(first, include_provenance=False)
    b = build_run_summary(second, include_provenance=False)
    assert a == b


# ---------------------------------------------------------------------------
# Golden manifest and provenance (fail closed)
# ---------------------------------------------------------------------------
def test_golden_manifest_verifies_against_current_state():
    manifest = load_manifest()
    problems = verify_provenance(manifest)
    assert problems == [], problems
    for message in provenance_warnings(manifest):  # patch-version / dependency differences only warn
        warnings.warn(message, stacklevel=1)


def test_golden_directory_holds_exactly_the_recorded_files():
    names = sorted(p.name for p in GOLDEN_DIR.iterdir())
    assert names == sorted([*GOLDEN_FILE_NAMES.values(), "golden_manifest.json"])


def test_provenance_inputs_are_lf_only():
    paths = [REPO_ROOT / "src" / "maps" / rel for rel in SOURCE_FILES] + [SYN_ROOT / rel for rel in HELPER_FILES]
    assert all(b"\r" not in p.read_bytes() for p in paths)


def _maps_module_files(tree: ast.AST, rel: str = "") -> set[str]:
    """src/maps files implied by the absolute AND relative `maps` imports in a parsed module.

    `rel` is the module's own path relative to src/maps; it is needed to resolve relative imports."""
    src = REPO_ROOT / "src" / "maps"
    package = list(Path(rel).parent.parts) if rel else []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if not node.module or node.module.split(".")[0] != "maps":
                    continue
                base = node.module.split(".")[1:]
            else:
                up = node.level - 1
                if up > len(package):
                    continue
                base = package[: len(package) - up] + (node.module.split(".") if node.module else [])
            candidates = [base] + [base + [alias.name] for alias in node.names]
        elif isinstance(node, ast.Import):
            candidates = [a.name.split(".")[1:] for a in node.names if a.name.split(".")[0] == "maps"]
        else:
            continue
        for parts in candidates:
            for k in range(len(parts) + 1):
                prefix = parts[:k]
                package_init = "/".join([*prefix, "__init__.py"])
                if (src / package_init).is_file():
                    found.add(package_init)
                if prefix and k == len(parts) and (src / ("/".join(prefix) + ".py")).is_file():
                    found.add("/".join(prefix) + ".py")
    return found


_DYNAMIC_MODULES = {"importlib", "runpy", "pkgutil", "imp"}
_DYNAMIC_CALLS = {"__import__", "exec", "eval"}


def _dynamic_import_markers(tree: ast.AST) -> list[str]:
    """Markers of code loading that the static closure cannot follow."""
    markers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            markers += [f"import {a.name}" for a in node.names if a.name.split(".")[0] in _DYNAMIC_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] in _DYNAMIC_MODULES:
            markers.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") in _DYNAMIC_CALLS:
            markers.append(f"call to {node.func.id}")
    return markers


def test_source_set_covers_the_static_import_closure():
    """Every `maps` module imported (transitively) by the recorded sources is itself recorded.

    Static inspection of non-sensitive production sources only. Absolute and relative imports are
    followed. Known limits (documented in README_SYNTHETIC.md): dynamic loading is only detected by
    markers (`__import__`, `exec`, `eval`, importlib/runpy/pkgutil), and runtime file reads,
    environment variables and the contents of third-party packages are not covered by the source
    digest (only the recorded dependency versions)."""
    base = REPO_ROOT / "src" / "maps"
    recorded = set(SOURCE_FILES)
    closure: set[str] = set()
    pending = ["experiments/receiver.py", "mock_client.py", "prompts/receiver.py"]
    while pending:
        rel = pending.pop()
        if rel in closure:
            continue
        closure.add(rel)
        tree = ast.parse((base / rel).read_text(encoding="utf-8"))
        assert _dynamic_import_markers(tree) == [], rel
        pending += sorted(_maps_module_files(tree, rel) - closure)
    missing = sorted(closure - recorded)
    assert missing == [], f"imported but not recorded: {missing}"
    for rel in SOURCE_FILES:  # also scan the remaining recorded files for unrecorded imports
        tree = ast.parse((base / rel).read_text(encoding="utf-8"))
        assert _dynamic_import_markers(tree) == [], rel
        assert _maps_module_files(tree, rel) <= recorded, rel


def test_closure_check_resolves_relative_imports():
    tree = ast.parse("from . import metrics\nfrom ..schemas import PromptVariant\nfrom .metrics import summarize\n")
    assert _maps_module_files(tree, "experiments/receiver.py") == {
        "__init__.py", "experiments/__init__.py", "experiments/metrics.py", "schemas.py",
    }
    assert _maps_module_files(ast.parse("from . import schemas\n"), "mock_client.py") == {"__init__.py", "schemas.py"}
    assert _maps_module_files(ast.parse("from .... import nothing\n"), "mock_client.py") == set()  # beyond the package


def test_closure_check_flags_dynamic_loading_markers():
    assert _dynamic_import_markers(ast.parse("x = __import__('maps.llm_client')")) == ["call to __import__"]
    assert _dynamic_import_markers(ast.parse("import importlib\nfrom runpy import run_path\nexec('1')")) == [
        "import importlib", "from runpy import ...", "call to exec",
    ]
    assert _dynamic_import_markers(ast.parse("import json\nfrom maps import schemas\n")) == []


# ---------------------------------------------------------------------------
# Golden-write guards (static scan of routine test code)
# ---------------------------------------------------------------------------
_GOLDEN_NAMES = {"GOLDEN_DIR", "GOLDEN_FILES", "MANIFEST_PATH", "AUDIT_DIR", "ARCHIVE_DIR", "RECEIPT_PATH"}
_PATH_WRITE_ATTRS = {
    "write_text", "write_bytes", "mkdir", "touch", "unlink", "rename", "replace", "chmod", "rmdir",
    "symlink_to", "hardlink_to", "truncate",
}
_OS_WRITE_ATTRS = {
    "remove", "rename", "replace", "unlink", "rmdir", "mkdir", "makedirs", "chmod", "truncate", "link",
    "symlink", "utime",
}


def _writes_in(node: ast.AST) -> list[str]:
    bad = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Attribute):
            owner = func.value.id if isinstance(func.value, ast.Name) else None
            if owner == "shutil" or (owner == "os" and func.attr in _OS_WRITE_ATTRS) or func.attr in _PATH_WRITE_ATTRS:
                bad.append(func.attr)
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name == "open":
            mode = None
            if len(sub.args) > 1 and isinstance(sub.args[1], ast.Constant):
                mode = sub.args[1].value
            elif len(sub.args) == 1 and isinstance(func, ast.Attribute) and isinstance(sub.args[0], ast.Constant):
                mode = sub.args[0].value
            for kw in sub.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = kw.value.value
            if isinstance(mode, str) and any(c in mode for c in "wax+"):
                bad.append("open(" + mode + ")")
    return bad


def _mentions_golden_paths(node: ast.AST) -> bool:
    return any(
        (isinstance(n, ast.Name) and n.id in _GOLDEN_NAMES) or (isinstance(n, ast.Attribute) and n.attr in _GOLDEN_NAMES)
        for n in ast.walk(node)
    )


def test_routine_test_code_has_no_write_path_to_the_golden_directory():
    sources = sorted(SYN_ROOT.glob("test_syn_*.py")) + [SYN_ROOT / "synthetic_support.py"]
    assert len(sources) >= 6
    offenders = []
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scopes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        scopes += [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        for scope in scopes:
            if _mentions_golden_paths(scope) and _writes_in(scope):
                offenders.append(f"{path.name}:{getattr(scope, 'name', 'module-level')}")
    assert offenders == [], offenders


def test_recorder_and_wrapper_are_not_collectable_and_stay_separate():
    for name in ("record_goldens.py", "run_synthetic.py"):
        path = TOOLS_DIR / name
        assert path.is_file()
        assert not (path.name.startswith("test_") or path.name.endswith("_test.py"))
    assert not list(TOOLS_DIR.glob("test_*.py")) and not (TOOLS_DIR / "conftest.py").exists()
    recorder = (TOOLS_DIR / "record_goldens.py").read_text(encoding="utf-8")
    assert "--confirm-authorized" in recorder and "--expect-old-manifest-sha256" in recorder
    wrapper = (TOOLS_DIR / "run_synthetic.py").read_text(encoding="utf-8")
    assert "record_goldens" not in wrapper
    assert "--replace" not in wrapper and "import synthetic_support" not in wrapper


# ---------------------------------------------------------------------------
# Failure modes and redaction
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode,status", [("malformed", "parse_error"), ("error", "call_error")])
def test_failed_episodes_are_recorded_and_excluded_from_rates(tmp_path, mode, status):
    _, _, results = run_mock_experiment(tmp_path / mode, client=MockClient(mode))
    assert len(results) == 96 and all(r.status == status for r in results)
    summary = json.loads((tmp_path / mode / "summary.json").read_text(encoding="utf-8"))
    assert all(r["n_valid"] == 0 and r["n_invalid"] == 2 for r in summary)
    assert all(r["mean_confidence"] is None for r in summary)
    assert len(read_jsonl(tmp_path / mode / "calls.jsonl")) == 96


def test_secrets_are_redacted_everywhere(tmp_path):
    payload = json.dumps(
        {
            "accepts_claim": True,
            "confidence": 50,
            "estimated_independent_roots": 1,
            "evidence_used": [],
            "reasoning": f"SYNTHETIC reasoning {FAKE_SECRET}",
        }
    )
    out = tmp_path / "redaction"
    run_mock_experiment(out, client=MockClient("scripted", scripted=[payload]), secrets=[FAKE_SECRET])
    for path in out.iterdir():
        assert FAKE_SECRET not in path.read_text(encoding="utf-8"), path.name
    assert "[REDACTED]" in (out / "episodes.jsonl").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Isolation: no restricted path is opened while a mock run executes
# ---------------------------------------------------------------------------
def test_mock_run_opens_no_restricted_path(tmp_path):
    with record_file_opens() as opened:
        run_mock_experiment(tmp_path / "audited")
        opened = list(opened)
    assert opened, "the audit hook recorded nothing"
    assert any(str(EVID_DIR) in p for p in opened), "hook did not see the synthetic evidence being read"
    assert forbidden_opened(opened) == []
