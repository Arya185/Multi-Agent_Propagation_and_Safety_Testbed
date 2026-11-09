"""Scenario loading and file-level validation (extra module beyond the original plan).

Schema-level rules live in maps.schemas.Scenario. This module checks what
needs the filesystem: evidence documents exist, are labelled synthetic, and
agree with the declared truth label.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path

from maps.schemas import Scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_MARKER = "SYNTHETIC DOCUMENT"
_HEX64 = re.compile(r"[0-9a-f]{64}")
# Evidence-binding route (Stage 4J.7): from author_checked upward the scenario file itself carries evidence.sha256, the
# loader, the registry and the readiness report check it against the CURRENT evidence bytes, and any policy
# scope.content evidence digest must equal it. One recorded value, one rule, no second route.
HASH_REQUIRED_STATUSES = ("author_checked", "pilot_frozen", "independently_checked", "frozen")


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_scenario(path: str | Path) -> Scenario:
    with open(path, encoding="utf-8") as fh:
        return Scenario.model_validate(json.load(fh))


def evidence_path(scenario: Scenario, repo_root: Path = REPO_ROOT) -> Path:
    return repo_root / scenario.evidence.reference


def evidence_integrity_problems(scenario: Scenario, repo_root: Path = REPO_ROOT) -> list[str]:
    """Return integrity problems between the recorded evidence.sha256 and the CURRENT bytes of the evidence file.

    Never raises, pure read, no caching (the file is re-read on every call). An empty list means the current bytes
    match the recorded digest. A matching hash proves content identity only; it does not prove that any reviewer
    read or understood the evidence. Messages name the scenario id and path only, never claim values.
    """
    sid = scenario.scenario_id
    try:
        path = evidence_path(scenario, repo_root)
        recorded = scenario.evidence.sha256
        problems: list[str] = []
        if not recorded:
            problems.append(f"{sid}: no evidence.sha256 recorded")
        elif not isinstance(recorded, str) or not _HEX64.fullmatch(recorded):
            problems.append(f"{sid}: evidence.sha256 is malformed (need 64 lowercase hex characters)")
        try:
            if not path.is_file():
                problems.append(f"{sid}: evidence file missing or not a regular file: {path}")
                return problems
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            problems.append(f"{sid}: evidence file unreadable ({type(exc).__name__}): {path}")
            return problems
        if not problems and actual != recorded:
            problems.append(f"{sid}: evidence sha256 mismatch for {path}")
        return problems
    except Exception as exc:  # never raise
        return [f"{sid}: evidence integrity check failed ({type(exc).__name__})"]


def check_evidence_file(scenario: Scenario, repo_root: Path = REPO_ROOT) -> None:
    """Truth-by-construction check against the evidence document. Raises ValueError."""
    path = evidence_path(scenario, repo_root)
    if not path.is_file():
        raise ValueError(f"{scenario.scenario_id}: evidence file missing: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        digest = file_sha256(path) if scenario.evidence.sha256 is not None else None
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{scenario.scenario_id}: evidence file unreadable ({type(exc).__name__}): {path}") from exc
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if SYNTHETIC_MARKER not in first:
        raise ValueError(f"{scenario.scenario_id}: evidence must open with a '{SYNTHETIC_MARKER}' label")
    if scenario.evidence.ground_truth_value not in text:
        raise ValueError(f"{scenario.scenario_id}: ground_truth_value not found in evidence")
    asserted_in_doc = scenario.claim.asserted_value in text
    if asserted_in_doc != (scenario.truth_status == "true"):
        raise ValueError(f"{scenario.scenario_id}: evidence document disagrees with truth_status")
    if scenario.evidence.sha256 is not None and digest != scenario.evidence.sha256:
        raise ValueError(f"{scenario.scenario_id}: evidence sha256 mismatch")


def check_pair_matched(true_s: Scenario, false_s: Scenario) -> None:
    """The true and false members of a pair must be matched on everything but truth."""
    pid = true_s.pair_id
    if true_s.domain != false_s.domain or true_s.claim.attribute != false_s.claim.attribute:
        raise ValueError(f"pair {pid}: domain/attribute mismatch")
    if true_s.claim.calendar_convention != false_s.claim.calendar_convention:
        raise ValueError(f"pair {pid}: calendar convention mismatch")
    for field in ("stated_origin", "acquisition_process", "instrument_class", "artifact_type", "quality_tier"):
        if [getattr(r, field) for r in true_s.communication_roots] != [
            getattr(r, field) for r in false_s.communication_roots
        ]:
            raise ValueError(f"pair {pid}: root {field} differs between true and false members")
    td, fd = true_s.claim.event_date, false_s.claim.event_date
    if (td is None) != (fd is None):
        raise ValueError(f"pair {pid}: only one member has an event_date")
    if td is not None and (
        datetime.date.fromisoformat(td).weekday() != datetime.date.fromisoformat(fd).weekday()
    ):
        raise ValueError(f"pair {pid}: event_date weekdays differ ({td} vs {fd})")


def load_scenario_dir(directory: str | Path, repo_root: Path = REPO_ROOT) -> list[Scenario]:
    """Load all *.json scenarios in a directory (non-recursive; archive is never read)."""
    paths = sorted(Path(directory).glob("*.json"))
    scenarios = [load_scenario(p) for p in paths]
    ids = [s.scenario_id for s in scenarios]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate scenario_id across files")
    pairs: dict[str, list[str]] = {}
    for s in scenarios:
        check_evidence_file(s, repo_root)
        if s.status in HASH_REQUIRED_STATUSES:
            problems = evidence_integrity_problems(s, repo_root)
            if problems:
                raise ValueError("; ".join(problems))
        pairs.setdefault(s.pair_id, []).append(s.truth_status)
    for pair, truths in pairs.items():
        if sorted(truths) != ["false", "true"]:
            raise ValueError(f"pair {pair} must have exactly one true and one false scenario")
        members = {x.truth_status: x for x in scenarios if x.pair_id == pair}
        check_pair_matched(members["true"], members["false"])
    return scenarios
