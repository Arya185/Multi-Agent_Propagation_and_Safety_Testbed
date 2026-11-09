"""Pilot exposure recording and run-report provenance (Stage 4J.7, Agent B).

THIS IS A MECHANISM ONLY. Nothing here is called automatically: the executor and the receiver do NOT record
exposure, and no existing module imports this one. Hooking it into the live run path would change protected code and
the mock-run bytes and needs separate authorization. Exposure is recorded by an explicit, authorized step AFTER an
authorized pilot run has happened. No run has happened; no exposure event has been created by this module.

Pure and deterministic except the two explicit file writers, ``append_exposures_to_file`` and
``write_run_exposure_sidecar``. Messages carry ids and keys, never claim values. A digest proves content identity
only.
"""

import json
import os
import tempfile
from pathlib import Path

from maps.registry import (
    PilotExposure,
    Registry,
    ScenarioRef,
    _parents,
    ancestors,
)
from maps.runs.ids import InvalidRunIdError, validate_run_id
from maps.scenarios import REPO_ROOT, evidence_path, file_sha256
from maps.schemas import Scenario, parse_timestamp, scenario_content_sha256

SIDECAR_NAME = "pilot_exposure.json"
STATEMENT = (
    "Pilot exposure disqualifies these scenario versions and their descendants from any confirmatory cohort. "
    "A digest proves content identity only."
)


def _key(s: Scenario) -> str:
    return f"{s.scenario_id}@{s.scenario_version}"


def exposure_records(
    registry: Registry,
    scenarios: list[Scenario],
    cohort_id: str,
    run_id: str,
    recorded_on: str,
    repo_root: Path = REPO_ROOT,
    note: str = "",
) -> list[PilotExposure]:
    """One exposure record per member of the named PILOT cohort. Raises ValueError on any refusal."""
    cohort = next((c for c in registry.cohorts if c.cohort_id == cohort_id), None)
    if cohort is None:
        raise ValueError(f"unknown cohort {cohort_id!r}")
    if cohort.family != "pilot":
        raise ValueError(f"cohort {cohort_id!r} is {cohort.family}, not pilot: exposure is recorded for pilot cohorts only")
    try:
        validate_run_id(run_id)
    except InvalidRunIdError as exc:
        raise ValueError(f"invalid run_id: {exc}") from exc
    if not isinstance(recorded_on, str) or not recorded_on.strip():
        raise ValueError("recorded_on is required")
    try:
        parse_timestamp(recorded_on)
    except Exception as exc:
        raise ValueError(f"recorded_on is not a valid timestamp: {type(exc).__name__}") from exc

    by_key = {_key(s): s for s in scenarios}
    existing = {(e.scenario.key, e.run_id) for e in registry.exposures}
    records: list[PilotExposure] = []
    for m in cohort.members:
        s = by_key.get(m.key)
        if s is None:
            raise ValueError(f"{cohort_id}: {m.key} is not among the loaded scenarios")
        if (m.key, run_id) in existing:
            raise ValueError(f"exposure of {m.key} by run {run_id!r} is already recorded")
        try:
            evidence_sha = file_sha256(evidence_path(s, repo_root))
        except OSError as exc:
            raise ValueError(f"{m.key}: evidence cannot be read ({type(exc).__name__})") from exc
        records.append(
            PilotExposure(
                scenario=ScenarioRef(scenario_id=m.scenario_id, scenario_version=m.scenario_version),
                run_id=run_id,
                recorded_on=recorded_on,
                note=note,
                cohort_id=cohort_id,
                scenario_sha256=scenario_content_sha256(s),
                evidence_sha256=evidence_sha,
            )
        )
    return records


def with_exposures(registry: Registry, records: list[PilotExposure]) -> Registry:
    """A NEW validated registry with ``records`` appended. Existing exposures are never edited or removed."""
    data = registry.model_dump(mode="json")
    data["exposures"] = data["exposures"] + [r.model_dump(mode="json") for r in records]
    return Registry.model_validate(data)


def append_exposures_to_file(path: str | Path, records: list[PilotExposure]) -> Registry:
    """Append ``records`` to the exposures list of the registry JSON at ``path``, atomically.

    Refuses a missing file. Validates the whole result before writing; on any failure the file is untouched.
    Only the ``exposures`` value changes (other top-level keys keep their values and order; JSON is re-indented)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"registry file does not exist: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    updated = with_exposures(Registry.model_validate(raw), records)  # raises before anything is written
    raw["exposures"] = [e.model_dump(mode="json") for e in updated.exposures]
    text = json.dumps(raw, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return updated


def run_exposure_report(registry: Registry, scenarios: list[Scenario], run_id: str) -> dict:
    """Sidecar content for ``run_id``: exposed scenarios and their descendants, all confirmatory-ineligible."""
    events = sorted((e for e in registry.exposures if e.run_id == run_id), key=lambda e: e.scenario.key)
    exposed_keys = {e.scenario.key for e in events}
    exposed = [
        {
            "confirmatory_eligible": False,
            "reason": "pilot-exposed",
            "cohort_id": e.cohort_id,
            "evidence_sha256": e.evidence_sha256,
            "key": e.scenario.key,
            "recorded_on": e.recorded_on,
            "scenario_sha256": e.scenario_sha256,
        }
        for e in events
    ]
    from_files = {_key(s): s.supersedes for s in scenarios if s.supersedes is not None}
    parents = _parents(registry, from_files)
    descendants = []
    for s in sorted(scenarios, key=_key):
        key = _key(s)
        if key in exposed_keys:
            continue
        hit = next((a for a in ancestors(key, parents) if a in exposed_keys), None)
        if hit is not None:
            descendants.append(
                {
                    "confirmatory_eligible": False,
                    "key": key,
                    "reason": f"descends from pilot-exposed scenario {hit}",
                }
            )
    return {
        "cohort_ids": sorted({e.cohort_id for e in events if e.cohort_id is not None}),
        "descendants": descendants,
        "exposed": exposed,
        "run_id": run_id,
        "stage": "pilot",
        "statement": STATEMENT,
    }


def write_run_exposure_sidecar(run_dir: str | Path, report: dict) -> Path:
    """Write ``pilot_exposure.json`` into an existing directory. Never overwrites."""
    d = Path(run_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {d}")
    target = d / SIDECAR_NAME
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with open(target, "x", encoding="utf-8") as fh:  # exclusive create: refuses an existing file
            fh.write(text)
    except FileExistsError as exc:
        raise FileExistsError(f"{target} already exists; refusing to overwrite") from exc
    return target
