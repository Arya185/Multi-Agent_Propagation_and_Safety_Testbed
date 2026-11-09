"""Canonical serialization and digests; the digest is integrity only, never authentication (v2.3.66, Stage 4D). Offline."""

from __future__ import annotations

import hashlib
import json
import random

import pytest

from maps.runs.policy_source import (
    PolicySourceError, canonical_bytes, design_digest, effective_digest, load_policy, policy_digest,
)

from ps_support import PROFILE, SENTINEL, SYN_CONFIG, load_inputs, make_doc, make_limits, mutated, tripwires, write_policy  # noqa: F401
from maps.config import load_config


@pytest.fixture(scope="module")
def inputs():
    return load_inputs()


@pytest.fixture(scope="module")
def doc(inputs):
    cfg, _s, specs, digests = inputs
    return make_doc(cfg, specs, digests)


def independent_digest(document: dict) -> str:
    """Recomputed with the standard library only, from the documented recipe."""
    content = {k: v for k, v in document.items() if k != "approval"}
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def load(path, inputs, **kw):
    cfg, _s, specs, digests = inputs
    return load_policy(path, cfg=cfg, specs=specs, content_digests=digests, profile=kw.pop("profile", PROFILE), **kw)


def test_the_digest_is_recomputable_independently(doc):
    assert policy_digest(doc) == independent_digest(doc)


def test_the_digest_is_stable_across_key_order_and_file_formatting(tmp_path, inputs, doc):
    shuffled = {}
    for key in random.Random(1).sample(list(doc), len(doc)):
        shuffled[key] = doc[key]
    compact = tmp_path / "compact.json"
    compact.write_text(json.dumps(shuffled, separators=(",", ":")), encoding="utf-8")
    pretty = write_policy(tmp_path, doc)
    assert load(compact, inputs).policy_digest == load(pretty, inputs).policy_digest == independent_digest(doc)


def test_the_digest_is_a_lowercase_sha256_hex_string(doc):
    assert len(policy_digest(doc)) == 64 and policy_digest(doc) == policy_digest(doc).lower()


@pytest.mark.parametrize("change", [
    lambda d: d.update(policy_id="synthetic-test-policy-2"),
    lambda d: d["scope"].update(seed=d["scope"]["seed"] + 1),
    lambda d: d["scope"].update(max_tokens_per_request=d["scope"]["max_tokens_per_request"] + 1),
    lambda d: d["scope"]["models"][0].update(model_id="x/y"),
    lambda d: d["scope"]["scenario_ids"].append("zzz"),
    lambda d: next(iter(d["scope"]["content"].values())).update(scenario_sha256="e" * 64),
    lambda d: d["profiles"][PROFILE].update(deadline_seconds=1),
    lambda d: d["profiles"][PROFILE].update(fatal_3xx=False),
    lambda d: d["profiles"][PROFILE].update(nonfatal_4xx_statuses=[]),
    lambda d: d["profiles"].update({"another": make_limits(96, 2)}),
])
def test_any_content_change_changes_the_digest(doc, change):
    assert policy_digest(mutated(doc, change)) != policy_digest(doc)


def test_the_approval_reference_is_outside_the_hashed_content(doc):
    other = mutated(doc, lambda d: d["approval"].update(approval_reference="a completely different reference"))
    assert policy_digest(other) == policy_digest(doc)
    assert "approval" not in json.dumps({k: v for k, v in doc.items() if k != "approval"})
    assert effective_digest(other, PROFILE) == effective_digest(doc, PROFILE)


def test_the_effective_digest_covers_the_scope_and_only_the_selected_profile(doc):
    two = mutated(doc, lambda d: d["profiles"].update({"second": make_limits(96, 2, deadline_seconds=7)}))
    assert effective_digest(two, PROFILE) == effective_digest(doc, PROFILE)             # an unselected profile does not matter
    assert effective_digest(two, "second") != effective_digest(two, PROFILE)
    assert policy_digest(two) != policy_digest(doc)                                      # the whole-document digest does cover it


def test_the_canonical_form_rejects_unsupported_values():
    for bad in (1.5, None, {"a": 1.0}, [object()], {1: "a"}, {"a": {"b": float("nan")}}, {"a": b"bytes"}):
        with pytest.raises(PolicySourceError):
            canonical_bytes(bad)
    assert canonical_bytes({"b": [1, True, "x"], "a": 2}) == b'{"a":2,"b":[1,true,"x"]}'
    assert canonical_bytes({"k": "é\ud800"}) == b'{"k":"\\u00e9\\ud800"}'               # non-ASCII and lone surrogates are escaped


