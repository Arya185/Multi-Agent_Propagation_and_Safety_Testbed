"""Result-file hash binding (v2.3.53): the artifact allow-list, the hash manifest and the set digest.

A finished run's integrity report (schema version 2) carries an ``artifacts`` block that lists the allow-listed
run files with their byte length and raw-file SHA-256, plus one SHA-256 over that list (the "set digest"). The
lifecycle writes the block; the integrity gate checks it before a persisted run is admitted to analysis.

ALLOW-LIST (``HASHED_ARTIFACTS``): ``episodes.jsonl`` and ``.maps_run_claim`` are required; ``calls.jsonl``,
``manifest.json`` and ``run_provenance.json`` are listed when present. NOT hashed (``NOT_HASHED``): the event log
(it is appended to after the report is written), the report itself, the legacy ``summary.json`` and
``contrast_gaps.json`` (written by the runner, read by no analysis code) and the pipeline report (written later).

SET DIGEST format (``DIGEST_FORMAT``): SHA-256 of the UTF-8 text made of the lines ``<name>:<bytes>:<sha256>``
sorted by name and joined by LF with no trailing LF (the same convention as the WP2 manifest digests).

READING: ``read_artifact`` takes ``lstat`` of the path (never following a link), requires a regular file, reads it
in bounded chunks while hashing, takes ``lstat`` again, and fails if the file's identity or size changed. The
caller can keep the bytes it just hashed and parse THOSE bytes, so there is no gap between verification and use.

WHAT THIS IS AND IS NOT. SHA-256 here is integrity checking. It shows the listed files are byte-for-byte what the
report recorded; it does not authenticate who wrote them, does not show the data are truthful, and does not stop
someone with write access from replacing the data, the claim and the report together. A very narrow race remains
for an attacker who can swap a file between the two ``lstat`` calls with exact timing. Errors carry a bounded
reason code and a fixed message; they never include file content.
"""

from __future__ import annotations

import hashlib
import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from maps.runs.guard import CLAIM_FILENAME

ALGORITHM = "sha256"
EPISODES_NAME = "episodes.jsonl"
CLAIM_NAME = CLAIM_FILENAME
HASHED_ARTIFACTS: tuple[tuple[str, bool], ...] = (
    (EPISODES_NAME, True), (CLAIM_NAME, True), ("calls.jsonl", False), ("manifest.json", False), ("run_provenance.json", False),
)
NOT_HASHED = ("run_events.jsonl", "run_integrity.json", "summary.json", "contrast_gaps.json", "pipeline_report.json")
DIGEST_FORMAT = "sha256 of lines '<name>:<bytes>:<sha256>' sorted by name, joined by LF, no trailing LF"
CHUNK_BYTES = 1 << 20
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_UNLISTED_NOTES = 20
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ALLOWED_NAMES = frozenset(name for name, _ in HASHED_ARTIFACTS)
_REQUIRED_NAMES = frozenset(name for name, required in HASHED_ARTIFACTS if required)

ARTIFACT_REASONS = {
    "artifacts_missing": "a version 2 report has no artifact hash block",
    "artifacts_malformed": "the artifact hash block is malformed",
    "unsupported_hash_algorithm": "the artifact hash block uses an unsupported hash algorithm",
    "artifact_digest_inconsistent": "the artifact set digest does not match the listed files",
    "artifact_missing": "a file listed in the report is missing",
    "artifact_not_regular_file": "a file listed in the report is not a regular file (a link, directory or special file)",
    "artifact_too_large": "a file listed in the report is larger than the supported size",
    "artifact_unreadable": "a file listed in the report could not be read",
    "artifact_size_differs": "a file's byte length differs from the report",
    "artifact_hash_differs": "a file's SHA-256 differs from the report",
    "artifact_changed_during_verification": "a file changed while it was being verified",
}


class ArtifactError(Exception):
    """A file could not be read or verified. ``reason`` is a code from ``ARTIFACT_REASONS``; no file content is included."""

    def __init__(self, reason: str):
        super().__init__(ARTIFACT_REASONS[reason])
        self.reason = reason


@dataclass(frozen=True)
class FileRead:
    """The size and SHA-256 of the exact bytes read, and the bytes themselves if they were kept."""

    name: str
    size: int
    sha256: str
    data: bytes | None = None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_artifact(path: str | Path, *, keep_bytes: bool = False, max_bytes: int = MAX_ARTIFACT_BYTES) -> FileRead:
    """Read a regular file (never a link), hash exactly what was read, and confirm the file did not change."""
    target = Path(path)
    try:
        before = target.lstat()
    except FileNotFoundError:
        raise ArtifactError("artifact_missing") from None
    except OSError:
        raise ArtifactError("artifact_unreadable") from None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ArtifactError("artifact_not_regular_file")
    if before.st_size > max_bytes:
        raise ArtifactError("artifact_too_large")
    digest, chunks, total = hashlib.sha256(), [], 0
    try:
        with target.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ArtifactError("artifact_too_large")
                digest.update(chunk)
                if keep_bytes:
                    chunks.append(chunk)
    except ArtifactError:
        raise
    except OSError:
        raise ArtifactError("artifact_unreadable") from None
    try:
        after = target.lstat()
    except OSError:
        raise ArtifactError("artifact_changed_during_verification") from None
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)  # noqa: E731
    if identity(before) != identity(after) or total != before.st_size:
        raise ArtifactError("artifact_changed_during_verification")
    return FileRead(name=target.name, size=total, sha256=digest.hexdigest(), data=b"".join(chunks) if keep_bytes else None)


