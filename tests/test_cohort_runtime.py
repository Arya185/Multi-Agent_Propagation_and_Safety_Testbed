"""Run-boundary checks of the cohort registry (Stage 4J.3). Offline; real scenario and evidence files are only read.

These test the functions a runner calls at its boundary (``confirmatory_run_problems``, ``pilot_run_problems`` and
the ``require_*`` wrappers). They use real objects, not mocks. The ``--registry`` command-line option of
``receiver.py`` is NOT wired in this change, so there is no CLI test here.
"""

import copy
import json
from pathlib import Path

import pytest

from maps.registry import (
    CohortGateError,
    Registry,
    confirmatory_run_problems,
    pilot_run_problems,
    require_confirmatory_run,
    require_pilot_registry,
)
from maps.scenarios import file_sha256, load_scenario_dir
from maps.schemas import STAGE_CRITERIA, Adjudication, Scenario, scenario_content_sha256

ROOT = Path(__file__).resolve().parents[1]
FIXED = "2026-12-01T09:00:00+00:00"
T_DECLARE = "2026-12-01T09:00:00+00:00"
T_SUBMIT = "2026-12-02T10:00:00+00:00"


def ref(sid, version=1):
    return {"scenario_id": sid, "scenario_version": version}


def cohort(cid, family, members):
    return {"cohort_id": cid, "family": family, "members": members, "fixed_on": FIXED}


def registry(cohorts, **fields):
    return Registry.model_validate({"registry_version": 1, "cohorts": cohorts, "exposures": [], "lineage": [], **fields})


def _raw(name):
    return json.loads((ROOT / f"data/scenarios/v2/{name}.json").read_text(encoding="utf-8"))


def _reviewed(raw, status="frozen"):
    """The same scenario record carrying two complete, clean, perfect independent reviews."""
    raw = copy.deepcopy(raw)
    raw["author_id"] = "author-1"
    raw["status"] = status
    raw["evidence"]["verification_status"] = "independently_checked"
    raw["evidence"]["sha256"] = "a" * 64
    raw["review"] = {"reviewer": "rev-a", "blind_to_truth": True, "reviewed_on": "2026-12-02", "independence_confirmed": True}
    raw["reviewer_assignments"], raw["conflict_declarations"], raw["review_submissions"] = [], [], []
    for rid in ("rev-a", "rev-b"):
        raw["reviewer_assignments"].append({"reviewer_id": rid, "stages": list(STAGE_CRITERIA), "assigned_on": "2026-12-01T08:00:00+00:00"})
        raw["conflict_declarations"].append({"reviewer_id": rid, "declared_on": T_DECLARE, "authored_or_edited": False,
                                             "had_truth_label_information": False, "other_conflict": None})
        for stage, criteria in STAGE_CRITERIA.items():
            raw["review_submissions"].append({"reviewer_id": rid, "stage": stage, "submitted_at": T_SUBMIT,
                                              "scores": {c: 3 for c in criteria}, "form_sha256": None, "notes": ""})
    return raw


def _hash(raw):
    return scenario_content_sha256(Scenario.model_validate({**raw, "status": "author_checked"}))


def _bound_pair(status="frozen", mod_a=None):
    """Stage 4J.5: reviews must be bound to the content they saw (and pair-stage ones to the partner's content), so
    the raw records are completed first, hashed, and only then given their final status. Returns two raw dicts."""
    ra, rb = _reviewed(_raw("biz-a"), status), _reviewed(_raw("biz-b"), status)
    for raw in (ra, rb):  # the real evidence hash (the content hash covers evidence.sha256; the CLI loader verifies it)
        raw["evidence"]["sha256"] = file_sha256(ROOT / raw["evidence"]["reference"])
    if mod_a:
        mod_a(ra)
    ha, hb = _hash(ra), _hash(rb)
    for raw, own, other in ((ra, ha, hb), (rb, hb, ha)):
        for sub in raw["review_submissions"]:
            sub["content_sha256"] = own
            if sub["stage"] == "pair":
                sub["partner_content_sha256"] = other
    return ra, rb


@pytest.fixture(scope="module")
def ten():
    return load_scenario_dir(ROOT / "data/scenarios/v2")


def _author_checked_raw(name):
    """Stage 4J.7: the pilot gate needs author_checked (or pilot_frozen) + author_id + a real evidence hash."""
    raw = _raw(name)
    raw["status"], raw["author_id"] = "author_checked", "author-1"
    raw["evidence"]["verification_status"] = "author_checked"
    raw["evidence"]["sha256"] = file_sha256(ROOT / raw["evidence"]["reference"])
    return raw


TEN_IDS = [f"{p}-{m}" for p in ("biz", "geo", "hist", "sci", "sw") for m in "ab"]


