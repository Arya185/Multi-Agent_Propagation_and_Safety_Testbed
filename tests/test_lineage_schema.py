"""Stage 4J.6A schema tests: lineage, evidence hash, case-folded identities, optional declaration fields."""
import copy
import hashlib
import json

import pytest
from pydantic import ValidationError

from maps.schemas import (
    ConflictDeclaration, ReviewerAssignment, Scenario, declaration_record_sha256, qualifying_independent_reviewers,
)
from test_review_records import (
    SHA, T_ASSIGN, T_DECLARE, T_LATE, _adjudicated, _base, _bind, _checked, _frozen, _independently_checked, _invalid,
    _reviewer_block, _with_adjudicator, _with_reviewers,
)

# ---- lineage ---------------------------------------------------------------------------------------------
def test_version_one_without_parent_is_valid():
    s = Scenario.model_validate(_base())
    assert s.scenario_version == 1 and s.supersedes is None


def test_version_above_one_requires_a_parent():
    raw = _base()
    raw["scenario_version"] = 2
    _invalid(raw, "requires supersedes")


def test_valid_parent_and_child():
    raw = _base()
    raw.update(scenario_version=2, supersedes="biz-a@1")
    assert Scenario.model_validate(raw).supersedes == "biz-a@1"
    raw.update(scenario_version=3, supersedes="biz-a@2")
    Scenario.model_validate(raw)


def test_cross_id_supersession_is_allowed():
    raw = _base()
    raw.update(scenario_version=2, supersedes="other-id@7")
    Scenario.model_validate(raw)


def test_self_reference_and_non_earlier_parent_rejected():
    for version, ref in ((2, "biz-a@2"), (2, "biz-a@3"), (1, "biz-a@1")):
        raw = _base()
        raw.update(scenario_version=version, supersedes=ref)
        _invalid(raw, "earlier version")


@pytest.mark.parametrize("ref", ["biz-a@0", "biz-a@-1", "biz-a", "biz-a@", "@1", "biz-a@01", "biz-a@1.5", "biz a@1", ""])
def test_malformed_or_invalid_version_reference_rejected(ref):
    raw = _base()
    raw.update(scenario_version=2, supersedes=ref)
    _invalid(raw, "supersedes must look like")


# ---- evidence hash ---------------------------------------------------------------------------------------
def test_valid_evidence_hash_accepted_and_none_still_ok_for_draft():
    raw = _base()
    assert raw["evidence"]["sha256"] is None or len(raw["evidence"]["sha256"]) == 64
    raw["evidence"]["sha256"] = SHA
    Scenario.model_validate(raw)


@pytest.mark.parametrize("bad", ["xyz", "A" * 64, "a" * 63, "a" * 65, ""])
def test_malformed_evidence_hash_rejected(bad):
    raw = _base()
    raw["evidence"]["sha256"] = bad
    _invalid(raw, "evidence.sha256 must be a lowercase")


def test_missing_evidence_hash_rejected_at_independently_checked_and_frozen():
    for builder in (_frozen, _independently_checked):
        raw = builder()
        raw["evidence"]["sha256"] = None
        _bind(raw)   # rebind so the failure is the missing hash, not stale content
        _invalid(raw, "needs evidence.sha256")
        Scenario.model_validate(builder())


def test_cue_and_independence_only_data_is_unaffected_by_the_evidence_hash():
    raw = _base()
    raw["evidence"]["sha256"] = None
    raw["status"] = "author_checked"
    raw["evidence"]["verification_status"] = "author_checked"
    Scenario.model_validate(raw)


# ---- case-folded identities ------------------------------------------------------------------------------
def test_author_and_reviewer_collide_case_insensitively():
    raw = _frozen([_reviewer_block("AUTHOR-1"), _reviewer_block("rev-b"), _reviewer_block("rev-c")])
    raw["review"]["reviewer"] = "rev-b"
    s = _checked(raw)
    assert qualifying_independent_reviewers(s) == ["rev-b", "rev-c"]


def test_distinct_ids_remain_distinct():
    s = _checked(_frozen([_reviewer_block("rev-a"), _reviewer_block("rev-b")]))
    assert qualifying_independent_reviewers(s) == ["rev-a", "rev-b"]


def test_duplicate_assignment_collides_across_case():
    raw = _frozen()
    raw["reviewer_assignments"].append({**raw["reviewer_assignments"][0], "reviewer_id": "REV-A"})
    _invalid(raw, "duplicate reviewer assignment")


def test_duplicate_declaration_collides_across_case():
    raw = _frozen()
    raw["conflict_declarations"].append({**raw["conflict_declarations"][0], "reviewer_id": "REV-A"})
    # Stage 4J.6B: an unlinked second record is no longer a "duplicate" but an invalid supersession chain.
    _invalid(raw, "do not form a valid supersession chain")


def test_duplicate_submission_collides_across_case():
    raw = _frozen()
    raw["review_submissions"].append({**raw["review_submissions"][0], "reviewer_id": "REV-A"})
    _invalid(raw, "duplicate submission")


