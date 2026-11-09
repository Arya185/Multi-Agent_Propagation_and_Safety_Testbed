"""SYNTHETIC grid tests: determinism, identifiers, rotation properties (no real data)."""

from __future__ import annotations

from collections import Counter

import pytest

from maps.experiments.receiver import PLAN_COLUMNS, build_grid, grid_tsv, message_plan, rotation_orders

from synthetic_support import (  # noqa: F401
    EXPECTED_SCENARIO_IDS,
    compare_golden,
    expected_episode_id,
    expected_seed,
    golden_write_guard,
    load_syn_scenarios,
    read_golden,
    syn_cfg,
    syn_scenarios,
)

CONDITIONS = ("C0", "C1", "C2", "C3", "C4", "C5")
SHAPES = {"C0": (0, 0), "C1": (1, 1), "C2": (2, 1), "C3": (4, 1), "C4": (2, 2), "C5": (4, 4)}
EXPECTED_COLUMNS = (
    "idx", "episode_id", "model_alias", "model_id", "scenario_id", "truth_status", "condition_id",
    "n_messages", "n_roots", "prompt_variant", "repetition", "seed", "template_order", "root_ids",
)


@pytest.fixture(scope="module")
def grid(syn_cfg, syn_scenarios):
    return build_grid(syn_cfg, syn_scenarios)


def _by_key(grid):
    groups: dict[tuple, dict] = {}
    for s in grid:
        groups.setdefault((s.model_alias, s.scenario_id, s.prompt_variant, s.repetition), {})[s.condition_id] = s
    return groups


def test_grid_size_and_balance(grid):
    assert len(grid) == 2 * 4 * 2 * 6 * 1 == 96
    assert len({s.episode_id for s in grid}) == 96
    assert Counter(s.condition_id for s in grid) == {c: 16 for c in CONDITIONS}
    assert Counter(s.model_alias for s in grid) == {"synalpha": 48, "synbeta": 48}
    assert Counter(s.prompt_variant for s in grid) == {"neutral": 48, "source-aware": 48}
    assert Counter(s.truth_status for s in grid) == {"true": 48, "false": 48}
    assert Counter(s.scenario_id for s in grid) == {sid: 24 for sid in EXPECTED_SCENARIO_IDS}


def test_grid_is_deterministic(syn_cfg, syn_scenarios, grid):
    again = build_grid(syn_cfg, load_syn_scenarios())
    assert [s.model_dump() for s in grid] == [s.model_dump() for s in again]
    assert grid_tsv(grid) == grid_tsv(again)


def test_grid_header_and_row_count(grid):
    lines = grid_tsv(grid).splitlines()
    assert tuple(lines[0].split("\t")) == EXPECTED_COLUMNS == tuple(PLAN_COLUMNS)
    assert len(lines) == 97
    assert all(len(ln.split("\t")) == 14 for ln in lines)


def test_episode_ids_and_seeds_match_independent_recomputation(syn_cfg, grid):
    for s in grid:
        eid = expected_episode_id(syn_cfg.experiment_id, s.model_id, s.scenario_id, s.prompt_variant, s.condition_id, s.repetition)
        assert s.episode_id == eid
        assert s.seed == expected_seed(syn_cfg.seed, eid)


def test_seed_changes_order_and_seeds_not_membership(syn_cfg, syn_scenarios, grid):
    other = build_grid(syn_cfg.model_copy(update={"seed": syn_cfg.seed + 1}), syn_scenarios)
    assert {s.episode_id for s in other} == {s.episode_id for s in grid}
    assert [s.episode_id for s in other] != [s.episode_id for s in grid]
    assert {s.episode_id: s.seed for s in other} != {s.episode_id: s.seed for s in grid}


def test_condition_shapes_and_plans(grid):
    for s in grid:
        n, roots = SHAPES[s.condition_id]
        assert (s.n_messages, s.n_roots) == (n, roots)
        assert len(s.message_plan) == n
        assert [p.relay_id for p in s.message_plan] == [f"Relay-{k + 1}" for k in range(n)]
        assert len({p.root_id for p in s.message_plan}) == roots
        assert len({p.template_idx for p in s.message_plan}) == n
        assert all(p.root_id.startswith(s.scenario_id + "-R") for p in s.message_plan)


