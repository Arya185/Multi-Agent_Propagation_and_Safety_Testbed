"""Pilot exposure mechanism (Stage 4J.7, Agent B). Offline; tmp_path only; no real exposure is recorded."""

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from maps.exposure import (
    STATEMENT,
    append_exposures_to_file,
    exposure_records,
    run_exposure_report,
    with_exposures,
    write_run_exposure_sidecar,
)
from maps.registry import Registry
from maps.scenarios import evidence_path, file_sha256, load_scenario_dir
from maps.schemas import scenario_content_sha256

ROOT = Path(__file__).resolve().parents[1]
FIXED = "2026-12-01T09:00:00+00:00"
RUN = "2026-12-05T09:00:00+00:00"


def ref(sid, version=1):
    return {"scenario_id": sid, "scenario_version": version}


def cohort(cid, family, members, fixed=FIXED):
    return {"cohort_id": cid, "family": family, "members": members, "fixed_on": fixed}


@pytest.fixture(scope="module")
def real():
    return load_scenario_dir(ROOT / "data" / "scenarios" / "v2")


@pytest.fixture
def scen(real):
    return {s.scenario_id: s for s in real}


@pytest.fixture
def reg():
    return Registry.model_validate({
        "cohorts": [cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b"), ref("geo-a"), ref("geo-b")]),
                    cohort("conf-1", "confirmatory", [ref("sw-a"), ref("sw-b")])],
    })


def recs(reg, real, **kw):
    args = dict(cohort_id="pilot-1", run_id="run-1", recorded_on=RUN)
    args.update(kw)
    return exposure_records(reg, real, **args)


# ---- records ------------------------------------------------------------------------------------------------
def test_records_cover_every_member_with_correct_hashes(reg, real, scen):
    out = recs(reg, real, note="n")
    assert [r.scenario.key for r in out] == ["biz-a@1", "biz-b@1", "geo-a@1", "geo-b@1"]
    for r in out:
        s = scen[r.scenario.scenario_id]
        assert r.run_id == "run-1" and r.recorded_on == RUN and r.cohort_id == "pilot-1" and r.note == "n"
        assert r.scenario_sha256 == scenario_content_sha256(s)
        assert r.evidence_sha256 == file_sha256(evidence_path(s, ROOT))


def test_changed_evidence_bytes_change_evidence_sha(reg, real, scen, tmp_path):
    for s in real:
        dst = tmp_path / s.evidence.reference
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / s.evidence.reference, dst)
    before = {r.scenario.key: r.evidence_sha256 for r in recs(reg, real, repo_root=tmp_path)}
    (tmp_path / scen["biz-a"].evidence.reference).write_bytes(b"changed bytes")
    after = {r.scenario.key: r.evidence_sha256 for r in recs(reg, real, repo_root=tmp_path)}
    assert after["biz-a@1"] != before["biz-a@1"]
    assert after["biz-b@1"] == before["biz-b@1"]


@pytest.mark.parametrize("kw,match", [
    ({"cohort_id": "conf-1"}, "not pilot"),
    ({"cohort_id": "nope"}, "unknown cohort"),
    ({"run_id": "bad id"}, "invalid run_id"),
    ({"run_id": ".."}, "invalid run_id"),
    ({"run_id": ""}, "invalid run_id"),
    ({"recorded_on": ""}, "recorded_on"),
    ({"recorded_on": "   "}, "recorded_on"),
    ({"recorded_on": "yesterday"}, "recorded_on"),
])
def test_refusals(reg, real, kw, match):
    with pytest.raises(ValueError, match=match):
        recs(reg, real, **kw)


def test_member_missing_from_loaded_scenarios_is_refused(reg, real):
    with pytest.raises(ValueError, match="geo-b@1 is not among the loaded"):
        recs(reg, [s for s in real if s.scenario_id != "geo-b"])


def test_unreadable_evidence_is_refused(reg, real, tmp_path):
    with pytest.raises(ValueError, match="evidence cannot be read"):
        recs(reg, real, repo_root=tmp_path)


def test_duplicate_scenario_run_is_refused(reg, real):
    r2 = with_exposures(reg, recs(reg, real))
    with pytest.raises(ValueError, match="already recorded"):
        recs(r2, real)
    assert len(recs(r2, real, run_id="run-2")) == 4  # a different run is fine


# ---- with_exposures -----------------------------------------------------------------------------------------
def test_with_exposures_is_append_only_and_non_mutating(reg, real):
    first = with_exposures(reg, recs(reg, real))
    snapshot = reg.model_dump_json()
    second = with_exposures(first, recs(first, real, run_id="run-2"))
    assert reg.model_dump_json() == snapshot and reg.exposures == []
    assert len(first.exposures) == 4 and len(second.exposures) == 8
    assert second.exposures[:4] == first.exposures
    assert second is not first and isinstance(second, Registry)


