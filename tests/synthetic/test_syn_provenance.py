"""SYNTHETIC tests of the manifest receipt, the audit directory, the Python-version policy and the
manifest refresh (--refresh-manifest). The refresh tests work on temporary copies only; the accepted
golden files, the real manifest and the real audit directory are only read.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import platform
import re
import shutil

import pytest

from synthetic_support import (
    ARCHIVE_DIR,
    AUDIT_DIR,
    CANONICALIZATION,
    GOLDEN_FILE_NAMES,
    LEGACY_SOURCE_FILES,
    MANIFEST_NAME,
    RECEIPT_NAME,
    REQUIRED_RECEIPT_KEYS,
    TOOLS_DIR,
    combined_digest,
    current_provenance,
    dump_summary,
    MANIFEST_PATH,
    golden_write_guard,  # noqa: F401
    load_manifest,
    provenance_warnings,
    read_golden,
    source_provenance,
    verify_provenance,
    verify_receipt,
)


def _load_recorder():
    spec = importlib.util.spec_from_file_location("syn_record_goldens_prov", TOOLS_DIR / "record_goldens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_golden_dir(dst):
    """A temporary copy of the accepted goldens. The legacy provenance block embedded in the accepted
    summary names the nine production files of the original recording; once any of them changes it can
    never match again, so the COPY's block is re-embedded for the current files (the accepted file on
    disk is never touched). Everything else, grid and episodes included, is a byte copy."""
    dst.mkdir(parents=True, exist_ok=True)
    for key, fname in GOLDEN_FILE_NAMES.items():
        (dst / fname).write_bytes(read_golden(key).encode("utf-8"))
    summary = dst / GOLDEN_FILE_NAMES["summary"]
    doc = json.loads(summary.read_text(encoding="utf-8"))
    doc["provenance"] = {
        **source_provenance(LEGACY_SOURCE_FILES),
        "python_version": platform.python_version(),
        "recorded_by": "test copy: legacy block re-embedded for the current source files",
    }
    summary.write_bytes(dump_summary(doc).encode("utf-8"))
    return dst


def _tree(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.rglob("*")) if p.is_file()}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Canonicalization, Python-version policy, recorded dependencies
# ---------------------------------------------------------------------------
def test_canonicalization_declaration_matches_the_implemented_rule():
    assert load_manifest()["canonicalization"] == CANONICALIZATION
    # independent re-statement of the rule: sorted "<path>:<hex>" lines, LF-joined, no trailing LF
    files = {"b.py": "bb", "a.py": "aa"}
    assert combined_digest(files) == hashlib.sha256(b"a.py:aa\nb.py:bb").hexdigest()


def test_the_manifest_records_third_party_versions_including_requests_and_dotenv():
    deps = load_manifest()["provenance"]["dependencies"]
    assert {"pydantic", "pydantic_core", "pytest", "requests", "python-dotenv"} <= set(deps)
    assert all(re.fullmatch(r"\d+(\.\d+)*\S*", v) for v in deps.values())


def test_a_python_patch_difference_warns_and_a_minor_difference_fails():
    manifest = copy.deepcopy(load_manifest())
    major, minor, patch = platform.python_version().split(".")[:3]
    manifest["provenance"]["python_version"] = f"{major}.{minor}.{int(patch) + 1}"
    assert verify_provenance(manifest) == []
    assert any("patch version differs" in w for w in provenance_warnings(manifest))
    manifest["provenance"]["python_version"] = f"{major}.{int(minor) + 1}.0"
    assert any("major.minor differs" in p for p in verify_provenance(manifest))


def test_a_changed_dependency_version_only_warns():
    manifest = copy.deepcopy(load_manifest())
    manifest["provenance"]["dependencies"]["requests"] = "0.0.1"
    assert verify_provenance(manifest) == []
    assert any("dependency requests differs" in w for w in provenance_warnings(manifest))


# ---------------------------------------------------------------------------
# Receipt and audit directory (real files, read only)
# ---------------------------------------------------------------------------
def test_receipt_is_consistent_with_the_manifest_and_the_archive():
    assert verify_receipt() == []
    receipt = json.loads((AUDIT_DIR / RECEIPT_NAME).read_text(encoding="utf-8"))
    assert "not an independent trust anchor" in receipt["note"]


def test_audit_directory_holds_only_the_receipt_and_archived_manifests():
    found = sorted(p.relative_to(AUDIT_DIR).as_posix() for p in AUDIT_DIR.rglob("*") if p.is_file())
    assert all(f == RECEIPT_NAME or re.fullmatch(r"manifests/golden_manifest\.[0-9a-f]{64}\.json", f) for f in found), found
    assert not (AUDIT_DIR / "replaced").exists()  # goldens have never been replaced


def _real_audit_paths():
    return MANIFEST_PATH, AUDIT_DIR / RECEIPT_NAME, ARCHIVE_DIR


def _copy_audit(tmp_path):
    real_manifest, real_receipt, real_archive = _real_audit_paths()
    manifest = tmp_path / MANIFEST_NAME
    receipt = tmp_path / "audit" / RECEIPT_NAME
    archive = tmp_path / "audit" / "manifests"
    archive.mkdir(parents=True)
    shutil.copyfile(real_manifest, manifest)
    shutil.copyfile(real_receipt, receipt)
    for p in real_archive.glob("*.json"):
        shutil.copyfile(p, archive / p.name)
    return manifest, receipt, archive


def test_receipt_tampering_is_detected(tmp_path):
    manifest, receipt, archive = _copy_audit(tmp_path)
    assert verify_receipt(manifest, receipt, archive) == []
    original = json.loads(receipt.read_text(encoding="utf-8"))

    def broken(**changes):
        receipt.write_text(json.dumps({**original, **changes}), encoding="utf-8")
        return verify_receipt(manifest, receipt, archive)

    assert broken(manifest_sha256="0" * 64)
    assert broken(goldens_digest="0" * 64)
    assert broken(source_digest="0" * 64)
    assert broken(fixture_digest="0" * 64)
    assert broken(helper_digest="0" * 64)
    assert broken(previous_manifest_sha256="1" * 64)  # no such archived manifest
    for key in REQUIRED_RECEIPT_KEYS:
        trimmed = {k: v for k, v in original.items() if k != key}
        receipt.write_text(json.dumps(trimmed), encoding="utf-8")
        assert verify_receipt(manifest, receipt, archive), key
    receipt.write_text(json.dumps(original), encoding="utf-8")
    victim = archive / f"golden_manifest.{original['previous_manifest_sha256']}.json"
    victim.write_text("altered", encoding="utf-8")
    assert verify_receipt(manifest, receipt, archive)
    victim.unlink()
    assert verify_receipt(manifest, receipt, archive)
    receipt.unlink()
    assert verify_receipt(manifest, receipt, archive) == ["manifest receipt is missing"]


# ---------------------------------------------------------------------------
# --refresh-manifest on temporary copies
# ---------------------------------------------------------------------------
def _drifted_manifest_dir(tmp_path):
    """A golden directory whose manifest records stale provenance (as after a legitimate edit)."""
    recorder = _load_recorder()
    gdir = _seed_golden_dir(tmp_path / "golden")
    assert recorder.main(["--manifest-only", "--confirm-authorized"], golden_dir=gdir) == 0
    manifest_path = gdir / MANIFEST_NAME
    stale = json.loads(manifest_path.read_text(encoding="utf-8"))
    stale["provenance"]["helper_digest"] = "0" * 64
    stale["provenance"]["fixture_files"]["README_SYNTHETIC.md"] = "0" * 64
    stale.pop("legacy_embedded_provenance", None)
    manifest_path.write_text(json.dumps(stale, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert verify_provenance(json.loads(manifest_path.read_text(encoding="utf-8")), golden_dir=gdir)  # drift is detected
    return recorder, gdir, manifest_path, _sha(manifest_path)


def _refresh_args(old_sha, reason="authorized documentation edit"):
    return ["--refresh-manifest", "--confirm-authorized", "--reason", reason, "--expect-old-manifest-sha256", old_sha]


def test_refresh_reissues_the_manifest_without_touching_any_golden(tmp_path):
    recorder, gdir, manifest_path, old_sha = _drifted_manifest_dir(tmp_path)
    old_bytes = manifest_path.read_bytes()
    goldens = {n: _sha(gdir / n) for n in GOLDEN_FILE_NAMES.values()}
    assert recorder.main(_refresh_args(old_sha), golden_dir=gdir) == 0
    assert {n: _sha(gdir / n) for n in GOLDEN_FILE_NAMES.values()} == goldens
    new = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert verify_provenance(new, golden_dir=gdir) == []
    assert new["provenance"] == current_provenance()
    assert new["previous_manifest_sha256"] == old_sha and new["reason"].startswith("refresh: ")
    audit = gdir.parent / "audit"
    assert (audit / "manifests" / f"golden_manifest.{old_sha}.json").read_bytes() == old_bytes
    assert verify_receipt(manifest_path, audit / RECEIPT_NAME, audit / "manifests") == []
    assert not (audit / "replaced").exists()
    assert not [p for p in gdir.parent.rglob("*") if ".tmp-" in p.name]


def test_refresh_requires_confirmation_reason_and_the_exact_old_digest(tmp_path):
    recorder, gdir, manifest_path, old_sha = _drifted_manifest_dir(tmp_path)
    before = _tree(gdir.parent)
    assert recorder.main(["--refresh-manifest", "--reason", "x", "--expect-old-manifest-sha256", old_sha], golden_dir=gdir) == 2
    assert recorder.main(_refresh_args(old_sha, reason="   "), golden_dir=gdir) == 2
    assert recorder.main(["--refresh-manifest", "--confirm-authorized", "--reason", "x"], golden_dir=gdir) == 2
    assert recorder.main(_refresh_args("0" * 64), golden_dir=gdir) == 3
    assert recorder.main(_refresh_args(old_sha) + ["--replace"], golden_dir=gdir) == 2
    assert _tree(gdir.parent) == before


def test_refresh_refuses_when_a_golden_differs_from_the_old_manifest(tmp_path):
    recorder, gdir, manifest_path, old_sha = _drifted_manifest_dir(tmp_path)
    episodes = gdir / GOLDEN_FILE_NAMES["episodes"]
    lines = episodes.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[2], lines[3] = lines[3], lines[2]
    episodes.write_text("".join(lines), encoding="utf-8")
    before = _tree(gdir.parent)
    assert recorder.main(_refresh_args(old_sha), golden_dir=gdir) == 3
    assert _tree(gdir.parent) == before


def test_refresh_stops_when_the_rederived_goldens_differ_even_if_the_manifest_agrees(tmp_path):
    recorder, gdir, manifest_path, _ = _drifted_manifest_dir(tmp_path)
    episodes = gdir / GOLDEN_FILE_NAMES["episodes"]
    lines = episodes.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[2], lines[3] = lines[3], lines[2]
    episodes.write_text("".join(lines), encoding="utf-8")
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["goldens"][GOLDEN_FILE_NAMES["episodes"]] = _sha(episodes)  # the old manifest now records the altered file
    doc["goldens_digest"] = combined_digest(doc["goldens"])
    manifest_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = _tree(gdir.parent)
    assert recorder.main(_refresh_args(_sha(manifest_path)), golden_dir=gdir) == 3
    assert _tree(gdir.parent) == before  # nothing archived, nothing replaced
    assert not (gdir.parent / "audit" / "manifests").exists()


def test_an_identical_existing_archive_is_accepted_and_a_different_one_is_refused(tmp_path):
    recorder, gdir, manifest_path, old_sha = _drifted_manifest_dir(tmp_path)
    archive_dir = gdir.parent / "audit" / "manifests"
    archive_dir.mkdir(parents=True)
    archive = archive_dir / f"golden_manifest.{old_sha}.json"
    archive.write_bytes(b"different content")
    before = _tree(gdir.parent)
    assert recorder.main(_refresh_args(old_sha), golden_dir=gdir) == 3
    assert _tree(gdir.parent) == before
    archive.write_bytes(manifest_path.read_bytes())
    assert recorder.main(_refresh_args(old_sha), golden_dir=gdir) == 0
    assert verify_provenance(json.loads(manifest_path.read_text(encoding="utf-8")), golden_dir=gdir) == []


def test_refresh_dry_run_checks_everything_and_writes_nothing(tmp_path):
    recorder, gdir, manifest_path, old_sha = _drifted_manifest_dir(tmp_path)
    before = _tree(gdir.parent)
    assert recorder.main(["--refresh-manifest", "--dry-run", "--reason", "x", "--expect-old-manifest-sha256", old_sha], golden_dir=gdir) == 0
    assert _tree(gdir.parent) == before


def test_refresh_and_replace_are_separate_operations_in_the_tool():
    source = (TOOLS_DIR / "record_goldens.py").read_text(encoding="utf-8")
    refresh = source[source.index("def _refresh("): source.index("def main(")]
    assert "args.replace" not in refresh and "manifest_only" not in refresh
    assert "_write_replacing(path" not in refresh and "_write_new(path" not in refresh  # no golden is ever written
