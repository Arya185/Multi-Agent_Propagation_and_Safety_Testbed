"""Standalone recorder for the SYNTHETIC golden files (NOT a test; pytest never collects this file).

Recording is an explicitly authorized operation. Routine tests never record, regenerate or overwrite
goldens. This tool works only with the synthetic fixtures and the mock client; it never reads
truth-bearing files and never contacts a network. It runs in its own process, outside the
preventive write guard that protects the golden and audit directories during test runs.

Modes (all require --confirm-authorized, except --dry-run which writes nothing):
  (default)           record grid / episodes / summary, the manifest and its receipt into an EMPTY
                      golden directory. Refuses if any golden file or the manifest already exists.
  --manifest-only     hash the already accepted goldens and write golden_manifest.json (+ receipt).
                      The goldens are re-derived from the current sources in a temporary directory
                      and must agree with the accepted files, and the legacy provenance embedded in
                      the accepted summary must match the current legacy source files.
  --refresh-manifest  replace the manifest WITHOUT touching any golden, after legitimate changes to
                      fixture, helper or source files. Requires --reason and
                      --expect-old-manifest-sha256 (the sha256 of the current manifest file).
                      Order of checks: old manifest digest; the three golden hashes against the old
                      manifest; temporary re-derivation compared byte-for-byte with the accepted
                      goldens (exit 3 on any difference); only then fresh provenance. The old
                      manifest is archived under <audit dir>/manifests/ (an identical existing
                      archive is accepted, a different one is refused), the new manifest is
                      published atomically (os.replace), and the golden bytes are verified again.
  --replace           replace recorded goldens (reviewed behaviour change). Needs --reason and
                      --expect-old-manifest-sha256. Old files are archived under
                      <audit dir>/replaced/<first 12 hex digits of the old manifest digest>/.
                      Never part of --refresh-manifest.

Exit codes: 0 done, 2 usage error, 3 refused or discrepancy found.
The receipt (<audit dir>/manifest_receipt.json) is an in-repository consistency aid, not an
independent trust anchor; record the manifest sha256 outside the repository for stronger anchoring.

Example (after authorized documentation/helper changes):
  PYTHONDONTWRITEBYTECODE=1 python tests/synthetic/tools/record_goldens.py --refresh-manifest \\
      --confirm-authorized --reason "<why>" --expect-old-manifest-sha256 <sha256 of the manifest file>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

SYN_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SYN_ROOT.parents[1]
for _p in (str(REPO_ROOT / "src"), str(SYN_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import synthetic_support as S  # noqa: E402

EXIT_OK, EXIT_USAGE, EXIT_REFUSED = 0, 2, 3
RECEIPT_NOTE = (
    "In-repository consistency aid, not an independent trust anchor: whoever can edit the manifest can "
    "edit this receipt. Stronger anchoring requires recording the manifest sha256 outside the repository."
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="record_goldens.py", description="Record SYNTHETIC goldens (explicit authorization required).")
    p.add_argument("--confirm-authorized", action="store_true", help="required: confirms this operation is explicitly authorized")
    p.add_argument("--manifest-only", action="store_true", help="write only golden_manifest.json for the accepted goldens")
    p.add_argument("--refresh-manifest", action="store_true", help="re-issue the manifest; goldens are verified, never rewritten")
    p.add_argument("--replace", action="store_true", help="replace recorded goldens (needs --reason and --expect-old-manifest-sha256)")
    p.add_argument("--reason", help="why the manifest or goldens are being refreshed or replaced")
    p.add_argument("--expect-old-manifest-sha256", help="sha256 of the manifest file that is being replaced")
    p.add_argument("--dry-run", action="store_true", help="run every check but write nothing")
    return p


def _say(msg: str) -> None:
    print(msg, flush=True)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tmp_sibling(dest: Path) -> Path:
    return dest.with_name(f"{dest.name}.tmp-{os.getpid()}")


def _write_new(dest: Path, data: bytes) -> None:
    """Publish without clobbering: write a sibling temporary file, then hard-link it into place."""
    tmp = _tmp_sibling(dest)
    tmp.write_bytes(data)
    try:
        os.link(tmp, dest)  # FileExistsError if dest exists
    finally:
        tmp.unlink(missing_ok=True)


def _write_replacing(dest: Path, data: bytes) -> None:
    """Atomic publication: write a sibling temporary file, then os.replace it over the destination."""
    tmp = _tmp_sibling(dest)
    tmp.write_bytes(data)
    os.replace(tmp, dest)


def _derive_artifacts() -> dict[str, str]:
    """Re-derive the three golden texts from the current sources in a temporary directory."""
    with tempfile.TemporaryDirectory(prefix="syn_golden_") as tmp:
        return S.compute_golden_artifacts(Path(tmp), include_provenance=False)


def _check_legacy_provenance(summary_text: str) -> tuple[dict | None, str | None]:
    """Compare the provenance embedded in the accepted summary with the current legacy source files."""
    embedded = json.loads(summary_text).get("provenance")
    if embedded is None:
        return None, None
    current = S.source_provenance(S.LEGACY_SOURCE_FILES)
    if embedded.get("source_files") != current["source_files"] or embedded.get("source_digest") != current["source_digest"]:
        return None, "legacy provenance embedded in the accepted summary differs from the current source files"
    return {
        "source_digest": embedded["source_digest"],
        "n_files": len(embedded["source_files"]),
        "python_version": embedded.get("python_version"),
        "matches_current_files": True,
    }, None


def _build_manifest(golden_dir: Path, reason: str, legacy: dict | None, recorded_by: str, previous: str | None = None) -> dict:
    goldens = S.golden_hashes(golden_dir)
    manifest = {
        "manifest_format": S.MANIFEST_FORMAT,
        "synthetic": True,
        "note": "SYNTHETIC golden manifest. Hashes and provenance for the accepted golden files; values show stability only.",
        "recorded_by": recorded_by,
        "reason": reason,
        "canonicalization": S.CANONICALIZATION,
        "goldens": goldens,
        "goldens_digest": S.combined_digest(goldens),
        "provenance": S.current_provenance(),
    }
    if legacy is not None:
        manifest["legacy_embedded_provenance"] = legacy
    if previous is not None:
        manifest["previous_manifest_sha256"] = previous
    return manifest


def _manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _receipt_bytes(manifest_bytes: bytes, manifest: dict, previous: str | None, reason: str, recorded_by: str) -> bytes:
    prov = manifest["provenance"]
    receipt = {
        "receipt_format": 1,
        "note": RECEIPT_NOTE,
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "goldens_digest": manifest["goldens_digest"],
        "source_digest": prov["source_digest"],
        "fixture_digest": prov["fixture_digest"],
        "helper_digest": prov["helper_digest"],
        "previous_manifest_sha256": previous,
        "reason": reason,
        "recorded_by": recorded_by,
    }
    return (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _archive_manifest(audit_dir: Path, old_bytes: bytes) -> str | None:
    """Archive the old manifest. Returns an error message when an archive differs, else None."""
    archive = audit_dir / "manifests" / f"golden_manifest.{_sha256_bytes(old_bytes)}.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        return None if archive.read_bytes() == old_bytes else f"archive exists with different content: {archive.name}"
    _write_new(archive, old_bytes)
    return None


def _golden_bytes(paths: dict[str, Path]) -> dict[str, bytes]:
    return {key: path.read_bytes() for key, path in paths.items()}


def _rederivation_differences(paths: dict[str, Path], before: dict[str, bytes]) -> list[str]:
    """Byte-for-byte comparison of the re-derived goldens with the accepted ones.

    The accepted summary may carry a legacy embedded provenance block; that block is copied from the
    accepted file onto the re-derived document (and checked separately), everything else must match."""
    artifacts = _derive_artifacts()
    differences = []
    for key in ("grid", "episodes"):
        if artifacts[key].encode("utf-8") != before[key]:
            differences.append(f"{key}: re-derived bytes differ from the accepted file")
    doc = json.loads(artifacts["summary"])
    legacy = json.loads(before["summary"].decode("utf-8")).get("provenance")
    if legacy is not None:
        doc["provenance"] = legacy
    if S.dump_summary(doc).encode("utf-8") != before["summary"]:
        differences.append("summary: re-derived bytes differ from the accepted file")
    return differences


def _refresh(args, golden_dir: Path, audit_dir: Path, paths: dict[str, Path], manifest_path: Path) -> int:
    reason = (args.reason or "").strip()
    if not reason or not args.expect_old_manifest_sha256:
        _say("--refresh-manifest requires a non-empty --reason and --expect-old-manifest-sha256")
        return EXIT_USAGE
    if not manifest_path.is_file():
        _say("refusing: --refresh-manifest needs an existing manifest")
        return EXIT_REFUSED
    old_bytes = manifest_path.read_bytes()
    old_sha = _sha256_bytes(old_bytes)
    if old_sha != args.expect_old_manifest_sha256:
        _say(f"refusing: current manifest digest {old_sha} does not equal the expected digest")
        return EXIT_REFUSED
    old = json.loads(old_bytes)
    recorded = old.get("goldens")
    if not isinstance(recorded, dict) or set(recorded) != set(S.GOLDEN_FILE_NAMES.values()):
        _say("refusing: the old manifest does not record exactly the three accepted goldens")
        return EXIT_REFUSED
    for fname, digest in sorted(recorded.items()):
        path = golden_dir / fname
        if not path.is_file() or S.file_sha256(path) != digest:
            _say(f"refusing: accepted golden {fname} differs from the old manifest")
            return EXIT_REFUSED
    before = _golden_bytes(paths)
    differences = _rederivation_differences(paths, before)
    if differences:
        for line in differences:
            _say(f"DISCREPANCY: {line}")
        _say("stopping: a refresh never regenerates goldens; a behaviour change needs a reviewed --replace")
        return EXIT_REFUSED
    legacy, _problem = _check_legacy_provenance(before["summary"].decode("utf-8"))
    if legacy is None and _problem:
        legacy = {"matches_current_files": False, "note": _problem}
    manifest = _build_manifest(golden_dir, f"refresh: {reason}", legacy, "record_goldens.py --refresh-manifest", previous=old_sha)
    new_bytes = _manifest_bytes(manifest)
    receipt = _receipt_bytes(new_bytes, manifest, old_sha, reason, "record_goldens.py --refresh-manifest")
    if args.dry_run:
        _say(f"dry run: refresh checks passed; the golden bytes are re-derived and identical; new manifest would be {_sha256_bytes(new_bytes)}")
        return EXIT_OK
    error = _archive_manifest(audit_dir, old_bytes)
    if error:
        _say(f"refusing: {error}")
        return EXIT_REFUSED
    receipt_path = audit_dir / S.RECEIPT_NAME
    old_receipt = receipt_path.read_bytes() if receipt_path.exists() else None
    _write_replacing(manifest_path, new_bytes)
    _write_replacing(receipt_path, receipt)
    problems = S.verify_provenance(json.loads(new_bytes), golden_dir=golden_dir)
    if _golden_bytes(paths) != before:
        problems.append("golden bytes changed during the refresh")
    if problems:
        _write_replacing(manifest_path, old_bytes)
        if old_receipt is not None:
            _write_replacing(receipt_path, old_receipt)
        else:
            receipt_path.unlink(missing_ok=True)
        for line in problems:
            _say(f"POST-CHECK FAILED: {line}")
        _say("the previous manifest was restored")
        return EXIT_REFUSED
    _say(f"refreshed the manifest; old manifest {old_sha} archived; new manifest {_sha256_bytes(new_bytes)}; goldens unchanged")
    return EXIT_OK


def main(argv: list[str] | None = None, *, golden_dir: Path | None = None, audit_dir: Path | None = None) -> int:
    golden_dir = Path(golden_dir) if golden_dir is not None else S.GOLDEN_DIR
    if audit_dir is not None:
        audit_dir = Path(audit_dir)
    elif golden_dir == S.GOLDEN_DIR:
        audit_dir = S.AUDIT_DIR
    else:
        audit_dir = golden_dir.parent / "audit"  # never default to the real audit directory for a custom golden directory
    manifest_path = golden_dir / S.MANIFEST_NAME
    receipt_path = audit_dir / S.RECEIPT_NAME
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:  # argparse usage errors
        return int(exc.code or 0)

    chosen = [args.manifest_only, args.refresh_manifest, args.replace]
    if sum(bool(c) for c in chosen) > 1:
        _say("--manifest-only, --refresh-manifest and --replace are mutually exclusive")
        return EXIT_USAGE
    if args.replace and not (args.reason and args.expect_old_manifest_sha256):
        _say("--replace requires --reason and --expect-old-manifest-sha256")
        return EXIT_USAGE
    if not args.dry_run and not args.confirm_authorized:
        _say("refusing: --confirm-authorized is required (recording is an explicitly authorized operation)")
        return EXIT_USAGE

    paths = {key: golden_dir / fname for key, fname in S.GOLDEN_FILE_NAMES.items()}
    existing = [key for key, path in paths.items() if path.exists()]

    if args.refresh_manifest:
        return _refresh(args, golden_dir, audit_dir, paths, manifest_path)

    if args.replace:
        if not manifest_path.is_file():
            _say("refusing: --replace needs an existing manifest")
            return EXIT_REFUSED
        old_bytes = manifest_path.read_bytes()
        old_sha = _sha256_bytes(old_bytes)
        if old_sha != args.expect_old_manifest_sha256:
            _say(f"refusing: current manifest digest {old_sha} does not equal the expected digest")
            return EXIT_REFUSED
        artifacts = _derive_artifacts()
        manifest_reason = f"replacement: {args.reason}"
        if args.dry_run:
            _say("dry run: replacement checks passed; nothing written")
            return EXIT_OK
        error = _archive_manifest(audit_dir, old_bytes)
        if error:
            _say(f"refusing: {error}")
            return EXIT_REFUSED
        archive = audit_dir / "replaced" / old_sha[:12]
        if archive.exists():
            _say(f"refusing: archive directory already exists: {archive}")
            return EXIT_REFUSED
        archive.mkdir(parents=True)
        for key, path in paths.items():
            if path.exists():
                (archive / path.name).write_bytes(path.read_bytes())
        for key, path in paths.items():
            _write_replacing(path, artifacts[key].encode("utf-8"))
        manifest = _build_manifest(golden_dir, manifest_reason, None, "record_goldens.py --replace", previous=old_sha)
        new_bytes = _manifest_bytes(manifest)
        _write_replacing(manifest_path, new_bytes)
        _write_replacing(receipt_path, _receipt_bytes(new_bytes, manifest, old_sha, manifest_reason, "record_goldens.py --replace"))
        _say(f"replaced goldens and manifest; previous files archived in {archive}")
        return EXIT_OK

    if manifest_path.exists():
        _say("refusing: a manifest already exists; use --refresh-manifest (provenance only) or --replace (reviewed goldens change)")
        return EXIT_REFUSED

    if args.manifest_only:
        missing = [key for key in paths if key not in existing]
        if missing:
            _say(f"refusing: accepted golden file(s) missing: {missing}")
            return EXIT_REFUSED
        artifacts = _derive_artifacts()
        for key, path in paths.items():
            diff = S.compare_golden(key, path.read_text(encoding="utf-8"), artifacts[key])
            if diff:
                _say(f"DISCREPANCY: accepted golden '{key}' does not match the current sources: {diff}")
                return EXIT_REFUSED
        legacy, problem = _check_legacy_provenance(paths["summary"].read_text(encoding="utf-8"))
        if problem:
            _say(f"DISCREPANCY: {problem}")
            return EXIT_REFUSED
        reason = "one-time manifest for the accepted goldens"
        manifest = _build_manifest(golden_dir, reason, legacy, "record_goldens.py --manifest-only")
        if args.dry_run:
            _say(json.dumps(manifest, indent=2, sort_keys=True))
            return EXIT_OK
        new_bytes = _manifest_bytes(manifest)
        _write_new(manifest_path, new_bytes)
        audit_dir.mkdir(parents=True, exist_ok=True)
        _write_replacing(receipt_path, _receipt_bytes(new_bytes, manifest, None, reason, "record_goldens.py --manifest-only"))
        _say(f"wrote {manifest_path.name}; goldens digest {manifest['goldens_digest']}")
        return EXIT_OK

    if existing:
        _say(f"refusing to overwrite existing golden file(s): {existing}")
        return EXIT_REFUSED
    artifacts = _derive_artifacts()
    if args.dry_run:
        _say("dry run: would record " + ", ".join(S.GOLDEN_FILE_NAMES.values()) + " and the manifest")
        return EXIT_OK
    golden_dir.mkdir(parents=True, exist_ok=True)
    for key, path in paths.items():
        _write_new(path, artifacts[key].encode("utf-8"))
    manifest = _build_manifest(golden_dir, "initial recording", None, "record_goldens.py")
    new_bytes = _manifest_bytes(manifest)
    _write_new(manifest_path, new_bytes)
    audit_dir.mkdir(parents=True, exist_ok=True)
    _write_replacing(receipt_path, _receipt_bytes(new_bytes, manifest, None, "initial recording", "record_goldens.py"))
    _say(f"recorded {len(paths)} goldens, the manifest and its receipt in {golden_dir}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