def test_exposed_scenario_cannot_join_a_confirmatory_cohort(reg, real):
    exposed = with_exposures(reg, recs(reg, real))
    data = exposed.model_dump(mode="json")
    data["cohorts"].append(cohort("conf-2", "confirmatory", [ref("biz-a")]))
    with pytest.raises(ValidationError):
        Registry.model_validate(data)


def test_recording_exposure_of_a_confirmatory_member_is_refused_by_validation(reg, real):
    r = recs(reg, real)[0].model_copy(update={"scenario": recs(reg, real)[0].scenario.model_copy(update={"scenario_id": "sw-a"})})
    with pytest.raises(ValidationError, match="confirmatory eligibility"):
        with_exposures(reg, [r])


def test_descendant_of_an_exposed_scenario_cannot_be_confirmatory(reg, real):
    exposed = with_exposures(reg, recs(reg, real))
    data = exposed.model_dump(mode="json")
    data["lineage"].append({"scenario": ref("biz-a", 2), "supersedes": ref("biz-a", 1)})
    data["cohorts"].append(cohort("conf-2", "confirmatory", [ref("biz-a", 2)]))
    with pytest.raises(ValidationError, match="descends from pilot-exposed"):
        Registry.model_validate(data)


# ---- file append --------------------------------------------------------------------------------------------
def write_reg(tmp_path, reg):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return p


def test_append_to_file_changes_only_exposures(reg, real, tmp_path):
    p = write_reg(tmp_path, reg)
    before = json.loads(p.read_text())
    out = append_exposures_to_file(p, recs(reg, real))
    after = json.loads(p.read_text())
    assert len(out.exposures) == 4 and len(after["exposures"]) == 4
    for k in ("cohorts", "lineage", "registry_version"):
        assert after[k] == before[k]
    assert [f.name for f in tmp_path.iterdir()] == ["registry.json"]  # no temp file left


def test_append_failure_leaves_original_untouched(reg, real, tmp_path):
    p = write_reg(tmp_path, reg)
    original = p.read_bytes()
    good = recs(reg, real)
    bad = good[0].model_copy(update={"recorded_on": "2020-01-01T00:00:00+00:00"})  # before the cohort was fixed
    with pytest.raises(ValidationError):
        append_exposures_to_file(p, [bad])
    assert p.read_bytes() == original
    assert [f.name for f in tmp_path.iterdir()] == ["registry.json"]


def test_append_refuses_a_missing_file(reg, real, tmp_path):
    with pytest.raises(FileNotFoundError):
        append_exposures_to_file(tmp_path / "absent.json", recs(reg, real))
    assert list(tmp_path.iterdir()) == []


# ---- report and sidecar -------------------------------------------------------------------------------------
def test_report_is_deterministic_and_marks_descendants(reg, real, scen):
    exposed = with_exposures(reg, recs(reg, real))
    child = scen["biz-a"].model_copy(update={"scenario_version": 2, "supersedes": "biz-a@1"})
    loaded = list(real) + [child]
    rep = run_exposure_report(exposed, loaded, "run-1")
    assert rep == run_exposure_report(exposed, list(reversed(loaded)), "run-1")
    assert rep["run_id"] == "run-1" and rep["stage"] == "pilot" and rep["cohort_ids"] == ["pilot-1"]
    assert rep["statement"] == STATEMENT
    assert [e["key"] for e in rep["exposed"]] == ["biz-a@1", "biz-b@1", "geo-a@1", "geo-b@1"]
    e0 = rep["exposed"][0]
    assert e0["confirmatory_eligible"] is False and e0["reason"] == "pilot-exposed"
    assert e0["scenario_sha256"] == scenario_content_sha256(scen["biz-a"])
    assert rep["descendants"] == [{"confirmatory_eligible": False, "key": "biz-a@2",
                                   "reason": "descends from pilot-exposed scenario biz-a@1"}]
    assert run_exposure_report(exposed, loaded, "other-run")["exposed"] == []


def test_sidecar_written_once_and_never_overwritten(reg, real, tmp_path):
    rep = run_exposure_report(with_exposures(reg, recs(reg, real)), real, "run-1")
    path = write_run_exposure_sidecar(tmp_path, rep)
    assert path.name == "pilot_exposure.json"
    text = path.read_text()
    assert text.endswith("\n") and json.loads(text) == rep
    assert text == json.dumps(rep, indent=2, sort_keys=True) + "\n"
    with pytest.raises(FileExistsError):
        write_run_exposure_sidecar(tmp_path, {"x": 1})
    assert path.read_text() == text
    with pytest.raises(FileNotFoundError):
        write_run_exposure_sidecar(tmp_path / "missing", rep)
    assert not (tmp_path / "missing").exists()


def test_real_data_is_not_modified(reg, real):
    files = sorted((ROOT / "data" / "scenarios" / "v2").glob("*.json"))[:4] + [ROOT / "src" / "maps" / "registry.py"]
    before = [file_sha256(f) for f in files]
    run_exposure_report(with_exposures(reg, recs(reg, real)), real, "run-1")
    assert [file_sha256(f) for f in files] == before
