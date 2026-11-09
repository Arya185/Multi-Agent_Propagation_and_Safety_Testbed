"""Evidence integrity: recorded evidence.sha256 vs the CURRENT bytes of the evidence file (tmp copies only)."""

import hashlib
import os
import shutil
from pathlib import Path

import pytest

import maps.scenarios as sc
from maps.scenarios import REPO_ROOT, evidence_integrity_problems, load_scenario_dir

SCEN_DIR = REPO_ROOT / "data" / "scenarios" / "v2"


@pytest.fixture(scope="module")
def real():
    return load_scenario_dir(SCEN_DIR)


@pytest.fixture()
def env(real, tmp_path):
    """(scenario with correct hash, tmp repo root holding a copy of its evidence)."""
    s = real[0]
    src = REPO_ROOT / s.evidence.reference
    dst = tmp_path / s.evidence.reference
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    digest = hashlib.sha256(dst.read_bytes()).hexdigest()
    s2 = s.model_copy(update={"evidence": s.evidence.model_copy(update={"sha256": digest})})
    return s2, tmp_path, dst


def _with_hash(s, value):
    return s.model_copy(update={"evidence": s.evidence.model_copy(update={"sha256": value})})


def test_valid(env):
    s, root, _ = env
    assert evidence_integrity_problems(s, root) == []


def test_missing_hash(env):
    s, root, _ = env
    p = evidence_integrity_problems(_with_hash(s, None), root)
    assert len(p) == 1 and "no evidence.sha256 recorded" in p[0] and s.scenario_id in p[0]


@pytest.mark.parametrize("bad", ["A" * 64, "ab12", "g" * 64, "a" * 65])
def test_malformed_hash(env, bad):
    s, root, _ = env
    p = evidence_integrity_problems(_with_hash(s, bad), root)
    assert p and "malformed" in p[0]


def test_file_changed_without_json_update(env):
    s, root, path = env
    path.write_bytes(path.read_bytes() + b"\nextra")
    p = evidence_integrity_problems(s, root)
    assert len(p) == 1 and "evidence sha256 mismatch" in p[0]


def test_hash_changed_without_file_change(env):
    s, root, _ = env
    p = evidence_integrity_problems(_with_hash(s, "0" * 64), root)
    assert len(p) == 1 and "evidence sha256 mismatch" in p[0]


def test_missing_file(env):
    s, root, path = env
    path.unlink()
    p = evidence_integrity_problems(s, root)
    assert p and "missing" in p[0]


def test_unreadable_file(env):
    s, root, path = env
    path.chmod(0)
    try:
        if os.geteuid() == 0:
            pytest.skip("root can read chmod 000 files")
        p = evidence_integrity_problems(s, root)
        assert p and "unreadable" in p[0]
    finally:
        path.chmod(0o644)


def test_directory_instead_of_file(env):
    s, root, path = env
    path.unlink()
    path.mkdir()
    p = evidence_integrity_problems(s, root)
    assert p and "not a regular file" in p[0]


def test_no_caching(env):
    s, root, path = env
    assert evidence_integrity_problems(s, root) == []
    path.write_bytes(path.read_bytes() + b" ")
    assert any("mismatch" in m for m in evidence_integrity_problems(s, root))


def test_messages_leak_no_claim_values(env):
    s, root, path = env
    msgs = []
    msgs += evidence_integrity_problems(_with_hash(s, None), root)
    msgs += evidence_integrity_problems(_with_hash(s, "0" * 64), root)
    msgs += evidence_integrity_problems(_with_hash(s, "XYZ"), root)
    path.unlink()
    msgs += evidence_integrity_problems(s, root)
    text = " ".join(msgs)
    assert s.evidence.ground_truth_value not in text
    assert s.claim.asserted_value not in text


@pytest.mark.parametrize("status", ["pilot_frozen", "independently_checked", "frozen"])
def test_loader_fails_closed_for_hash_statuses(real, tmp_path, monkeypatch, status):
    for s in real:
        dst = tmp_path / s.evidence.reference
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / s.evidence.reference, dst)
    orig = sc.load_scenario

    def patched(path):
        s = orig(path)
        if s.scenario_id == real[0].scenario_id:
            s = s.model_copy(update={"status": status, "evidence": s.evidence.model_copy(update={"sha256": "0" * 64})})
        return s

    monkeypatch.setattr(sc, "load_scenario", patched)
    with pytest.raises(ValueError, match="sha256 mismatch"):
        load_scenario_dir(SCEN_DIR, repo_root=tmp_path)


def test_loader_fails_closed_on_missing_hash_for_frozen(real, tmp_path, monkeypatch):
    for s in real:
        dst = tmp_path / s.evidence.reference
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / s.evidence.reference, dst)
    orig = sc.load_scenario
    monkeypatch.setattr(
        sc, "load_scenario",
        lambda p: (lambda s: s.model_copy(update={"status": "frozen"}) if s.scenario_id == real[0].scenario_id else s)(orig(p)),
    )
    with pytest.raises(ValueError, match="no evidence.sha256"):
        load_scenario_dir(SCEN_DIR, repo_root=tmp_path)


def test_loader_still_loads_real_drafts(real):
    assert len(real) == 10
    assert all(s.status == "draft" and s.evidence.sha256 is None for s in real)
