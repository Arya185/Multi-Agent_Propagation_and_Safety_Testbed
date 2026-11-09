"""Pair-level review gate (Stage 4J.5): ``pair_review_problems`` and its wiring into ``check_registry``.
Offline; builds scenarios from data/scenarios/v2/biz-a.json and biz-b.json as dicts; no answer key is read."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from maps.registry import Registry, check_registry, pair_review_problems
from maps.scenarios import file_sha256, load_scenario_dir
from maps.schemas import STAGE_CRITERIA, Adjudication, Scenario, operative_scores, scenario_content_sha256

ROOT = Path(__file__).resolve().parents[1]
T_ASSIGN = "2026-12-01T08:00:00+00:00"
T_DECLARE = "2026-12-01T09:00:00+00:00"
T_SUBMIT = "2026-12-02T10:00:00+00:00"
FIXED = "2026-12-01T09:00:00+00:00"


def _raw(name):
    return json.loads((ROOT / f"data/scenarios/v2/{name}.json").read_text(encoding="utf-8"))


def _reviewed(raw, rids=("rev-a", "rev-b")):
    """Unbound record with complete, clean, perfect independent reviews (status still to be set)."""
    raw = copy.deepcopy(raw)
    raw["author_id"] = "author-1"
    raw["evidence"]["verification_status"] = "independently_checked"
    raw["evidence"]["sha256"] = file_sha256(ROOT / raw["evidence"]["reference"])  # real digest: check_registry reads the file bytes
    raw["review"] = {"reviewer": rids[0], "blind_to_truth": True, "reviewed_on": "2026-12-02", "independence_confirmed": True}
    raw["reviewer_assignments"], raw["conflict_declarations"], raw["review_submissions"] = [], [], []
    for rid in rids:
        raw["reviewer_assignments"].append({"reviewer_id": rid, "stages": list(STAGE_CRITERIA), "assigned_on": T_ASSIGN})
        raw["conflict_declarations"].append({"reviewer_id": rid, "declared_on": T_DECLARE, "authored_or_edited": False,
                                             "had_truth_label_information": False, "other_conflict": None})
        for stage, criteria in STAGE_CRITERIA.items():
            raw["review_submissions"].append({"reviewer_id": rid, "stage": stage, "submitted_at": T_SUBMIT,
                                              "scores": {c: 3 for c in criteria}, "form_sha256": None, "notes": ""})
    return raw


def _hash(raw):
    return scenario_content_sha256(Scenario.model_validate({**raw, "status": "author_checked"}))


def _bind(raw, own, partner):
    for sub in raw["review_submissions"]:
        sub["content_sha256"] = own
        if sub["stage"] == "pair":
            sub["partner_content_sha256"] = partner


def make_pair(rids_a=("rev-a", "rev-b"), rids_b=("rev-a", "rev-b"), status="frozen"):
    ra, rb = _reviewed(_raw("biz-a"), rids_a), _reviewed(_raw("biz-b"), rids_b)
    ha, hb = _hash(ra), _hash(rb)
    _bind(ra, ha, hb)
    _bind(rb, hb, ha)
    return Scenario.model_validate({**ra, "status": status}), Scenario.model_validate({**rb, "status": status})


def adjudication(who="adj-1", outcome="revise", resolved=True):
    if not resolved:
        return Adjudication(reason="gap")
    return Adjudication(reason="gap", adjudicator_id=who, decided_on=T_SUBMIT, outcome=outcome, rationale="r")


@pytest.fixture
def pair():
    return make_pair()


# ---- eligibility ------------------------------------------------------------------------------------------------
def test_two_eligible_members_have_no_problems(pair):
    assert pair_review_problems(*pair) == []


def test_a_reviewer_with_a_conflict_on_one_member_blocks_the_pair(pair):
    a, b = pair
    decls = [d.model_copy(update={"authored_or_edited": d.reviewer_id == "rev-b"}) for d in b.conflict_declarations]
    problems = pair_review_problems(a, b.model_copy(update={"conflict_declarations": decls}))
    # Stage 4J.6B: a reviewer who no longer qualifies on one member also breaks pair symmetry; both kinds of
    # message name the member that caused them.
    assert problems and all(p.startswith(("biz-b@1", "pair symmetry:")) for p in problems)
    assert any(p.startswith("biz-b@1") for p in problems) and any("biz-b@1" in p for p in problems)


def test_a_threshold_failure_on_one_member_blocks_the_pair(pair):
    a, b = pair
    subs = [s.model_copy(update={"scores": {"truth": 2, "ambiguity": 3}}) if s.stage == "fact" else s for s in a.review_submissions]
    problems = pair_review_problems(a.model_copy(update={"review_submissions": subs}), b)
    assert any("biz-a@1" in p and "truth" in p for p in problems)


def test_a_frozen_member_cannot_bypass_a_draft_partner():
    a, _ = make_pair()
    _, b_draft = make_pair(status="author_checked")
    problems = pair_review_problems(a, b_draft)
    assert any("biz-b@1 has status 'author_checked', not 'frozen'" in p for p in problems)
    assert not any(p.startswith("biz-a@1") for p in problems)


def test_a_frozen_member_cannot_bypass_a_blocked_partner(pair):
    a, b = pair
    blocked = b.model_copy(update={"conflict_declarations": []})
    assert pair_review_problems(a, blocked)


# ---- adjudication (pair-level, no rescue) --------------------------------------------------------------------------
@pytest.mark.parametrize("which", [0, 1])
def test_a_revise_adjudication_on_either_member_blocks_the_pair(pair, which):
    members = list(pair)
    members[which] = members[which].model_copy(update={"adjudication": adjudication()})
    problems = pair_review_problems(*members)
    key = members[which].scenario_id + "@1"
    assert f"pair needs a new version of both members: revise outcome on {key}" in problems


def test_a_reject_adjudication_retires_the_pair(pair):
    a, b = pair
    problems = pair_review_problems(a, b.model_copy(update={"adjudication": adjudication(outcome="reject")}))
    assert "pair retired: reject outcome on biz-b@1" in problems


def test_an_unresolved_adjudication_blocks_the_pair(pair):
    a, b = pair
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication(resolved=False)}), b)
    assert "adjudication unresolved on biz-a@1" in problems


def test_adjudication_cannot_raise_or_overwrite_reviewer_scores(pair):
    a, _ = pair
    subs = [s.model_copy(update={"scores": {"truth": 1, "ambiguity": 3}}) if s.stage == "fact" and s.reviewer_id == "rev-a" else s
            for s in a.review_submissions]
    low = a.model_copy(update={"review_submissions": subs})
    adjudicated = low.model_copy(update={"adjudication": adjudication()})
    assert operative_scores(adjudicated) == operative_scores(low) and operative_scores(low)["truth"] == 1
    assert adjudicated.review_submissions == low.review_submissions


# ---- adjudicator exclusion across the pair --------------------------------------------------------------------------
def test_a_clean_adjudicator_is_not_flagged_for_exclusion(pair):
    a, b = pair
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication("adj-1")}), b)
    assert not any("adjudicator of" in p for p in problems)


def test_an_adjudicator_who_authored_the_partner_is_flagged(pair):
    a, b = pair
    b2 = b.model_copy(update={"author_id": "author-2"})
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication("author-2")}), b2)
    assert "adjudicator of biz-a@1 is the author of biz-b@1" in problems


def test_an_adjudicator_who_authored_the_adjudicated_member_is_flagged(pair):
    a, b = pair
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication("author-1")}), b)
    assert "adjudicator of biz-a@1 is the author of biz-a@1" in problems


def test_an_adjudicator_who_reviewed_the_partner_is_flagged():
    a, b = make_pair(rids_a=("rev-a", "rev-b"), rids_b=("rev-a", "rev-c"))
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication("rev-c")}), b)
    assert "adjudicator of biz-a@1 is a reviewer of biz-b@1" in problems
    assert not any("is a reviewer of biz-a@1" in p for p in problems)  # clean on A, still no pass
    assert problems


def test_an_adjudicator_who_reviewed_the_adjudicated_member_is_flagged(pair):
    a, b = pair
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication("rev-b")}), b)
    assert "adjudicator of biz-a@1 is a reviewer of biz-a@1" in problems


def test_the_same_adjudicator_on_both_members_is_flagged(pair):
    a, b = pair
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication("adj-1")}),
                                    b.model_copy(update={"adjudication": adjudication("adj-1")}))
    assert "adjudicator of biz-a@1 is also the adjudicator of biz-b@1" in problems
    assert "adjudicator of biz-b@1 is also the adjudicator of biz-a@1" in problems


def test_different_adjudicators_on_both_members_are_still_blocked_by_the_outcomes(pair):
    a, b = pair
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication("adj-1")}),
                                    b.model_copy(update={"adjudication": adjudication("adj-2")}))
    assert problems and not any("also the adjudicator" in p for p in problems)


# ---- content binding ------------------------------------------------------------------------------------------------------
def test_stale_partner_content_is_reported(pair):
    a, b = pair
    edited = b.model_copy(update={"domain": "edited after the partner was reviewed"})
    problems = pair_review_problems(a, edited)
    assert any("pair-stage submission by rev-a on biz-a@1 is bound to different partner content (stale)" in p for p in problems)


def test_stale_own_content_is_reported(pair):
    a, b = pair
    edited = a.model_copy(update={"domain": "edited after review"})
    problems = pair_review_problems(edited, b)
    assert any(p.startswith("biz-a@1") and "different content" in p for p in problems)
    assert any("on biz-b@1 is bound to different partner content" in p for p in problems)


def test_a_member_edited_after_review_cannot_validate_as_frozen():
    ra = _reviewed(_raw("biz-a"))
    ra["status"] = "frozen"
    _bind(ra, "b" * 64, "c" * 64)
    with pytest.raises(ValidationError, match="qualifying independent reviewer"):
        Scenario.model_validate(ra)


def test_a_child_version_does_not_inherit_the_parents_review():
    parent = _reviewed(_raw("biz-a"))
    _bind(parent, _hash(parent), "c" * 64)
    child = {**copy.deepcopy(parent), "scenario_version": 2, "supersedes": "biz-a@1", "status": "frozen"}  # copied submissions
    assert _hash(child) != _hash(parent)
    with pytest.raises(ValidationError, match="qualifying independent reviewer"):
        Scenario.model_validate(child)


# ---- membership fails safe ------------------------------------------------------------------------------------------------
def test_inconsistent_membership_fails_safe(pair):
    a, b = pair
    for x, y in [(a, a), (b, b), (a, b.model_copy(update={"pair_id": "other"})),
                 (a, a.model_copy(update={"truth_status": "false"})), (b, a)]:
        problems = pair_review_problems(x, y)
        assert len(problems) == 1 and "pair membership invalid" in problems[0]


# ---- determinism, no mutation, messages --------------------------------------------------------------------------------------
def test_deterministic_and_does_not_mutate(pair):
    a, b = pair
    a = a.model_copy(update={"adjudication": adjudication("rev-a")})
    before = (a.model_dump(), b.model_dump())
    first = pair_review_problems(a, b)
    assert first == pair_review_problems(a, b) and first
    assert (a.model_dump(), b.model_dump()) == before
    assert len(first) == len(set(first))


def test_messages_carry_no_claim_values(pair):
    a, b = pair
    problems = pair_review_problems(a.model_copy(update={"adjudication": adjudication("rev-a"), "domain": "x"}), b)
    text = " ".join(problems)
    for s in pair:
        assert s.claim.asserted_value not in text and s.evidence.ground_truth_value not in text


# ---- check_registry wiring -----------------------------------------------------------------------------------------------------
def _registry(cohorts, lineage=()):
    return Registry.model_validate({"registry_version": 1, "cohorts": cohorts, "exposures": [], "lineage": list(lineage)})


def _conf(*refs):
    return {"cohort_id": "conf-1", "family": "confirmatory", "fixed_on": FIXED,
            "members": [{"scenario_id": i, "scenario_version": v} for i, v in refs]}


def test_check_registry_accepts_an_eligible_pair(pair):
    assert check_registry(_registry([_conf(("biz-a", 1), ("biz-b", 1))]), list(pair)) == []


def test_check_registry_reports_pair_problems_once_with_the_cohort_prefix(pair):
    a, b = pair
    blocked = a.model_copy(update={"adjudication": adjudication("adj-1")})
    problems = check_registry(_registry([_conf(("biz-a", 1), ("biz-b", 1))]), [blocked, b])
    assert "conf-1: pair retired: reject outcome on biz-a@1" not in problems
    assert "conf-1: pair needs a new version of both members: revise outcome on biz-a@1" in problems
    assert len(problems) == len(set(problems))


def test_check_registry_catches_a_stale_partner(pair):
    a, b = pair
    problems = check_registry(_registry([_conf(("biz-a", 1), ("biz-b", 1))]), [a, b.model_copy(update={"domain": "changed"})])
    assert any("bound to different partner content (stale)" in p for p in problems)


def test_check_registry_keeps_the_incomplete_pair_message(pair):
    problems = check_registry(_registry([_conf(("biz-a", 1))]), list(pair))
    assert any("not a complete true/false pair" in p for p in problems)


def _child_raw():
    ra, rb = _reviewed(_raw("biz-a")), _reviewed(_raw("biz-b"))
    ra.update(scenario_version=2, supersedes="biz-a@1")
    ha, hb = _hash(ra), _hash(rb)
    _bind(ra, ha, hb)
    _bind(rb, hb, ha)
    return ra, rb


def test_a_superseding_scenario_needs_a_registry_lineage_entry(pair):
    a, _ = pair
    ra, rb = _child_raw()
    child, b = Scenario.model_validate({**ra, "status": "frozen"}), Scenario.model_validate({**rb, "status": "frozen"})
    cohorts = [_conf(("biz-a", 2), ("biz-b", 1))]
    missing = check_registry(_registry(cohorts), [a, child, b])
    assert "biz-a@2 supersedes biz-a@1 but the registry has no lineage entry" in missing
    lineage = [{"scenario": {"scenario_id": "biz-a", "scenario_version": 2}, "supersedes": {"scenario_id": "biz-a", "scenario_version": 1}}]
    assert check_registry(_registry(cohorts, lineage), [a, child, b]) == []


# ---- the real scenarios -----------------------------------------------------------------------------------------------------------
def test_the_existing_ten_never_pass_a_confirmatory_pair_gate():
    ten = load_scenario_dir(ROOT / "data/scenarios/v2")
    pairs = {}
    for s in ten:
        pairs.setdefault(s.pair_id, {})[s.truth_status] = s
    assert len(pairs) == 5
    for members in pairs.values():
        assert pair_review_problems(members["true"], members["false"])
    cohorts = [_conf(*[(s.scenario_id, 1) for s in ten])]
    assert any("not 'frozen'" in p for p in check_registry(_registry(cohorts), ten))


# ---- Stage 4J.6A: identity separation across both members (ids compared through normalize_id) ----------------------------
def _with(s, **update):
    return s.model_copy(update=update)


def _retag(s, old, new):
    """Rename one reviewer id on every record of a member (submissions, assignments, declarations)."""
    def swap(items):
        return [x.model_copy(update={"reviewer_id": new}) if x.reviewer_id == old else x for x in items]
    return _with(s, review_submissions=swap(s.review_submissions), reviewer_assignments=swap(s.reviewer_assignments),
                 conflict_declarations=swap(s.conflict_declarations))


def test_valid_distinct_ids_pass_and_the_same_reviewer_on_both_members_is_allowed(pair):
    assert pair_review_problems(*pair) == []  # rev-a and rev-b review BOTH members; author-1 authored both


def test_a_case_variant_of_a_reviewer_id_is_the_same_identity_as_the_author(pair):
    a, b = pair
    a2 = _with(a, author_id="REV-A")  # differs from 'rev-a' only by case
    problems = pair_review_problems(a2, b)
    assert any("author of biz-a@1" in p and "is a reviewer of biz-a@1" in p for p in problems)
    assert any("author of biz-a@1" in p and "is a reviewer of biz-b@1" in p for p in problems)


def test_the_author_of_one_member_reviewing_the_other_is_blocked_both_ways(pair):
    a, b = pair
    assert any("author of biz-a@1" in p and "reviewer of biz-b@1" in p for p in pair_review_problems(_with(a, author_id="rev-b"), b))
    assert any("author of biz-b@1" in p and "reviewer of biz-a@1" in p for p in pair_review_problems(a, _with(b, author_id="rev-b")))


def test_authors_who_are_the_same_person_on_both_members_are_allowed(pair):
    a, b = pair
    assert a.author_id == b.author_id and pair_review_problems(a, b) == []


def test_an_author_who_only_has_an_assignment_or_declaration_is_still_a_reviewer(pair):
    a, b = pair
    only_assigned = _with(b, review_submissions=[], author_id="x")
    only_assigned = _with(only_assigned, author_id="rev-a")  # still listed in b.reviewer_assignments / declarations
    assert any("author of biz-b@1" in p and "reviewer of biz-b@1" in p for p in pair_review_problems(a, only_assigned))


@pytest.mark.parametrize("who,expect", [("AUTHOR-1", "is the author of biz-a@1"), ("Rev-B", "is a reviewer of biz-b@1")])
def test_adjudicator_overlap_is_detected_case_insensitively_on_either_member(pair, who, expect):
    a, b = pair
    problems = pair_review_problems(_with(a, adjudication=adjudication(who)), b)
    assert any("adjudicator of biz-a@1" in p and expect in p for p in problems)


def test_adjudicator_case_variant_of_the_other_adjudicator_is_flagged(pair):
    a, b = pair
    problems = pair_review_problems(_with(a, adjudication=adjudication("adj-1")), _with(b, adjudication=adjudication("ADJ-1")))
    assert "adjudicator of biz-a@1 is also the adjudicator of biz-b@1" in problems


def test_an_unrelated_adjudicator_adds_no_identity_problem(pair):
    a, b = pair
    problems = pair_review_problems(_with(b, adjudication=adjudication("adj-9")), a)
    assert not any("adjudicator of" in p for p in problems)


def test_identity_messages_use_keys_and_ids_not_claim_values(pair):
    a, b = pair
    text = " ".join(pair_review_problems(_with(a, author_id="REV-A"), b))
    for s in pair:
        assert s.claim.asserted_value not in text and s.evidence.ground_truth_value not in text


# ---- pair symmetry (Stage 4J.6B, owner Decision A: the same qualifying reviewer set on both members) -----------
def _symmetry(problems):
    return [p for p in problems if p.startswith("pair symmetry:")]


def test_identical_qualifying_reviewer_sets_pass():
    a, b = make_pair(rids_a=("rev-a", "rev-b"), rids_b=("rev-a", "rev-b"))
    assert pair_review_problems(a, b) == []


def test_disjoint_reviewer_sets_across_members_fail():
    a, b = make_pair(rids_a=("rev-a", "rev-b"), rids_b=("rev-c", "rev-d"))
    problems = _symmetry(pair_review_problems(a, b))
    assert len(problems) == 4                           # rev-a, rev-b missing on biz-b; rev-c, rev-d missing on biz-a
    assert any("reviewer rev-a qualifies on biz-a@1 but not on biz-b@1" in p and "has no record of them" in p for p in problems)
    assert any("reviewer rev-d qualifies on biz-b@1 but not on biz-a@1" in p for p in problems)


def test_one_additional_reviewer_on_one_member_fails():
    a, b = make_pair(rids_a=("rev-a", "rev-b", "rev-c"), rids_b=("rev-a", "rev-b"))
    problems = _symmetry(pair_review_problems(a, b))
    assert len(problems) == 1 and "reviewer rev-c qualifies on biz-a@1 but not on biz-b@1" in problems[0]


def test_case_only_id_differences_are_the_same_reviewer():
    a, b = make_pair(rids_a=("rev-a", "rev-b"), rids_b=("REV-A", "Rev-B"))
    assert _symmetry(pair_review_problems(a, b)) == []


def test_a_reviewer_who_fails_a_required_stage_on_the_other_member_breaks_symmetry():
    a, b = make_pair()
    subs = [s for s in b.review_submissions if not (s.reviewer_id == "rev-b" and s.stage == "independence")]
    problems = _symmetry(pair_review_problems(a, b.model_copy(update={"review_submissions": subs})))
    assert len(problems) == 1
    assert "reviewer rev-b qualifies on biz-a@1 but not on biz-b@1" in problems[0] and "do not qualify" in problems[0]


def test_a_missing_submission_for_one_reviewer_on_one_member_breaks_symmetry():
    a, b = make_pair()
    subs = [s for s in a.review_submissions if not (s.reviewer_id == "rev-a" and s.stage == "pair")]
    problems = _symmetry(pair_review_problems(a.model_copy(update={"review_submissions": subs}), b))
    assert any("reviewer rev-a qualifies on biz-b@1 but not on biz-a@1" in p for p in problems)


def test_a_stale_review_on_one_member_breaks_pair_eligibility():
    a, b = make_pair()
    stale = [s.model_copy(update={"content_sha256": "d" * 64}) if s.reviewer_id == "rev-a" else s for s in b.review_submissions]
    problems = pair_review_problems(a, b.model_copy(update={"review_submissions": stale}))
    assert problems and any("biz-b@1" in p for p in problems)
    assert any(p.startswith("pair symmetry:") and "reviewer rev-a" in p for p in problems)


def test_symmetric_valid_reviews_pass_with_larger_sets():
    a, b = make_pair(rids_a=("rev-a", "rev-b", "rev-c"), rids_b=("rev-c", "rev-b", "rev-a"))
    assert pair_review_problems(a, b) == []


def test_reviewer_overlap_across_different_pairs_is_not_a_pair_gate_failure():
    # the same people reviewing biz and another pair is a maps.validation human-review flag, never a pair-gate problem
    a, b = make_pair()
    other_a, other_b = make_pair(rids_a=("rev-a", "rev-b"), rids_b=("rev-a", "rev-b"))
    assert pair_review_problems(a, b) == [] and pair_review_problems(other_a, other_b) == []


def test_pair_eligibility_with_overlap_and_registry_gate_refuse(pair):
    a, b = pair
    overlapping = _with(a, author_id="Rev-A")
    reg = _registry([_conf(("biz-a", 1), ("biz-b", 1))])
    assert any("author of biz-a@1" in p for p in check_registry(reg, [overlapping, b], ROOT))
    from maps.registry import confirmatory_run_problems
    assert any("author of biz-a@1" in p for p in confirmatory_run_problems(reg, [overlapping, b], ROOT))


# ---- Stage 4J.6A: evidence integrity inside the pair gate (tmp_path copies; current bytes are read) ------------------------
def _evidence_root(tmp_path):
    (tmp_path / "data/evidence").mkdir(parents=True)
    for n in ("biz-a", "biz-b"):
        (tmp_path / f"data/evidence/{n}.md").write_bytes((ROOT / f"data/evidence/{n}.md").read_bytes())
    return tmp_path


def test_a_pair_with_matching_evidence_bytes_is_eligible(pair, tmp_path):
    root = _evidence_root(tmp_path)
    assert pair_review_problems(*pair, repo_root=root) == []
    assert check_registry(_registry([_conf(("biz-a", 1), ("biz-b", 1))]), list(pair), root) == []


def test_changed_evidence_bytes_without_a_json_change_block_eligibility(pair, tmp_path):
    root = _evidence_root(tmp_path)
    p = root / "data/evidence/biz-a.md"
    p.write_bytes(p.read_bytes() + b"\nsilently edited")
    problems = pair_review_problems(*pair, repo_root=root)
    assert problems and any("biz-a" in x and "mismatch" in x for x in problems)
    reg = _registry([_conf(("biz-a", 1), ("biz-b", 1))])
    assert any("mismatch" in x for x in check_registry(reg, list(pair), root))


def test_changed_partner_evidence_blocks_the_pair_with_the_partner_key(pair, tmp_path):
    root = _evidence_root(tmp_path)
    p = root / "data/evidence/biz-b.md"
    p.write_bytes(p.read_bytes() + b"x")
    problems = pair_review_problems(*pair, repo_root=root)
    assert problems and all(x.startswith("biz-b@1") for x in problems)


def test_missing_evidence_file_blocks_the_pair_and_a_single_confirmatory_member(pair, tmp_path):
    root = _evidence_root(tmp_path)
    (root / "data/evidence/biz-a.md").unlink()
    assert any("missing" in x for x in pair_review_problems(*pair, repo_root=root))
    single = _registry([_conf(("biz-a", 1))])  # single members are verified too, fail closed
    assert any("missing" in x for x in check_registry(single, list(pair), root))


def test_without_repo_root_the_pair_gate_does_not_read_files(pair, tmp_path):
    assert pair_review_problems(*pair) == []  # same result regardless of the file system


def test_no_extra_evidence_rule_for_cue_or_independence_fields(pair, tmp_path):
    a, b = pair
    root = _evidence_root(tmp_path)
    changed = _with(a, domain=a.domain)  # nothing but identity-neutral copy
    assert pair_review_problems(changed, b, repo_root=root) == []
