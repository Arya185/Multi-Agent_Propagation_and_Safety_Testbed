"""Receiver experiment: grid construction, runner, CLI.

Scope: belief formation under repeated and apparently independent testimony.
Evidence documents are withheld from the receiver.

Default CLI behaviour prints the plan and makes NO calls. Calls need either
--mock (synthetic, offline) or --live together with --confirm-spend and
api.enabled=true in the config. --mock and --live are mutually exclusive.

CLI exit codes: 0 done / plan printed; 1 a mock run was started but failed its integrity lifecycle (its
partial output is preserved and it is not eligible for analysis); 2 refused or invalid input
(contradictory flags, invalid run id, unreadable or invalid configuration or scenarios, a design
check such as "main stage needs frozen scenarios" or a failed cohort registry check (Stage 4J.3: a main-stage run
needs --registry and fails closed on any problem; nothing is assigned or written), --mock with a configuration that enables live API
calls, --live (temporarily unavailable until Stage 4E), or an unsafe run directory). Unexpected programming errors are not
caught. Every mock run claims its output directory with maps.runs.guard before the runner starts, so an
existing non-empty run directory is refused, never reused, resumed or appended to.

Run ids come from maps.runs.ids for both modes (generated: UTC microseconds plus a random suffix; an
explicit --run-id is validated by the same rule).

The mock path runs through maps.runs.executor.execute_mock_run (claim, pre-run provenance, the runner
exactly once, post-run provenance and drift check, loader validation, integrity report). The live path runs a PREFLIGHT and then
stops at a FINAL REFUSAL (Stage 4E, owner decision 4E-ACTIVATION: KEEP FINAL REFUSAL): --live needs --policy, --profile
and --expected-policy-digest; the policy is loaded and bound to the configuration and the planned grid, the digest is
compared with the independently supplied one, and the configured endpoint is validated; then the CLI refuses with exit 2
before any credential, client, run directory or network use. ``run_live_after_preflight`` (the executor call and the exit-code
mapping) is NOT reachable from ``main``; only tests call it, with a fake client factory.

Live exit codes (``live_exit_code``): 0 complete and eligible, 1 lifecycle failure, 2 refused or invalid input (including a
policy or endpoint refusal), 3 policy stop, 4 report unwritable, 5 finished but not analysis-eligible, 130 interrupted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import sys
from pathlib import Path

from pydantic import ValidationError

from maps.config import ConditionSpec, ExperimentConfig, config_hash, load_config
from maps.experiments.metrics import contrast_gaps, summarize
from maps.llm_client import LLMClient
from maps.logging_utils import JsonlWriter, redact_obj, utc_now_iso
from maps.mock_client import MockClient
from maps.prompts.receiver import PROMPT_VERSION, build_messages
from maps.registry import CohortGateError, load_registry, require_confirmatory_run, require_pilot_registry
from maps.runs.endpoint_policy import EndpointPolicyError, validate_base_url
from maps.runs.executor import execute_mock_run
from maps.runs.ids import InvalidRunIdError, generate_run_id, validate_run_id
from maps.runs.live_executor import execute_live_run
from maps.runs.policy_source import LoadedPolicy, PolicySourceError, compute_content_digests, load_policy
from maps.scenarios import REPO_ROOT, evidence_path, file_sha256, load_scenario_dir
from maps.schemas import (
    CallRecord,
    ChatRequest,
    EpisodeResult,
    EpisodeSpec,
    PlanItem,
    ResponseParseError,
    Scenario,
    parse_receiver_response,
)

# Seeded, truth-independent rotation. For each pair (not scenario), a random base permutation of
# the four roots and an independent one of the four templates are drawn from (seed, pair_id).
# Repetition r uses the base cyclically shifted by r, so over four repetitions every root and
# every template is first exactly once. Both members of a pair share the same orders (matched),
# and nothing here reads the truth label. The pilot (r=0) uses the random base permutation itself.
PLAN_COLUMNS = (
    "idx", "episode_id", "model_alias", "model_id", "scenario_id", "truth_status",
    "condition_id", "n_messages", "n_roots", "prompt_variant", "repetition", "seed",
    "template_order", "root_ids",
)


def _digest(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _base_permutation(seed: int, kind: str, pair_id: str) -> list[int]:
    rng = random.Random(int(_digest(seed, kind, pair_id)[:16], 16))
    perm = [0, 1, 2, 3]
    rng.shuffle(perm)
    return perm


def rotation_orders(
    seed: int, pair_id: str, repetition: int, rotate: bool = True
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(root_order, template_order) for a pair and repetition. Truth-independent."""
    if not rotate:
        return (0, 1, 2, 3), (0, 1, 2, 3)
    r = repetition % 4
    rb, tb = _base_permutation(seed, "root", pair_id), _base_permutation(seed, "template", pair_id)
    return tuple(rb[(r + k) % 4] for k in range(4)), tuple(tb[(r + k) % 4] for k in range(4))