def test_adjudicator_vs_author_and_reviewers_case_insensitive():
    _invalid(_with_adjudicator(_frozen(adjudication=_adjudicated(adjudicator_id="AUTHOR-1"))), "cannot adjudicate")
    _invalid(_frozen(adjudication=_adjudicated(adjudicator_id="REV-A")), "cannot be a reviewer")


def test_adjudicator_who_is_assignment_only_reviewer_is_rejected():
    raw = _with_adjudicator(_frozen(adjudication=_adjudicated()))
    raw["reviewer_assignments"].append({"reviewer_id": "ADJ-1", "stages": ["fact"], "assigned_on": T_ASSIGN})
    _invalid(raw, "cannot be a reviewer")


def test_conflict_declaration_lookup_is_case_insensitive_and_stored_ids_unchanged():
    raw = _frozen()
    for d in raw["conflict_declarations"]:
        d["reviewer_id"] = d["reviewer_id"].upper()
    s = _checked(raw)
    assert qualifying_independent_reviewers(s) == ["rev-a", "rev-b"]
    assert [d.reviewer_id for d in s.conflict_declarations] == ["REV-A", "REV-B"]
    # a disqualifying declaration under a different case still disqualifies
    raw = _frozen()
    raw["conflict_declarations"][0]["reviewer_id"] = "REV-A"
    raw["conflict_declarations"][0]["authored_or_edited"] = True
    assert "rev-a" not in qualifying_independent_reviewers(_checked(raw))


# ---- declaration fields ----------------------------------------------------------------------------------
def _decl(**kw):
    base = {"reviewer_id": "rev-a", "declared_on": T_DECLARE, "authored_or_edited": False,
            "had_truth_label_information": False}
    base.update(kw)
    return base


def test_defaults_keep_old_records_valid_and_nothing_new_is_required():
    d = ConflictDeclaration.model_validate(_decl())
    assert (d.author_relationship, d.paired_scenario_relationship) == (False, False)
    assert d.content_sha256 is None and d.independent_assessment_declared is None and d.declaration_sha256 is None
    assert not d.disqualifying
    a = ReviewerAssignment.model_validate({"reviewer_id": "rev-a", "stages": ["fact"], "assigned_on": T_ASSIGN})
    assert a.accepted_on is None
    Scenario.model_validate(_frozen())   # the standard fixture carries none of the new fields


def test_accepted_on_must_not_precede_assigned_on():
    ok = {"reviewer_id": "rev-a", "stages": ["fact"], "assigned_on": T_ASSIGN}
    assert ReviewerAssignment.model_validate({**ok, "accepted_on": T_ASSIGN}).accepted_on == T_ASSIGN
    assert ReviewerAssignment.model_validate({**ok, "accepted_on": T_LATE})
    with pytest.raises(ValidationError, match="accepted_on"):
        ReviewerAssignment.model_validate({**ok, "accepted_on": "2000-01-01T00:00:00+00:00"})
    with pytest.raises(ValidationError):
        ReviewerAssignment.model_validate({**ok, "accepted_on": "not-a-time"})


@pytest.mark.parametrize("field", ["content_sha256", "declaration_sha256"])
@pytest.mark.parametrize("bad", ["xyz", "A" * 64, "a" * 63])
def test_malformed_declaration_hashes_rejected(field, bad):
    with pytest.raises(ValidationError, match="lowercase SHA-256"):
        ConflictDeclaration.model_validate(_decl(**{field: bad}))


def test_declaration_sha256_must_match_the_record():
    d = ConflictDeclaration.model_validate(_decl(content_sha256=SHA, independent_assessment_declared=True))
    good = declaration_record_sha256(d)
    data = d.model_dump(mode="json")
    data.pop("declaration_sha256")
    assert good == hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    assert ConflictDeclaration.model_validate(_decl(content_sha256=SHA, independent_assessment_declared=True,
                                                    declaration_sha256=good)).declaration_sha256 == good
    with pytest.raises(ValidationError, match="does not match"):
        ConflictDeclaration.model_validate(_decl(content_sha256=SHA, independent_assessment_declared=True,
                                                 declaration_sha256="0" * 64))
    with pytest.raises(ValidationError, match="does not match"):   # edited after hashing
        ConflictDeclaration.model_validate(_decl(content_sha256=SHA, independent_assessment_declared=False,
                                                 declaration_sha256=good))


@pytest.mark.parametrize("field", ["author_relationship", "paired_scenario_relationship"])
def test_true_relationship_flag_disqualifies(field):
    assert ConflictDeclaration.model_validate(_decl(**{field: True})).disqualifying
    raw = _frozen()
    raw["conflict_declarations"][0][field] = True
    s = _checked(raw)
    assert qualifying_independent_reviewers(s) == ["rev-b"]
    _invalid(raw, "at least 2 required")


def test_independent_assessment_declared_is_recorded_only():
    for value in (True, False, None):
        raw = _frozen()
        raw["conflict_declarations"][0]["independent_assessment_declared"] = value
        Scenario.model_validate(raw)