def test_the_design_digest_covers_the_design_timeout_and_backoff_and_excludes_the_rest_of_api_and_output(tmp_path):
    base = json.loads(SYN_CONFIG.read_text(encoding="utf-8"))

    def digest_of(mutate):
        config = json.loads(json.dumps(base))
        mutate(config)
        path = tmp_path / "c.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return design_digest(load_config(path))

    reference = digest_of(lambda c: None)
    assert reference == design_digest(load_config(SYN_CONFIG)) and len(reference) == 64
    for same in (lambda c: c["api"].update(base_url="https://x.invalid/v1"),
                 lambda c: c["api"].update(max_retries=0), lambda c: c["output"].update(results_dir="elsewhere"),
                 lambda c: c["api"].update(api_key_env="ANOTHER_NAME"), lambda c: c["api"].update(enabled=True)):
        assert digest_of(same) == reference
    for different in (lambda c: c["api"].update(timeout_s=9.0), lambda c: c["api"].update(backoff_s=3.0),
                      lambda c: c["sampling"].update(temperature=0.7), lambda c: c["sampling"].update(max_tokens=801),
                      lambda c: c.update(seed=1), lambda c: c.update(prompt_version="x"), lambda c: c["output"].update(stage="main"),
                      lambda c: c["design"].update(repetitions=2), lambda c: c["models"][0].update(model_id="x/y"),
                      lambda c: c["design"]["conditions"][1].update(n_messages=3, n_roots=1)):
        assert digest_of(different) != reference


# ---- expected digest: caller-supplied, and not authentication ---------------------------------------------------------------
def test_a_matching_caller_supplied_expected_digest_is_accepted_and_flagged(tmp_path, inputs, doc):
    path = write_policy(tmp_path, doc)
    loaded = load(path, inputs, expected_digest=independent_digest(doc))
    assert loaded.expected_digest_checked is True
    assert load(path, inputs).expected_digest_checked is False


def test_a_mismatching_or_malformed_expected_digest_is_refused(tmp_path, inputs, doc):
    path = write_policy(tmp_path, doc)
    with pytest.raises(PolicySourceError) as e:
        load(path, inputs, expected_digest="0" * 64)
    assert e.value.reason == "digest_mismatch"
    for bad in ("short", "G" * 64, "A" * 64, 5, b"x" * 64):
        with pytest.raises(PolicySourceError) as e2:
            load(path, inputs, expected_digest=bad)
        assert e2.value.reason == "expected_digest_invalid"


def test_the_file_cannot_carry_its_own_expected_digest(tmp_path, inputs, doc):
    """A digest stored in the untrusted policy file is refused outright, so it can never be mistaken for authentication."""
    for where in ("approval", "top"):
        def add(d, where=where):
            (d["approval"] if where == "approval" else d)["approved_policy_digest"] = independent_digest(d)

        with pytest.raises(PolicySourceError) as e:
            load(write_policy(tmp_path, mutated(doc, add)), inputs)
        assert e.value.reason == "field_unknown"


def test_every_result_states_that_the_digest_is_not_authentication(tmp_path, inputs, doc):
    loaded = load(write_policy(tmp_path, doc), inputs)
    assert "not authenticated" in loaded.trust and "not proof of owner approval" in loaded.trust
    record = loaded.record()
    assert record["trust"] == loaded.trust and record["policy_digest"] == independent_digest(doc)
    assert set(record) >= {"policy_digest", "effective_digest", "design_digest", "profile", "policy_id", "schema_version"}
    assert not any(isinstance(v, str) and "synthetic-test-only" in v for v in record.values())      # the approval reference is not in it


def test_the_loaded_result_is_immutable(tmp_path, inputs, doc):
    loaded = load(write_policy(tmp_path, doc), inputs)
    with pytest.raises(Exception):
        loaded.profile = "other"                                                         # type: ignore[misc]
    with pytest.raises(Exception):
        loaded.policy.max_retries = 9                                                    # type: ignore[misc]


def test_timeout_and_backoff_each_change_the_digest_on_their_own_and_unchanged_values_are_stable(tmp_path):
    """Stage 4G, TIMEOUT-BACKOFF option A."""
    base = json.loads(SYN_CONFIG.read_text(encoding="utf-8"))

    def digest(timeout=None, backoff=None):
        config = json.loads(json.dumps(base))
        if timeout is not None:
            config["api"]["timeout_s"] = timeout
        if backoff is not None:
            config["api"]["backoff_s"] = backoff
        path = tmp_path / "c.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return design_digest(load_config(path))

    reference = digest()
    assert digest() == reference and digest(timeout=base["api"]["timeout_s"], backoff=base["api"]["backoff_s"]) == reference
    assert digest(timeout=base["api"]["timeout_s"] + 1) != reference                      # only timeout_s changed
    assert digest(backoff=base["api"]["backoff_s"] + 1) != reference                      # only backoff_s changed
    assert digest(timeout=base["api"]["timeout_s"] + 1) != digest(backoff=base["api"]["backoff_s"] + 1)


def test_the_digest_input_names_only_the_two_api_values_and_holds_no_secret_or_endpoint():
    import ast
    import inspect

    import maps.runs.policy_source as module

    source = inspect.getsource(module.design_digest)
    tree = ast.parse(source)
    keys = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "timeout_s" in keys and "backoff_s" in keys
    assert not {"base_url", "api_key_env", "enabled", "max_retries"} & set(keys)