def message_plan(
    scenario: Scenario, condition: ConditionSpec, repetition: int, rotate: bool = True, seed: int = 0
) -> list[PlanItem]:
    """Controlled rotation. Message k always uses template order[k]; relay ids are
    distinct per message in every condition; only the root assignment depends on
    n_roots (1 repeated root vs one distinct root per message)."""
    root_order, template_order = rotation_orders(seed, scenario.pair_id, repetition, rotate)
    plan = []
    for k in range(condition.n_messages):
        root_idx = root_order[0] if condition.n_roots == 1 else root_order[k]
        plan.append(
            PlanItem(
                position=k,
                relay_id=f"Relay-{k + 1}",
                template_idx=template_order[k],
                root_id=scenario.communication_roots[root_idx].root_id,
            )
        )
    return plan


class DesignRefusal(ValueError):
    """An intentional refusal to build a grid (still a ValueError, so existing callers are unaffected)."""


def build_grid(cfg: ExperimentConfig, scenarios: list[Scenario]) -> list[EpisodeSpec]:
    """Full factorial grid; deterministic ids, seeds and (seeded) order."""
    for s in scenarios:
        if s.evidence.visible_to_receiver:
            raise DesignRefusal(f"{s.scenario_id}: evidence must not be visible to the receiver")
    if cfg.output.stage == "main":
        bad = [s.scenario_id for s in scenarios if s.status != "frozen"]
        if bad:
            raise DesignRefusal(f"main stage requires frozen scenarios; not frozen: {bad}")
    specs: list[EpisodeSpec] = []
    for model in cfg.models:
        for sc in sorted(scenarios, key=lambda s: s.scenario_id):
            for variant in cfg.design.prompt_variants:
                for cond in cfg.design.conditions:
                    for rep in range(cfg.design.repetitions):
                        key = (cfg.experiment_id, model.model_id, sc.scenario_id, variant, cond.id, rep)
                        eid = "ep_" + _digest(*key)[:12]
                        specs.append(
                            EpisodeSpec(
                                episode_id=eid,
                                model_alias=model.alias,
                                model_id=model.model_id,
                                scenario_id=sc.scenario_id,
                                pair_id=sc.pair_id,
                                truth_status=sc.truth_status,
                                condition_id=cond.id,
                                n_messages=cond.n_messages,
                                n_roots=cond.n_roots,
                                prompt_variant=variant,
                                repetition=rep,
                                seed=int(_digest(cfg.seed, eid)[:8], 16),
                                message_plan=message_plan(sc, cond, rep, cfg.design.rotate_templates_and_roots, cfg.seed),
                            )
                        )
    random.Random(cfg.seed).shuffle(specs)
    return specs


