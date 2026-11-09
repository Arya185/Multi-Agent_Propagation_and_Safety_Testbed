"""Stage 4J.6B: conflict declarations are superseded by new records, never overwritten."""
import copy

import pytest

from maps.schemas import (
    ConflictDeclaration, Scenario, active_declaration, declaration_chain, declaration_record_sha256,
    independent_review_problems, qualifying_independent_reviewers, scenario_content_sha256,
)
from test_review_records import T_ASSIGN, T_DECLARE, T_LATE, T_SUBMIT, _adjudicated, _checked, _frozen, _invalid, _with_adjudicator

T1 = "2026-12-01T09:00:00+00:00"   # == T_DECLARE, before T_SUBMIT
T2 = "2026-12-01T09:30:00+00:00"
T3 = "2026-12-01T10:00:00+00:00"
MATCH = "do not form a valid supersession chain"


def ident(raw_decl):
    return declaration_record_sha256(ConflictDeclaration.model_validate(raw_decl))


def rev(raw, rid="rev-a"):
    return [d for d in raw["conflict_declarations"] if d["reviewer_id"].casefold() == rid.casefold()]


def supersede(raw, prev, declared_on, **fields):
    new = {**prev, "declared_on": declared_on, "supersedes_declaration_sha256": ident(prev), **fields}
    new.pop("declaration_sha256", None)
    raw["conflict_declarations"].append(new)
    return new


def root(raw, rid="rev-a"):
    return rev(raw, rid)[0]


def test_single_plain_declaration_unchanged():
    s = _checked(_frozen())
    assert qualifying_independent_reviewers(s) == ["rev-a", "rev-b"]
    assert len(declaration_chain(s, "rev-a")) == 1 and active_declaration(s, "rev-a").supersedes_declaration_sha256 is None
    assert declaration_chain(s, "nobody") == [] and active_declaration(s, "nobody") is None
    assert independent_review_problems(_checked(_frozen())) == []


def test_two_and_three_record_chains_and_latest_is_identifiable():
    raw = _frozen()
    second = supersede(raw, root(raw), T2, other_conflict="x")
    third = supersede(raw, second, T3, other_conflict=None)
    s = Scenario.model_validate(raw)
    chain = declaration_chain(s, "rev-a")
    assert [d.declared_on for d in chain] == [T1, T2, T3]
    assert active_declaration(s, "rev-a") == chain[-1] and chain[-1].other_conflict is None
    two = _frozen()
    supersede(two, root(two), T2)
    assert len(declaration_chain(Scenario.model_validate(two), "rev-a")) == 2


def test_chain_order_is_independent_of_file_order():
    raw = _frozen()
    supersede(raw, root(raw), T2)
    raw["conflict_declarations"].reverse()
    s = Scenario.model_validate(raw)
    assert [d.declared_on for d in declaration_chain(s, "rev-a")] == [T1, T2]


def test_previous_records_preserved_and_content_hash_unchanged():
    base = _checked(_frozen())
    raw = _frozen()
    first = copy.deepcopy(root(raw))
    supersede(raw, root(raw), T2, other_conflict="x")
    s = _checked(raw)
    assert scenario_content_sha256(s) == scenario_content_sha256(base)
    assert ConflictDeclaration.model_validate(first) in s.conflict_declarations
    assert len(rev(raw)) == 2


def test_fork_rejected():
    raw = _frozen()
    r = root(raw)
    supersede(raw, r, T2)
    supersede(raw, r, T3)
    _invalid(raw, MATCH)


def test_self_reference_rejected():
    raw = _frozen()
    raw["conflict_declarations"][0]["supersedes_declaration_sha256"] = ident(raw["conflict_declarations"][0])
    _invalid(raw, MATCH)


def test_cycle_rejected():
    raw = _frozen()
    r = root(raw)
    a = {**r, "declared_on": T2, "supersedes_declaration_sha256": "1" * 64}
    b = {**r, "declared_on": T3, "supersedes_declaration_sha256": ident(a)}
    a["supersedes_declaration_sha256"] = ident(b)  # a -> b -> (old a): the hashes no longer match, so also dangling
    raw["conflict_declarations"] += [a, b]
    _invalid(raw, MATCH)


def test_detached_cycle_with_a_root_rejected():
    raw = _frozen()
    r = root(raw)
    a = {**r, "declared_on": T2, "supersedes_declaration_sha256": ident(r)}
    b = {**r, "declared_on": T3, "supersedes_declaration_sha256": ident(a)}
    # a points at r, b at a; make r also point at b is impossible by hash, so approximate with two roots instead
    raw["conflict_declarations"] += [a, b, {**r, "declared_on": T3, "other_conflict": "y"}]
    _invalid(raw, MATCH)


def test_dangling_reference_rejected():
    raw = _frozen()
    supersede(raw, root(raw), T2)
    raw["conflict_declarations"][-1]["supersedes_declaration_sha256"] = "f" * 64
    _invalid(raw, MATCH)


def test_duplicate_identity_rejected():
    raw = _frozen()
    raw["conflict_declarations"].append(copy.deepcopy(root(raw)))
    _invalid(raw, MATCH)
    raw = _frozen()
    n = supersede(raw, root(raw), T2)
    raw["conflict_declarations"].append(copy.deepcopy(n))
    _invalid(raw, MATCH)


