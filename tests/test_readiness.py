"""Tests for maps.readiness. Real files are only read; the synthetic world lives in tmp_path. Nothing here calls a provider."""

import builtins
import copy
import json
import shutil
from pathlib import Path

import pytest

from maps import registry as reg
from maps.config import load_config
from maps.readiness import (
    NOT_READY_TEXT, READY_TEXT, ProposalError, ReadinessItem, ReadinessReport, derived_policy_values,
    c0_episodes, format_readiness, load_policy_proposal, planned_episodes, readiness_report,
)
from maps.scenarios import file_sha256, load_scenario

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "configs/pilot_policy_proposal.json"


def codes(report, severity="blocker"):
    return {i.code for i in report.items if i.severity == severity}


# ---- proposal file


def test_proposal_loads_and_nothing_is_approved():
    doc = load_policy_proposal(PROPOSAL)
    assert doc["status"] == "PROPOSAL — NOT APPROVED"
    assert len(doc["fields"]) == 16
    assert all(f["status"] != "approved" for f in doc["fields"].values())
    assert {f["status"] for f in doc["fields"].values()} <= {"proposed", "pending_owner"}
    assert doc["fields"]["ps12_consec"]["value"] == 5 and doc["fields"]["nonfatal_4xx_statuses"]["value"] == [408, 429]
    for name in ("theta_fraction", "pi", "pi_breach_rule", "pi_breach_consequence", "approval_reference"):
        assert doc["fields"][name]["value"] is None and doc["fields"][name]["status"] == "pending_owner"
    assert doc["pilot_intent"] == "NOT AUTHORIZED"
    assert len(doc["custody"]) == 5 and doc["attestation_file"] is None
    assert doc["owner_decisions"]["author_id"]["status"] == "pending_owner"
    assert doc["owner_decisions"]["near_duplicate_geo_sci"]["applied"] is False


def test_proposal_is_not_a_loadable_live_policy():
    from maps.runs.live_policy import LivePolicy, PolicyError
    with pytest.raises(PolicyError):
        LivePolicy.from_mapping(json.loads(PROPOSAL.read_text(encoding="utf-8")))


def _write(tmp_path, mutate):
    doc = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    mutate(doc)
    p = tmp_path / "p.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_invalid_proposals_rejected(tmp_path):
    cases = {
        "unknown top field": lambda d: d.update(extra=1),
        "unknown policy field": lambda d: d["fields"].update(bogus={"value": 1, "status": "proposed", "source": "x"}),
        "missing policy field": lambda d: d["fields"].pop("pi"),
        "missing status": lambda d: d["fields"]["pi"].pop("status"),
        "missing source": lambda d: d["fields"]["ps11"].pop("source"),
        "bad status": lambda d: d["fields"]["ps11"].update(status="maybe"),
        "approved without reference": lambda d: d["fields"]["ps11"].update(status="approved"),
        "pending with value": lambda d: d["fields"]["pi"].update(value=0.1),
        "top approved w/o fields": lambda d: d.update(status="APPROVED"),
        "authorized w/o reference": lambda d: d.update(pilot_intent="AUTHORIZED"),
        "bad custody status": lambda d: d["custody"][0].update(status="done"),
        "custody count": lambda d: d["custody"].pop(),
        "missing decision": lambda d: d["owner_decisions"].pop("author_id"),
    }
    for name, mut in cases.items():
        with pytest.raises(ProposalError):
            load_policy_proposal(_write(tmp_path, mut))
        assert name  # label for failures
    with pytest.raises(ProposalError):
        load_policy_proposal(tmp_path / "nope.json")


def test_approved_only_with_reference(tmp_path):
    def ok(d):
        d["fields"]["approval_reference"].update(value="OWNER-REF-1", status="approved")
        d["fields"]["ps11"].update(status="approved")
    assert load_policy_proposal(_write(tmp_path, ok))["fields"]["ps11"]["status"] == "approved"

    def ref_not_approved(d):
        d["fields"]["approval_reference"].update(value="OWNER-REF-1")
        d["fields"]["ps11"].update(status="approved")
    with pytest.raises(ProposalError):
        load_policy_proposal(_write(tmp_path, ref_not_approved))


# ---- arithmetic


def test_planned_episode_arithmetic():
    cfg = load_config(ROOT / "configs/receiver_experiment.json")
    assert planned_episodes(cfg, 10) == 240 and c0_episodes(cfg, 10) == 40
    assert planned_episodes(cfg, 8) == 192 and c0_episodes(cfg, 8) == 32
    assert derived_policy_values(240) == {"ps05a_max_episodes": 240, "ps05b_max_request_attempts": 720, "ps09_deadline_seconds": 183 * 241}
    assert derived_policy_values(192) == {"ps05a_max_episodes": 192, "ps05b_max_request_attempts": 576, "ps09_deadline_seconds": 183 * 193}


# ---- real repository


