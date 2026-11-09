import json
from collections import Counter
from pathlib import Path

import pytest

from maps.config import load_config
from maps.experiments.receiver import (
    balance_report,
    build_grid,
    grid_tsv,
    message_plan,
    rotation_orders,
    run_episode,
    run_experiment,
)
from maps.mock_client import MockClient
from maps.prompts.receiver import (
    PROMPT_VERSION,
    SOURCE_AWARE_INSTRUCTION,
    build_messages,
    build_user_prompt,
    render_messages,
)
from maps.scenarios import load_scenario_dir

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260  # configs/receiver_experiment.json seed


@pytest.fixture(scope="module")
def cfg():
    return load_config(ROOT / "configs/receiver_experiment.json")


@pytest.fixture(scope="module")
def scenarios(cfg):
    return load_scenario_dir(ROOT / cfg.design.scenario_dir)


@pytest.fixture(scope="module")
def conds(cfg):
    return {c.id: c for c in cfg.design.conditions}


# ---- grid ---------------------------------------------------------------
def test_six_conditions_as_specified(cfg):
    got = [(c.id, c.n_messages, c.n_roots) for c in cfg.design.conditions]
    assert got == [("C0", 0, 0), ("C1", 1, 1), ("C2", 2, 1), ("C3", 4, 1), ("C4", 2, 2), ("C5", 4, 4)]


def test_pilot_grid_size_and_balance(cfg, scenarios):
    g = build_grid(cfg, scenarios)
    assert len(g) == 240 == 2 * 10 * 2 * 6 * cfg.design.repetitions
    assert Counter(s.condition_id for s in g) == {c: 40 for c in ("C0", "C1", "C2", "C3", "C4", "C5")}
    assert Counter(s.model_alias for s in g) == {"gemini": 120, "qwen": 120}
    assert Counter(s.prompt_variant for s in g) == {"neutral": 120, "source-aware": 120}
    assert Counter(s.truth_status for s in g) == {"true": 120, "false": 120}
    assert len({s.episode_id for s in g}) == 240


def test_grid_is_deterministic(cfg, scenarios):
    a = build_grid(cfg, scenarios)
    b = build_grid(cfg, load_scenario_dir(ROOT / cfg.design.scenario_dir))
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]
    assert grid_tsv(a) == grid_tsv(b)


def test_grid_matches_committed_plan_file(cfg, scenarios):
    committed = (ROOT / "experiments/plans/receiver_pilot_grid.tsv").read_text()
    assert grid_tsv(build_grid(cfg, scenarios)) == committed


def test_grid_seed_changes_order_not_membership(cfg, scenarios):
    other = cfg.model_copy(update={"seed": cfg.seed + 1})
    a, b = build_grid(cfg, scenarios), build_grid(other, scenarios)
    assert [s.episode_id for s in a] != [s.episode_id for s in b] or [s.seed for s in a] != [s.seed for s in b]


def test_main_stage_requires_frozen(cfg, scenarios):
    main = cfg.model_copy(update={"output": cfg.output.model_copy(update={"stage": "main"})})
    with pytest.raises(ValueError, match="frozen"):
        build_grid(main, scenarios)


def test_grid_refuses_visible_evidence(cfg, scenarios):
    bad = scenarios[0].model_copy(deep=True)
    bad.evidence.visible_to_receiver = True
    with pytest.raises(ValueError, match="must not be visible"):
        build_grid(cfg, [bad, *scenarios[1:]])


def test_four_repetitions_for_main_size(cfg, scenarios):
    four = cfg.model_copy(update={"design": cfg.design.model_copy(update={"repetitions": 4})})
    assert len(build_grid(four, scenarios)) == 960


# ---- rotation: seeded, randomized, truth-independent -------------------------------
def _pairs(scenarios):
    d = {}
    for s in scenarios:
        d.setdefault(s.pair_id, {})[s.truth_status] = s
    return d


def test_rotation_orders_are_permutations_and_cover_every_root_and_template_once(cfg, scenarios):
    for pair in _pairs(scenarios):
        firsts_r, firsts_t = [], []
        for r in range(4):
            ro, to = rotation_orders(cfg.seed, pair, r)
            assert sorted(ro) == [0, 1, 2, 3] and sorted(to) == [0, 1, 2, 3]
            firsts_r.append(ro[0])
            firsts_t.append(to[0])
        assert sorted(firsts_r) == [0, 1, 2, 3] and sorted(firsts_t) == [0, 1, 2, 3]  # balanced over 4 reps
        assert rotation_orders(cfg.seed, pair, 4) == rotation_orders(cfg.seed, pair, 0)


def test_rotation_is_deterministic_and_seed_dependent(cfg, scenarios):
    pairs = list(_pairs(scenarios))
    a = [rotation_orders(cfg.seed, p, 0) for p in pairs]
    assert a == [rotation_orders(cfg.seed, p, 0) for p in pairs]
    others = [rotation_orders(cfg.seed + 1, p, 0) for p in pairs]
    assert a != others