def balance_report(specs: list[EpisodeSpec], scenarios: list[Scenario]) -> dict:
    """Realized balance of root/template assignment, split by truth label.

    'single_root_index' is the pool index (R1..R4 -> 1..4) of the repeated root in C1-C3;
    'first_template_index' is the template used by message 1 (every message-bearing condition).
    Counted once per (scenario, repetition) so conditions and models do not inflate counts.
    """
    by_id = {s.scenario_id: s for s in scenarios}
    root_pos = {r.root_id: i + 1 for s in scenarios for i, r in enumerate(s.communication_roots)}
    seen: set[tuple[str, int]] = set()
    single = {"true": {}, "false": {}}
    first_t = {"true": {}, "false": {}}
    per_scenario = {}
    for sp in specs:
        key = (sp.scenario_id, sp.repetition)
        if sp.n_messages == 0 or key in seen:
            continue
        seen.add(key)
        first = sp.message_plan[0]
        ridx, tidx = root_pos[first.root_id], first.template_idx + 1
        single[sp.truth_status][ridx] = single[sp.truth_status].get(ridx, 0) + 1
        first_t[sp.truth_status][tidx] = first_t[sp.truth_status].get(tidx, 0) + 1
        per_scenario.setdefault(sp.scenario_id, []).append({"repetition": sp.repetition, "single_root": ridx, "first_template": tidx})
    return {
        "units": "(scenario, repetition) pairs",
        "single_root_index_by_truth": {k: dict(sorted(v.items())) for k, v in single.items()},
        "first_template_index_by_truth": {k: dict(sorted(v.items())) for k, v in first_t.items()},
        "per_scenario": per_scenario,
        "scenario_truth": {s.scenario_id: s.truth_status for s in sorted(by_id.values(), key=lambda x: x.scenario_id)},
    }


def grid_rows(specs: list[EpisodeSpec]) -> list[list[str]]:
    return [
        [
            str(i), s.episode_id, s.model_alias, s.model_id, s.scenario_id, s.truth_status,
            s.condition_id, str(s.n_messages), str(s.n_roots), s.prompt_variant, str(s.repetition),
            str(s.seed), ",".join(str(p.template_idx) for p in s.message_plan),
            ",".join(p.root_id for p in s.message_plan),
        ]
        for i, s in enumerate(specs)
    ]


def grid_tsv(specs: list[EpisodeSpec]) -> str:
    lines = ["\t".join(PLAN_COLUMNS)] + ["\t".join(r) for r in grid_rows(specs)]
    return "\n".join(lines) + "\n"


def run_episode(
    spec: EpisodeSpec,
    scenario: Scenario,
    client: LLMClient,
    cfg: ExperimentConfig,
    call_writer: JsonlWriter | None = None,
) -> EpisodeResult:
    messages = build_messages(scenario, spec.message_plan, spec.prompt_variant)
    request = ChatRequest(
        model=spec.model_id,
        messages=messages,
        temperature=cfg.sampling.temperature,
        max_tokens=cfg.sampling.max_tokens,
        seed=spec.seed,
    )
    result = client.complete(request)
    if call_writer is not None:
        record = CallRecord(
            episode_id=spec.episode_id,
            timestamp_utc=utc_now_iso(),
            client=client.name,
            requested_model_id=spec.model_id,
            response_model_id=result.response_model_id,
            prompt_version=PROMPT_VERSION,
            prompt_variant=spec.prompt_variant,
            condition_id=spec.condition_id,
            params={
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "seed": request.seed,
            },
            messages=messages,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            latency_s=result.latency_s,
            attempts=result.attempts,
            error=result.error,
            raw_content=result.content,
        )
        call_writer.write(record.model_dump(mode="json"))

    if result.error is not None or result.content is None:
        return EpisodeResult(spec=spec, status="call_error", error=result.error or "empty response")
    try:
        response = parse_receiver_response(result.content)
    except ResponseParseError as exc:
        return EpisodeResult(spec=spec, status="parse_error", error=str(exc))
    return EpisodeResult(spec=spec, status="ok", response=response)


