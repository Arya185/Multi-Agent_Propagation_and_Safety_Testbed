"""Exact scope binding: size, same-size substitutions, content digests, configuration conflicts (v2.3.66, Stage 4D). Offline."""

from __future__ import annotations

import json
import shutil

import pytest

from maps.config import load_config
from maps.experiments.receiver import build_grid
from maps.runs.policy_source import PolicySourceError, check_scope, compute_content_digests, load_policy
from maps.scenarios import load_scenario_dir

from ps_support import PROFILE, REPO_ROOT, SYN, SYN_CONFIG, load_inputs, make_doc, make_limits, mutated, tripwires, write_policy  # noqa: F401


@pytest.fixture(scope="module")
def inputs():
    return load_inputs()


@pytest.fixture(scope="module")
def doc(inputs):
    cfg, _s, specs, digests = inputs
    return make_doc(cfg, specs, digests)


def reason_of(doc, cfg, specs, digests) -> str:
    with pytest.raises(PolicySourceError) as e:
        check_scope(doc, cfg, specs, digests)
    return e.value.reason


def test_the_matching_scope_passes(inputs, doc):
    cfg, _s, specs, digests = inputs
    check_scope(doc, cfg, specs, digests)
    assert len(specs) == 96 == 2 * 4 * 2 * 6 * cfg.design.repetitions


@pytest.mark.parametrize("name,value,expected", [
    ("experiment_id", "other-experiment", "scope_mismatch"), ("config_version", "9.9", "scope_mismatch"),
    ("prompt_version", "receiver-v9", "scope_mismatch"), ("stage", "main", "scope_mismatch"), ("seed", 1, "scope_mismatch"),
    ("repetitions", 2, "scope_mismatch"), ("rotate_templates_and_roots", False, "scope_mismatch"),
    ("max_tokens_per_request", 801, "scope_mismatch"), ("planned_episodes", 95, "grid_mismatch"), ("planned_episodes", 97, "grid_mismatch"),
    ("design_digest", "0" * 64, "design_mismatch"),
])
def test_scalar_scope_values_must_equal_the_configuration(inputs, doc, name, value, expected):
    cfg, _s, specs, digests = inputs
    assert reason_of(mutated(doc, lambda d: d["scope"].update({name: value})), cfg, specs, digests) == expected


def test_a_changed_model_list_is_refused(inputs, doc):
    cfg, _s, specs, digests = inputs
    for change in (
        lambda d: d["scope"]["models"][0].update(model_id="other/model"),
        lambda d: d["scope"]["models"][0].update(family="other"),
        lambda d: d["scope"]["models"][0].update(alias="aaaa"),
        lambda d: d["scope"]["models"].pop(),
    ):
        assert reason_of(mutated(doc, change), cfg, specs, digests) in ("scope_mismatch", "grid_mismatch")


def test_changed_conditions_variants_are_refused(inputs, doc):
    cfg, _s, specs, digests = inputs
    assert reason_of(mutated(doc, lambda d: d["scope"]["conditions"][2].update(n_messages=9)), cfg, specs, digests) == "scope_mismatch"
    assert reason_of(mutated(doc, lambda d: d["scope"]["conditions"][2].update(n_roots=0)), cfg, specs, digests) == "scope_mismatch"
    assert reason_of(mutated(doc, lambda d: d["scope"].update(prompt_variants=["neutral"])), cfg, specs, digests) == "scope_mismatch"
    assert reason_of(mutated(doc, lambda d: d["scope"]["conditions"].pop()), cfg, specs, digests) == "scope_mismatch"


# ---- same-size substitutions -----------------------------------------------------------------------------------------
def clone_specs(specs, **change_for):
    """Copies of the specs with one scenario or model id replaced, so the grid keeps its size."""
    out = []
    for spec in specs:
        update = {}
        for field, (old, new) in change_for.items():
            if getattr(spec, field) == old:
                update[field] = new
        out.append(spec.model_copy(update=update))
    return out


