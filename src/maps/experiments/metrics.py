"""Pure metric functions for the receiver experiment (no I/O).

Scope: belief formation under repeated and apparently independent testimony.
Evidence is withheld from the receiver, so truth-conditioned rates are
label-based (acceptance split by truth label), not evidence-verification rates.

Definitions (only episodes with status "ok" enter any statistic):
  false-claim acceptance rate  = P(accepts_claim) among truth == "false"
  correct-claim rejection rate = P(not accepts_claim) among truth == "true"
  confidence diff vs control   = confidence - confidence of the matched C0 episode
                                 (same model, scenario, prompt variant, repetition)
  corroboration inflation      = max(0, est. roots - actual roots); None (N/A) for C0
  root-count error (signed)    = est. roots - actual roots; None (N/A) for C0
  confidence change per dup.   = (conf_Cn - conf_C1) / (n_messages - 1) for the
                                 single-root repeat conditions C2, C3; else None
  repetition-vs-independence   = paired differences (independent minus repeated) at equal
  gaps                           message count: C4-C2 and C5-C3. The C0 control cancels, so
                                 the confidence-diff gap equals the raw confidence gap.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from maps.schemas import EpisodeResult

CONTROL = "C0"
SINGLE_ROOT_REPEATS = {"C2": "C1", "C3": "C1"}  # condition -> baseline condition
CONTRASTS = (("C4", "C2"), ("C5", "C3"))  # (independent, repeated)

MatchKey = tuple[str, str, str, int]
Lookup = dict[tuple[MatchKey, str], EpisodeResult]


def match_key(r: EpisodeResult) -> MatchKey:
    s = r.spec
    return (s.model_alias, s.scenario_id, s.prompt_variant, s.repetition)


def corroboration_inflation(estimated_roots: int, n_roots: int) -> int | None:
    if n_roots == 0:
        return None
    return max(0, estimated_roots - n_roots)


def root_count_error(estimated_roots: int, n_roots: int) -> int | None:
    if n_roots == 0:
        return None
    return estimated_roots - n_roots


def build_lookup(results: list[EpisodeResult]) -> Lookup:
    return {(match_key(r), r.spec.condition_id): r for r in results if r.status == "ok"}


def _conf(r: EpisodeResult | None) -> int | None:
    return None if r is None or r.response is None else r.response.confidence


def confidence_diff_vs_control(r: EpisodeResult, lookup: Lookup) -> int | None:
    if r.status != "ok" or r.response is None or r.spec.condition_id == CONTROL:
        return None
    control = _conf(lookup.get((match_key(r), CONTROL)))
    return None if control is None else r.response.confidence - control


def confidence_change_per_duplicate(r: EpisodeResult, lookup: Lookup) -> float | None:
    base_id = SINGLE_ROOT_REPEATS.get(r.spec.condition_id)
    if base_id is None or r.status != "ok" or r.response is None:
        return None
    base = _conf(lookup.get((match_key(r), base_id)))
    if base is None:
        return None
    return (r.response.confidence - base) / (r.spec.n_messages - 1)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def summarize(results: list[EpisodeResult]) -> list[dict[str, Any]]:
    """One row per (model, prompt variant, condition, truth label)."""
    lookup = build_lookup(results)
    groups: dict[tuple[str, str, str, str], list[EpisodeResult]] = defaultdict(list)
    for r in results:
        s = r.spec
        groups[(s.model_alias, s.prompt_variant, s.condition_id, s.truth_status)].append(r)

    rows: list[dict[str, Any]] = []
    for (model, variant, cond, truth), rs in sorted(groups.items()):
        ok = [r for r in rs if r.status == "ok" and r.response is not None]
        accept = _mean([float(r.response.accepts_claim) for r in ok])
        diffs = [d for r in ok if (d := confidence_diff_vs_control(r, lookup)) is not None]
        infl = [i for r in ok if (i := corroboration_inflation(r.response.estimated_independent_roots, r.spec.n_roots)) is not None]
        err = [e for r in ok if (e := root_count_error(r.response.estimated_independent_roots, r.spec.n_roots)) is not None]
        per_dup = [p for r in ok if (p := confidence_change_per_duplicate(r, lookup)) is not None]
        rows.append(
            {
                "model_alias": model,
                "prompt_variant": variant,
                "condition_id": cond,
                "n_messages": rs[0].spec.n_messages,
                "n_roots": rs[0].spec.n_roots,
                "truth_status": truth,
                "n_episodes": len(rs),
                "n_valid": len(ok),
                "n_invalid": len(rs) - len(ok),
                "false_claim_acceptance_rate": accept if truth == "false" else None,
                "correct_claim_rejection_rate": (1 - accept) if truth == "true" and accept is not None else None,
                "mean_confidence": _mean([float(r.response.confidence) for r in ok]),
                "mean_confidence_diff_vs_control": _mean(diffs),
                "n_matched_to_control": len(diffs),
                "mean_estimated_independent_roots": _mean(
                    [float(r.response.estimated_independent_roots) for r in ok]
                ),
                "mean_corroboration_inflation": _mean(infl),  # None for C0 (N/A)
                "mean_root_count_error": _mean(err),  # signed; None for C0 (N/A)
                "mean_confidence_change_per_duplicate": _mean(per_dup),
            }
        )
    return rows


def contrast_gaps(results: list[EpisodeResult]) -> list[dict[str, Any]]:
    """Independent-minus-repeated gaps at equal message count, one row per
    (model, prompt variant, truth label, contrast). Unmatched pairs are counted, not imputed."""
    lookup = build_lookup(results)
    scen_truth = {r.spec.scenario_id: r.spec.truth_status for r in results}
    groups: dict[tuple[str, str, str, str], dict[str, list[float]]] = defaultdict(
        lambda: {"conf": [], "accept": [], "roots": []}
    )
    unmatched: dict[tuple[str, str, str, str], int] = defaultdict(int)
    keys = {k for (k, _c) in lookup}
    for ind, rep in CONTRASTS:
        for key in sorted(keys):
            model, scen, variant, _rep = key
            gkey = (model, variant, scen_truth[scen], f"{ind}-{rep}")
            a, b = lookup.get((key, ind)), lookup.get((key, rep))
            if a is None or b is None:
                if a is not None or b is not None:
                    unmatched[gkey] += 1
                continue
            groups[gkey]["conf"].append(a.response.confidence - b.response.confidence)
            groups[gkey]["accept"].append(float(a.response.accepts_claim) - float(b.response.accepts_claim))
            groups[gkey]["roots"].append(
                float(a.response.estimated_independent_roots - b.response.estimated_independent_roots)
            )
    rows = []
    for gkey in sorted(set(groups) | set(unmatched)):
        g = groups.get(gkey, {"conf": [], "accept": [], "roots": []})
        model, variant, truth, contrast = gkey
        rows.append(
            {
                "model_alias": model,
                "prompt_variant": variant,
                "truth_status": truth,
                "contrast": contrast,
                "n_pairs": len(g["conf"]),
                "n_unmatched": unmatched.get(gkey, 0),
                "mean_confidence_gap": _mean(g["conf"]),
                "mean_acceptance_gap": _mean(g["accept"]),
                "mean_estimated_roots_gap": _mean(g["roots"]),
            }
        )
    return rows