def run_experiment(
    cfg: ExperimentConfig,
    scenarios: list[Scenario],
    client: LLMClient,
    out_dir: str | Path,
    secrets: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[EpisodeResult]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    secrets = secrets or []
    by_id = {s.scenario_id: s for s in scenarios}
    specs = build_grid(cfg, scenarios)

    manifest = {
        "experiment_id": cfg.experiment_id,
        "stage": cfg.output.stage,
        "client": client.name,
        "synthetic_mock_data": client.name == "mock",
        "started_utc": utc_now_iso(),
        "scope": "belief formation under repeated and apparently independent testimony; evidence withheld from receiver",
        "prompt_version": PROMPT_VERSION,
        "evidence_visible_to_receiver": False,
        "scenarios": {
            s.scenario_id: {
                "status": s.status,
                "evidence_verification": s.evidence.verification_status,
                "evidence_sha256_actual": file_sha256(evidence_path(s, repo_root)),
            }
            for s in scenarios
        },
        "model_ids": [m.model_id for m in cfg.models],
        "config_hash": config_hash(cfg),
        "config": cfg.model_dump(mode="json"),
        "n_episodes": len(specs),
        "python": platform.python_version(),
    }
    (out / "manifest.json").write_text(
        json.dumps(redact_obj(manifest, secrets), indent=2), encoding="utf-8"
    )

    call_writer = JsonlWriter(out / "calls.jsonl", secrets)
    episode_writer = JsonlWriter(out / "episodes.jsonl", secrets)
    results: list[EpisodeResult] = []
    for spec in specs:
        res = run_episode(spec, by_id[spec.scenario_id], client, cfg, call_writer)
        episode_writer.write(res.model_dump(mode="json"))
        results.append(res)
    (out / "summary.json").write_text(json.dumps(summarize(results), indent=2), encoding="utf-8")
    (out / "contrast_gaps.json").write_text(json.dumps(contrast_gaps(results), indent=2), encoding="utf-8")
    return results




class CliInputError(Exception):
    """An expected user-input, configuration or design failure; reported as a clean error (exit code 2)."""


def _describe_validation(exc: ValidationError) -> str:
    """Field locations and error types only; input values are never printed."""
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    shown = [f"{'.'.join(str(part) for part in e['loc']) or '<config>'}: {e['type']}" for e in errors[:5]]
    extra = len(errors) - len(shown)
    return "; ".join(shown) + (f" (+{extra} more)" if extra > 0 else "")


def _load_inputs(config_path: str) -> tuple[ExperimentConfig, list[Scenario], list[EpisodeSpec]]:
    """Load the configuration, scenarios and grid. Expected failures become CliInputError (the original
    exception stays attached as __cause__); anything else, such as a programming error, propagates."""
    try:
        cfg = load_config(config_path)
    except FileNotFoundError as exc:
        raise CliInputError(f"configuration file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise CliInputError(
            f"configuration file is not valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno}): {config_path}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise CliInputError(f"configuration file is not valid UTF-8 text: {config_path}") from exc
    except ValidationError as exc:
        raise CliInputError(f"configuration is invalid: {_describe_validation(exc)}") from exc
    except OSError as exc:
        raise CliInputError(f"configuration file could not be read ({type(exc).__name__}): {config_path}") from exc
    try:
        scenarios = load_scenario_dir(REPO_ROOT / cfg.design.scenario_dir)
    except (OSError, ValueError) as exc:
        raise CliInputError(
            f"scenario files could not be loaded or failed validation ({type(exc).__name__}; "
            "details withheld to avoid printing scenario content)"
        ) from exc
    try:
        specs = build_grid(cfg, scenarios)
    except DesignRefusal as exc:
        raise CliInputError(f"refused by a design check: {exc}") from exc
    return cfg, scenarios, specs


def _check_cohort_registry(cfg: ExperimentConfig, scenarios: list[Scenario], registry_path: str | None) -> None:
    """Fail-closed cohort checks (Stage 4J.3). Required for the main stage, validation only for any other stage.
    Nothing is assigned, frozen or written; pilot exposure is recorded by hand. Details are withheld from the message
    because they can contain scenario values."""
    main_stage = cfg.output.stage == "main"
    if registry_path is None:
        if main_stage:
            raise CliInputError("main stage requires --registry PATH (a cohort registry)")
        return
    try:
        registry = load_registry(registry_path)
    except (OSError, ValueError) as exc:
        raise CliInputError(
            f"cohort registry could not be loaded or failed validation ({type(exc).__name__}; "
            "details withheld to avoid printing scenario content)"
        ) from exc
    try:
        (require_confirmatory_run if main_stage else require_pilot_registry)(registry, scenarios)
    except CohortGateError as exc:
        raise CliInputError(
            f"refused by the cohort registry check: {len(exc.problems)} problem(s); "
            "details withheld to avoid printing scenario content"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=str(REPO_ROOT / "configs/receiver_experiment.json"))
    p.add_argument("--mock", action="store_true", help="offline synthetic run (not research data)")
    p.add_argument("--live", action="store_true", help="real API calls (spends credits); excludes --mock")
    p.add_argument("--confirm-spend", action="store_true", help="required with --live")
    p.add_argument("--export-grid", default=None, help="write the episode grid TSV to this path and exit")
    p.add_argument("--export-balance", default=None, help="write the root/template balance JSON and exit")
    p.add_argument("--run-id", default=None, help="1-128 characters from A-Z a-z 0-9 . _ - (not '.' or '..'); default: generated")
    p.add_argument("--policy", default=None, help="live only: path to the live policy file")
    p.add_argument("--profile", default=None, help="live only: name of the policy profile (there is no default profile)")
    p.add_argument(
        "--expected-policy-digest", default=None,
        help="live only: SHA-256 of the policy content, supplied independently of the policy file",
    )
    p.add_argument("--registry", default=None, help="path to a cohort registry; REQUIRED when output.stage is main, otherwise only validated")
    args = p.parse_args(argv)

    # Argument checks come first: nothing is loaded, built or created for a contradictory or malformed request.
    if args.mock and args.live:
        print(
            "error: --mock and --live are mutually exclusive; choose one (omit both for a plan-only listing).",
            file=sys.stderr,
        )
        return 2
    live_only = (args.policy, args.profile, args.expected_policy_digest)
    if not args.live and any(value is not None for value in live_only):
        print("error: --policy, --profile and --expected-policy-digest are only valid with --live.", file=sys.stderr)
        return 2
    if args.run_id is not None:
        try:
            validate_run_id(args.run_id)
        except InvalidRunIdError:   # the value is never echoed
            print("error: --run-id must be 1-128 characters from A-Z a-z 0-9 . _ - and must not be '.' or '..'", file=sys.stderr)
            return 2

    try:
        cfg, scenarios, specs = _load_inputs(args.config)
        _check_cohort_registry(cfg, scenarios, args.registry)
    except CliInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"episodes: {len(specs)}  models: {[m.model_id for m in cfg.models]}")
    print(f"scenario statuses: {sorted({s.status for s in scenarios})}")

    if args.export_grid:
        Path(args.export_grid).write_text(grid_tsv(specs), encoding="utf-8")
        print(f"grid written: {args.export_grid}")
        return 0
    if args.export_balance:
        Path(args.export_balance).write_text(
            json.dumps(balance_report(specs, scenarios), indent=2), encoding="utf-8")
        print(f"balance written: {args.export_balance}")
        return 0
    if not (args.mock or args.live):
        print("PLAN ONLY: pass --mock (offline) or --live --confirm-spend. No calls made.")
        return 0

    run_id = args.run_id or generate_run_id()
    base = REPO_ROOT / cfg.output.results_dir

    if args.mock:
        out = base / "mock" / run_id
        print("MOCK RUN: synthetic responses, NOT research data.")
        # The executor claims the directory, records provenance before and after, calls the runner exactly
        # once, validates the written results and writes the integrity report. Nothing is retried, resumed,
        # appended to, overwritten or redirected, and partial output is preserved.
        outcome = execute_mock_run(
            run_fn=run_experiment, cfg=cfg, scenarios=scenarios, client=MockClient(), run_dir=out, run_id=run_id,
            repo_root=REPO_ROOT,
        )
        if outcome.status == "refused":
            print(f"refused: {outcome.detail}", file=sys.stderr)
            return 2
        if not outcome.analysis_eligible:
            print(
                f"failed: the mock run did not pass its integrity lifecycle (stage: {outcome.failed_stage or 'report'}); "
                f"partial output is preserved and the run is not eligible for analysis. output: {out}",
                file=sys.stderr,
            )
            return 1
        results = outcome.results
        ok = sum(r.status == "ok" for r in results)
        print(f"done: {ok}/{len(results)} valid. output: {out}")
        print(f"integrity report: {outcome.report_path}")
        return 0
    # Live path: PREFLIGHT, then the FINAL REFUSAL (Stage 4E). Everything before the refusal reads only the policy file, the
    # scenario and evidence files (as hashes) and the configured URL string: no .env, no key lookup, no client, no run
    # directory or claim, no network. Any failure here is a refusal with exit 2 and a fixed message that never echoes a value.
    if any(value is None for value in live_only):
        print("error: --live requires --policy, --profile and --expected-policy-digest.", file=sys.stderr)
        return REFUSED
    try:
        content = compute_content_digests(REPO_ROOT / cfg.design.scenario_dir, REPO_ROOT)
        load_policy(
            args.policy, cfg=cfg, specs=specs, content_digests=content, profile=args.profile,
            expected_digest=args.expected_policy_digest,
        )
        validate_base_url(cfg.api.base_url)
    except (PolicySourceError, EndpointPolicyError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return REFUSED
    print(FINAL_REFUSAL_TEXT, file=sys.stderr)
    return REFUSED


# ---------------------------------------------------------------------------------------------------------------------
# Live exit codes and the downstream (post-preflight) flow. NOT reachable from ``main`` while the final refusal stands.
# ---------------------------------------------------------------------------------------------------------------------
OK, LIFECYCLE_FAILED, REFUSED, POLICY_STOP, REPORT_UNWRITABLE, NOT_ELIGIBLE, INTERRUPTED = 0, 1, 2, 3, 4, 5, 130
FINAL_REFUSAL_TEXT = (
    "refused: live execution is not authorized in this version (FINAL REFUSAL after a passed preflight). The policy digest "
    "comparison confirms content equality only; it is not authenticated owner approval. No credentials were read, no client "
    "was built, no run directory was created and no calls were made."
)


def live_exit_code(outcome) -> int:
    """Map an ``ExecutionOutcome`` to the approved live exit code."""
    if outcome.status == "refused":
        return REFUSED
    if outcome.report_path is None:
        return REPORT_UNWRITABLE
    if outcome.failed_stage == "policy_stop":
        return POLICY_STOP
    if outcome.failed_stage == "interrupted":
        return INTERRUPTED
    if outcome.status == "failed":
        return LIFECYCLE_FAILED
    return OK if outcome.analysis_eligible else NOT_ELIGIBLE


def build_policy_record(loaded: LoadedPolicy, endpoint) -> dict:
    """The secret-free policy and endpoint record stored in the live report (PS-15 option A)."""
    return {
        **loaded.record(),
        "endpoint": endpoint.record(),
        "owner_authentication": "none: a digest comparison confirms content equality only",
    }


def run_live_after_preflight(
    *, cfg: ExperimentConfig, scenarios: list[Scenario], specs: list[EpisodeSpec], loaded: LoadedPolicy, endpoint,
    client_factory, run_dir: Path, run_id: str, redaction_values=(),
) -> int:
    """Run the guarded executor after a passed preflight and return the approved exit code.

    TEST-ONLY entry point while the final refusal stands: ``main`` never calls it, nothing reads a credential or builds a
    client here (the caller supplies ``client_factory``), and the executor re-checks the policy against the configuration."""
    try:
        outcome = execute_live_run(
            run_fn=run_experiment, cfg=cfg, scenarios=scenarios, client_factory=client_factory, policy=loaded.policy,
            run_dir=run_dir, run_id=run_id, repo_root=REPO_ROOT, expected_episode_ids=[s.episode_id for s in specs],
            redaction_values=list(redaction_values), policy_record=build_policy_record(loaded, endpoint),
        )
    except KeyboardInterrupt as interrupt:
        recorded = getattr(interrupt, "maps_outcome", None)
        where = f" output: {recorded.run_dir}" if recorded is not None else ""
        print(f"interrupted: partial output is preserved and the run is not eligible for analysis.{where}", file=sys.stderr)
        return INTERRUPTED
    code = live_exit_code(outcome)
    if code == REFUSED:
        print(f"refused: {outcome.detail}", file=sys.stderr)
    elif code == OK:
        print(f"done: run complete and eligible. output: {outcome.run_dir}")
        print(f"integrity report: {outcome.report_path}")
    else:
        print(
            f"not usable (exit {code}, stage: {outcome.failed_stage or 'report'}): partial output is preserved and the run is "
            f"not eligible for analysis. output: {outcome.run_dir}", file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
