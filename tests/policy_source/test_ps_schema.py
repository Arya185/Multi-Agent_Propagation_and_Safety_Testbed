"""Schema v1: strict structure, no defaults, no unknown fields, limit semantics left to LivePolicy (v2.3.66, Stage 4D). Offline."""

from __future__ import annotations

import pytest

from maps.runs.policy_source import (
    LIMIT_FIELDS, SCOPE_FIELDS, TOP_FIELDS, PolicySourceError, load_policy, validate_document,
)

from ps_support import PROFILE, SENTINEL, load_inputs, make_doc, make_limits, mutated, tripwires, write_policy  # noqa: F401


@pytest.fixture(scope="module")
def inputs():
    return load_inputs()


@pytest.fixture(scope="module")
def doc(inputs):
    cfg, _s, specs, digests = inputs
    return make_doc(cfg, specs, digests)


def refuse(document, expected, field_part=None):
    with pytest.raises(PolicySourceError) as e:
        validate_document(document)
    assert e.value.reason == expected, str(e.value)
    if field_part:
        assert field_part in str(e.value)


def test_the_valid_document_passes(doc):
    assert validate_document(doc) is doc


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema="other-policy"), lambda d: d.update(schema_version=2), lambda d: d.update(schema_version=0),
    lambda d: d.update(schema_version=True), lambda d: d.update(schema_version="1"), lambda d: d.update(schema_version=1.0),
    lambda d: d.pop("schema"), lambda d: d.pop("schema_version"),
], ids=["schema-id", "version-2", "version-0", "version-bool", "version-str", "version-float", "no-schema", "no-version"])
def test_unsupported_schema_or_version_is_refused_first(doc, change):
    refuse(mutated(doc, change), "schema_unsupported")


@pytest.mark.parametrize("name", [n for n in TOP_FIELDS if n not in ("schema", "schema_version")])
def test_every_top_level_field_is_required(doc, name):
    refuse(mutated(doc, lambda d: d.pop(name)), "field_missing", name)


@pytest.mark.parametrize("name", SCOPE_FIELDS)
def test_every_scope_field_is_required(doc, name):
    refuse(mutated(doc, lambda d: d["scope"].pop(name)), "field_missing", name)


@pytest.mark.parametrize("name", LIMIT_FIELDS)
def test_every_limit_field_is_required_so_nothing_is_defaulted(doc, name):
    refuse(mutated(doc, lambda d: d["profiles"][PROFILE].pop(name)), "field_missing", name)


@pytest.mark.parametrize("where", ["top", "scope", "profile", "model", "condition", "content", "approval"])
def test_unknown_fields_are_refused_without_echoing_their_names(doc, where):
    def add(d):
        target = {
            "top": d, "scope": d["scope"], "profile": d["profiles"][PROFILE], "model": d["scope"]["models"][0],
            "condition": d["scope"]["conditions"][0], "content": next(iter(d["scope"]["content"].values())), "approval": d["approval"],
        }[where]
        target[SENTINEL] = 1

    with pytest.raises(PolicySourceError) as e:
        validate_document(mutated(doc, add))
    assert e.value.reason == "field_unknown" and SENTINEL not in str(e.value)


@pytest.mark.parametrize("path,value", [
    (("policy_id",), ""), (("policy_id",), "bad id with spaces"), (("policy_id",), "x" * 65), (("policy_id",), 7),
    (("scope", "experiment_id"), ""), (("scope", "config_version"), 3), (("scope", "prompt_version"), None),
    (("scope", "stage"), "other"), (("scope", "stage"), 1), (("scope", "seed"), "20260"), (("scope", "seed"), 1.5),
    (("scope", "seed"), True), (("scope", "repetitions"), "1"), (("scope", "repetitions"), True),
    (("scope", "planned_episodes"), "96"), (("scope", "max_tokens_per_request"), 800.0), (("scope", "max_tokens_per_request"), "800"),
    (("scope", "rotate_templates_and_roots"), 1), (("scope", "design_digest"), "abc"), (("scope", "design_digest"), "G" * 64),
    (("scope", "models"), []), (("scope", "models"), {}), (("scope", "conditions"), "C0"), (("scope", "scenario_ids"), []),
    (("scope", "prompt_variants"), "neutral"), (("scope", "content"), {}), (("scope", "content"), []),
    (("profiles",), {}), (("profiles",), []), (("approval", "approval_reference"), ""), (("approval", "approval_reference"), 5),
    (("approval",), "reference"),
])
def test_wrong_types_and_forms_are_refused(doc, path, value):
    def change(d):
        target = d
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    with pytest.raises(PolicySourceError) as e:
        validate_document(mutated(doc, change))
    assert e.value.reason in ("type_invalid", "range_invalid", "field_missing"), str(e.value)


