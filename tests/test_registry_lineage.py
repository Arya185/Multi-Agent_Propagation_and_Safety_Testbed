"""Stage 4J.6A lineage checks in ``check_registry``. Offline; scenarios come from data/scenarios/v2 as dicts."""

import copy
import json
from pathlib import Path

import pytest

from maps.registry import Registry, check_registry, confirmatory_run_problems
from maps.scenarios import file_sha256, load_scenario_dir
from maps.schemas import STAGE_CRITERIA, Scenario, scenario_content_sha256

ROOT = Path(__file__).resolve().parents[1]
FIXED = "2026-12-01T09:00:00+00:00"
T = "2026-12-02T10:00:00+00:00"


def ref(i, v=1):
    return {"scenario_id": i, "scenario_version": v}


def cohort(cid, family, members):
    return {"cohort_id": cid, "family": family, "fixed_on": FIXED, "members": members}


def registry(cohorts, lineage=(), exposures=()):
    return Registry.model_validate({"registry_version": 1, "cohorts": cohorts, "exposures": list(exposures), "lineage": list(lineage)})


def link(child, parent):
    return {"scenario": child, "supersedes": parent}


def raw(name):
    return json.loads((ROOT / f"data/scenarios/v2/{name}.json").read_text(encoding="utf-8"))


def reviewed(r):
    r = copy.deepcopy(r)
    r["author_id"] = "author-1"
    r["evidence"]["verification_status"] = "independently_checked"
    r["evidence"]["sha256"] = file_sha256(ROOT / r["evidence"]["reference"])
    r["review"] = {"reviewer": "rev-a", "blind_to_truth": True, "reviewed_on": "2026-12-02", "independence_confirmed": True}
    r["reviewer_assignments"], r["conflict_declarations"], r["review_submissions"] = [], [], []
    for rid in ("rev-a", "rev-b"):
        r["reviewer_assignments"].append({"reviewer_id": rid, "stages": list(STAGE_CRITERIA), "assigned_on": "2026-12-01T08:00:00+00:00"})
        r["conflict_declarations"].append({"reviewer_id": rid, "declared_on": FIXED, "authored_or_edited": False,
                                           "had_truth_label_information": False, "other_conflict": None})
        for stage, crit in STAGE_CRITERIA.items():
            r["review_submissions"].append({"reviewer_id": rid, "stage": stage, "submitted_at": T,
                                            "scores": {c: 3 for c in crit}, "form_sha256": None, "notes": ""})
    return r


def h(r):
    return scenario_content_sha256(Scenario.model_validate({**r, "status": "author_checked"}))


def bind(ra, rb):
    ha, hb = h(ra), h(rb)
    for r, own, other in ((ra, ha, hb), (rb, hb, ha)):
        for sub in r["review_submissions"]:
            sub["content_sha256"] = own
            if sub["stage"] == "pair":
                sub["partner_content_sha256"] = other


def frozen_pair(version_a=1, **a_update):
    ra, rb = reviewed(raw("biz-a")), reviewed(raw("biz-b"))
    ra.update(a_update, scenario_version=version_a)
    bind(ra, rb)
    return Scenario.model_validate({**ra, "status": "frozen"}), Scenario.model_validate({**rb, "status": "frozen"})


@pytest.fixture(scope="module")
def v1():
    return frozen_pair()


def problems_of(reg, scenarios):
    return check_registry(reg, scenarios, ROOT)


CONF_V1 = [cohort("conf-1", "confirmatory", [ref("biz-a"), ref("biz-b")])]


def test_a_version_1_scenario_needs_no_parent(v1):
    assert problems_of(registry(CONF_V1), list(v1)) == []