def test_real_repo_not_ready():
    report = readiness_report()
    assert not report.ready and isinstance(report, ReadinessReport)
    got = codes(report)
    for c in ("policy_not_approved", "author_id_unconfirmed", "near_duplicate_unresolved", "policy_value_unset",
              "approval_reference_missing", "custody_pending", "attestation_missing", "pilot_intent_not_authorized",
              "cohort_not_fixed", "policy_fields_not_approved", "not_pilot_eligible"):
        assert c in got, c
    assert "protocol_not_approved" in codes(report, "warning")
    assert "hist_decision_provisional" in codes(report, "warning")
    text = format_readiness(report)
    assert text.rstrip().endswith(NOT_READY_TEXT) and "READY (engineering" not in text


def test_report_without_blockers_says_ready_with_caveat():
    text = format_readiness(ReadinessReport((ReadinessItem("w", "warning", "x"),)))
    assert text.endswith(READY_TEXT) and "owner authorization still required" in text
    with pytest.raises(ValueError):
        ReadinessItem("x", "fatal", "y")


# ---- synthetic world


def build_world(tmp_path):
    shutil.copytree(ROOT / "data/evidence", tmp_path / "data/evidence")
    sdir = tmp_path / "data/scenarios/v2"
    sdir.mkdir(parents=True)
    content = {}
    for p in sorted((ROOT / "data/scenarios/v2").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        ev = tmp_path / d["evidence"]["reference"]
        d["status"] = "author_checked"
        d["author_id"] = "project-owner-01"
        d["evidence"]["sha256"] = file_sha256(ev)
        d["evidence"]["verification_status"] = "author_checked"
        (sdir / p.name).write_text(json.dumps(d, indent=2), encoding="utf-8")
    cfg = json.loads((ROOT / "configs/receiver_experiment.json").read_text(encoding="utf-8"))
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/receiver_experiment.json").write_text(json.dumps(cfg), encoding="utf-8")
    scenarios = [load_scenario(p) for p in sorted(sdir.glob("*.json"))]
    for s in scenarios:
        content[s.scenario_id] = {"scenario_sha256": file_sha256(sdir / f"{s.scenario_id}.json"), "evidence_sha256": s.evidence.sha256}
    prop = reg.build_cohort_proposal(scenarios, "pilot-proposal-1", tmp_path)
    (tmp_path / "configs/pilot_cohort_proposal.json").write_text(prop.model_dump_json(), encoding="utf-8")
    registry = reg.proposal_to_registry(prop, "pilot-1", "2026-11-09T00:00:00Z")
    (tmp_path / "configs/pilot_registry.json").write_text(registry.model_dump_json(), encoding="utf-8")
    (tmp_path / "configs/pilot_run_policy.json").write_text(json.dumps({"scope": {
        "planned_episodes": 240, "scenario_ids": sorted(content), "content": content}}), encoding="utf-8")
    man = tmp_path / "protocol/scenario_v1"
    man.mkdir(parents=True)
    (man / "PROTOCOL_MANIFEST.json").write_text(json.dumps({"status": "APPROVED"}), encoding="utf-8")
    (tmp_path / "attestation.txt").write_text("owner attestation placeholder", encoding="utf-8")
    doc = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    for f in doc["fields"].values():
        f["status"] = "approved"
    ref = doc["fields"]
    ref["theta_fraction"]["value"], ref["pi"]["value"] = 0.5, 0.1
    ref["pi_breach_rule"]["value"], ref["pi_breach_consequence"]["value"] = "rule", "consequence"
    ref["approval_reference"]["value"] = "OWNER-REF-1"
    doc["status"] = "APPROVED"
    doc["pilot_intent"] = "AUTHORIZED"
    d = doc["owner_decisions"]
    d["cohort"]["status"] = "frozen"
    d["hist_a_year_1612"]["status"] = "accepted"
    d["near_duplicate_geo_sci"]["status"] = "resolved"
    d["author_id"].update(status="confirmed", value="project-owner-01")
    for c in doc["custody"]:
        c["status"] = "complete"
    doc["attestation_file"] = "attestation.txt"
    (tmp_path / "configs/pilot_policy_proposal.json").write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


def test_satisfied_world_has_no_blockers(tmp_path):
    w = build_world(tmp_path)
    report = readiness_report(w)
    assert report.ready, [(i.code, i.message) for i in report.blockers]
    assert format_readiness(report).rstrip().endswith(READY_TEXT)


def edit_proposal(w, fn):
    p = w / "configs/pilot_policy_proposal.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d), encoding="utf-8")


def _unapprove_all(d):
    for f in d["fields"].values():
        f["status"] = "proposed"
    d["status"] = "PROPOSAL — NOT APPROVED"
    d["pilot_intent"] = "NOT AUTHORIZED"
    d["fields"]["approval_reference"].update(status="pending_owner", value=None)


FLIPS = {
    "policy_not_approved": lambda w: edit_proposal(w, _unapprove_all),
    "policy_fields_not_approved": lambda w: edit_proposal(w, lambda d: (d["fields"]["ps11"].update(status="proposed"), d.update(status="PROPOSAL — NOT APPROVED"))),
    "author_id_unconfirmed": lambda w: edit_proposal(w, lambda d: d["owner_decisions"]["author_id"].update(status="pending_owner", value=None)),
    "near_duplicate_unresolved": lambda w: edit_proposal(w, lambda d: d["owner_decisions"]["near_duplicate_geo_sci"].update(status="unresolved")),
    "cohort_not_frozen": lambda w: edit_proposal(w, lambda d: d["owner_decisions"]["cohort"].update(status="selected_by_owner_not_frozen")),
    "hist_decision_open": lambda w: edit_proposal(w, lambda d: d["owner_decisions"]["hist_b_wording"].update(status="unresolved")),
    "custody_pending": lambda w: edit_proposal(w, lambda d: d["custody"][2].update(status="pending_owner_action")),
    "attestation_missing": lambda w: edit_proposal(w, lambda d: d.update(attestation_file=None)),
    "attestation_missing_file": lambda w: (w / "attestation.txt").unlink(),
    "pilot_intent_not_authorized": lambda w: edit_proposal(w, lambda d: d.update(pilot_intent="NOT AUTHORIZED")),
    "policy_value_unset": lambda w: edit_proposal(w, lambda d: (d["fields"]["pi"].update(value=None, status="pending_owner"), d.update(status="PROPOSAL — NOT APPROVED"))),
    "policy_value_mismatch": lambda w: edit_proposal(w, lambda d: d["fields"]["ps05a_max_episodes"].update(value=999)),
    "cohort_not_fixed": lambda w: (w / "configs/pilot_registry.json").unlink(),
    "policy_file_missing": lambda w: (w / "configs/pilot_run_policy.json").unlink(),
    "cohort_proposal_invalid": lambda w: (w / "configs/pilot_cohort_proposal.json").unlink(),
}


@pytest.mark.parametrize("name", sorted(FLIPS))
def test_each_condition_is_required(tmp_path, name):
    w = build_world(tmp_path)
    FLIPS[name](w)
    report = readiness_report(w)
    assert not report.ready
    expected = "attestation_missing" if name.startswith("attestation") else name
    assert expected in codes(report), [(i.code, i.message) for i in report.items]


def test_evidence_mismatch_blocker(tmp_path):
    w = build_world(tmp_path)
    ev = w / "data/evidence/geo-a.md"
    ev.write_text(ev.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
    report = readiness_report(w)
    assert not report.ready and "evidence_binding" in codes(report)


def test_missing_evidence_hash_blocks(tmp_path):
    w = build_world(tmp_path)
    p = w / "data/scenarios/v2/geo-a.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["evidence"]["sha256"] = None
    p.write_text(json.dumps(d), encoding="utf-8")
    report = readiness_report(w)
    assert not report.ready and {"evidence_binding", "not_pilot_eligible"} & codes(report)


def test_policy_digest_mismatch_blocker(tmp_path):
    w = build_world(tmp_path)
    p = w / "configs/pilot_run_policy.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["scope"]["content"]["geo-a"]["evidence_sha256"] = "0" * 64
    p.write_text(json.dumps(d), encoding="utf-8")
    assert "policy_digest_mismatch" in codes(readiness_report(w))


def test_stale_cohort_proposal_blocker(tmp_path):
    w = build_world(tmp_path)
    p = w / "configs/pilot_cohort_proposal.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["members"][0]["scenario_sha256"] = "1" * 64
    p.write_text(json.dumps(d), encoding="utf-8")
    assert "cohort_proposal_stale" in codes(readiness_report(w))


def test_scenario_count_mismatch_blocks(tmp_path):
    w = build_world(tmp_path)
    for n in ("hist-a", "hist-b"):
        (w / f"data/scenarios/v2/{n}.json").unlink()
    report = readiness_report(w)
    assert not report.ready and codes(report) & {"cohort_size_mismatch", "cohort_proposal_stale", "policy_value_mismatch"}


# ---- never reads secrets or the key


def test_reader_never_opens_answer_key_or_env(tmp_path, monkeypatch):
    seen = []
    real_open, real_read_text, real_read_bytes = builtins.open, Path.read_text, Path.read_bytes
    real_path_open = Path.open

    def rec(p):
        seen.append(str(p))

    def fake_open(file, *a, **k):
        rec(file)
        return real_open(file, *a, **k)

    def fake_text(self, *a, **k):
        rec(self)
        return real_read_text(self, *a, **k)

    def fake_bytes(self, *a, **k):
        rec(self)
        return real_read_bytes(self, *a, **k)

    def fake_popen(self, *a, **k):
        rec(self)
        return real_path_open(self, *a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(Path, "read_text", fake_text)
    monkeypatch.setattr(Path, "read_bytes", fake_bytes)
    monkeypatch.setattr(Path, "open", fake_popen)
    readiness_report()
    assert seen
    for s in seen:
        low = s.lower()
        assert "answer_key" not in low and not low.endswith(".env") and "/.env" not in low, s