def test_a_swapped_scenario_with_the_same_grid_size_is_refused(inputs, doc):
    cfg, _s, specs, digests = inputs
    first = doc["scope"]["scenario_ids"][0]
    swapped = clone_specs(specs, scenario_id=(first, "syn-swapped"))
    assert len(swapped) == len(specs) == doc["scope"]["planned_episodes"]
    assert reason_of(doc, cfg, swapped, digests) == "grid_mismatch"


def test_a_swapped_model_with_the_same_grid_size_is_refused(inputs, doc):
    cfg, _s, specs, digests = inputs
    swapped = clone_specs(specs, model_id=(cfg.models[0].model_id, "other/model"))
    assert len(swapped) == len(specs)
    assert reason_of(doc, cfg, swapped, digests) == "grid_mismatch"


def test_a_policy_and_grid_that_agree_on_a_new_scenario_still_fail_on_content(inputs, doc):
    cfg, _s, specs, digests = inputs
    first = doc["scope"]["scenario_ids"][0]

    def rename(d):
        d["scope"]["scenario_ids"][0] = "syn-zzz"
        d["scope"]["scenario_ids"].sort()
        d["scope"]["content"] = {sid: d["scope"]["content"].get(sid, d["scope"]["content"][first]) for sid in d["scope"]["scenario_ids"]}

    swapped = clone_specs(specs, scenario_id=(first, "syn-zzz"))
    assert reason_of(mutated(doc, rename), cfg, swapped, digests) == "content_mismatch"


def test_duplicate_missing_or_extra_episodes_are_refused(inputs, doc):
    cfg, _s, specs, digests = inputs
    assert reason_of(doc, cfg, list(specs[:-1]) + [specs[0]], digests) == "grid_mismatch"          # same size, one duplicated
    assert reason_of(doc, cfg, list(specs[:-1]), digests) == "grid_mismatch"                       # one missing
    assert reason_of(doc, cfg, list(specs) + [specs[0]], digests) == "grid_mismatch"               # one extra


def test_a_condition_shape_that_differs_from_the_policy_is_refused(inputs, doc):
    cfg, _s, specs, digests = inputs
    changed = [s.model_copy(update={"n_messages": s.n_messages + 1}) if s.condition_id == "C3" else s for s in specs]
    assert reason_of(doc, cfg, changed, digests) == "grid_mismatch"


def test_specs_without_the_needed_attributes_are_refused(inputs, doc):
    cfg, _s, specs, digests = inputs
    assert reason_of(doc, cfg, [object()] * len(specs), digests) == "input_invalid"


# ---- scenario and evidence content --------------------------------------------------------------------------------------
@pytest.mark.parametrize("which", ["scenario_sha256", "evidence_sha256"])
def test_a_changed_content_digest_is_refused(inputs, doc, which):
    cfg, _s, specs, digests = inputs
    first = doc["scope"]["scenario_ids"][0]
    actual = {k: dict(v) for k, v in digests.items()}
    actual[first][which] = "f" * 64
    assert reason_of(doc, cfg, specs, actual) == "content_mismatch"


def test_missing_or_extra_actual_scenarios_are_refused(inputs, doc):
    cfg, _s, specs, digests = inputs
    fewer = {k: v for k, v in list(digests.items())[1:]}
    more = {**digests, "syn-extra": next(iter(digests.values()))}
    assert reason_of(doc, cfg, specs, fewer) == "content_mismatch"
    assert reason_of(doc, cfg, specs, more) == "content_mismatch"
    assert reason_of(doc, cfg, specs, ["not", "a", "mapping"]) == "input_invalid"