def test_a_valid_parent_and_child_pass(v1):
    a1, b = v1
    a2, _ = frozen_pair(2, supersedes="biz-a@1")
    reg = registry([cohort("pilot-1", "pilot", [ref("hist-a")]), cohort("conf-1", "confirmatory", [ref("biz-a", 2), ref("biz-b")])],
                   lineage=[link(ref("biz-a", 2), ref("biz-a", 1))])
    # the child is reviewed afresh (its own content hash covers version and supersedes); the parent is merely loaded
    got = problems_of(reg, [a1, a2, b])
    assert not any("biz-a@2" in p for p in got), got


def test_a_child_whose_parent_is_not_loaded_is_a_problem(v1):
    a2, b = frozen_pair(2, supersedes="biz-a@1")[0], v1[1]
    reg = registry([cohort("conf-1", "confirmatory", [ref("biz-a", 2), ref("biz-b")])], lineage=[link(ref("biz-a", 2), ref("biz-a", 1))])
    got = problems_of(reg, [a2, b])
    assert "biz-a@2 supersedes biz-a@1, which is not among the loaded scenarios" in got
    assert "biz-a@2: registry lineage names parent biz-a@1, which is not among the loaded scenarios" in got


def test_a_version_above_1_without_supersedes_is_caught_even_if_built_by_model_copy(v1):
    a1, b = v1
    a2 = a1.model_copy(update={"scenario_version": 2})  # model_copy skips validators: defence in depth
    got = problems_of(registry([cohort("pilot-1", "pilot", [ref("biz-a", 2), ref("biz-b")])]), [a2, b])
    assert "biz-a@2 has scenario_version above 1 but its file sets no supersedes" in got
    assert "biz-a@2 has scenario_version above 1 but the registry has no lineage entry" in got


def test_a_parent_with_an_invalid_version_is_reported(v1):
    a1, b = v1
    a2 = a1.model_copy(update={"scenario_version": 2, "supersedes": "biz-a@7"})
    reg = registry([cohort("pilot-1", "pilot", [ref("biz-a", 2), ref("biz-b")])], lineage=[link(ref("biz-a", 2), ref("biz-a", 7))])
    assert "biz-a@2 supersedes biz-a@7, which is not among the loaded scenarios" in problems_of(reg, [a2, b])


