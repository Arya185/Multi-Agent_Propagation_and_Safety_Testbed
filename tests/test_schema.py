import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from maps.config import config_hash, load_config
from maps.schemas import (
    EpisodeResult,
    EpisodeSpec,
    PlanItem,
    ResponseParseError,
    Scenario,
    parse_receiver_response,
)

ROOT = Path(__file__).resolve().parents[1]

VALID = {
    "accepts_claim": True,
    "confidence": 80,
    "estimated_independent_roots": 1,
    "evidence_used": ["message 1"],
    "reasoning": "One message supports it.",
}


def _dump(**overrides):
    return json.dumps({**VALID, **overrides})


def test_valid_response_parses():
    r = parse_receiver_response(_dump())
    assert r.accepts_claim is True and r.confidence == 80 and r.estimated_independent_roots == 1


def test_old_field_name_is_rejected():
    data = dict(VALID)
    data["estimated_independent_sources"] = data.pop("estimated_independent_roots")
    with pytest.raises(ResponseParseError):
        parse_receiver_response(json.dumps(data))


def test_empty_evidence_list_is_valid():
    assert parse_receiver_response(_dump(evidence_used=[])).evidence_used == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"confidence": 101}, {"confidence": -1}, {"confidence": "80"}, {"confidence": 80.5},
        {"confidence": True}, {"accepts_claim": "true"}, {"accepts_claim": 1},
        {"estimated_independent_roots": -1}, {"estimated_independent_roots": 1.0},
        {"evidence_used": "message 1"}, {"evidence_used": [1]}, {"reasoning": ""},
        {"extra_key": 1},
    ],
)
def test_bad_fields_rejected(overrides):
    with pytest.raises(ResponseParseError):
        parse_receiver_response(_dump(**overrides))


def test_missing_field_rejected():
    data = dict(VALID)
    del data["reasoning"]
    with pytest.raises(ResponseParseError):
        parse_receiver_response(json.dumps(data))


@pytest.mark.parametrize(
    "text",
    [
        "", "not json",
        "```json\n" + json.dumps(VALID) + "\n```",
        "Here you go: " + json.dumps(VALID),
        json.dumps([VALID]),
        json.dumps(VALID).replace("80", "NaN"),
        json.dumps(VALID)[:-1],
    ],
)
def test_malformed_json_rejected_not_repaired(text):
    with pytest.raises(ResponseParseError):
        parse_receiver_response(text)


# ---- episode spec ---------------------------------------------------------
def _plan(n, roots):
    return [
        PlanItem(position=k, relay_id=f"Relay-{k + 1}", template_idx=k, root_id=roots[k % len(roots)])
        for k in range(n)
    ]


def _spec(n, root_ids, **kw):
    base = dict(
        episode_id="ep_x", model_alias="m", model_id="a/b", scenario_id="s", pair_id="p",
        truth_status="true", condition_id="C", n_messages=n, n_roots=len(set(root_ids)) if n else 0,
        prompt_variant="neutral", repetition=0, seed=1, message_plan=_plan(n, root_ids) if n else [],
    )
    return {**base, **kw}


def test_spec_accepts_valid_shapes():
    EpisodeSpec(**_spec(0, []))
    EpisodeSpec(**_spec(2, ["a"]))
    EpisodeSpec(**_spec(2, ["a", "b"]))
    EpisodeSpec(**_spec(4, ["a", "b", "c", "d"]))


def test_spec_rejects_inconsistent_plans():
    with pytest.raises(ValidationError):
        EpisodeSpec(**_spec(2, ["a", "b"], n_roots=1))  # claims 1 root, plan has 2
    with pytest.raises(ValidationError):
        EpisodeSpec(**_spec(2, ["a"], n_messages=3))
    with pytest.raises(ValidationError):
        EpisodeSpec(**_spec(2, ["a"], message_plan=[
            PlanItem(position=0, relay_id="R", template_idx=0, root_id="a"),
            PlanItem(position=1, relay_id="R", template_idx=1, root_id="a")]))  # duplicate relay
    with pytest.raises(ValidationError):
        EpisodeSpec(**_spec(2, ["a"], message_plan=[
            PlanItem(position=0, relay_id="R1", template_idx=0, root_id="a"),
            PlanItem(position=1, relay_id="R2", template_idx=0, root_id="a")]))  # duplicate template


def test_episode_result_consistency():
    spec = EpisodeSpec(**_spec(2, ["a"]))
    with pytest.raises(ValidationError):
        EpisodeResult(spec=spec, status="ok")
    with pytest.raises(ValidationError):
        EpisodeResult(spec=spec, status="parse_error")
    EpisodeResult(spec=spec, status="parse_error", error="bad")


