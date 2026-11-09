"""Explicit profile selection: no default, no overrides, no scope changes (v2.3.66, Stage 4D). Offline."""

from __future__ import annotations

import inspect

import pytest

import maps.runs.policy_source as policy_source
from maps.runs.policy_source import PolicySourceError, load_policy, select_profile

from ps_support import PROFILE, load_inputs, make_doc, make_limits, mutated, tripwires, write_policy  # noqa: F401


@pytest.fixture(scope="module")
def inputs():
    return load_inputs()


@pytest.fixture(scope="module")
def two_profiles(inputs):
    cfg, _s, specs, digests = inputs
    doc = make_doc(cfg, specs, digests)
    doc["profiles"]["second-profile"] = make_limits(96, 2, deadline_seconds=120, max_consecutive_nonfatal_errors=2)
    return doc


def load(path, inputs, profile):
    cfg, _s, specs, digests = inputs
    return load_policy(path, cfg=cfg, specs=specs, content_digests=digests, profile=profile)


def test_the_profile_argument_is_required_and_keyword_only_with_no_default():
    parameter = inspect.signature(load_policy).parameters["profile"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        load_policy("x", cfg=None, specs=[], content_digests={})                         # type: ignore[call-arg]


def test_the_loader_accepts_no_per_limit_overrides():
    names = set(inspect.signature(load_policy).parameters)
    assert names == {"path", "cfg", "specs", "content_digests", "profile", "expected_digest"}
    assert not any("limit" in n or "override" in n or "max_" in n for n in names)


@pytest.mark.parametrize("name", ["", "missing", "Synthetic-Test-Profile", " " + PROFILE, PROFILE + " ", "../x", None, 3, b"x", ["a"]])
def test_unknown_or_malformed_profile_names_are_refused(tmp_path, inputs, two_profiles, name):
    path = write_policy(tmp_path, two_profiles)
    with pytest.raises(PolicySourceError) as e:
        load(path, inputs, name)
    assert e.value.reason == "profile_unknown"


def test_a_single_profile_file_still_needs_the_name(tmp_path, inputs):
    cfg, _s, specs, digests = inputs
    path = write_policy(tmp_path, make_doc(cfg, specs, digests))
    assert load(path, inputs, PROFILE).profile == PROFILE
    with pytest.raises(PolicySourceError):
        load(path, inputs, "anything-else")


def test_each_profile_gives_its_own_limits_and_the_same_scope(tmp_path, inputs, two_profiles):
    path = write_policy(tmp_path, two_profiles)
    a, b = load(path, inputs, PROFILE), load(path, inputs, "second-profile")
    assert a.policy.deadline_seconds == 3600 and b.policy.deadline_seconds == 120
    assert b.policy.max_consecutive_nonfatal_errors == 2
    assert a.policy_digest == b.policy_digest and a.effective_digest != b.effective_digest
    assert a.planned_episodes == b.planned_episodes == 96 and a.design_digest == b.design_digest


def test_a_profile_cannot_change_the_scope(inputs, two_profiles):
    for extra in ("scope", "scenario_ids", "models", "planned_episodes", "max_tokens_per_request"):
        with pytest.raises(PolicySourceError) as e:
            policy_source.validate_document(mutated(two_profiles, lambda d, x=extra: d["profiles"][PROFILE].update({x: 1})))
        assert e.value.reason == "field_unknown"


def test_there_is_no_ceilings_block_in_schema_v1(inputs, two_profiles):
    with pytest.raises(PolicySourceError) as e:
        policy_source.validate_document(mutated(two_profiles, lambda d: d.update(ceilings={"max_episodes": 96})))
    assert e.value.reason == "field_unknown"


def test_select_profile_returns_the_limits_of_that_profile_only(two_profiles):
    assert select_profile(two_profiles, "second-profile")["deadline_seconds"] == 120
    assert select_profile(two_profiles, PROFILE)["deadline_seconds"] == 3600


def test_the_profile_name_is_not_read_from_the_environment(monkeypatch, tmp_path, inputs, two_profiles):
    monkeypatch.setenv("MAPS_POLICY_PROFILE", "second-profile")
    monkeypatch.setenv("MAPS_MAX_EPISODES", "1")
    path = write_policy(tmp_path, two_profiles)
    assert load(path, inputs, PROFILE).policy.deadline_seconds == 3600