def test_self_reference_is_reported_for_a_scenario_file(v1):
    a1, b = v1
    selfref = a1.model_copy(update={"supersedes": "biz-a@1"})
    assert "biz-a@1 supersedes itself" in problems_of(registry([cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")])]), [selfref, b])


def test_registry_self_reference_and_cycles_are_rejected_at_construction():
    with pytest.raises(ValueError, match="cannot supersede itself"):
        registry(CONF_V1, lineage=[link(ref("biz-a", 2), ref("biz-a", 2))])
    with pytest.raises(ValueError, match="cycle"):
        registry(CONF_V1, lineage=[link(ref("biz-a", 2), ref("biz-a", 3)), link(ref("biz-a", 3), ref("biz-a", 2))])


def test_a_cycle_formed_only_through_scenario_files_is_reported(v1):
    a1, b = v1
    x = a1.model_copy(update={"scenario_version": 2, "supersedes": "biz-a@3"})
    y = a1.model_copy(update={"scenario_version": 3, "supersedes": "biz-a@2"})
    reg = registry([cohort("pilot-1", "pilot", [ref("biz-b")])],
                   lineage=[link(ref("biz-a", 2), ref("biz-a", 3))])  # registry alone is acyclic
    got = problems_of(reg, [x, y, b])
    assert any("supersession cycle" in p for p in got)


def test_parent_and_child_must_share_pair_id_and_truth_status(v1):
    a1, b = v1
    reg = registry([cohort("pilot-1", "pilot", [ref("biz-b")])], lineage=[link(ref("biz-a", 2), ref("biz-a", 1))])
    other_pair = a1.model_copy(update={"scenario_version": 2, "supersedes": "biz-a@1", "pair_id": "elsewhere"})
    assert "biz-a@2 and its parent biz-a@1 have different pair_id" in problems_of(reg, [a1, other_pair, b])
    flipped = a1.model_copy(update={"scenario_version": 2, "supersedes": "biz-a@1", "truth_status": "false"})
    assert "biz-a@2 and its parent biz-a@1 have different truth_status" in problems_of(reg, [a1, flipped, b])


# ---- re-pairing (Stage 4J.6B, owner Decision B) --------------------------------------------------------------
def test_an_existing_identity_cannot_change_its_pair_id_in_a_revision(v1):
    a1, b = v1
    reg = registry([cohort("pilot-1", "pilot", [ref("biz-b")])], lineage=[link(ref("biz-a", 2), ref("biz-a", 1))])
    moved = a1.model_copy(update={"scenario_version": 2, "supersedes": "biz-a@1", "pair_id": "other-pair"})
    assert any("have different pair_id" in p for p in problems_of(reg, [a1, moved, b]))


def test_a_new_identity_for_a_new_pairing_is_recorded_through_lineage_and_inherits_no_review(v1):
    a1, b = v1
    reg = registry([cohort("pilot-1", "pilot", [ref("biz-b")])], lineage=[link(ref("biz-a2"), ref("biz-a"))])
    fresh = a1.model_copy(update={"scenario_id": "biz-a2", "scenario_version": 1, "supersedes": "biz-a@1", "pair_id": "other-pair"})
    # the lineage mechanism accepts the new identity ...
    assert not any("different pair_id" in p for p in problems_of(reg, [a1, fresh, b]))
    # ... but none of the parent's review records bind to the new content, so it needs fresh review
    from maps.schemas import independent_review_problems
    assert any("different content" in p or "stale" in p or "content" in p for p in independent_review_problems(
        fresh.model_copy(update={"status": "frozen"}), bound=True))


def test_a_pilot_exposed_parent_blocks_a_confirmatory_child(v1):
    a1, b = v1
    a2, _ = frozen_pair(2, supersedes="biz-a@1")
    reg = registry([cohort("conf-1", "confirmatory", [ref("biz-a", 2), ref("biz-b")])],
                   lineage=[link(ref("biz-a", 2), ref("biz-a", 1))],
                   exposures=[])
    # exposure recorded for the parent only in a pilot run: constructing the registry with it must already refuse
    with pytest.raises(ValueError, match="descends from pilot-exposed"):
        registry(reg.model_dump()["cohorts"], lineage=[link(ref("biz-a", 2), ref("biz-a", 1))],
                 exposures=[{"scenario": ref("biz-a", 1), "run_id": "run-1", "recorded_on": "2026-12-05T09:00:00+00:00", "note": ""}])
    # exposure without a registry lineage entry: the scenario file's supersedes still exposes the descent at the gate
    exposed = registry([cohort("conf-1", "confirmatory", [ref("biz-a", 2), ref("biz-b")])],
                       exposures=[{"scenario": ref("biz-a", 1), "run_id": "run-1", "recorded_on": "2026-12-05T09:00:00+00:00", "note": ""}])
    got = confirmatory_run_problems(exposed, [a1, a2, b], ROOT)
    assert any("descends from pilot-exposed scenario biz-a@1" in p for p in got)


def test_a_revised_scenario_needs_fresh_reviews_and_never_inherits_validity(v1):
    a1, _ = v1
    stale = a1.model_dump()
    stale.update(scenario_version=2, supersedes="biz-a@1")
    with pytest.raises(ValueError, match="qualifying independent reviewer"):  # copied submissions bind to the parent's hash
        Scenario.model_validate({**stale, "status": "frozen"})
    a2, b = frozen_pair(2, supersedes="biz-a@1")  # freshly bound to its own hash
    assert scenario_content_sha256(a2) != scenario_content_sha256(a1)


def test_the_existing_ten_still_have_no_lineage_problems():
    ten = load_scenario_dir(ROOT / "data/scenarios/v2")
    got = problems_of(registry([cohort("pilot-1", "pilot", [ref(s.scenario_id) for s in ten])]), ten)
    assert got == []