def test_rotation_is_randomized_not_identity(cfg, scenarios):
    pairs = list(_pairs(scenarios))
    roots0 = [rotation_orders(cfg.seed, p, 0)[0] for p in pairs]
    assert any(ro != (0, 1, 2, 3) for ro in roots0)
    assert len(set(roots0)) > 1  # different pairs get different orders
    assert not all(ro[0] == 0 for ro in roots0)  # R1 is not always the first/single root


def test_rotation_is_independent_of_truth_label(cfg, scenarios):
    # Orders are keyed by pair, so both truth members get identical plans; the function
    # takes no truth argument at all.
    import inspect

    assert "truth" not in str(inspect.signature(rotation_orders))
    for pair, d in _pairs(scenarios).items():
        c = {x.id: x for x in cfg.design.conditions}["C5"]
        for r in range(4):
            pt, pf = message_plan(d["true"], c, r, True, cfg.seed), message_plan(d["false"], c, r, True, cfg.seed)
            assert [p.template_idx for p in pt] == [p.template_idx for p in pf]
            assert [d["true"].root_by_id(p.root_id).stated_origin for p in pt] == \
                   [d["false"].root_by_id(p.root_id).stated_origin for p in pf]


def test_pilot_single_root_is_not_always_r1_and_balance_is_reported(cfg, scenarios):
    grid = build_grid(cfg, scenarios)
    bal = balance_report(grid, scenarios)
    for truth in ("true", "false"):
        single = bal["single_root_index_by_truth"][truth]
        assert sum(single.values()) == 5  # five scenarios per truth label
        assert set(single) != {1}  # R1 is not the only single root
    assert bal["single_root_index_by_truth"]["true"] == bal["single_root_index_by_truth"]["false"]
    committed = json.loads((ROOT / "experiments/plans/receiver_pilot_balance.json").read_text())
    assert committed == json.loads(json.dumps(bal))


def test_four_repetition_balance_is_exact(cfg, scenarios):
    four = cfg.model_copy(update={"design": cfg.design.model_copy(update={"repetitions": 4})})
    bal = balance_report(build_grid(four, scenarios), scenarios)
    for truth in ("true", "false"):
        assert bal["single_root_index_by_truth"][truth] == {1: 5, 2: 5, 3: 5, 4: 5}
        assert bal["first_template_index_by_truth"][truth] == {1: 5, 2: 5, 3: 5, 4: 5}


def test_rotation_off_uses_fixed_order(cfg, scenarios, conds):
    s = scenarios[0]
    assert message_plan(s, conds["C5"], 3, rotate=False, seed=cfg.seed) == \
        message_plan(s, conds["C5"], 0, rotate=False, seed=cfg.seed)


# ---- message-content matching: C2/C4 and C3/C5 --------------------------------
@pytest.mark.parametrize("repetition", range(4))
@pytest.mark.parametrize("repeated,independent", [("C2", "C4"), ("C3", "C5")])
def test_repeated_and_independent_conditions_match_in_content(scenarios, conds, repetition, repeated, independent):
    for s in scenarios:
        pr = message_plan(s, conds[repeated], repetition, True, SEED)
        pi = message_plan(s, conds[independent], repetition, True, SEED)
        rr, ri = render_messages(s, pr), render_messages(s, pi)
        assert [m.text for m in rr] == [m.text for m in ri]  # identical message content
        assert [m.relay_id for m in rr] == [m.relay_id for m in ri]  # identical, distinct relay ids
        assert [p.template_idx for p in pr] == [p.template_idx for p in pi]
        assert len({m.relay_id for m in rr}) == len(rr)
        assert len({p.root_id for p in pr}) == 1
        assert len({p.root_id for p in pi}) == len(pi)
        assert len({m.stated_origin for m in rr}) == 1 and len({m.stated_origin for m in ri}) == len(ri)
        for variant in ("neutral", "source-aware"):  # only the origin lines differ
            a = build_user_prompt(s, pr, variant).splitlines()
            b = build_user_prompt(s, pi, variant).splitlines()
            diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
            assert len(a) == len(b) and all(" | stated origin: " in a[i] for i in diff)


def test_single_root_conditions_share_the_first_root(scenarios, conds):
    for s in scenarios:
        for c in ("C1", "C2", "C3"):
            assert len({p.root_id for p in message_plan(s, conds[c], 1)}) == 1
        assert message_plan(s, conds["C1"], 1)[0].root_id == message_plan(s, conds["C3"], 1)[0].root_id


def test_independent_roots_are_upstream_disjoint(scenarios, conds):
    for s in scenarios:
        for c in ("C4", "C5"):
            roots = [s.root_by_id(p.root_id) for p in message_plan(s, conds[c], 2)]
            ups = [u for r in roots for u in r.upstream_ids]
            assert len(ups) == len(set(ups)) and len(roots) == conds[c].n_roots


def test_messages_are_information_equal(scenarios):
    for s in scenarios:
        for t in s.message_templates:
            assert t.count(s.claim.asserted_value) == 1


