"""Cohort and pilot-exposure registry (Stage 4J.2). Offline; no provider calls; no scenario files are modified."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from maps.registry import (
    Registry,
    ancestors,
    check_registry,
    confirmatory_violations,
    load_registry,
    pilot_cohort_keys,
    pilot_exposed_keys,
)
from maps.scenarios import load_scenario_dir
from maps.schemas import Scenario

ROOT = Path(__file__).resolve().parents[1]
FIXED = "2026-12-01T09:00:00+00:00"
RUN = "2026-12-05T09:00:00+00:00"


def ref(sid, version=1):
    return {"scenario_id": sid, "scenario_version": version}


def cohort(cid, family, members, fixed=FIXED):
    return {"cohort_id": cid, "family": family, "members": members, "fixed_on": fixed}


def registry(**fields):
    base = {"registry_version": 1, "cohorts": [], "exposures": [], "lineage": []}
    base.update(fields)
    return base


def invalid(raw, match=None):
    with pytest.raises(ValidationError, match=match):
        Registry.model_validate(raw)


# ---- representation ---------------------------------------------------------------------------------------
def test_a_pilot_cohort_can_be_represented():
    r = Registry.model_validate(registry(cohorts=[cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")])]))
    assert r.cohorts[0].family == "pilot" and pilot_cohort_keys(r) == {"biz-a@1", "biz-b@1"}


def test_an_eligible_confirmatory_cohort_can_be_represented():
    r = Registry.model_validate(registry(cohorts=[
        cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")]),
        cohort("conf-1", "confirmatory", [ref("new-a"), ref("new-b")]),
    ]))
    assert confirmatory_violations(r) == []


def test_an_empty_registry_is_valid():
    assert Registry.model_validate(registry()).cohorts == []


# ---- confirmatory eligibility -----------------------------------------------------------------------------
def test_pilot_cohort_membership_is_rejected_in_a_confirmatory_cohort():
    invalid(registry(cohorts=[cohort("pilot-1", "pilot", [ref("biz-a")]),
                              cohort("conf-1", "confirmatory", [ref("biz-a")])]),
            "both a pilot and a confirmatory cohort")


def test_a_pilot_exposure_event_disqualifies_confirmatory_membership():
    invalid(registry(cohorts=[cohort("conf-1", "confirmatory", [ref("new-a")])],
                     exposures=[{"scenario": ref("new-a"), "run_id": "run-1", "recorded_on": RUN, "note": ""}]),
            "is pilot-exposed")


def test_a_superseding_descendant_of_a_pilot_exposed_scenario_is_rejected():
    invalid(registry(
        cohorts=[cohort("conf-1", "confirmatory", [ref("hist-a", 2)])],
        exposures=[{"scenario": ref("hist-a", 1), "run_id": "run-1", "recorded_on": RUN, "note": ""}],
        lineage=[{"scenario": ref("hist-a", 2), "supersedes": ref("hist-a", 1)}]),
        "descends from pilot-exposed scenario hist-a@1")


def test_a_superseding_descendant_of_a_pilot_cohort_scenario_is_rejected():
    invalid(registry(
        cohorts=[cohort("pilot-1", "pilot", [ref("hist-a", 1)]), cohort("conf-1", "confirmatory", [ref("hist-a", 3)])],
        lineage=[{"scenario": ref("hist-a", 2), "supersedes": ref("hist-a", 1)},
                 {"scenario": ref("hist-a", 3), "supersedes": ref("hist-a", 2)}]),
        "descends from pilot-cohort scenario hist-a@1")


def test_a_new_version_cannot_erase_exposure_history():
    raw = registry(
        cohorts=[cohort("conf-1", "confirmatory", [ref("hist-a", 4)])],
        exposures=[{"scenario": ref("hist-a", 1), "run_id": "run-1", "recorded_on": RUN, "note": ""}],
        lineage=[{"scenario": ref("hist-a", 2), "supersedes": ref("hist-a", 1)},
                 {"scenario": ref("hist-a", 3), "supersedes": ref("hist-a", 2)},
                 {"scenario": ref("hist-a", 4), "supersedes": ref("hist-a", 3)}])
    invalid(raw, "descends from pilot-exposed scenario hist-a@1")
    # the same history is visible through the lineage
    raw["cohorts"] = []
    r = Registry.model_validate(raw)
    assert ancestors("hist-a@4", {s.scenario.key: s.supersedes.key for s in r.lineage}) == ["hist-a@3", "hist-a@2", "hist-a@1"]
    assert pilot_exposed_keys(r) == {"hist-a@1"}


def test_moving_a_scenario_between_cohorts_cannot_hide_its_pilot_membership():
    raw = registry(cohorts=[cohort("pilot-1", "pilot", [ref("biz-a")])])
    assert Registry.model_validate(raw)
    raw["cohorts"].append(cohort("conf-1", "confirmatory", [ref("biz-a")]))
    invalid(raw)


def test_an_unrelated_new_scenario_can_join_a_confirmatory_cohort_next_to_exposed_ones():
    r = Registry.model_validate(registry(
        cohorts=[cohort("pilot-1", "pilot", [ref("biz-a")]), cohort("conf-1", "confirmatory", [ref("other-a")])],
        exposures=[{"scenario": ref("biz-a"), "run_id": "run-1", "recorded_on": RUN, "note": ""}]))
    assert confirmatory_violations(r) == []


# ---- traceability and malformed input -----------------------------------------------------------------------
def test_cohort_and_exposure_history_stays_traceable():
    r = Registry.model_validate(registry(
        cohorts=[cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")])],
        exposures=[{"scenario": ref("biz-a"), "run_id": "run-1", "recorded_on": RUN, "note": "first pilot run"}]))
    assert r.exposures[0].run_id == "run-1" and r.exposures[0].note == "first pilot run"
    assert r.cohorts[0].fixed_on == FIXED


def test_exposure_before_the_pilot_cohort_was_fixed_is_rejected():
    invalid(registry(cohorts=[cohort("pilot-1", "pilot", [ref("biz-a")], fixed=RUN)],
                     exposures=[{"scenario": ref("biz-a"), "run_id": "run-1", "recorded_on": FIXED, "note": ""}]),
            "before its pilot cohort was fixed")


def test_duplicate_cohort_ids_and_members_are_rejected():
    invalid(registry(cohorts=[cohort("c-1", "pilot", [ref("a")]), cohort("c-1", "pilot", [ref("b")])]), "duplicate cohort_id")
    invalid(registry(cohorts=[cohort("c-1", "pilot", [ref("a"), ref("a")])]), "more than once")


def test_duplicate_exposure_events_are_rejected():
    event = {"scenario": ref("a"), "run_id": "run-1", "recorded_on": RUN, "note": ""}
    invalid(registry(cohorts=[], exposures=[event, dict(event)]), "duplicate pilot-exposure event")


def test_invalid_identifiers_families_and_relationships_are_rejected():
    invalid(registry(cohorts=[cohort("bad id", "pilot", [ref("a")])]), "identifier")
    invalid(registry(cohorts=[cohort("c-1", "exploratory", [ref("a")])]))
    invalid(registry(cohorts=[cohort("c-1", "pilot", [])]))
    invalid(registry(cohorts=[cohort("c-1", "pilot", [ref("a")], fixed="2026-12-01")]), "UTC offset|datetime|offset")
    invalid(registry(cohorts=[cohort("c-1", "pilot", [{"scenario_id": "a", "scenario_version": 0}])]))
    invalid(registry(lineage=[{"scenario": ref("a", 2), "supersedes": ref("a", 2)}]), "cannot supersede itself")
    invalid(registry(lineage=[{"scenario": ref("a", 2), "supersedes": ref("a", 1)},
                              {"scenario": ref("a", 2), "supersedes": ref("a", 3)}]), "only one earlier version")
    invalid(registry(lineage=[{"scenario": ref("a", 2), "supersedes": ref("a", 1)},
                              {"scenario": ref("a", 1), "supersedes": ref("a", 2)}]), "cycle")
    invalid({**registry(), "unexpected": 1})
    invalid({**registry(), "registry_version": 2})


def test_load_registry_reads_a_json_file(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry(cohorts=[cohort("pilot-1", "pilot", [ref("biz-a")])])), encoding="utf-8")
    assert load_registry(path).cohorts[0].cohort_id == "pilot-1"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_registry(path)


# ---- cross-checks against scenario files -------------------------------------------------------------------
def test_check_registry_requires_whole_true_false_pairs_and_existing_scenarios():
    scenarios = load_scenario_dir(ROOT / "data/scenarios/v2")
    whole = Registry.model_validate(registry(cohorts=[cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")])]))
    assert check_registry(whole, scenarios) == []
    half = Registry.model_validate(registry(cohorts=[cohort("pilot-1", "pilot", [ref("biz-a")])]))
    assert any("not a complete true/false pair" in p for p in check_registry(half, scenarios))
    missing = Registry.model_validate(registry(cohorts=[cohort("pilot-1", "pilot", [ref("nope-a")])]))
    assert any("not among the loaded scenarios" in p for p in check_registry(missing, scenarios))


def test_a_registry_entry_is_not_proof_of_independent_review():
    scenarios = load_scenario_dir(ROOT / "data/scenarios/v2")
    r = Registry.model_validate(registry(cohorts=[cohort("conf-1", "confirmatory", [ref("biz-a"), ref("biz-b")])]))
    problems = check_registry(r, scenarios)
    assert any("not 'frozen'" in p for p in problems)
    assert any("qualifying independent reviewer" in p for p in problems)


def test_check_registry_merges_the_supersedes_field_of_scenario_files():
    base = json.loads((ROOT / "data/scenarios/v2/biz-a.json").read_text(encoding="utf-8"))
    v2 = dict(base, scenario_version=2, supersedes="biz-a@1")
    scenarios = [Scenario.model_validate(base), Scenario.model_validate(v2)]
    r = Registry.model_validate(registry(
        cohorts=[cohort("pilot-1", "pilot", [ref("biz-a", 1)]), cohort("conf-1", "confirmatory", [ref("biz-a", 2)])]))
    # the registry alone sees no link, but the scenario file records the supersession
    assert confirmatory_violations(r) == []
    assert any("descends from pilot-cohort scenario biz-a@1" in p for p in check_registry(r, scenarios))
    disagree = Registry.model_validate(registry(lineage=[{"scenario": ref("biz-a", 2), "supersedes": ref("biz-a", 1)}]))
    assert check_registry(disagree, scenarios) == []
    # Stage 4J.5 (decision 7): without a lineage entry the superseding file is a problem (this call used to be clean)
    none = Registry.model_validate(registry())
    assert "biz-a@2 supersedes biz-a@1 but the registry has no lineage entry" in check_registry(none, scenarios)
    wrong = Registry.model_validate(registry(lineage=[{"scenario": ref("biz-a", 2), "supersedes": ref("zzz", 1)}]))
    assert any("scenario file says it supersedes biz-a@1" in p for p in check_registry(wrong, scenarios))