# ---- scenario schema rules (independence, feasibility, balance, gates) ------------
def _raw(pair="biz", truth="true"):
    for path in sorted((ROOT / "data/scenarios/v2").glob(f"{pair}-*.json")):
        raw = json.loads(path.read_text())
        if raw["truth_status"] == truth:
            return raw
    raise AssertionError((pair, truth))


def _expect_invalid(mutate, match=None, pair="biz", truth="true"):
    raw = _raw(pair, truth)
    mutate(raw)
    with pytest.raises(ValidationError, match=match):
        Scenario.model_validate(raw)


def test_scenario_files_roundtrip():
    for pair in ("biz", "sci", "sw", "geo", "hist"):
        for truth in ("true", "false"):
            Scenario.model_validate(_raw(pair, truth))


def test_roots_with_overlapping_upstream_are_rejected():
    def m(raw):
        raw["communication_roots"][1]["upstream_ids"] = list(raw["communication_roots"][0]["upstream_ids"])
    _expect_invalid(m, "share upstream provenance")


def test_partial_upstream_overlap_is_rejected():
    def m(raw):
        raw["communication_roots"][2]["upstream_ids"].append(raw["communication_roots"][3]["upstream_ids"][0])
    _expect_invalid(m, "share upstream provenance")


def test_root_cannot_be_upstream_of_another_root():
    def m(raw):
        raw["communication_roots"][1]["upstream_ids"].append(raw["communication_roots"][0]["root_id"])
    _expect_invalid(m, "another root as upstream")


def test_different_names_and_ids_do_not_imply_independence():
    # Distinct stated origins and distinct upstream ids are not enough on their own:
    # the same operator, the same instrument, derived records, or reading another
    # root's output each invalidate independence regardless of ids.
    def same_operator(raw):
        raw["communication_roots"][1]["operator_id"] = raw["communication_roots"][0]["operator_id"]
    _expect_invalid(same_operator, "duplicate operator_id")

    def same_instrument(raw):
        raw["communication_roots"][1]["instrument_id"] = raw["communication_roots"][0]["instrument_id"]
    _expect_invalid(same_instrument, "duplicate instrument_id")

    def reads_other(raw):
        raw["communication_roots"][1]["reads_other_roots_output"] = True
    _expect_invalid(reads_other, "must not read another root")

    def derived(raw):
        raw["communication_roots"][1]["acquisition_kind"] = "derived_record"
    _expect_invalid(derived)

    def shared_artifact(raw):
        raw["communication_roots"][0]["upstream_ids"] = ["shared-artifact"]
        raw["communication_roots"][1]["upstream_ids"] = ["shared-artifact"]
        assert raw["communication_roots"][0]["stated_origin"] != raw["communication_roots"][1]["stated_origin"]
    _expect_invalid(shared_artifact, "share upstream provenance")


def test_duplicate_acquisition_process_or_origin_rejected():
    def p(raw):
        raw["communication_roots"][1]["acquisition_process"] = raw["communication_roots"][0]["acquisition_process"]
    _expect_invalid(p, "duplicate acquisition_process")

    def o(raw):
        raw["communication_roots"][1]["stated_origin"] = raw["communication_roots"][0]["stated_origin"]
    _expect_invalid(o, "duplicate stated_origin")


@pytest.mark.parametrize("field", ["is_synthetic", "asserts_claim", "follows_standard_procedure"])
def test_root_boolean_requirements(field):
    def m(raw):
        raw["communication_roots"][0][field] = False
    _expect_invalid(m)


@pytest.mark.parametrize("field", ["measures_claimed_quantity", "can_establish_exact_quantity"])
def test_measurement_feasibility_is_required(field):
    def m(raw):
        raw["communication_roots"][0]["measurement"][field] = False
    _expect_invalid(m, "measure the exact claimed quantity", pair="geo")


def test_credibility_labels_rejected_in_stated_origin():
    for bad in ("Amateur Group", "Royal Archive Group", "Government Group", "University Group"):
        def m(raw, bad=bad):
            raw["communication_roots"][0]["stated_origin"] = bad
        _expect_invalid(m, "signals credibility")


def test_stated_origins_must_share_one_form_and_quality_tier():
    def form(raw):
        raw["communication_roots"][0]["stated_origin"] = "Tessaly Office"
    _expect_invalid(form, "same final word")

    def tier(raw):
        raw["communication_roots"][0]["quality_tier"] = "premium"
    _expect_invalid(tier, "quality_tier")


def test_evidence_document_type_must_differ_from_root_artifacts():
    def m(raw):
        raw["evidence"]["document_type"] = raw["communication_roots"][0]["artifact_type"]
    _expect_invalid(m, "document_type must differ")