def test_repeated_and_independent_conditions_differ_only_in_roots(grid):
    for groups in _by_key(grid).values():
        for repeated, independent in (("C2", "C4"), ("C3", "C5")):
            a, b = groups[repeated].message_plan, groups[independent].message_plan
            assert [p.template_idx for p in a] == [p.template_idx for p in b]
            assert [p.relay_id for p in a] == [p.relay_id for p in b]
            assert a[0].root_id == b[0].root_id
            assert all(x.root_id == a[0].root_id for x in a)
            assert all(x.root_id != y.root_id for x, y in zip(b, b[1:]))  # distinct neighbours
            assert len({p.root_id for p in b}) == len(b)


def test_single_root_conditions_share_the_first_root(grid):
    for groups in _by_key(grid).values():
        c1 = groups["C1"].message_plan[0].root_id
        assert groups["C2"].message_plan[0].root_id == c1 == groups["C3"].message_plan[0].root_id


def test_rotation_covers_every_root_and_template_first_once_and_ignores_truth(syn_cfg, syn_scenarios):
    cfg4 = syn_cfg.model_copy(update={"design": syn_cfg.design.model_copy(update={"repetitions": 4})})
    grid4 = build_grid(cfg4, syn_scenarios)
    assert len(grid4) == 384
    for pair in {s.pair_id for s in syn_scenarios}:
        firsts_r, firsts_t = [], []
        for r in range(4):
            ro, to = rotation_orders(cfg4.seed, pair, r)
            assert sorted(ro) == [0, 1, 2, 3] and sorted(to) == [0, 1, 2, 3]
            firsts_r.append(ro[0])
            firsts_t.append(to[0])
        assert sorted(firsts_r) == [0, 1, 2, 3] and sorted(firsts_t) == [0, 1, 2, 3]
    cond = {c.id: c for c in cfg4.design.conditions}["C5"]
    for s in syn_scenarios:
        flipped = s.model_copy(update={"truth_status": "false" if s.truth_status == "true" else "true"})
        for r in range(4):
            assert message_plan(flipped, cond, r, True, cfg4.seed) == message_plan(s, cond, r, True, cfg4.seed)
    by_pair: dict[str, list] = {}
    for s in syn_scenarios:
        by_pair.setdefault(s.pair_id, []).append(s)
    for members in by_pair.values():
        for r in range(4):
            a, b = (message_plan(m, cond, r, True, cfg4.seed) for m in members)
            assert [p.template_idx for p in a] == [p.template_idx for p in b]
            idx = lambda sc, plan: [[x.root_id for x in sc.communication_roots].index(p.root_id) for p in plan]
            assert idx(members[0], a) == idx(members[1], b)


def test_main_stage_requires_frozen_scenarios(syn_cfg, syn_scenarios):
    main_cfg = syn_cfg.model_copy(update={"output": syn_cfg.output.model_copy(update={"stage": "main"})})
    with pytest.raises(ValueError, match="frozen"):
        build_grid(main_cfg, syn_scenarios)


def test_grid_refuses_visible_evidence(syn_cfg, syn_scenarios):
    bad = [s.model_copy(deep=True) for s in syn_scenarios]
    bad[0].evidence.visible_to_receiver = True
    with pytest.raises(ValueError, match="must not be visible"):
        build_grid(syn_cfg, bad)


def test_synthetic_identifiers_are_synthetic(syn_cfg, grid):
    assert syn_cfg.experiment_id.startswith("synthetic_")
    assert all(s.model_id.startswith("synthetic/") for s in grid)
    assert all(s.scenario_id.startswith("syn-") and s.pair_id.startswith("synpair") for s in grid)


def test_grid_matches_recorded_golden(grid):
    diff = compare_golden("grid", read_golden("grid"), grid_tsv(grid))
    assert diff is None, diff
