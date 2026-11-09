"""Exploratory pilot runner (hackathon weekend, Nov 2026).

Runs the receiver-v2 grid (configs/receiver_experiment.json) against real models
through OpenRouter, outside the staged live executor (which ends in a deliberate
FINAL REFUSAL). Results are EXPLORATORY PILOT data: n=10 draft scenarios,
AUTHOR_CHECKED_ONLY, temperature 0, not confirmatory.

Reuses the repo's grid builder, prompts and response parser unchanged, so the
episodes are exactly the ones listed in experiments/plans/receiver_pilot_grid.tsv.

Usage:
  .venv/bin/python scripts/pilot_live.py --mock                     # offline dry run, fake answers
  .venv/bin/python scripts/pilot_live.py --confirm-spend            # live, models from config
  .venv/bin/python scripts/pilot_live.py --confirm-spend --models openai/gpt-4o-mini,qwen/qwen-2.5-72b-instruct
  .venv/bin/python scripts/pilot_live.py --analyze-only experiments/results/pilot_<id>

Key contrasts (same scenario, model, prompt variant):
  C3 - C5 : 4 messages from 1 root vs 4 messages from 4 roots  (repetition vs corroboration)
  C2 - C4 : 2 messages from 1 root vs 2 messages from 2 roots
  C3 - C1 : 4 repeats of 1 root vs a single message           (does repetition alone raise confidence?)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import requests  # noqa: E402

from maps.experiments.receiver import _load_inputs, run_episode  # noqa: E402
from maps.llm_client import OpenRouterClient  # noqa: E402
from maps.schemas import LLMResult, ResponseParseError, parse_receiver_response  # noqa: E402

CONTRASTS = [("C3", "C5"), ("C2", "C4"), ("C3", "C1"), ("C5", "C1")]


# --------------------------------------------------------------------------- io
class LockedJsonl:
    def __init__(self, path: Path):
        self._f = path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, obj: dict) -> None:
        with self._lock:
            self._f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._f.flush()

    def close(self) -> None:
        self._f.close()


def load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Never prints values."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class PayloadSession(requests.Session):
    """Adds extra OpenRouter fields to every request body. Used to switch off provider-side
    "thinking": reasoning models (e.g. qwen3.x) otherwise spend the whole max_tokens budget on
    hidden reasoning and return content=None, which the repo client rejects."""

    def __init__(self, extra: dict):
        super().__init__()
        self.trust_env = False
        self._extra = extra

    def post(self, url, **kw):  # type: ignore[override]
        if isinstance(kw.get("json"), dict):
            kw["json"] = {**kw["json"], **self._extra}
        return super().post(url, **kw)


class MockClient:
    """Synthetic receivers with KNOWN behaviour, used to validate that the metrics separate them.
    kind="counter": counts messages (double-counts relays).
    kind="dedup":   counts distinct stated origins (the normatively correct use of the shown labels)."""

    name = "mock"

    def __init__(self, kind: str = "counter", noise: bool = True):
        self.kind = kind
        self.noise = noise

    def complete(self, request) -> LLMResult:
        user = request.messages[-1].content
        if self.kind == "dedup":
            n = len({ln.split("stated origin:", 1)[1].strip() for ln in user.splitlines() if "stated origin:" in ln})
        else:
            n = user.count("Message ")
        conf = min(95, 50 + 12 * n + random.randint(-5, 5))
        body = {
            "accepts_claim": n > 0,
            "confidence": conf if n else 50,
            "estimated_independent_roots": n,
            "evidence_used": [],
            "reasoning": "mock",
        }
        text = json.dumps(body)
        if random.random() < 0.2:  # exercise the lenient-parse path
            text = "```json\n" + text + "\n```"
        return LLMResult(content=text, response_model_id="mock")


# -------------------------------------------------------------------- analysis
def mean_ci(xs: list[float], n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    if not xs:
        return (float("nan"),) * 3
    m = statistics.fmean(xs)
    if len(xs) < 2:
        return m, float("nan"), float("nan")
    rng = random.Random(seed)
    boots = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) for _ in range(n_boot))
    return m, boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]


def sign_flip_p(xs: list[float], n_perm: int = 10000, seed: int = 0) -> float:
    """Two-sided paired sign-flip permutation p-value for mean != 0."""
    if not xs or all(x == 0 for x in xs):
        return 1.0
    rng = random.Random(seed)
    obs = abs(statistics.fmean(xs))
    hits = sum(abs(statistics.fmean([x if rng.random() < 0.5 else -x for x in xs])) >= obs - 1e-12 for _ in range(n_perm))
    return (hits + 1) / (n_perm + 1)


def lenient_parse(text: str | None) -> dict | None:
    """Fallback for answers the strict parser rejects only for formatting (code fences, prose
    around the JSON). Extracts the outermost {...} and validates against the same schema."""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return parse_receiver_response(text[start : end + 1]).model_dump(mode="json")
    except ResponseParseError:
        return None


def analyze(run_dir: Path, lenient: bool = True) -> dict:
    rows = [json.loads(l) for l in (run_dir / "episodes.jsonl").read_text().splitlines() if l.strip()]
    out: dict = {"n_episodes": len(rows), "status_counts": {}, "lenient_recovered": 0}
    for r in rows:
        out["status_counts"][r["status"]] = out["status_counts"].get(r["status"], 0) + 1
    out["n_ok_strict"] = out["status_counts"].get("ok", 0)
    if lenient and (run_dir / "calls.jsonl").exists():
        raw = {}
        for l in (run_dir / "calls.jsonl").read_text().splitlines():
            if l.strip():
                c = json.loads(l)
                raw[c["episode_id"]] = c.get("raw_content")
        for r in rows:
            if r["status"] == "parse_error":
                resp = lenient_parse(raw.get(r["spec"]["episode_id"]))
                if resp is not None:
                    r["status"], r["response"], r["lenient"] = "ok", resp, True
                    out["lenient_recovered"] += 1
    ok = [r for r in rows if r["status"] == "ok"]
    out["n_ok"] = len(ok)

    # condition means
    cells: dict = defaultdict(list)
    for r in ok:
        s = r["spec"]
        cells[(s["model_alias"], s["prompt_variant"], s["condition_id"])].append(r)
    cond_table = []
    for (model, variant, cond), rs in sorted(cells.items()):
        conf = [x["response"]["confidence"] for x in rs]
        roots = [x["response"]["estimated_independent_roots"] for x in rs]
        acc = [1.0 if x["response"]["accepts_claim"] else 0.0 for x in rs]
        n_roots = rs[0]["spec"]["n_roots"]
        n_msgs = rs[0]["spec"]["n_messages"]
        mc = mean_ci(conf)
        cond_table.append(
            {
                "model": model, "variant": variant, "condition": cond, "n_messages": n_msgs, "n_roots": n_roots,
                "n": len(rs), "confidence_mean": mc[0], "confidence_ci95": [mc[1], mc[2]],
                "confidence_sd": statistics.stdev(conf) if len(conf) > 1 else 0.0,
                "accept_rate": statistics.fmean(acc),
                "est_roots_mean": statistics.fmean(roots),
                "root_overcount_mean": statistics.fmean([e - n_roots for e in roots]),
                "accept_rate_true": _rate(rs, "true"), "accept_rate_false": _rate(rs, "false"),
            }
        )
    out["conditions"] = cond_table

    # paired contrasts by scenario
    by_key = {(r["spec"]["model_alias"], r["spec"]["prompt_variant"], r["spec"]["scenario_id"], r["spec"]["condition_id"]): r for r in ok}
    contrasts = []
    models = sorted({k[0] for k in by_key})
    variants = sorted({k[1] for k in by_key})
    scen = sorted({k[2] for k in by_key})
    for model in models:
        for variant in variants:
            for a, b in CONTRASTS:
                dconf, droots = [], []
                for s in scen:
                    ra, rb = by_key.get((model, variant, s, a)), by_key.get((model, variant, s, b))
                    if ra and rb:
                        dconf.append(ra["response"]["confidence"] - rb["response"]["confidence"])
                        droots.append(ra["response"]["estimated_independent_roots"] - rb["response"]["estimated_independent_roots"])
                m, lo, hi = mean_ci(dconf)
                contrasts.append(
                    {
                        "model": model, "variant": variant, "contrast": f"{a}-{b}", "n_pairs": len(dconf),
                        "confidence_diff_mean": m, "confidence_diff_ci95": [lo, hi],
                        "confidence_diff_signflip_p": sign_flip_p(dconf),
                        "est_roots_diff_mean": statistics.fmean(droots) if droots else float("nan"),
                    }
                )
    out["contrasts"] = contrasts
    return out


def _rate(rs: list[dict], truth: str) -> float | None:
    sub = [1.0 if x["response"]["accepts_claim"] else 0.0 for x in rs if x["spec"]["truth_status"] == truth]
    return statistics.fmean(sub) if sub else None


def write_report(run_dir: Path, summary: dict) -> None:
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    lines = [f"# Pilot summary ({run_dir.name})", "",
             f"Episodes: {summary['n_episodes']}; strict-parse ok: {summary['n_ok_strict']}; "
             f"recovered by lenient JSON extraction: {summary['lenient_recovered']}; analysed: {summary['n_ok']}; "
             f"raw status: {summary['status_counts']}", "",
             "## Condition means", "",
             "| model | variant | cond | msgs | roots | n | conf mean [95% CI] | sd | accept | accept (false claims) | est roots | overcount |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    fmt = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
    for c in summary["conditions"]:
        lo, hi = c["confidence_ci95"]
        lines.append(f"| {c['model']} | {c['variant']} | {c['condition']} | {c['n_messages']} | {c['n_roots']} | {c['n']} | "
                     f"{c['confidence_mean']:.1f} [{lo:.1f}, {hi:.1f}] | {c['confidence_sd']:.1f} | {c['accept_rate']:.2f} | "
                     f"{fmt(c['accept_rate_false'])} | {c['est_roots_mean']:.2f} | {c['root_overcount_mean']:+.2f} |")
    lines += ["", "## Paired contrasts (per scenario; bootstrap 95% CI; sign-flip p)", "",
              "| model | variant | contrast | pairs | Δconf [95% CI] | p | Δest roots |", "|---|---|---|---|---|---|---|"]
    for c in summary["contrasts"]:
        lo, hi = c["confidence_diff_ci95"]
        lines.append(f"| {c['model']} | {c['variant']} | {c['contrast']} | {c['n_pairs']} | {c['confidence_diff_mean']:+.1f} "
                     f"[{lo:+.1f}, {hi:+.1f}] | {c['confidence_diff_signflip_p']:.3f} | {c['est_roots_diff_mean']:+.2f} |")
    lines += ["", "Exploratory pilot: 10 draft AUTHOR_CHECKED_ONLY scenarios, temperature 0, one repetition. Not confirmatory."]
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    plot(run_dir, summary)


def plot(run_dir: Path, summary: dict) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib missing; skipping figure")
        return
    conds = ["C0", "C1", "C2", "C3", "C4", "C5"]
    labels = ["C0\n0 msg", "C1\n1 msg/1 src", "C2\n2 msg/1 src", "C3\n4 msg/1 src", "C4\n2 msg/2 src", "C5\n4 msg/4 src"]
    models = sorted({c["model"] for c in summary["conditions"]})
    variants = sorted({c["variant"] for c in summary["conditions"]})
    fig, axes = plt.subplots(2, len(models), figsize=(5.5 * len(models), 7), squeeze=False)
    for j, model in enumerate(models):
        for metric, ax, ylabel in (("confidence_mean", axes[0][j], "mean confidence (0-100)"),
                                   ("est_roots_mean", axes[1][j], "mean estimated independent sources")):
            w = 0.8 / max(1, len(variants))
            for k, variant in enumerate(variants):
                vals, errs = [], [[], []]
                for cid in conds:
                    c = next((x for x in summary["conditions"] if x["model"] == model and x["variant"] == variant and x["condition"] == cid), None)
                    v = c[metric] if c else float("nan")
                    vals.append(v)
                    if metric == "confidence_mean" and c:
                        errs[0].append(v - c["confidence_ci95"][0]); errs[1].append(c["confidence_ci95"][1] - v)
                    else:
                        errs[0].append(0); errs[1].append(0)
                xs = [i + (k - (len(variants) - 1) / 2) * w for i in range(len(conds))]
                ax.bar(xs, vals, w, yerr=errs if metric == "confidence_mean" else None, capsize=2, label=variant)
            if metric == "est_roots_mean":
                ax.plot(range(len(conds)), [0, 1, 1, 1, 2, 4], "k_", markersize=22, mew=2, label="true # sources")
            ax.set_xticks(range(len(conds)), labels, fontsize=7)
            ax.set_ylabel(ylabel, fontsize=8)
            ax.set_title(model, fontsize=9)
            ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(run_dir / "pilot_conditions.png", dpi=180)
    print(f"figure: {run_dir / 'pilot_conditions.png'}")


# ------------------------------------------------------------------------- main
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(REPO_ROOT / "configs/receiver_experiment.json"))
    p.add_argument("--mock", action="store_true")
    p.add_argument("--mock-kind", choices=["counter", "dedup"], default="counter", help="synthetic receiver behaviour")
    p.add_argument("--confirm-spend", action="store_true")
    p.add_argument("--models", default=None, help="comma-separated OpenRouter ids overriding the config models")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=None, help="run only the first N episodes (smoke test)")
    p.add_argument("--max-tokens", type=int, default=1200, help="overrides config max_tokens (800 truncated JSON)")
    p.add_argument("--keep-reasoning", action="store_true", help="do not send reasoning={enabled:false}")
    p.add_argument("--resume", default=None, help="existing run dir: re-run only episodes that are not ok")
    p.add_argument("--analyze-only", default=None)
    args = p.parse_args()

    if args.analyze_only:
        write_report(Path(args.analyze_only), analyze(Path(args.analyze_only)))
        return 0
    if not (args.mock or args.confirm_spend):
        print("pass --mock (offline) or --confirm-spend (live, spends OpenRouter credits)")
        return 2

    cfg, scenarios, specs = _load_inputs(args.config)
    cfg = cfg.model_copy(update={"sampling": cfg.sampling.model_copy(update={"max_tokens": args.max_tokens})})
    # Gemini rejects seeds outside int32 (http_400 "generation_config.seed TYPE_INT32").
    specs = [s.model_copy(update={"seed": s.seed % (2**31 - 1)}) for s in specs]
    if args.models:
        ids = [m.strip() for m in args.models.split(",") if m.strip()]
        old = sorted({s.model_id for s in specs})
        if len(ids) != len(old):
            print(f"--models must list {len(old)} ids (config has {old}); grid balance depends on it")
            return 2
        remap = dict(zip(old, ids))
        specs = [s.model_copy(update={"model_id": remap[s.model_id], "model_alias": remap[s.model_id].split("/")[-1]}) for s in specs]
    if args.limit:
        specs = specs[: args.limit]
    by_id = {s.scenario_id: s for s in scenarios}

    kept: list[dict] = []
    if args.resume:
        run_dir = Path(args.resume)
        prev = [json.loads(l) for l in (run_dir / "episodes.jsonl").read_text().splitlines() if l.strip()]
        kept = [r for r in prev if r["status"] == "ok"]
        done_ids = {r["spec"]["episode_id"] for r in kept}
        specs = [s for s in specs if s.episode_id not in done_ids]
        (run_dir / "episodes.jsonl").rename(run_dir / f"episodes.before_resume_{int(time.time())}.jsonl")
        print(f"resume: keeping {len(kept)} ok episodes, re-running {len(specs)}")
        meta = json.loads((run_dir / "run_meta.json").read_text())
        meta.setdefault("resumes", []).append({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rerun": len(specs)})
    else:
        run_id = time.strftime("pilot_%Y%m%dT%H%M%S") + (f"_mock_{args.mock_kind}" if args.mock else "")
        run_dir = REPO_ROOT / "experiments/results" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        meta = {"run_id": run_id, "mode": f"mock_{args.mock_kind}" if args.mock else "live", "config": args.config,
                "label": "EXPLORATORY PILOT - draft AUTHOR_CHECKED_ONLY scenarios - not confirmatory"}
    meta.update({"models": sorted({s.model_id for s in specs}) or meta.get("models"), "n_episodes_total": len(specs) + len(kept),
                 "temperature": cfg.sampling.temperature, "max_tokens": cfg.sampling.max_tokens,
                 "reasoning_disabled": not args.keep_reasoning, "seed_rule": "grid seed mod (2^31-1)",
                 "started_utc": meta.get("started_utc") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))

    if args.mock:
        random.seed(cfg.seed)
        client = MockClient(args.mock_kind)
    else:
        load_dotenv(REPO_ROOT / ".env")
        key = os.environ.get(cfg.api.api_key_env)
        if not key:
            print(f"{cfg.api.api_key_env} not set (env or .env)")
            return 2
        extra = {} if args.keep_reasoning else {"reasoning": {"enabled": False}}
        client = OpenRouterClient(key, base_url=cfg.api.base_url, timeout_s=cfg.api.timeout_s,
                                  max_retries=cfg.api.max_retries, backoff_s=cfg.api.backoff_s, enabled=True,
                                  session=PayloadSession(extra))

    calls = LockedJsonl(run_dir / "calls.jsonl")
    eps = LockedJsonl(run_dir / "episodes.jsonl")
    for r in kept:
        eps.write(r)
    done, credit_errors, aborted = 0, 0, False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_episode, s, by_id[s.scenario_id], client, cfg, calls): s for s in specs}
        for f in as_completed(futs):
            try:
                res = f.result()
                eps.write(res.model_dump(mode="json"))
                if res.status == "call_error" and (res.error or "").startswith("http_402"):
                    credit_errors += 1
            except Exception as exc:  # keep going; record failure
                s = futs[f]
                eps.write({"spec": s.model_dump(mode="json"), "status": "exception", "error": repr(exc)})
            done += 1
            if done % 20 == 0 or done == len(specs):
                print(f"{done}/{len(specs)}", flush=True)
            if credit_errors >= 5 and not aborted:
                aborted = True
                print("ABORT: repeated http_402 (OpenRouter credits). Top up, then rerun with "
                      f"--resume {run_dir}", flush=True)
                for other in futs:
                    other.cancel()
    if aborted:
        cancelled = [s for fut, s in futs.items() if fut.cancelled()]
        for s in cancelled:
            eps.write({"spec": s.model_dump(mode="json"), "status": "call_error", "error": "not_run: aborted on credits"})
    calls.close(); eps.close()
    write_report(run_dir, analyze(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