# ---- prompt equivalence and hidden metadata ------------------------------------
def test_prompt_variants_equal_except_one_instruction(scenarios, conds):
    for s in scenarios:
        for c in conds.values():
            for rep in (0, 1):
                plan = message_plan(s, c, rep)
                neutral = build_user_prompt(s, plan, "neutral")
                aware = build_user_prompt(s, plan, "source-aware")
                assert SOURCE_AWARE_INSTRUCTION in aware and SOURCE_AWARE_INSTRUCTION not in neutral
                assert aware.replace(SOURCE_AWARE_INSTRUCTION + "\n\n", "") == neutral
                sys_n = build_messages(s, plan, "neutral")[0].content
                sys_a = build_messages(s, plan, "source-aware")[0].content
                assert sys_n == sys_a


def test_both_variants_show_origin_metadata(scenarios, conds):
    s = scenarios[0]
    plan = message_plan(s, conds["C4"], 0)
    for variant in ("neutral", "source-aware"):
        text = build_user_prompt(s, plan, variant)
        for m in render_messages(s, plan):
            assert f"sender: {m.relay_id} | stated origin: {m.stated_origin}" in text


def test_prompt_does_not_leak_hidden_metadata_or_answers(scenarios, conds):
    forbidden_words = ["authenticat", "verified", "synthetic", "independent roots", "truth", "evidence document"]
    for s in scenarios:
        for c in conds.values():
            plan = message_plan(s, c, 0)
            for variant in ("neutral", "source-aware"):
                msgs = build_messages(s, plan, variant)
                blob = "\n".join(m.content for m in msgs)
                low = blob.lower()
                for r in s.communication_roots:
                    assert r.root_id not in blob
                    assert r.description not in blob
                    assert r.acquisition_process not in blob
                    assert all(u not in blob for u in r.upstream_ids)
                    assert r.operator_id not in blob and r.instrument_id not in blob
                    assert r.measurement.coverage_note not in blob
                assert s.claim.quantity_definition not in blob
                assert s.evidence.reference not in blob
                for w in forbidden_words:
                    assert w not in low, (s.scenario_id, c.id, w)
                if s.truth_status == "false":
                    assert s.evidence.ground_truth_value not in blob  # document content never shown
                assert "stated origin" in low or c.n_messages == 0
                assert str(c.n_roots) + " independent" not in low  # expected root count not revealed


def test_no_messages_prompt_for_c0(scenarios, conds):
    s = scenarios[0]
    text = build_user_prompt(s, message_plan(s, conds["C0"], 0), "neutral")
    assert "no messages" in text and "Message 1" not in text


def test_prompt_version_is_v2(cfg):
    assert PROMPT_VERSION == "receiver-v2" == cfg.prompt_version


def test_root_metadata_consistency_between_plan_and_prompt(cfg, scenarios):
    by_id = {s.scenario_id: s for s in scenarios}
    for spec in build_grid(cfg, scenarios):
        s = by_id[spec.scenario_id]
        assert {p.root_id for p in spec.message_plan} <= {r.root_id for r in s.communication_roots}
        assert spec.n_roots == len({p.root_id for p in spec.message_plan})
        assert all(p.root_id.startswith(spec.scenario_id + "-R") for p in spec.message_plan)
        text = build_user_prompt(s, spec.message_plan, spec.prompt_variant)
        shown = {s.root_by_id(p.root_id).stated_origin for p in spec.message_plan}
        assert len(shown) == spec.n_roots
        assert all(o in text for o in shown)


# ---- end to end (mock only) ----------------------------------------------------
def test_end_to_end_mock_run_logs_everything(tmp_path, cfg, scenarios):
    res = run_experiment(cfg, scenarios, MockClient(), tmp_path)
    assert len(res) == 240 and all(r.status == "ok" for r in res)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["synthetic_mock_data"] is True and manifest["evidence_visible_to_receiver"] is False
    assert manifest["model_ids"] == ["google/gemini-3.8-flash", "qwen/qwen3.6-flash"]
    assert set(manifest["scenarios"]) == {s.scenario_id for s in scenarios}
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert len(calls) == 240
    for k in ("episode_id", "requested_model_id", "prompt_version", "prompt_variant", "condition_id",
              "params", "total_tokens", "latency_s", "error", "messages", "client"):
        assert k in calls[0]
    assert calls[0]["prompt_version"] == "receiver-v2"
    assert (tmp_path / "summary.json").exists() and (tmp_path / "contrast_gaps.json").exists()


def test_malformed_and_error_calls_are_not_valid(cfg, scenarios):
    spec = next(s for s in build_grid(cfg, scenarios) if s.n_messages > 0)
    scenario = next(s for s in scenarios if s.scenario_id == spec.scenario_id)
    assert run_episode(spec, scenario, MockClient("malformed"), cfg).status == "parse_error"
    assert run_episode(spec, scenario, MockClient("error"), cfg).status == "call_error"


def test_mock_output_dir_is_separate_from_empirical_results():
    src = (ROOT / "src/maps/experiments/receiver.py").read_text()
    assert 'base / "mock" / run_id' in src
    # Stage 4C removed the unguarded live branch, which was the only code that wrote under the empirical stage directory;
    # the CLI now has no path that does, so nothing it writes can land among empirical results.
    assert "base / cfg.output.stage" not in src and "/ cfg.output.stage /" not in src