def test_two_roots_rejected():
    raw = _frozen()
    raw["conflict_declarations"].append({**root(raw), "declared_on": T2, "other_conflict": "z"})
    _invalid(raw, MATCH)


@pytest.mark.parametrize("when", [T1, "2026-12-01T08:59:00+00:00"])
def test_chronology_must_strictly_increase(when):
    raw = _frozen()
    supersede(raw, root(raw), when)
    _invalid(raw, MATCH)


def test_message_names_the_reviewer_only():
    raw = _frozen()
    raw["conflict_declarations"].append({**root(raw), "other_conflict": "SECRET-DETAIL"})
    with pytest.raises(Exception) as e:
        Scenario.model_validate(raw)
    assert "rev-a" in str(e.value) and "SECRET-DETAIL" not in str(e.value)


def test_case_variant_ids_form_one_chain():
    raw = _frozen()
    supersede(raw, root(raw), T2, reviewer_id="REV-A")
    s = Scenario.model_validate(raw)
    assert len(declaration_chain(s, "rev-A")) == 2
    assert active_declaration(s, "Rev-a").reviewer_id == "REV-A"
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-a", "rev-b"]


@pytest.mark.parametrize("bad", ["abc", "A" * 64, "g" * 64, "", "a" * 63])
def test_malformed_supersedes_hash_rejected(bad):
    raw = _frozen()
    raw["conflict_declarations"][0]["supersedes_declaration_sha256"] = bad
    _invalid(raw, "supersedes_declaration_sha256")


def test_retraction_after_submission_does_not_requalify():
    from test_review_records import _reviewer_block
    raw = _frozen([_reviewer_block("rev-a", authored_or_edited=True), _reviewer_block("rev-b")])
    supersede(raw, root(raw), T_LATE, authored_or_edited=False)
    s = _checked(raw)
    assert "rev-a" not in qualifying_independent_reviewers(s)


def test_retraction_before_any_submission_requalifies():
    from test_review_records import _reviewer_block
    raw = _frozen([_reviewer_block("rev-a", authored_or_edited=True), _reviewer_block("rev-b")])
    supersede(raw, root(raw), T2, authored_or_edited=False)
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-a", "rev-b"]


def test_revised_declaration_adding_a_conflict_disqualifies_even_before_submission():
    raw = _frozen()
    supersede(raw, root(raw), T2, other_conflict="friend of author")
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]


def test_revision_filed_after_submission_adding_a_conflict_disqualifies():
    raw = _frozen()
    supersede(raw, root(raw), T_LATE, authored_or_edited=True)
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]


def test_root_declared_after_first_submission_still_fails_timing_rule():
    from test_review_records import _reviewer_block
    raw = _frozen([_reviewer_block("rev-a", declared=T_LATE), _reviewer_block("rev-b")])
    supersede(raw, root(raw), "2026-12-04T10:00:00+00:00")
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]


@pytest.mark.parametrize("flag", ["author_relationship", "paired_scenario_relationship"])
def test_declared_relationship_flags_disqualify_including_on_the_active_record(flag):
    raw = _frozen()
    raw["conflict_declarations"][0][flag] = True
    assert "rev-a" not in qualifying_independent_reviewers(_checked(raw))
    raw = _frozen()
    supersede(raw, root(raw), T2, **{flag: True})
    assert "rev-a" not in qualifying_independent_reviewers(_checked(raw))


def test_no_new_field_is_required_for_qualification():
    raw = _frozen()
    for d in raw["conflict_declarations"]:
        for k in ("supersedes_declaration_sha256", "declaration_sha256", "content_sha256", "independent_assessment_declared",
                  "author_relationship", "paired_scenario_relationship"):
            d.pop(k, None)
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-a", "rev-b"]
    raw = _frozen()
    supersede(raw, root(raw), T2)   # active record without content hash or assessment flag
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-a", "rev-b"]


def test_declaration_sha256_on_a_chain_record_must_match():
    raw = _frozen()
    n = supersede(raw, root(raw), T2)
    n["declaration_sha256"] = ident(n)
    Scenario.model_validate(raw)
    n["declaration_sha256"] = "0" * 64
    _invalid(raw, "declaration_sha256 does not match")


def test_supersedes_field_is_part_of_the_identity():
    raw = _frozen()
    r = root(raw)
    assert ident(r) != ident({**r, "supersedes_declaration_sha256": "1" * 64})


def test_adjudicator_with_superseded_declaration_uses_the_active_one():
    raw = _with_adjudicator(_frozen(adjudication=_adjudicated()), other_conflict="old conflict")
    adj_root = [d for d in raw["conflict_declarations"] if d["reviewer_id"] == "adj-1"][0]
    _invalid(raw, "clean conflict declaration")
    supersede(raw, adj_root, T2, other_conflict=None)
    s = _checked(raw)
    assert active_declaration(s, "adj-1").other_conflict is None
    # and the reverse: an active conflicted record is rejected although the root was clean
    raw = _with_adjudicator(_frozen(adjudication=_adjudicated()))
    adj_root = [d for d in raw["conflict_declarations"] if d["reviewer_id"] == "adj-1"][0]
    supersede(raw, adj_root, T2, other_conflict="new conflict")
    _invalid(raw, "clean conflict declaration")