@pytest.fixture(scope="module")
def eligible_ten():
    """The real ten, as in-memory author_checked copies (data/ is never edited)."""
    return [Scenario.model_validate(_author_checked_raw(i)) for i in TEN_IDS]


@pytest.fixture
def biz_pair():
    return [Scenario.model_validate(r) for r in _bound_pair()]


CONF = [cohort("conf-1", "confirmatory", [ref("biz-a"), ref("biz-b")])]


# ---- a confirmatory run ------------------------------------------------------------------------------------------
def test_an_eligible_confirmatory_set_has_no_problems(biz_pair):
    assert confirmatory_run_problems(registry(CONF), biz_pair, ROOT) == []
    require_confirmatory_run(registry(CONF), biz_pair, ROOT)  # does not raise


def test_a_scenario_without_a_cohort_assignment_is_refused_and_never_assigned(ten, biz_pair):
    reg = registry(CONF)
    before = reg.model_dump()
    problems = confirmatory_run_problems(reg, biz_pair + [s for s in ten if s.scenario_id == "geo-a"], ROOT)
    assert any("is not assigned to any confirmatory cohort" in p for p in problems)
    assert reg.model_dump() == before  # nothing was assigned or written


def test_a_registry_without_a_confirmatory_cohort_is_refused(biz_pair):
    reg = registry([cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")])])
    problems = confirmatory_run_problems(reg, biz_pair, ROOT)
    assert any("no confirmatory cohort" in p for p in problems)
    assert any("not assigned to any confirmatory cohort" in p for p in problems)


def test_half_a_pair_is_refused(biz_pair):
    reg = registry([cohort("conf-1", "confirmatory", [ref("biz-a")])])
    problems = confirmatory_run_problems(reg, biz_pair[:1], ROOT)
    assert any("not a complete true/false pair" in p for p in problems)


def test_members_without_independent_review_evidence_are_refused(ten):
    biz = [s for s in ten if s.pair_id == "biz"]
    problems = confirmatory_run_problems(registry(CONF), biz, ROOT)
    assert any("not 'frozen'" in p for p in problems)
    assert any("qualifying independent reviewer" in p for p in problems)  # a registry entry is not proof of review


def test_a_pilot_frozen_scenario_is_not_confirmatory(biz_pair):
    raw, _ = _bound_pair(status="pilot_frozen", mod_a=lambda r: r["review"].update(independence_confirmed=False))
    scenarios = [Scenario.model_validate(raw), biz_pair[1]]
    assert any("'pilot_frozen', not 'frozen'" in p for p in confirmatory_run_problems(registry(CONF), scenarios, ROOT))


def test_a_scenario_file_that_supersedes_a_pilot_cohort_scenario_is_refused(biz_pair):
    raw, _ = _bound_pair(mod_a=lambda r: r.update(scenario_version=2, supersedes="biz-a@1"))
    scenarios = [Scenario.model_validate(raw), biz_pair[1]]
    reg = registry([cohort("pilot-1", "pilot", [ref("biz-a", 1)]), cohort("conf-1", "confirmatory", [ref("biz-a", 2), ref("biz-b")])])
    problems = confirmatory_run_problems(reg, scenarios, ROOT)
    assert any("descends from pilot-cohort scenario biz-a@1" in p for p in problems)
    # Stage 4J.5 (decision 7): a superseding file without a registry lineage entry is itself a problem
    assert any("biz-a@2 supersedes biz-a@1 but the registry has no lineage entry" in p for p in problems)


def test_pilot_exposure_of_an_ancestor_recorded_only_in_the_registry_is_refused_at_construction():
    with pytest.raises(ValueError, match="descends from pilot-exposed"):
        registry([cohort("conf-1", "confirmatory", [ref("biz-a", 2)])],
                 exposures=[{"scenario": ref("biz-a", 1), "run_id": "run-1", "recorded_on": "2026-12-05T09:00:00+00:00", "note": ""}],
                 lineage=[{"scenario": ref("biz-a", 2), "supersedes": ref("biz-a", 1)}])


def test_mechanical_failures_block_a_confirmatory_run(ten):
    # Stage 4J.6B: the real hist pair was revised (1612 vs 1583) and no longer fails the 50-year bound, so the
    # failure is seeded: the old 1741 value is put back on a copy (the gap is 158 years against the bound of 50).
    hist = [s for s in ten if s.pair_id == "hist"]
    seeded = [s.model_copy(update={"claim": s.claim.model_copy(update={"asserted_value": "1741"})}) if s.scenario_id == "hist-a" else s
              for s in hist]
    reg = registry([cohort("conf-1", "confirmatory", [ref("hist-a"), ref("hist-b")])])
    problems = confirmatory_run_problems(reg, seeded, ROOT)
    assert any("50" in p and "year" in p.lower() for p in problems)


def test_the_gate_raises_with_every_problem_and_does_not_mutate_its_inputs(ten):
    reg = registry([])
    before = [s.model_dump() for s in ten]
    with pytest.raises(CohortGateError) as caught:
        require_confirmatory_run(reg, ten, ROOT)
    assert len(caught.value.problems) >= 10
    assert [s.model_dump() for s in ten] == before


def test_the_gate_is_deterministic(biz_pair, ten):
    others = [s for s in ten if s.pair_id == "geo"]
    a = confirmatory_run_problems(registry(CONF), biz_pair + others, ROOT)
    b = confirmatory_run_problems(registry(CONF), list(reversed(biz_pair + others)), ROOT)
    assert a == b and a


def test_a_pair_with_an_adjudication_record_or_stale_binding_is_refused(biz_pair):
    # Stage 4J.5: the pair-level gate is part of the confirmatory run check
    a, b = biz_pair
    stale = b.model_copy(update={"domain": "edited after review"})
    problems = confirmatory_run_problems(registry(CONF), [a, stale], ROOT)
    assert any("bound to different partner content (stale)" in p for p in problems)
    adjudicated = a.model_copy(update={"adjudication": Adjudication(reason="gap")})
    assert any("adjudication unresolved on biz-a@1" in p for p in confirmatory_run_problems(registry(CONF), [adjudicated, b], ROOT))


def test_the_existing_ten_cannot_pass_a_confirmatory_gate(ten):
    reg = registry([cohort("conf-1", "confirmatory", [ref(s.scenario_id) for s in ten])])
    problems = confirmatory_run_problems(reg, ten, ROOT)
    assert any("not 'frozen'" in p for p in problems)


# ---- a pilot run given a registry --------------------------------------------------------------------------
def test_a_pilot_registry_must_assign_every_loaded_scenario_to_a_pilot_cohort(eligible_ten):
    ten = eligible_ten  # 4J.7: drafts no longer pass the pilot gate, so the fixture is author_checked
    full = registry([cohort("pilot-1", "pilot", [ref(s.scenario_id) for s in ten])])
    assert pilot_run_problems(full, ten) == []
    require_pilot_registry(full, ten)
    partial = registry([cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")])])
    problems = pilot_run_problems(partial, ten)
    assert any("is not assigned to any pilot cohort" in p for p in problems)
    with pytest.raises(CohortGateError):
        require_pilot_registry(partial, ten)


def test_draft_scenarios_in_a_pilot_cohort_are_refused(ten):
    full = registry([cohort("pilot-1", "pilot", [ref(s.scenario_id) for s in ten])])
    assert any("found 'draft'" in p for p in pilot_run_problems(full, ten))


def test_a_pilot_registry_cannot_hide_a_half_pair(ten):
    half = registry([cohort("pilot-1", "pilot", [ref("biz-a")])])
    assert any("not a complete true/false pair" in p for p in pilot_run_problems(half, [s for s in ten if s.scenario_id == "biz-a"]))


def test_pilot_exposure_is_never_recorded_by_these_checks(eligible_ten):
    ten = eligible_ten
    reg = registry([cohort("pilot-1", "pilot", [ref(s.scenario_id) for s in ten])])
    before = reg.model_dump()
    pilot_run_problems(reg, ten)
    require_pilot_registry(reg, ten)
    assert reg.model_dump() == before and reg.exposures == []


# ---- the command-line gate (real receiver.main, real files in a temporary directory) -------------------------
from maps.experiments import receiver  # noqa: E402  (kept next to its tests)


def _write_stage(tmp_path, stage, scenario_dir=None, pair=True):
    """A configuration for `stage`, with a scenario directory holding the frozen biz pair when pair is True."""
    cfg = json.loads((ROOT / "configs/receiver_experiment.json").read_text(encoding="utf-8"))
    cfg["output"]["stage"] = stage
    cfg["output"]["results_dir"] = str(tmp_path / "results")
    if scenario_dir is None:
        scenario_dir = tmp_path / "scenarios"
        scenario_dir.mkdir()
        if pair:
            for name, raw in zip(("biz-a", "biz-b"), _bound_pair()):
                (scenario_dir / f"{name}.json").write_text(json.dumps(raw), encoding="utf-8")
    cfg["design"]["scenario_dir"] = str(scenario_dir)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


def _write_registry(tmp_path, cohorts, name="registry.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"registry_version": 1, "cohorts": cohorts, "exposures": [], "lineage": []}), encoding="utf-8")
    return str(path)


def test_a_main_stage_run_without_a_registry_is_refused_before_any_run_directory(tmp_path, capsys):
    config = _write_stage(tmp_path, "main")
    assert receiver.main(["--config", config, "--mock"]) == 2
    err = capsys.readouterr().err
    assert "main stage requires --registry" in err
    assert not (tmp_path / "results").exists()


def test_a_main_stage_plan_with_an_eligible_registry_is_allowed_and_assigns_nothing(tmp_path, capsys):
    config = _write_stage(tmp_path, "main")
    registry_path = _write_registry(tmp_path, CONF)
    before = Path(registry_path).read_bytes()
    assert receiver.main(["--config", config, "--registry", registry_path]) == 0
    assert "PLAN ONLY" in capsys.readouterr().out
    assert Path(registry_path).read_bytes() == before  # nothing was written to the registry
    assert not (tmp_path / "results").exists()


def test_an_ineligible_registry_refuses_a_main_stage_run_without_printing_scenario_values(tmp_path, capsys):
    config = _write_stage(tmp_path, "main")
    registry_path = _write_registry(tmp_path, [cohort("conf-1", "confirmatory", [ref("biz-a")])])  # half a pair
    assert receiver.main(["--config", config, "--registry", registry_path, "--mock"]) == 2
    err = capsys.readouterr().err
    assert "refused by the cohort registry check" in err and "problem(s)" in err
    assert "342" not in err and "264" not in err  # asserted values stay out of the message
    assert not (tmp_path / "results").exists()


def test_a_registry_that_leaves_a_scenario_unassigned_is_refused(tmp_path, capsys):
    config = _write_stage(tmp_path, "main")
    registry_path = _write_registry(tmp_path, [cohort("conf-1", "confirmatory", [ref("other-a"), ref("other-b")])])
    assert receiver.main(["--config", config, "--registry", registry_path]) == 2
    assert "refused by the cohort registry check" in capsys.readouterr().err


def test_a_pilot_cohort_registry_does_not_open_the_main_stage(tmp_path, capsys):
    config = _write_stage(tmp_path, "main")
    registry_path = _write_registry(tmp_path, [cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")])])
    assert receiver.main(["--config", config, "--registry", registry_path]) == 2
    assert "refused by the cohort registry check" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["{not json", '{"registry_version": 1}', '{"registry_version": 1, "cohorts": [], "extra": 1}'])
def test_an_unreadable_or_invalid_registry_file_is_refused(tmp_path, capsys, content):
    config = _write_stage(tmp_path, "main")
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    assert receiver.main(["--config", config, "--registry", str(bad)]) == 2
    err = capsys.readouterr().err
    assert "could not be loaded or failed validation" in err and "details withheld" in err
    assert receiver.main(["--config", config, "--registry", str(tmp_path / "missing.json")]) == 2


def test_the_existing_frozen_refusal_still_comes_first_for_unfrozen_scenarios(tmp_path, capsys):
    # the real ten scenarios are drafts: the main stage refuses them for being unfrozen before the registry is consulted
    config = _write_stage(tmp_path, "main", scenario_dir=ROOT / "data/scenarios/v2")
    assert receiver.main(["--config", config]) == 2
    err = capsys.readouterr().err
    assert "frozen" in err and "refused by a design check" in err


def test_pilot_and_mock_behavior_is_unchanged_without_a_registry(tmp_path, capsys):
    config = _write_stage(tmp_path, "pilot", scenario_dir=ROOT / "data/scenarios/v2")
    assert receiver.main(["--config", config]) == 0
    assert "PLAN ONLY" in capsys.readouterr().out


def test_a_registry_given_to_a_pilot_run_is_only_validated(tmp_path, capsys):
    scen = tmp_path / "ten"
    scen.mkdir()
    for i in TEN_IDS:  # author_checked copies in a temporary directory (4J.7); data/ is not edited
        (scen / f"{i}.json").write_text(json.dumps(_author_checked_raw(i)), encoding="utf-8")
    config = _write_stage(tmp_path, "pilot", scenario_dir=scen)
    ten_ids = TEN_IDS
    full = _write_registry(tmp_path, [cohort("pilot-1", "pilot", [ref(i) for i in ten_ids])])
    assert receiver.main(["--config", config, "--registry", full]) == 0
    partial = _write_registry(tmp_path, [cohort("pilot-1", "pilot", [ref("biz-a"), ref("biz-b")])], name="partial.json")
    assert receiver.main(["--config", config, "--registry", partial]) == 2
    assert "refused by the cohort registry check" in capsys.readouterr().err


def test_a_draft_ten_with_a_pilot_registry_is_refused_at_the_command_line(tmp_path, capsys):
    config = _write_stage(tmp_path, "pilot", scenario_dir=ROOT / "data/scenarios/v2")
    full = _write_registry(tmp_path, [cohort("pilot-1", "pilot", [ref(i) for i in TEN_IDS])])
    assert receiver.main(["--config", config, "--registry", full]) == 2
    assert "refused by the cohort registry check" in capsys.readouterr().err
