"""Figure 1 for the hackathon report: estimated independent sources and confidence by condition for
(a) a synthetic double-counting receiver, (b) a synthetic deduplicating receiver, and (c) the 20
message-bearing real-model episodes that completed in the credit-limited partial pilot (pooled
over models and prompt variants; descriptive only).

Usage: .venv/bin/python scripts/make_paper_figure.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SYN = {"Synthetic double-counter": ROOT / "experiments/validation/synthetic_counter",
       "Synthetic deduplicator": ROOT / "experiments/validation/synthetic_dedup"}
PARTIAL = ROOT / "experiments/results/pilot_20261109T155007"
CONDS = ["C1", "C2", "C3", "C4", "C5"]
LABELS = ["C1\n1 msg\n1 src", "C2\n2 msg\n1 src", "C3\n4 msg\n1 src", "C4\n2 msg\n2 src", "C5\n4 msg\n4 src"]
TRUE_ROOTS = [1, 1, 1, 2, 4]


def load_ok(run_dir: Path) -> list[dict]:
    rows = [json.loads(l) for l in (run_dir / "episodes.jsonl").read_text().splitlines() if l.strip()]
    return [r for r in rows if r["status"] == "ok"]


def by_cond(rows: list[dict], key: str) -> tuple[list[float], list[int]]:
    acc = defaultdict(list)
    for r in rows:
        acc[r["spec"]["condition_id"]].append(r["response"][key])
    return [sum(acc[c]) / len(acc[c]) if acc[c] else float("nan") for c in CONDS], [len(acc[c]) for c in CONDS]


def main() -> None:
    series = {name: load_ok(d) for name, d in SYN.items()}
    series["Real models, partial pilot (n per bar shown)"] = load_ok(PARTIAL)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    w = 0.26
    for k, (name, rows) in enumerate(series.items()):
        xs = [i + (k - 1) * w for i in range(len(CONDS))]
        roots, ns = by_cond(rows, "estimated_independent_roots")
        conf, _ = by_cond(rows, "confidence")
        axes[0].bar(xs, roots, w, label=name)
        axes[1].bar(xs, conf, w, label=name)
        if k == 2:
            for x, v, n in zip(xs, conf, ns):
                if n:
                    axes[1].text(x, (v if v == v else 0) + 1, f"n={n}", ha="center", fontsize=6)
    axes[0].plot(range(len(CONDS)), TRUE_ROOTS, "k_", markersize=26, mew=2, label="true # sources")
    axes[0].set_ylabel("mean estimated independent sources")
    axes[1].set_ylabel("mean confidence (0-100)")
    axes[1].set_ylim(0, 105)
    for ax in axes:
        ax.set_xticks(range(len(CONDS)), LABELS, fontsize=7)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, fontsize=7, frameon=False)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    out = ROOT / "experiments/validation/figure1.png"
    fig.savefig(out, dpi=200)
    print(out)


if __name__ == "__main__":
    main()
