"""Builders for the run-integrity tests (SYNTHETIC mock records only; temporary directories only).

Records are written with the real ``JsonlWriter`` so that the accepted line format is the one the
existing writer produces, never a format assumed here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from maps.logging_utils import JsonlWriter
from maps.schemas import EpisodeResult, EpisodeSpec, PlanItem, ReceiverResponse

SHAPES = {"C0": (0, 0), "C1": (1, 1), "C2": (2, 1), "C3": (4, 1), "C4": (2, 2), "C5": (4, 4)}


def make_result(
    *, episode_id="ep_000000000001", alias="alpha", model_id="synthetic/alpha", scenario="s1", pair="p1",
    truth="true", cond="C4", variant="neutral", rep=0, seed=1, status="ok", accepts=True, confidence=80, roots=2,
    reasoning="SYNTHETIC reasoning", error="synthetic failure",
) -> EpisodeResult:
    n_messages, n_roots = SHAPES[cond]
    plan = [
        PlanItem(position=k, relay_id=f"Relay-{k + 1}", template_idx=k, root_id=f"{scenario}-R{k % n_roots + 1}")
        for k in range(n_messages)
    ]
    spec = EpisodeSpec(
        episode_id=episode_id, model_alias=alias, model_id=model_id, scenario_id=scenario, pair_id=pair,
        truth_status=truth, condition_id=cond, n_messages=n_messages, n_roots=n_roots, prompt_variant=variant,
        repetition=rep, seed=seed, message_plan=plan,
    )
    if status == "ok":
        response = ReceiverResponse(
            accepts_claim=accepts, confidence=confidence, estimated_independent_roots=roots,
            evidence_used=[], reasoning=reasoning,
        )
        return EpisodeResult(spec=spec, status="ok", response=response)
    return EpisodeResult(spec=spec, status=status, error=error)


def numbered(n: int, **kw) -> list[EpisodeResult]:
    """n distinct valid results with ids ep_000000000001 ... and repetitions 0..n-1."""
    return [make_result(episode_id=f"ep_{i + 1:012d}", rep=i, **kw) for i in range(n)]


def write_records(path: Path, results) -> Path:
    writer = JsonlWriter(path)
    for result in results:
        writer.write(result.model_dump(mode="json"))
    return Path(path)


def raw_line(result: EpisodeResult, **changes) -> str:
    """The writer's line for a result, with top-level or ``spec``/``response`` fields altered afterwards."""
    data = result.model_dump(mode="json")
    for key, value in changes.items():
        if key.startswith("response__"):
            data["response"][key.split("__", 1)[1]] = value
        elif key.startswith("spec__"):
            data["spec"][key.split("__", 1)[1]] = value
        else:
            data[key] = value
    return json.dumps(data, ensure_ascii=False)


def write_lines(path: Path, lines: list[str]) -> Path:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return Path(path)


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hashes(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): file_hash(p) for p in sorted(Path(directory).rglob("*")) if p.is_file()}