@pytest.mark.parametrize("name,value", [("repetitions", 0), ("repetitions", -1), ("planned_episodes", 0), ("max_tokens_per_request", 0), ("max_tokens_per_request", -5)])
def test_scope_numbers_must_be_positive(doc, name, value):
    refuse(mutated(doc, lambda d: d["scope"].update({name: value})), "range_invalid")


def test_condition_counts_must_not_be_negative(doc):
    refuse(mutated(doc, lambda d: d["scope"]["conditions"][1].update(n_messages=-1)), "range_invalid")
    refuse(mutated(doc, lambda d: d["scope"]["conditions"][1].update(n_roots=True)), "type_invalid")


@pytest.mark.parametrize("name", ["scenario_ids", "prompt_variants", "models", "conditions"])
def test_lists_must_be_unique_and_canonically_ordered(doc, name):
    refuse(mutated(doc, lambda d: d["scope"][name].append(d["scope"][name][0])), "duplicate_identifier")
    refuse(mutated(doc, lambda d: d["scope"][name].reverse()), "not_canonical_order")


def test_duplicate_model_ids_under_different_aliases_are_refused(doc):
    def change(d):
        d["scope"]["models"][1]["model_id"] = d["scope"]["models"][0]["model_id"]

    refuse(mutated(doc, change), "duplicate_identifier")


def test_content_keys_must_equal_the_scenario_ids(doc):
    def extra(d):
        d["scope"]["content"]["syn-extra"] = next(iter(d["scope"]["content"].values()))

    def short(d):
        d["scope"]["content"].pop(d["scope"]["scenario_ids"][0])

    refuse(mutated(doc, extra), "scope_mismatch")
    refuse(mutated(doc, short), "scope_mismatch")


def test_content_digests_must_be_sha256_hex(doc):
    refuse(mutated(doc, lambda d: next(iter(d["scope"]["content"].values())).update(scenario_sha256="nothex")), "type_invalid")
    refuse(mutated(doc, lambda d: next(iter(d["scope"]["content"].values())).update(evidence_sha256=("A" * 64))), "type_invalid")


@pytest.mark.parametrize("change,expected", [
    (lambda l: l.update(max_episodes="96"), "type_invalid"), (lambda l: l.update(max_retries=True), "type_invalid"),
    (lambda l: l.update(deadline_seconds=1.5), "type_invalid"), (lambda l: l.update(accounting_basis=3), "type_invalid"),
    (lambda l: l.update(fatal_3xx="yes"), "type_invalid"), (lambda l: l.update(nonfatal_4xx_statuses="429"), "type_invalid"),
    (lambda l: l.update(nonfatal_4xx_statuses=[429, "408"]), "type_invalid"),
    (lambda l: l.update(nonfatal_4xx_statuses=[429, 408]), "not_canonical_order"),
    (lambda l: l.update(nonfatal_4xx_statuses=[408, 408]), "duplicate_identifier"),
])
def test_profile_limit_types_and_canonical_status_order(doc, change, expected):
    refuse(mutated(doc, lambda d: change(d["profiles"][PROFILE])), expected)


def test_profile_ids_must_be_plain_identifiers(doc):
    def rename(d):
        d["profiles"]["bad profile!"] = d["profiles"].pop(PROFILE)

    refuse(mutated(doc, rename), "type_invalid")


@pytest.mark.parametrize("override,field_part", [
    ({"max_request_attempts": 1}, "max_request_attempts"), ({"max_episodes": 1}, "max_episodes"), ({"deadline_seconds": 0}, "deadline_seconds"),
    ({"max_retries": -1}, "max_retries"), ({"max_consecutive_nonfatal_errors": 0}, "max_consecutive_nonfatal_errors"),
    ({"max_consecutive_nonfatal_errors": 10_000}, "max_consecutive_nonfatal_errors"), ({"accounting_basis": "unlimited"}, "accounting_basis"),
    ({"nonfatal_4xx_statuses": [200]}, "nonfatal_4xx_statuses"), ({"max_request_attempts": 0}, "max_request_attempts"),
])
def test_limit_semantics_are_refused_by_the_live_policy_validator(tmp_path, inputs, doc, override, field_part):
    cfg, _s, specs, digests = inputs
    bad = mutated(doc, lambda d: d["profiles"][PROFILE].update(override))
    with pytest.raises(PolicySourceError) as e:
        load_policy(write_policy(tmp_path, bad), cfg=cfg, specs=specs, content_digests=digests, profile=PROFILE)
    assert e.value.reason == "limits_invalid" and field_part in str(e.value)


def test_no_permissive_default_is_ever_applied(doc):
    """Dropping any field refuses; there is no value that means unlimited."""
    for name in LIMIT_FIELDS:
        with pytest.raises(PolicySourceError):
            validate_document(mutated(doc, lambda d, n=name: d["profiles"][PROFILE].pop(n)))
    limits = make_limits(96, 2)
    assert set(limits) == set(LIMIT_FIELDS)