def test_editing_a_scenario_or_evidence_file_under_the_same_id_is_detected(tmp_path):
    """Copy the synthetic scenarios and evidence, approve their digests, then edit one file in place."""
    work = tmp_path / "repo"
    shutil.copytree(SYN / "scenarios", work / "tests" / "synthetic" / "data" / "scenarios")
    shutil.copytree(SYN / "evidence", work / "tests" / "synthetic" / "data" / "evidence")
    scen_dir = work / "tests" / "synthetic" / "data" / "scenarios"
    approved = compute_content_digests(scen_dir, work)
    assert compute_content_digests(scen_dir, work) == approved
    evidence = sorted((work / "tests" / "synthetic" / "data" / "evidence").glob("*.md"))[0]
    evidence.write_text(evidence.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
    changed = compute_content_digests(scen_dir, work)
    assert changed != approved and sorted(changed) == sorted(approved)               # same ids, different content
    differing = [k for k in approved if approved[k] != changed[k]]
    assert len(differing) >= 1
    scen_file = sorted(scen_dir.glob("*.json"))[0]
    before = compute_content_digests(scen_dir, work)
    data = json.loads(scen_file.read_text(encoding="utf-8"))
    scen_file.write_text(json.dumps(data, indent=3), encoding="utf-8")               # same id, different bytes
    assert compute_content_digests(scen_dir, work) != before


def test_unreadable_content_is_refused(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PolicySourceError) as e:
        compute_content_digests(tmp_path, tmp_path)
    assert e.value.reason == "content_unreadable"


# ---- configuration conflicts ---------------------------------------------------------------------------------------------
def cfg_variant(tmp_path, mutate):
    config = json.loads(SYN_CONFIG.read_text(encoding="utf-8"))
    mutate(config)
    path = tmp_path / "variant_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return load_config(path)


def test_a_sampling_change_alters_the_design_digest_and_is_refused(tmp_path, inputs, doc):
    _cfg, _s, specs, digests = inputs
    cfg2 = cfg_variant(tmp_path, lambda c: c["sampling"].update(temperature=0.5))
    assert reason_of(doc, cfg2, specs, digests) == "design_mismatch"


def test_a_max_tokens_change_is_refused(tmp_path, inputs, doc):
    _cfg, _s, specs, digests = inputs
    cfg2 = cfg_variant(tmp_path, lambda c: c["sampling"].update(max_tokens=801))
    assert reason_of(doc, cfg2, specs, digests) == "scope_mismatch"


def test_the_rest_of_api_and_the_output_paths_are_not_part_of_the_design_digest(tmp_path, inputs, doc):
    cfg, _s, specs, digests = inputs
    cfg2 = cfg_variant(tmp_path, lambda c: (c["api"].update(base_url="https://x.invalid/v1", api_key_env="OTHER_NAME"),
                                            c["output"].update(results_dir="elsewhere")))
    check_scope(doc, cfg2, specs, digests)


@pytest.mark.parametrize("name,value", [("timeout_s", 5.0), ("backoff_s", 2.5)])
def test_a_timeout_or_backoff_change_is_refused_as_a_design_mismatch(tmp_path, inputs, doc, name, value):
    """Stage 4G, TIMEOUT-BACKOFF option A: the request timeout and the retry backoff are bound by the design digest."""
    _cfg, _s, specs, digests = inputs
    cfg2 = cfg_variant(tmp_path, lambda c: c["api"].update({name: value}))
    assert reason_of(doc, cfg2, specs, digests) == "design_mismatch"


def test_a_retry_count_that_differs_from_the_configuration_is_a_conflict(tmp_path, inputs, doc):
    cfg, _s, specs, digests = inputs
    bad = mutated(doc, lambda d: d["profiles"][PROFILE].update(make_limits(96, 1)))
    with pytest.raises(PolicySourceError) as e:
        load_policy(write_policy(tmp_path, bad), cfg=cfg, specs=specs, content_digests=digests, profile=PROFILE)
    assert e.value.reason == "config_conflict"


def test_a_scenario_list_change_in_the_configured_directory_changes_the_grid(inputs, doc):
    """The grid is built from the scenario files, so adding or removing one changes the specs and is refused."""
    cfg, scenarios, specs, digests = inputs
    fewer = build_grid(cfg, scenarios[:-1])
    assert reason_of(doc, cfg, fewer, digests) == "grid_mismatch"
    assert len(load_scenario_dir(REPO_ROOT / cfg.design.scenario_dir)) == len(scenarios)
