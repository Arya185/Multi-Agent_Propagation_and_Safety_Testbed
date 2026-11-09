"""SYNTHETIC prompt-construction and response-parsing tests (mock only; no real data)."""

from __future__ import annotations

import json

import pytest

from maps.experiments.receiver import build_grid
from maps.mock_client import MockClient
from maps.prompts.receiver import (
    PROMPT_VERSION,
    SCOPE_LINE,
    SOURCE_AWARE_INSTRUCTION,
    SYSTEM_PROMPT,
    build_messages,
    build_user_prompt,
)
from maps.schemas import ChatRequest, ResponseParseError, parse_receiver_response

from synthetic_support import syn_cfg, syn_scenarios  # noqa: F401

RESPONSE_KEYS = ("accepts_claim", "confidence", "estimated_independent_roots", "evidence_used", "reasoning")
VALID = {
    "accepts_claim": True,
    "confidence": 80,
    "estimated_independent_roots": 1,
    "evidence_used": ["message 1"],
    "reasoning": "Synthetic reasoning.",
}


@pytest.fixture(scope="module")
def grid(syn_cfg, syn_scenarios):
    return build_grid(syn_cfg, syn_scenarios)


@pytest.fixture(scope="module")
def by_id(syn_scenarios):
    return {s.scenario_id: s for s in syn_scenarios}


def test_prompt_version_matches_config(syn_cfg):
    assert syn_cfg.prompt_version == PROMPT_VERSION


def test_prompt_structure_for_every_episode(grid, by_id):
    for spec in grid:
        sc = by_id[spec.scenario_id]
        text = build_user_prompt(sc, spec.message_plan, spec.prompt_variant)
        paras = text.split("\n\n")
        assert paras[0] == f"Claim under evaluation: {sc.claim.text}"
        assert paras[1] == SCOPE_LINE
        idx = 2
        if spec.prompt_variant == "source-aware":
            assert paras[2] == SOURCE_AWARE_INSTRUCTION
            idx = 3
        else:
            assert SOURCE_AWARE_INSTRUCTION not in text
        assert len(paras) == idx + 1
        last = paras[idx]
        if spec.n_messages == 0:
            assert last == "You have received no messages about this claim."
            continue
        lines = last.split("\n")
        assert lines[0] == "Messages received:" and len(lines) == 1 + 2 * spec.n_messages
        for k, item in enumerate(spec.message_plan):
            origin = sc.root_by_id(item.root_id).stated_origin
            assert lines[1 + 2 * k] == f"Message {k + 1} | sender: Relay-{k + 1} | stated origin: {origin}"
            assert lines[2 + 2 * k] == sc.message_templates[item.template_idx]


def test_variants_differ_only_by_the_instruction_paragraph(grid, by_id):
    groups: dict[tuple, dict] = {}
    for spec in grid:
        groups.setdefault((spec.model_alias, spec.scenario_id, spec.condition_id, spec.repetition), {})[spec.prompt_variant] = spec
    for pair in groups.values():
        sc = by_id[pair["neutral"].scenario_id]
        neutral = build_user_prompt(sc, pair["neutral"].message_plan, "neutral")
        aware = build_user_prompt(sc, pair["source-aware"].message_plan, "source-aware")
        assert aware.replace(SOURCE_AWARE_INSTRUCTION + "\n\n", "") == neutral
        assert build_messages(sc, pair["neutral"].message_plan, "neutral")[0] == build_messages(
            sc, pair["source-aware"].message_plan, "source-aware"
        )[0]


def test_messages_have_system_then_user_roles(grid, by_id):
    spec = grid[0]
    msgs = build_messages(by_id[spec.scenario_id], spec.message_plan, spec.prompt_variant)
    assert [m.role for m in msgs] == ["system", "user"] and msgs[0].content == SYSTEM_PROMPT


def test_prompts_do_not_leak_hidden_metadata(grid, by_id):
    for spec in grid:
        sc = by_id[spec.scenario_id]
        blob = "\n".join(m.content for m in build_messages(sc, spec.message_plan, spec.prompt_variant))
        for root in sc.communication_roots:
            for hidden in (root.root_id, root.description, root.acquisition_process, root.operator_id, root.instrument_id, *root.upstream_ids):
                assert hidden not in blob
        assert sc.claim.quantity_definition not in blob
        assert sc.evidence.reference not in blob
        assert "SYNTHETIC DOCUMENT" not in blob and "Not research data" not in blob
        if sc.truth_status == "false":
            assert f"Value: {sc.evidence.ground_truth_value}" not in blob


def test_system_prompt_names_the_response_keys():
    for key in RESPONSE_KEYS:
        assert f'"{key}"' in SYSTEM_PROMPT
    assert "estimated_independent_sources" not in SYSTEM_PROMPT


def test_valid_response_parses():
    r = parse_receiver_response(json.dumps(VALID))
    assert r.accepts_claim is True and r.confidence == 80 and r.estimated_independent_roots == 1


INVALID = [
    ("empty", ""),
    ("not_json", "not json"),
    ("fenced", "```json\n" + json.dumps(VALID) + "\n```"),
    ("prefixed", "Here: " + json.dumps(VALID)),
    ("array", json.dumps([VALID])),
    ("nan", json.dumps(VALID).replace("80", "NaN")),
    ("truncated", json.dumps(VALID)[:-1]),
    ("confidence_high", json.dumps({**VALID, "confidence": 101})),
    ("confidence_low", json.dumps({**VALID, "confidence": -1})),
    ("confidence_string", json.dumps({**VALID, "confidence": "80"})),
    ("confidence_float", json.dumps({**VALID, "confidence": 80.5})),
    ("confidence_bool", json.dumps({**VALID, "confidence": True})),
    ("accepts_string", json.dumps({**VALID, "accepts_claim": "true"})),
    ("accepts_int", json.dumps({**VALID, "accepts_claim": 1})),
    ("roots_negative", json.dumps({**VALID, "estimated_independent_roots": -1})),
    ("roots_float", json.dumps({**VALID, "estimated_independent_roots": 1.0})),
    ("evidence_not_list", json.dumps({**VALID, "evidence_used": "message 1"})),
    ("evidence_wrong_item", json.dumps({**VALID, "evidence_used": [1]})),
    ("reasoning_empty", json.dumps({**VALID, "reasoning": ""})),
    ("extra_key", json.dumps({**VALID, "extra": 1})),
    ("old_key_name", json.dumps({**{k: v for k, v in VALID.items() if k != "estimated_independent_roots"}, "estimated_independent_sources": 1})),
]


@pytest.mark.parametrize("name,text", INVALID, ids=[i[0] for i in INVALID])
def test_invalid_responses_are_rejected_not_repaired(name, text):
    with pytest.raises(ResponseParseError):
        parse_receiver_response(text)


def test_missing_field_is_rejected():
    data = {k: v for k, v in VALID.items() if k != "reasoning"}
    with pytest.raises(ResponseParseError):
        parse_receiver_response(json.dumps(data))


def test_every_mock_answer_in_the_grid_parses(syn_cfg, grid, by_id):
    client = MockClient()
    for spec in grid:
        msgs = build_messages(by_id[spec.scenario_id], spec.message_plan, spec.prompt_variant)
        req = ChatRequest(
            model=spec.model_id, messages=msgs, temperature=syn_cfg.sampling.temperature,
            max_tokens=syn_cfg.sampling.max_tokens, seed=spec.seed,
        )
        result = client.complete(req)
        assert result.error is None
        parse_receiver_response(result.content)
    assert len(client.calls) == 96