def test_authority_loaded_templates_rejected():
    for phrase in ("Records give", "Surveys put", "According to the release history"):
        def m(raw, phrase=phrase):
            v = raw["claim"]["asserted_value"]
            raw["message_templates"][1] = f"{phrase} {v}."
        _expect_invalid(m, "authority-loaded")


def test_shared_factor_analysis_required():
    def none(raw):
        raw["shared_factors"] = []
    _expect_invalid(none, "shared_factors")

    def no_inherent(raw):
        for f in raw["shared_factors"]:
            f["severity"] = "minor"
    _expect_invalid(no_inherent, "inherent")

    def unknown(raw):
        raw["shared_factors"][0]["affects_roots"] = ["nope"]
    _expect_invalid(unknown, "unknown roots")


def test_event_date_requires_calendar_convention_and_valid_iso():
    def no_cal(raw):
        raw["claim"]["calendar_convention"] = None
    _expect_invalid(no_cal, "calendar_convention")

    def bad_date(raw):
        raw["claim"]["event_date"] = "12 May 2031"
    _expect_invalid(bad_date)


def test_truth_evidence_consistency_enforced():
    def a(raw):
        raw["evidence"]["supports_claim"] = False
    _expect_invalid(a, truth="true")

    def b(raw):
        raw["evidence"]["supports_claim"] = True
    _expect_invalid(b, truth="false")

    def c(raw):
        raw["evidence"]["ground_truth_value"] = raw["claim"]["asserted_value"]
    _expect_invalid(c, truth="false")

    def d(raw):
        raw["truth_status"] = "false"  # label flipped without changing evidence
    _expect_invalid(d, truth="true")


def test_template_must_carry_only_asserted_value():
    def extra(raw):
        raw["message_templates"][1] = raw["message_templates"][1] + " It was 77 people."
    _expect_invalid(extra, "unexpected numerals")

    def none(raw):
        raw["message_templates"][1] = "Nothing numeric here."
    _expect_invalid(none, "exactly once")


def test_status_gates_require_review_and_human_confirmed_independence():
    def frozen(raw):
        raw["status"] = "frozen"
    _expect_invalid(frozen)  # evidence unverified, no review, no sha

    raw = _raw()
    raw["status"] = "independently_checked"
    raw["evidence"]["verification_status"] = "independently_checked"
    with pytest.raises(ValidationError, match="review record"):
        Scenario.model_validate(raw)
    raw["review"] = {"reviewer": "x", "blind_to_truth": True, "reviewed_on": "2026-01-01",
                     "independence_confirmed": None}
    with pytest.raises(ValidationError, match="human-confirmed independence"):
        Scenario.model_validate(raw)
    raw["review"]["independence_confirmed"] = True
    # Stage 4J.5 expectation change (owner decision 1): the old record shape (an invented reviewer name and a true flag)
    # no longer reaches independently_checked. It now needs a known author and the independent-review evidence.
    with pytest.raises(ValidationError, match="author_id"):
        Scenario.model_validate(raw)
    raw["author_id"] = "author-1"
    with pytest.raises(ValidationError, match="qualifying independent reviewer"):
        Scenario.model_validate(raw)


def test_schema_version_enforced():
    def m(raw):
        raw["schema_version"] = "2.0-draft"
    _expect_invalid(m, "schema_version")


def test_config_loads_and_is_hash_stable():
    cfg = load_config(ROOT / "configs/receiver_experiment.json")
    assert [m.model_id for m in cfg.models] == ["google/gemini-3.8-flash", "qwen/qwen3.6-flash"]
    assert cfg.api.enabled is False
    assert config_hash(cfg) == config_hash(load_config(ROOT / "configs/receiver_experiment.json"))


def test_config_locks_evidence_hidden_and_requires_c0():
    raw = json.loads((ROOT / "configs/receiver_experiment.json").read_text())
    bad = copy.deepcopy(raw)
    bad["design"]["evidence_visible_to_receiver"] = True
    with pytest.raises(ValidationError):
        load_config_from(bad)
    bad = copy.deepcopy(raw)
    bad["design"]["conditions"] = [c for c in bad["design"]["conditions"] if c["id"] != "C0"]
    with pytest.raises(ValidationError):
        load_config_from(bad)
    bad = copy.deepcopy(raw)
    bad["design"]["conditions"][2] = {"id": "C2", "n_messages": 4, "n_roots": 2}  # 2 roots over 4 msgs
    with pytest.raises(ValidationError):
        load_config_from(bad)


def load_config_from(raw):
    from maps.config import ExperimentConfig

    return ExperimentConfig.model_validate(raw)
