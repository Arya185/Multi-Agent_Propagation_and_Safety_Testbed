"""Independent-review records and the scenario status gates (Stage 4J.2, updated for Stage 4J.3). Offline; no provider calls.

Stage 4J.3 expectation changes, all from owner decisions A and B (recorded in the ledger):
  * scores are integers 0-3 and each stage scores exactly its own criteria (fact: truth, ambiguity;
    cue: cues, equivalence; pair: pair; independence: provenance, manipulation);
  * the operative score of a criterion is the minimum across qualifying independent reviewers and must reach
    the approved threshold (3 for truth, manipulation, cues, provenance; 2 for pair, equivalence, ambiguity);
  * adjudication outcomes are revise or reject only. An adjudication never raises a score, and any adjudication
    record blocks 'frozen'. The Stage 4J.2 tests that expected a resolved 'accept' to permit 'frozen' were
    replaced by tests of the new rule; they were not weakened or skipped.
"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from maps.scenarios import load_scenario_dir
from maps.schemas import (
    CRITERION_THRESHOLDS,
    MIN_INDEPENDENT_REVIEWERS,
    REVIEW_STAGES,
    RUBRIC_CRITERIA,
    STAGE_CRITERIA,
    Scenario,
    adjudication_triggers,
    independent_review_problems,
    operative_scores,
    qualifying_independent_reviewers,
    scenario_content_sha256,
    threshold_failures,
)

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
T_DECLARE = "2026-12-01T09:00:00+00:00"
T_ASSIGN = "2026-12-01T08:00:00+00:00"
T_SUBMIT = "2026-12-02T10:00:00+00:00"
T_LATE = "2026-12-03T10:00:00+00:00"


def _full(value=3, **overrides):
    """Scores for one stage: every criterion of the stage at `value`, with per-criterion overrides."""
    return {stage: {c: overrides.get(c, value) for c in cs} for stage, cs in STAGE_CRITERIA.items()}


def _base():
    return json.loads((ROOT / "data/scenarios/v2/biz-a.json").read_text(encoding="utf-8"))


def _reviewer_block(rid, stages=REVIEW_STAGES, declared=T_DECLARE, scores=None, **declaration):
    scores = scores or _full()
    decl = {"reviewer_id": rid, "declared_on": declared, "authored_or_edited": False,
            "had_truth_label_information": False, "other_conflict": None}
    decl.update(declaration)
    return (
        {"reviewer_id": rid, "stages": list(stages), "assigned_on": T_ASSIGN},
        decl,
        [{"reviewer_id": rid, "stage": s, "submitted_at": T_SUBMIT, "scores": dict(scores[s]),
          "form_sha256": None, "notes": ""} for s in stages],
    )


def _with_reviewers(raw, reviewers):
    raw["reviewer_assignments"], raw["conflict_declarations"], raw["review_submissions"] = [], [], []
    for assignment, decl, subs in reviewers:
        raw["reviewer_assignments"].append(assignment)
        raw["conflict_declarations"].append(decl)
        raw["review_submissions"] += subs
    return raw


PARTNER = "b" * 64


def _bind(raw, partner=PARTNER):
    """Bind every submission to the content it reviews (Stage 4J.5): the hash excludes review fields and status, so it
    can be computed from a probe at a status that does not need the finished review record."""
    stripped = {k: v for k, v in raw.items() if k not in ("reviewer_assignments", "conflict_declarations",
                                                          "review_submissions", "adjudication")}
    content = scenario_content_sha256(Scenario.model_validate({**stripped, "status": "author_checked"}))
    for sub in raw["review_submissions"]:
        sub["content_sha256"] = content
        if sub["stage"] == "pair":
            sub["partner_content_sha256"] = partner
    return raw


def _frozen(reviewers=None, **overrides):
    raw = _base()
    raw["author_id"] = "author-1"
    raw["status"] = "frozen"
    raw["evidence"]["verification_status"] = "independently_checked"
    raw["evidence"]["sha256"] = SHA
    raw["review"] = {"reviewer": "rev-a", "blind_to_truth": True, "reviewed_on": "2026-12-02",
                     "independence_confirmed": True}
    _with_reviewers(raw, reviewers if reviewers is not None else [_reviewer_block("rev-a"), _reviewer_block("rev-b")])
    raw.update(overrides)
    return _bind(raw)


def _checked(raw):
    """The same record at a status that does not enforce the independent-review gate, to inspect the helpers."""
    return Scenario.model_validate({**raw, "status": "author_checked"})


def _invalid(raw, match=None):
    with pytest.raises(ValidationError, match=match):
        Scenario.model_validate(raw)


# ---- backward compatibility and defaults ----------------------------------------------------------------
def test_the_ten_existing_scenario_files_remain_valid_with_safe_defaults():
    scenarios = load_scenario_dir(ROOT / "data/scenarios/v2")
    assert len(scenarios) == 10
    for s in scenarios:
        assert s.schema_version == "2.1-draft" and s.status == "draft"
        assert s.scenario_version == 1 and s.supersedes is None and s.author_id is None
        assert s.reviewer_assignments == [] and s.conflict_declarations == []
        assert s.review_submissions == [] and s.adjudication is None
        assert qualifying_independent_reviewers(s) == [] and operative_scores(s) == {}
        assert adjudication_triggers(s) == []


def test_missing_optional_fields_receive_defaults():
    s = Scenario.model_validate(_base())
    assert (s.scenario_version, s.supersedes, s.author_id) == (1, None, None)


def test_scenario_version_must_be_positive():
    raw = _base()
    raw["scenario_version"] = 0
    _invalid(raw)


def test_supersedes_must_name_an_earlier_version_of_the_same_scenario():
    raw = _base()
    raw["scenario_version"] = 2
    raw["supersedes"] = "biz-a@1"
    assert Scenario.model_validate(raw).supersedes == "biz-a@1"
    for bad in ("biz-a@2", "biz-a@3", "biz-a", "biz a@1", ""):
        raw["supersedes"] = bad
        _invalid(raw)


def test_author_id_is_an_opaque_identifier_not_a_name():
    raw = _base()
    raw["author_id"] = "author-1"
    assert Scenario.model_validate(raw).author_id == "author-1"
    for bad in ("Arya Patel", "", " x", "a@b"):
        raw["author_id"] = bad
        _invalid(raw, "opaque identifier|string_too_short|author_id")


def test_timestamps_need_a_utc_offset():
    raw = _frozen()
    raw["review_submissions"][0]["submitted_at"] = "2026-12-02T10:00:00"
    _invalid(raw, "UTC offset")


# ---- the accepted scale and stage mapping -----------------------------------------------------------------
def test_the_seven_approved_criteria_are_unchanged_and_each_is_scored_in_exactly_one_stage():
    assert set(RUBRIC_CRITERIA) == {"truth", "manipulation", "cues", "provenance", "pair", "equivalence", "ambiguity"}
    assert STAGE_CRITERIA == {"fact": ("truth", "ambiguity"), "cue": ("cues", "equivalence"),
                              "pair": ("pair",), "independence": ("provenance", "manipulation")}
    assert sorted(c for cs in STAGE_CRITERIA.values() for c in cs) == sorted(RUBRIC_CRITERIA)
    assert CRITERION_THRESHOLDS == {"truth": 3, "manipulation": 3, "cues": 3, "provenance": 3,
                                    "pair": 2, "equivalence": 2, "ambiguity": 2}


@pytest.mark.parametrize("score", [-1, 4, 10, True, False])
def test_scores_must_be_integers_from_zero_to_three(score):
    raw = _frozen()
    raw["review_submissions"][0]["scores"] = {"truth": score, "ambiguity": 3}
    _invalid(raw)


@pytest.mark.parametrize("score", [0, 1, 2, 3])
def test_every_score_from_zero_to_three_is_accepted(score):
    raw = _frozen()
    raw["review_submissions"][0]["scores"] = {"truth": score, "ambiguity": 3}
    assert _checked(raw).review_submissions[0].scores["truth"] == score  # accepted as a score; the gate is tested separately


@pytest.mark.parametrize("scores", [
    {"truth": 3},                              # missing ambiguity
    {"truth": 3, "ambiguity": 3, "cues": 3},   # a criterion from another stage
    {"cues": 3, "equivalence": 3},             # the wrong stage entirely
    {"nonsense": 3, "truth": 3},               # unknown criterion
    {},
])
def test_each_stage_scores_exactly_its_own_criteria(scores):
    raw = _frozen()
    raw["review_submissions"][0]["scores"] = scores   # the first submission is the 'fact' stage
    _invalid(raw)


# ---- reviewer records ---------------------------------------------------------------------------------------
def test_multiple_reviewer_submissions_are_kept_separately_with_their_own_scores():
    reviewers = [_reviewer_block("rev-a", scores=_full(truth=3)), _reviewer_block("rev-b", scores=_full(truth=2))]
    s = _checked(_frozen(reviewers))
    assert qualifying_independent_reviewers(s) == ["rev-a", "rev-b"]
    by_reviewer = {r: [x for x in s.review_submissions if x.reviewer_id == r and x.stage == "fact"][0] for r in ("rev-a", "rev-b")}
    assert by_reviewer["rev-a"].scores["truth"] == 3 and by_reviewer["rev-b"].scores["truth"] == 2
    assert len(s.review_submissions) == 8
    assert operative_scores(s)["truth"] == 2  # the minimum; neither original score is altered


def test_duplicate_submission_for_the_same_reviewer_and_stage_is_rejected():
    raw = _frozen()
    raw["review_submissions"].append(copy.deepcopy(raw["review_submissions"][0]))
    _invalid(raw, "originals are never overwritten")


def test_submission_needs_a_matching_assignment():
    raw = _frozen()
    raw["review_submissions"].append({"reviewer_id": "rev-z", "stage": "fact", "submitted_at": T_SUBMIT,
                                      "scores": {"truth": 3, "ambiguity": 3}, "form_sha256": None, "notes": ""})
    _invalid(raw, "no matching assignment")
    raw = _frozen([_reviewer_block("rev-a", stages=("fact",)), _reviewer_block("rev-b")])
    raw["review_submissions"].append({"reviewer_id": "rev-a", "stage": "cue", "submitted_at": T_SUBMIT,
                                      "scores": {"cues": 3, "equivalence": 3}, "form_sha256": None, "notes": ""})
    _invalid(raw, "no matching assignment")


def test_form_hash_must_be_a_sha256_digest():
    raw = _frozen()
    raw["review_submissions"][0]["form_sha256"] = "xyz"
    _invalid(raw, "SHA-256")


# ---- independence -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("declaration", [
    {"authored_or_edited": True},
    {"had_truth_label_information": True},
    {"other_conflict": "co-author of the same study"},
])
def test_conflicted_reviewers_do_not_count_as_independent(declaration):
    raw = _frozen([_reviewer_block("rev-a", **declaration), _reviewer_block("rev-b")])
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]
    _invalid(raw, "at least 2 required")


def test_the_author_cannot_count_as_an_independent_reviewer():
    raw = _frozen([_reviewer_block("author-1"), _reviewer_block("rev-b")])
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]
    _invalid(raw, "at least 2 required")


def test_a_declaration_filed_after_the_first_submission_does_not_qualify():
    raw = _frozen([_reviewer_block("rev-a", declared=T_LATE), _reviewer_block("rev-b")])
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]


def test_a_reviewer_without_a_declaration_does_not_qualify():
    raw = _frozen()
    raw["conflict_declarations"] = [d for d in raw["conflict_declarations"] if d["reviewer_id"] != "rev-a"]
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]


def test_all_four_stages_are_required_from_each_reviewer():
    short = _reviewer_block("rev-a", stages=("fact", "cue", "pair"))
    raw = _frozen([short, _reviewer_block("rev-b")])
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]
    _invalid(raw, "at least 2 required")
    raw = _frozen()  # assigned all four but submitted only three
    raw["review_submissions"] = [s for s in raw["review_submissions"] if not (s["reviewer_id"] == "rev-a" and s["stage"] == "independence")]
    assert qualifying_independent_reviewers(_checked(raw)) == ["rev-b"]


def test_fewer_than_two_qualifying_reviewers_cannot_establish_frozen():
    assert MIN_INDEPENDENT_REVIEWERS == 2
    _invalid(_frozen([_reviewer_block("rev-a")]), "at least 2 required")
    assert Scenario.model_validate(_frozen()).status == "frozen"


def test_frozen_needs_a_known_author_and_the_legacy_gates():
    raw = _frozen()
    raw["author_id"] = None
    _invalid(raw, "needs author_id")
    raw = _frozen()
    raw["evidence"]["sha256"] = None
    _invalid(raw, "evidence.sha256")
    raw = _frozen()
    raw["review"]["independence_confirmed"] = None
    _invalid(raw, "human-confirmed independence")


def _independently_checked(**overrides):
    """Independently reviewed but not frozen. Stage 4J.6A: independently_checked now also needs evidence.sha256, so the
    evidence hash from _frozen is kept (it used to be set to None here)."""
    raw = _frozen(**overrides)
    raw["status"] = "independently_checked"
    return _bind(raw)


def test_independently_checked_needs_the_independent_review_evidence_and_the_evidence_hash():
    # Stage 4J.6A: was "...but_not_the_evidence_hash" (hash None accepted); the hash is now required.
    s = Scenario.model_validate(_independently_checked())
    assert s.status == "independently_checked" and s.evidence.sha256 == SHA
    raw = _independently_checked()
    raw["evidence"]["sha256"] = None
    _bind(raw)   # rebind so the failure is the missing hash, not stale content
    _invalid(raw, "needs evidence.sha256")
    _invalid(_frozen([_reviewer_block("rev-a")]) | {"status": "independently_checked"}, "at least 2 required")


def test_the_old_independently_checked_shape_no_longer_works():
    raw = _base()
    raw["status"] = "independently_checked"
    raw["evidence"]["verification_status"] = "independently_checked"
    raw["review"] = {"reviewer": "x", "blind_to_truth": True, "reviewed_on": "2026-01-01", "independence_confirmed": True}
    _invalid(raw, "author_id")           # the invented reviewer name and a true flag are not enough
    raw["author_id"] = "author-1"
    _invalid(raw, "qualifying independent reviewer")


def test_independently_checked_summary_record_must_agree_with_the_recorded_reviews():
    raw = _independently_checked()
    raw["review"]["reviewer"] = "someone-else"        # not a recorded qualifying reviewer
    _invalid(raw, "qualifying independent reviewers")
    raw = _independently_checked()
    raw["review"]["blind_to_truth"] = False            # 'independent' but not blind is contradictory
    _invalid(raw, "blind to the truth label")
    raw = _independently_checked()
    raw["review"]["reviewer"] = "author-1"             # the author is never a qualifying reviewer
    _invalid(raw, "qualifying independent reviewers")


def test_independently_checked_needs_a_known_author():
    raw = _independently_checked()
    raw["author_id"] = None
    _invalid(raw, "needs author_id")


# ---- content binding (Stage 4J.5, decision 2) ------------------------------------------------------------
def test_matching_content_hash_passes_and_the_hash_is_deterministic_and_order_independent():
    raw = _frozen()
    a = Scenario.model_validate(raw)
    reordered = json.loads(json.dumps(raw, sort_keys=True))     # same content, keys in a different order
    b = Scenario.model_validate(reordered)
    assert scenario_content_sha256(a) == scenario_content_sha256(b) == raw["review_submissions"][0]["content_sha256"]
    assert independent_review_problems(a) == []


@pytest.mark.parametrize("edit", [
    lambda r: r["claim"].__setitem__("text", r["claim"]["text"] + " "),
    lambda r: r["message_templates"].__setitem__(1, r["message_templates"][1] + " "),
    lambda r: r["communication_roots"][0].__setitem__("description", "changed"),
    lambda r: r["communication_roots"][2].__setitem__("stated_origin", "Other Group"),
    lambda r: r.__setitem__("construction_note", "edited after review"),
    lambda r: r.__setitem__("independence_assessment", "edited after review"),
    lambda r: r["evidence"].__setitem__("sha256", "c" * 64),
    lambda r: r.update(scenario_version=2, supersedes="biz-a@1"),  # v>1 now requires supersedes (Stage 4J.6A)
    lambda r: r.__setitem__("author_id", "author-2"),
])
def test_any_content_change_after_review_makes_the_reviews_stale_and_invalidates_frozen(edit):
    raw = _frozen()
    before = scenario_content_sha256(Scenario.model_validate(raw))
    edit(raw)
    probe = Scenario.model_validate({**raw, "status": "author_checked"})
    assert scenario_content_sha256(probe) != before         # the hash is sensitive to the change
    _invalid(raw, "bound to different content|stale|author_id|qualifying|already|supersedes")


def test_an_edited_frozen_scenario_cannot_keep_its_frozen_state_with_the_old_reviews():
    raw = _frozen()
    raw["message_templates"][2] = raw["message_templates"][2].replace("employees", "people")  # edit after review
    _invalid(raw, "bound to different content")


def test_lifecycle_and_review_fields_do_not_change_the_content_hash():
    raw = _frozen()
    base = scenario_content_sha256(Scenario.model_validate(raw))
    for edit in (lambda r: r.__setitem__("name_collision_check", "clear"),
                 lambda r: r["evidence"].__setitem__("verification_status", "author_checked"),
                 lambda r: r["review_submissions"][0].__setitem__("notes", "n"),
                 lambda r: r["review_submissions"][0]["scores"].__setitem__("truth", 0)):
        other = copy.deepcopy(raw)
        edit(other)
        assert scenario_content_sha256(Scenario.model_validate({**other, "status": "author_checked"})) == base


def test_a_missing_content_hash_fails_independently_checked_and_frozen():
    for builder in (_frozen, _independently_checked):
        raw = builder()
        raw["review_submissions"][0]["content_sha256"] = None
        _invalid(raw, "has no content hash")
        raw = builder()
        for sub in raw["review_submissions"]:
            sub["content_sha256"] = None
        _invalid(raw, "has no content hash|at least 2 required")


def test_a_pair_stage_submission_needs_a_partner_content_hash_when_bound():
    raw = _frozen()
    pair_sub = next(s for s in raw["review_submissions"] if s["stage"] == "pair" and s["reviewer_id"] == "rev-a")
    pair_sub["partner_content_sha256"] = None
    _invalid(raw, "no partner content hash")


def test_partner_hash_is_only_allowed_on_pair_stage_submissions_and_must_be_a_digest():
    raw = _frozen()
    raw["review_submissions"][0]["partner_content_sha256"] = PARTNER      # the first submission is the fact stage
    _invalid(raw, "pair-stage submissions only")
    raw = _frozen()
    raw["review_submissions"][0]["content_sha256"] = "not-a-digest"
    _invalid(raw, "content_sha256 must be")


def test_copied_reviews_do_not_qualify_a_revised_child_scenario():
    parent = _frozen()
    child = copy.deepcopy(parent)                       # a revised version copying the parent's whole review block
    child["scenario_version"], child["supersedes"] = 2, "biz-a@1"
    child["message_templates"][0] = child["message_templates"][0] + " "
    _invalid(child, "bound to different content")
    unchanged_content = copy.deepcopy(parent)           # even with identical text the version number alone changes the hash
    unchanged_content["scenario_version"], unchanged_content["supersedes"] = 2, "biz-a@1"
    _invalid(unchanged_content, "bound to different content")


def test_stale_records_do_not_count_as_qualifying_reviewers_in_bound_mode():
    raw = _frozen()
    for sub in raw["review_submissions"]:
        if sub["reviewer_id"] == "rev-a":
            sub["content_sha256"] = "d" * 64
    s = Scenario.model_validate({**raw, "status": "author_checked"})
    assert qualifying_independent_reviewers(s, bound=False) == ["rev-a", "rev-b"]
    assert qualifying_independent_reviewers(s, bound=True) == ["rev-b"]


# ---- operative scores and thresholds ----------------------------------------------------------------------
def test_operative_score_is_the_minimum_across_qualifying_reviewers_only():
    reviewers = [_reviewer_block("rev-a", scores=_full(cues=3)), _reviewer_block("rev-b", scores=_full(cues=2)),
                 _reviewer_block("rev-c", scores=_full(cues=0), authored_or_edited=True)]
    s = _checked(_frozen(reviewers))
    assert qualifying_independent_reviewers(s) == ["rev-a", "rev-b"]
    assert operative_scores(s)["cues"] == 2          # rev-c's 0 is ignored because rev-c is conflicted
    assert adjudication_triggers(s) == []             # 3 vs 2 is not a trigger


@pytest.mark.parametrize("criterion,threshold", sorted(CRITERION_THRESHOLDS.items()))
def test_each_criterion_must_reach_its_approved_threshold(criterion, threshold):
    assert threshold_failures(_checked(_frozen())) == []
    reached = _checked(_frozen([_reviewer_block("rev-a", scores=_full(**{criterion: threshold})), _reviewer_block("rev-b")]))
    assert threshold_failures(reached) == []
    missed = _frozen([_reviewer_block("rev-a", scores=_full(**{criterion: threshold - 1})), _reviewer_block("rev-b")])
    assert any(criterion in f for f in threshold_failures(_checked(missed)))
    _invalid(missed, "below the threshold")


def test_a_score_of_two_is_enough_for_pair_equivalence_and_ambiguity_but_not_for_the_other_four():
    ok = _frozen([_reviewer_block("rev-a", scores=_full(pair=2, equivalence=2, ambiguity=2)), _reviewer_block("rev-b")])
    assert Scenario.model_validate(ok).status == "frozen"
    for criterion in ("truth", "manipulation", "cues", "provenance"):
        _invalid(_frozen([_reviewer_block("rev-a", scores=_full(**{criterion: 2})), _reviewer_block("rev-b")]), criterion)


# ---- adjudication ---------------------------------------------------------------------------------------
def _adjudicated(**fields):
    base = {"reason": "reviewers disagreed on a criterion", "adjudicator_id": "adj-1",
            "decided_on": T_LATE, "outcome": "revise", "rationale": "documented", "evidence_ref": None}
    base.update(fields)
    return base


def _with_adjudicator(raw, declared=T_DECLARE, **declaration):
    decl = {"reviewer_id": "adj-1", "declared_on": declared, "authored_or_edited": False,
            "had_truth_label_information": False, "other_conflict": None}
    decl.update(declaration)
    raw["conflict_declarations"].append(decl)
    return raw


def test_triggers_are_a_zero_from_a_qualifying_reviewer_or_a_gap_of_two_points():
    zero = _checked(_frozen([_reviewer_block("rev-a", scores=_full(ambiguity=0)), _reviewer_block("rev-b")]))
    assert adjudication_triggers(zero) == ["ambiguity: score 0 from rev-a", "ambiguity: reviewers differ by 3 points"]
    gap = _checked(_frozen([_reviewer_block("rev-a", scores=_full(pair=3)), _reviewer_block("rev-b", scores=_full(pair=1))]))
    assert adjudication_triggers(gap) == ["pair: reviewers differ by 2 points"]
    near = _checked(_frozen([_reviewer_block("rev-a", scores=_full(pair=3)), _reviewer_block("rev-b", scores=_full(pair=2))]))
    assert adjudication_triggers(near) == []


def test_an_unresolved_trigger_blocks_frozen_and_the_problem_names_it():
    reviewers = [_reviewer_block("rev-a", scores=_full(pair=3)), _reviewer_block("rev-b", scores=_full(pair=1))]
    _invalid(_frozen(reviewers), "adjudication trigger unresolved: pair: reviewers differ by 2 points")


def test_a_resolved_adjudication_never_rescues_a_scenario_it_ends_in_revise_or_reject():
    reviewers = [_reviewer_block("rev-a", scores=_full(pair=3)), _reviewer_block("rev-b", scores=_full(pair=1))]
    for outcome in ("revise", "reject"):
        raw = _with_adjudicator(_frozen(reviewers, adjudication=_adjudicated(outcome=outcome)))
        s = _checked(raw)
        problems = independent_review_problems(s)
        assert any(f"adjudication outcome is {outcome!r}" in p for p in problems)
        assert any("below the threshold" in p for p in problems)   # the operative score was not raised
        _invalid(raw, "must be revised and reviewed again")


def test_accept_is_not_an_adjudication_outcome():
    raw = _with_adjudicator(_frozen(adjudication=_adjudicated(outcome="accept")))
    _invalid(raw)


def test_any_adjudication_record_blocks_frozen_even_without_a_trigger():
    raw = _with_adjudicator(_frozen(adjudication=_adjudicated()))
    assert independent_review_problems(_checked(raw)) != []
    _invalid(raw)


def test_adjudication_never_changes_the_original_reviewer_submissions():
    reviewers = [_reviewer_block("rev-a", scores=_full(pair=3)), _reviewer_block("rev-b", scores=_full(pair=1))]
    plain = _checked(_frozen(reviewers))
    adjudicated = _checked(_with_adjudicator(_frozen(reviewers, adjudication=_adjudicated())))
    assert [x.model_dump() for x in plain.review_submissions] == [x.model_dump() for x in adjudicated.review_submissions]
    assert operative_scores(plain) == operative_scores(adjudicated)


def test_adjudication_dated_before_or_at_the_last_submission_is_rejected():
    for stamp in ("2026-12-02T09:59:59+00:00", T_SUBMIT):
        _invalid(_with_adjudicator(_frozen(adjudication=_adjudicated(decided_on=stamp))), "after every reviewer submission")


def test_unresolved_adjudication_is_representable_and_blocks_frozen():
    raw = _with_adjudicator(_frozen(adjudication={"reason": "reviewers disagreed on a criterion"}))
    s = _checked(raw)
    assert not s.adjudication.resolved
    assert "adjudication is required but unresolved" in independent_review_problems(s)
    _invalid(raw, "adjudication is required but unresolved")


def test_adjudication_resolution_is_all_or_nothing_and_needs_a_basis():
    for partial in ({"decided_on": None}, {"outcome": None}, {"adjudicator_id": None}):
        _invalid(_with_adjudicator(_frozen(adjudication=_adjudicated(**partial))), "together")
    _invalid(_with_adjudicator(_frozen(adjudication=_adjudicated(rationale=None, evidence_ref=None))),
             "rationale or an evidence reference")
    assert Scenario.model_validate({**_with_adjudicator(_frozen(adjudication=_adjudicated(rationale=None, evidence_ref="form-17"))),
                                    "status": "author_checked"})


def test_the_author_and_the_reviewers_cannot_adjudicate():
    _invalid(_with_adjudicator(_frozen(adjudication=_adjudicated(adjudicator_id="author-1")), ), "cannot adjudicate")
    raw = _frozen(adjudication=_adjudicated(adjudicator_id="rev-a"))
    _invalid(raw, "cannot be a reviewer")


def test_an_adjudicator_needs_a_clean_conflict_declaration_filed_in_time():
    _invalid(_frozen(adjudication=_adjudicated()), "clean conflict declaration")                     # none filed
    _invalid(_with_adjudicator(_frozen(adjudication=_adjudicated()), authored_or_edited=True), "clean conflict declaration")
    _invalid(_with_adjudicator(_frozen(adjudication=_adjudicated()), had_truth_label_information=True), "clean conflict declaration")
    _invalid(_with_adjudicator(_frozen(adjudication=_adjudicated()), declared="2026-12-04T00:00:00+00:00"), "clean conflict declaration")


# ---- pilot_frozen ------------------------------------------------------------------------------------------
def _pilot_frozen(**overrides):
    raw = _base()
    raw["status"] = "pilot_frozen"
    raw["evidence"]["verification_status"] = "author_checked"
    raw["evidence"]["sha256"] = SHA
    raw.update(overrides)
    return raw


def test_pilot_frozen_is_a_distinct_status_that_claims_no_independence():
    s = Scenario.model_validate(_pilot_frozen())
    assert s.status == "pilot_frozen" and s.status != "frozen"
    assert qualifying_independent_reviewers(s) == [] and independent_review_problems(s)


def test_pilot_frozen_needs_a_content_hash_author_checked_evidence_and_no_independence_claim():
    raw = _pilot_frozen()
    raw["evidence"]["sha256"] = None
    _invalid(raw, "evidence.sha256")
    raw = _pilot_frozen()
    raw["evidence"]["verification_status"] = "unverified"
    _invalid(raw, "exceeds evidence")
    raw = _pilot_frozen()
    raw["review"]["independence_confirmed"] = True
    _invalid(raw, "no independence claim")


def test_pilot_frozen_cannot_be_used_as_frozen():
    s = Scenario.model_validate(_pilot_frozen())
    assert s.status != "frozen"  # the main stage requires 'frozen' exactly (receiver.build_grid)