def artifact_set_digest(files: Iterable[Mapping]) -> str:
    """SHA-256 over the sorted ``name:bytes:sha256`` lines (see ``DIGEST_FORMAT``)."""
    lines = "\n".join(f"{f['name']}:{f['bytes']}:{f['sha256']}" for f in sorted(files, key=lambda f: f["name"]))
    return sha256_hex(lines.encode("utf-8"))


def build_artifact_block(run_dir: str | Path, *, precomputed: Mapping[str, FileRead] | None = None) -> tuple[dict, list[dict]]:
    """The ``artifacts`` block for the files that exist, and a list of per-file errors (empty when all went well).

    A file that does not exist is simply not listed. A file that exists but cannot be hashed (a link, a directory,
    too large, unreadable, changed while read) is reported in the errors, never silently skipped. ``precomputed``
    supplies reads the caller already made (so the hash covers exactly the bytes the caller parsed)."""
    run = Path(run_dir)
    pre = dict(precomputed or {})
    files: list[dict] = []
    errors: list[dict] = []
    for name, required in HASHED_ARTIFACTS:
        if name in pre:
            read = pre[name]
        else:
            try:
                read = read_artifact(run / name)
            except ArtifactError as exc:
                if exc.reason != "artifact_missing":
                    errors.append({"name": name, "reason": exc.reason})
                continue
        files.append({"name": name, "bytes": read.size, "sha256": read.sha256, "required": required})
    block: dict = {
        "hash_algorithm": ALGORITHM, "files": files, "artifact_digest": artifact_set_digest(files),
        "digest_format": DIGEST_FORMAT, "not_hashed": list(NOT_HASHED),
    }
    if errors:
        block["errors"] = errors
    return block, errors


def _is_int(value) -> bool:
    return type(value) is int


def validate_artifact_block(block) -> str | None:
    """Reason code if the block is malformed (format only, strict types), else None. Does not touch the disk."""
    if not isinstance(block, dict):
        return "artifacts_malformed"
    algorithm = block.get("hash_algorithm")
    if type(algorithm) is not str:
        return "artifacts_malformed"
    if algorithm != ALGORITHM:
        return "unsupported_hash_algorithm"
    files = block.get("files")
    if not isinstance(files, list):
        return "artifacts_malformed"
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"name", "bytes", "sha256", "required"}:
            return "artifacts_malformed"
        name = entry["name"]
        if type(name) is not str or not name or "/" in name or "\\" in name or "\x00" in name or name in (".", ".."):
            return "artifacts_malformed"
        if name not in _ALLOWED_NAMES or name in seen:
            return "artifacts_malformed"
        seen.add(name)
        if not _is_int(entry["bytes"]) or entry["bytes"] < 0:
            return "artifacts_malformed"
        if type(entry["sha256"]) is not str or not _HEX64.fullmatch(entry["sha256"]):
            return "artifacts_malformed"
        if type(entry["required"]) is not bool or entry["required"] != (name in _REQUIRED_NAMES):
            return "artifacts_malformed"
    digest = block.get("artifact_digest")
    if type(digest) is not str or not _HEX64.fullmatch(digest):
        return "artifacts_malformed"
    if block.get("digest_format") != DIGEST_FORMAT or block.get("not_hashed") != list(NOT_HASHED):
        return "artifacts_malformed"
    errors = block.get("errors", [])
    if not isinstance(errors, list) or not all(
        isinstance(e, dict) and set(e) == {"name", "reason"} and type(e["name"]) is str and e["reason"] in ARTIFACT_REASONS for e in errors
    ):
        return "artifacts_malformed"
    if digest != artifact_set_digest(files):
        return "artifact_digest_inconsistent"
    return None


def missing_required(block: Mapping) -> list[str]:
    """Names of required artifacts the (already format-valid) block does not list."""
    listed = {entry["name"] for entry in block["files"]}
    return sorted(_REQUIRED_NAMES - listed)


def verify_entry(run_dir: str | Path, entry: Mapping, *, keep_bytes: bool = False) -> FileRead:
    """Read one listed file and check its length and SHA-256 against the entry. Raises ``ArtifactError``."""
    read = read_artifact(Path(run_dir) / entry["name"], keep_bytes=keep_bytes)
    if read.size != entry["bytes"]:
        raise ArtifactError("artifact_size_differs")
    if read.sha256 != entry["sha256"]:
        raise ArtifactError("artifact_hash_differs")
    return read


def list_unlisted(run_dir: str | Path, block: Mapping) -> tuple[str, ...]:
    """Bounded names of files in the run directory that are neither listed nor known-unhashed (a note, not an error)."""
    listed = {entry["name"] for entry in block["files"]}
    try:
        names = sorted(p.name for p in Path(run_dir).iterdir())
    except OSError:
        return ()
    extra = [n[:100] for n in names if n not in listed and n not in NOT_HASHED]
    return tuple(extra[:MAX_UNLISTED_NOTES])
