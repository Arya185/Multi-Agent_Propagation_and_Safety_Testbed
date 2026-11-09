"""Pilot gate and cohort proposal (Stage 4J.7, Agent A). Offline; data/ is only read, never edited.

author_checked is an AUTHOR self-check status only: not independent review, adjudication, protocol approval or a freeze.
"""

import json
import shutil
from pathlib import Path

import pytest

from maps.registry import (
    CohortProposal,
    Registry,
    build_cohort_proposal,
    check_registry,
    cohort_proposal_problems,
    load_cohort_proposal,
    pilot_eligibility_problems,
    pilot_run_problems,
    proposal_to_registry,
)
from maps.scenarios import file_sha256, load_scenario_dir
from maps.schemas import Scenario

ROOT = Path(__file__).resolve().parents[1]
FIXED = "2026-12-01T09:00:00+00:00"
IDS = [f"{p}-{m}" for p in ("biz", "geo", "hist", "sci", "sw") for m in "ab"]


def _raw(name):
    return json.loads((ROOT / f"data/scenarios/v2/{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def drafts():
    return load_scenario_dir(ROOT / "data/scenarios/v2")


@pytest.fixture
def repo(tmp_path):
    """A temporary repo root holding copies of the ten evidence files at their real relative paths."""
    for name in IDS:
        ref = _raw(name)["evidence"]["reference"]
        (tmp_path / ref).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / ref, tmp_path / ref)
    return tmp_path


def make(name, repo_root, status="author_checked", **over):
    raw = _raw(name)
    raw["status"], raw["author_id"] = status, "author-1"
    raw["evidence"]["verification_status"] = "author_checked"
    raw["evidence"]["sha256"] = file_sha256(repo_root / raw["evidence"]["reference"])
    for k, v in over.items():
        raw[k] = v
    return Scenario.model_validate(raw)


@pytest.fixture
def eligible(repo):
    return [make(n, repo) for n in IDS]


def ref(sid, version=1):
    return {"scenario_id": sid, "scenario_version": version}


def pilot_registry(ids=IDS):
    return Registry.model_validate({"cohorts": [{"cohort_id": "pilot-1", "family": "pilot", "members": [ref(i) for i in ids], "fixed_on": FIXED}]})


# ---- the pilot gate -------------------------------------------------------------------------------------------------
def test_real_drafts_fail_the_pilot_gate_with_a_draft_reason(drafts):
    problems = pilot_eligibility_problems(drafts)
    assert problems and all(any(f"{s.scenario_id}@1" in p for p in problems) for s in drafts)
    assert any("draft" in p for p in problems)


def test_author_checked_with_matching_hash_and_author_passes(eligible, repo):
    assert pilot_eligibility_problems(eligible, repo) == []
    assert pilot_run_problems(pilot_registry(), eligible, repo) == []


def test_pilot_frozen_is_allowed(repo):
    s = [make(n, repo, status="pilot_frozen") for n in IDS]
    assert pilot_eligibility_problems(s, repo) == []


def test_a_draft_member_is_named_with_its_status(repo):
    s = make("biz-a", repo, status="draft")
    assert any("biz-a@1" in p and "'draft'" in p for p in pilot_eligibility_problems([s], repo))


def test_missing_author_id(repo):
    s = make("biz-a", repo, author_id=None)
    assert any("biz-a@1" in p and "author_id" in p for p in pilot_eligibility_problems([s], repo))


def test_missing_evidence_hash(repo):
    s = make("biz-a", repo)
    s = s.model_copy(update={"evidence": s.evidence.model_copy(update={"sha256": None})})
    assert any("biz-a" in p and "no evidence.sha256" in p for p in pilot_eligibility_problems([s], repo))


def test_mismatching_and_malformed_evidence_hash(repo):
    s = make("biz-a", repo)
    wrong = s.model_copy(update={"evidence": s.evidence.model_copy(update={"sha256": "0" * 64})})
    assert any("mismatch" in p for p in pilot_eligibility_problems([wrong], repo))
    bad = s.model_copy(update={"evidence": s.evidence.model_copy(update={"sha256": "XYZ"})})
    assert any("malformed" in p for p in pilot_eligibility_problems([bad], repo))


def test_evidence_bytes_changed_after_hashing_block(eligible, repo):
    path = repo / eligible[0].evidence.reference
    path.write_bytes(path.read_bytes() + b"\nextra line\n")
    problems = pilot_eligibility_problems(eligible, repo)
    assert any(eligible[0].scenario_id in p and "mismatch" in p for p in problems)
    assert len(problems) == 1


def test_unverified_evidence_status_blocks(repo):
    s = make("biz-a", repo)
    u = s.model_copy(update={"evidence": s.evidence.model_copy(update={"verification_status": "unverified"})})
    assert any("biz-a@1" in p and "unverified" in p for p in pilot_eligibility_problems([u], repo))


def test_one_failing_pair_member_is_reported_by_key(eligible, repo):
    eligible[1] = eligible[1].model_copy(update={"author_id": None})
    problems = pilot_eligibility_problems(eligible, repo)
    assert problems and all(p.startswith("biz-b@1") for p in problems)
    run = pilot_run_problems(pilot_registry(), eligible, repo)
    assert any(p.startswith("biz-b@1") for p in run)


def test_messages_do_not_carry_claim_values(drafts):
    text = " ".join(pilot_eligibility_problems(drafts))
    for s in drafts:
        assert s.claim.asserted_value not in text


def test_gate_applies_only_to_assigned_scenarios(eligible, drafts, repo):
    reg = pilot_registry(["biz-a", "biz-b"])
    problems = pilot_run_problems(reg, eligible[:2] + [d for d in drafts if d.scenario_id == "geo-a"], repo)
    assert any("geo-a@1 is not assigned" in p for p in problems)
    assert not any("geo-a@1: pilot gate" in p for p in problems)


# ---- the confirmatory gate is unchanged -----------------------------------------------------------------------------
def test_a_pilot_cohort_scenario_still_cannot_enter_a_confirmatory_cohort():
    both = {"cohorts": [
        {"cohort_id": "pilot-1", "family": "pilot", "members": [ref("biz-a")], "fixed_on": FIXED},
        {"cohort_id": "conf-1", "family": "confirmatory", "members": [ref("biz-a")], "fixed_on": FIXED}]}
    with pytest.raises(ValueError, match="both a pilot and a confirmatory cohort"):
        Registry.model_validate(both)


def test_a_pilot_exposed_scenario_still_cannot_enter_a_confirmatory_cohort():
    raw = {"cohorts": [{"cohort_id": "conf-1", "family": "confirmatory", "members": [ref("biz-a")], "fixed_on": FIXED}],
           "exposures": [{"scenario": ref("biz-a"), "run_id": "run-1", "recorded_on": FIXED}]}
    with pytest.raises(ValueError, match="is pilot-exposed"):
        Registry.model_validate(raw)


def test_author_checked_does_not_satisfy_a_confirmatory_cohort(eligible, repo):
    reg = Registry.model_validate({"cohorts": [{"cohort_id": "conf-1", "family": "confirmatory",
                                                "members": [ref("biz-a"), ref("biz-b")], "fixed_on": FIXED}]})
    problems = check_registry(reg, eligible, repo)
    assert any("not 'frozen'" in p for p in problems)


# ---- the proposal ---------------------------------------------------------------------------------------------------
@pytest.fixture
def proposal(eligible, repo):
    return build_cohort_proposal(eligible, "prop-1", repo)


def test_build_is_sorted_hashed_and_not_fixed(proposal, eligible, repo):
    assert proposal.status == "PROPOSED — NOT FIXED" and proposal.family == "pilot" and proposal.fixed_on is None
    ids = [m.scenario.scenario_id for m in proposal.members]
    assert ids == sorted(IDS) and len(ids) == 10
    assert all(len(m.scenario_sha256) == 64 and len(m.evidence_sha256) == 64 for m in proposal.members)
    assert cohort_proposal_problems(proposal, eligible, repo) == []


def test_round_trip_load(proposal, tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps(proposal.model_dump()), encoding="utf-8")
    assert load_cohort_proposal(path) == proposal


def test_unreadable_evidence_gives_none(eligible, tmp_path):
    p = build_cohort_proposal(eligible[:2], "prop-1", tmp_path / "empty")
    assert all(m.evidence_sha256 is None for m in p.members)


def test_partial_pair_is_rejected(proposal, eligible, repo):
    half = proposal.model_copy(update={"members": proposal.members[1:]})
    problems = cohort_proposal_problems(half, eligible, repo)
    assert any("pair biz is not a complete" in p for p in problems)
    assert any("biz-a@1: loaded scenario is not in the proposal" in p for p in problems)


def test_unknown_version_and_duplicates(proposal, eligible, repo):
    m = proposal.members[0]
    ghost = m.model_copy(update={"scenario": m.scenario.model_copy(update={"scenario_version": 2})})
    problems = cohort_proposal_problems(proposal.model_copy(update={"members": [*proposal.members, ghost]}), eligible, repo)
    assert any("biz-a@2: not among the loaded" in p for p in problems)
    dup = proposal.model_copy(update={"members": [*proposal.members, m]})
    assert any("more than once" in p for p in cohort_proposal_problems(dup, eligible, repo))


def test_stale_scenario_hash(proposal, eligible, repo):
    changed = eligible[0].model_copy(update={"author_id": "someone-else"})
    problems = cohort_proposal_problems(proposal, [changed, *eligible[1:]], repo)
    assert problems == ["biz-a@1: recorded scenario_sha256 is stale"]


def test_stale_evidence_hash(proposal, eligible, repo):
    path = repo / eligible[0].evidence.reference
    path.write_bytes(path.read_bytes() + b"x")
    assert cohort_proposal_problems(proposal, eligible, repo) == ["biz-a@1: recorded evidence_sha256 is stale"]


def test_fixed_on_must_be_null(proposal):
    data = proposal.model_dump()
    data["fixed_on"] = FIXED
    with pytest.raises(ValueError):
        CohortProposal.model_validate(data)


def test_proposal_to_registry_refuses_blank_fixed_on(proposal):
    for bad in (None, "", "   "):
        with pytest.raises(ValueError, match="fixed_on"):
            proposal_to_registry(proposal, "pilot-1", bad)  # type: ignore[arg-type]


def test_proposal_to_registry_refuses_invalid_proposal(proposal):
    dup = proposal.model_copy(update={"members": [*proposal.members, proposal.members[0]]})
    with pytest.raises(ValueError, match="more than once"):
        proposal_to_registry(dup, "pilot-1", FIXED)


def test_proposal_to_registry_with_a_timestamp(proposal, eligible, repo):
    reg = proposal_to_registry(proposal, "pilot-1", FIXED)
    assert reg.cohorts[0].family == "pilot" and reg.cohorts[0].fixed_on == FIXED and len(reg.cohorts[0].members) == 10
    assert pilot_run_problems(reg, eligible, repo) == []
    with pytest.raises(ValueError):
        proposal_to_registry(proposal, "pilot-1", "not a time")


# ---- the committed proposal -----------------------------------------------------------------------------------------
def test_committed_proposal(drafts):
    p = load_cohort_proposal(ROOT / "configs/pilot_cohort_proposal.json")
    assert p.proposal_id == "pilot-proposal-1" and p.status == "PROPOSED — NOT FIXED" and p.fixed_on is None
    assert len(p.members) == 10
    pairs = {}
    for m in p.members:
        pairs.setdefault(m.scenario.scenario_id.rsplit("-", 1)[0], []).append(m.scenario.scenario_id)
    assert len(pairs) == 5 and all(len(v) == 2 for v in pairs.values())
    # Currently not stale against the real drafts; this WILL go stale at the author_checked transition (regenerate).
    assert cohort_proposal_problems(p, drafts) == []
    assert "draft" in p.note and "not a registry" in p.note
