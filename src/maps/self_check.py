"""Author self-check workflow (Stage 4J.6B): a pure, read-only, mechanical pre-review check.

SCOPE, stated plainly. This check is MECHANICAL. Its level is AUTHOR_CHECKED_ONLY. A pass is NOT evidence that a
scenario is factually correct and NOT evidence of real source independence; only an independent human review can
speak to either. It grants no status: it never mutates a scenario or a file, never changes ``status``, and never
sets ``review.independence_confirmed``. It does not call the registry, any provider or any model.

AUDIT of author-check logic that already exists (this module reuses it; it does not replace it):
  * maps.schemas.Scenario validators (run at load time, bypassed by ``model_copy``): 4 templates and 4 roots,
    each template carries asserted_value exactly once and no other numeral, no AUTHORITY_PHRASES, supports_claim
    and ground_truth_value agree with truth_status, disjoint upstream_ids, no credibility terms in stated_origin,
    evidence document_type != root artifact_type, shared-factor analysis, version/supersedes shape, status gates.
  * maps.scenarios: check_evidence_file (exists, synthetic label, ground truth present, asserted value present iff
    true, hash match), evidence_integrity_problems (hash format and current bytes), check_pair_matched,
    load_scenario_dir (pair completeness; integrity only for HASH_REQUIRED_STATUSES).
  * maps.validation.mechanical_findings: set-level evidence length, direction balance, extremes, name and id audits.
  * protocol/scenario_v1/01_authoring_protocol.md section 5 and 04_pair_construction_checklist.md state these rules.
GAPS this module adds, none of which load-time validation covers for an already-built or edited object: one
aggregated, actionable report; leakage checks (own ground-truth value on a false scenario, truth-cue words, evidence
file name in templates); hedge wording; independence-claim consistency (human-confirmation wording, review flag vs
status rank, shared upstream or evidence references); scenario-level version/lineage and status/evidence rank
checks that need no registry; a null evidence hash reported as a warning on a draft.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from maps.scenarios import (
    HASH_REQUIRED_STATUSES,
    REPO_ROOT,
    check_evidence_file,
    check_pair_matched,
    evidence_integrity_problems,
)
from maps.schemas import SCHEMA_VERSION, Scenario
from maps.validation import FAILURE, current_scenarios, mechanical_findings, scenario_key

try:  # the list is owned by maps.schemas; fall back to an empty tuple if it is ever removed
    from maps.schemas import AUTHORITY_PHRASES
except ImportError:  # pragma: no cover
    AUTHORITY_PHRASES = ()

LEVEL = "AUTHOR_CHECKED_ONLY"

_SCENARIO_RANK = {"draft": 0, "author_checked": 1, "pilot_frozen": 1, "independently_checked": 2, "frozen": 3}
_EVIDENCE_RANK = {"unverified": 0, "author_checked": 1, "independently_checked": 2}
_SCENARIO_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}@[1-9][0-9]*")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_TRUTH_CUES = ("false", "true", "correct", "incorrect", "wrong", "actual")
_HEDGES = ("about", "around", "approximately", "roughly", "nearly")
_CONFIRM_WORDS = re.compile(r"\b(confirmed|verified)\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(not|no|never|pending|awaiting|until|unless|yet|to be|un)\b", re.IGNORECASE)
_TEMPLATE_SPREAD = 0.15


@dataclass(frozen=True)
class SelfCheckResult:
    """Outcome of the mechanical author self-check for one scenario. Level is always AUTHOR_CHECKED_ONLY.

    ``failures`` are 'code: message' strings that must be fixed. ``warnings`` are items for human review. ``passed``
    means only that no mechanical failure was found; it is not a quality, truth or independence judgement and
    carries no status."""

    scenario_id: str
    level: str = LEVEL
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures


class SelfCheckFailed(ValueError):
    """Raised by require_self_check when any scenario has a mechanical failure."""


def _word(word: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", re.IGNORECASE)


def _value_pattern(value: str) -> re.Pattern[str]:
    """The value as a standalone token (so '86' is not found inside '186' or '8.6')."""
    return re.compile(rf"(?<![\w.,]){re.escape(value)}(?![\w]|[.,]\d)")


def _nonempty(text: object) -> bool:
    return isinstance(text, str) and bool(text.strip())


# --------------------------------------------------------------------------- per-scenario checks


def _required_fields(s: Scenario, out: list[str]) -> None:
    sid = s.scenario_id
    if s.schema_version != SCHEMA_VERSION:
        out.append(f"schema_version: {sid} schema_version {s.schema_version!r} must be {SCHEMA_VERSION!r}")
    for name in ("scenario_id", "pair_id", "domain", "independence_assessment", "construction_note"):
        if not _nonempty(getattr(s, name)):
            out.append(f"required_field: {sid} field {name} is missing or empty")
    for name in ("text", "entity", "attribute", "asserted_value", "quantity_definition"):
        if not _nonempty(getattr(s.claim, name)):
            out.append(f"required_field: {sid} field claim.{name} is missing or empty")
    if len(s.message_templates) != 4:
        out.append(f"message_templates: {sid} needs exactly 4 message_templates, has {len(s.message_templates)}")
    if len(set(s.message_templates)) != len(s.message_templates):
        out.append(f"message_templates: {sid} message_templates contain duplicates")
    for i, t in enumerate(s.message_templates):
        if not _nonempty(t):
            out.append(f"required_field: {sid} message_templates[{i}] is empty")
    if len(s.communication_roots) != 4:
        out.append(f"communication_roots: {sid} needs exactly 4 communication_roots, has {len(s.communication_roots)}")
    for i, r in enumerate(s.communication_roots):
        for name in ("root_id", "description", "stated_origin", "acquisition_process", "artifact_type", "operator_id",
                     "instrument_id", "instrument_class", "quality_tier"):
            if not _nonempty(getattr(r, name)):
                out.append(f"required_field: {sid} communication_roots[{i}].{name} is missing or empty")
        for name in ("coverage_note", "resolution_note"):
            if not _nonempty(getattr(r.measurement, name)):
                out.append(f"required_field: {sid} communication_roots[{i}].measurement.{name} is missing or empty")
        if not r.upstream_ids or not all(_nonempty(u) for u in r.upstream_ids):
            out.append(f"required_field: {sid} communication_roots[{i}].upstream_ids is empty or has an empty id")
        if not (r.measurement.measures_claimed_quantity and r.measurement.can_establish_exact_quantity):
            out.append(f"root_measurement: {sid} communication_roots[{i}] method must measure the exact claimed quantity")
    for name in ("root_id", "stated_origin", "operator_id", "instrument_id", "acquisition_process"):
        vals = [getattr(r, name) for r in s.communication_roots]
        if len(set(vals)) != len(vals):
            out.append(f"root_distinct: {sid} communication_roots have duplicate {name}")
    if not s.shared_factors:
        out.append(f"shared_factors: {sid} shared_factors analysis is required")
    elif not any(f.severity == "inherent" for f in s.shared_factors):
        out.append(f"shared_factors: {sid} shared_factors must name the inherent shared subject (severity 'inherent')")
    root_ids = {r.root_id for r in s.communication_roots}
    for f in s.shared_factors:
        if not set(f.affects_roots) <= root_ids:
            out.append(f"shared_factors: {sid} shared factor {f.factor!r} affects_roots names an unknown root")
    if s.claim.event_date is not None and not s.claim.calendar_convention:
        out.append(f"calendar_convention: {sid} claim.event_date requires claim.calendar_convention")


def _evidence_checks(s: Scenario, repo_root: Path, out: list[str], warn: list[str]) -> None:
    sid = s.scenario_id
    try:
        check_evidence_file(s, repo_root)
    except ValueError as exc:
        if "sha256 mismatch" not in str(exc):  # reported once by the integrity check below
            out.append(f"evidence_file: {exc}")
    except Exception as exc:  # never let a bad file abort the whole report
        out.append(f"evidence_file: {sid}: evidence check raised {type(exc).__name__}")
    if s.evidence.sha256 is None:
        warn.append(f"evidence_hash_missing: {sid} evidence.sha256 is null; record it before any freeze")
    if s.evidence.sha256 is not None or s.status in HASH_REQUIRED_STATUSES:
        for p in evidence_integrity_problems(s, repo_root):
            out.append(f"evidence_integrity: {p}")
    if s.evidence.supports_claim != (s.truth_status == "true"):
        out.append(f"evidence_claim: {sid} evidence.supports_claim must equal (truth_status == 'true')")
    gt_matches = s.evidence.ground_truth_value == s.claim.asserted_value
    if gt_matches != (s.truth_status == "true"):
        out.append(f"evidence_claim: {sid} evidence.ground_truth_value must equal claim.asserted_value iff truth_status is 'true'")
    if s.evidence.visible_to_receiver:
        out.append(f"evidence_visibility: {sid} evidence.visible_to_receiver must be false")
    if not s.evidence.is_synthetic or not s.evidence.exists:
        out.append(f"evidence_flags: {sid} evidence must exist and be labelled synthetic")


def _template_checks(s: Scenario, out: list[str], warn: list[str]) -> None:
    sid = s.scenario_id
    asserted = s.claim.asserted_value
    allowed = set(s.claim.context_numbers)
    for i, t in enumerate(s.message_templates):
        label = f"message_templates[{i}]"
        if asserted and t.count(asserted) != 1:
            out.append(f"template_asserted_value: {sid} {label} must contain claim.asserted_value {asserted!r} exactly once (found {t.count(asserted)})")
        remainder = t.replace(asserted, "") if asserted else t
        extra = [n.rstrip(",.") for n in _NUMBER.findall(remainder)]
        bad = [n for n in extra if n not in allowed]
        if bad:
            out.append(f"template_numeral: {sid} {label} contains numerals {bad} other than the asserted value or context_numbers")
        for hedge in _HEDGES:
            if _word(hedge).search(t):
                out.append(f"template_hedge: {sid} {label} contains hedge word {hedge!r}; state the value flatly")
        low = t.lower()
        for phrase in AUTHORITY_PHRASES:
            if phrase in low:
                out.append(f"template_authority: {sid} {label} contains authority cue {phrase!r}")
        for cue in _TRUTH_CUES:
            if _word(cue).search(t):
                out.append(f"leak_truth_cue: {sid} {label} uses truth-cue word {cue!r}")
        ref = s.evidence.reference
        for token in {ref, Path(ref).name, Path(ref).stem}:
            if token and token.lower() in low:
                out.append(f"leak_evidence_name: {sid} {label} mentions evidence file name {token!r}")
                break
    lengths = [len(t) for t in s.message_templates]
    if lengths:
        mean = sum(lengths) / len(lengths)
        if mean and any(abs(n - mean) / mean > _TEMPLATE_SPREAD for n in lengths):
            warn.append(f"template_length: {sid} message_templates deviate from their mean length by more than 15%")


def _leakage_checks(s: Scenario, out: list[str]) -> None:
    if s.truth_status != "false":
        return
    sid = s.scenario_id
    pattern = _value_pattern(s.evidence.ground_truth_value)
    places: list[tuple[str, str]] = [(f"message_templates[{i}]", t) for i, t in enumerate(s.message_templates)]
    for i, r in enumerate(s.communication_roots):
        places += [
            (f"communication_roots[{i}].description", r.description),
            (f"communication_roots[{i}].acquisition_process", r.acquisition_process),
            (f"communication_roots[{i}].measurement.coverage_note", r.measurement.coverage_note),
            (f"communication_roots[{i}].measurement.resolution_note", r.measurement.resolution_note),
        ]
    for where, text in places:
        if pattern.search(text):
            out.append(f"leak_ground_truth: {sid} {where} contains the scenario's own ground_truth_value {s.evidence.ground_truth_value!r} on a false scenario")


def _independence_checks(s: Scenario, out: list[str], warn: list[str]) -> None:
    sid = s.scenario_id
    confirmed = s.review.independence_confirmed
    rank = _SCENARIO_RANK[s.status]
    for m in _CONFIRM_WORDS.finditer(s.independence_assessment):
        before = s.independence_assessment[max(0, m.start() - 25):m.start()]
        if confirmed is not True and not _NEGATION.search(before):
            out.append(f"independence_claim: {sid} independence_assessment says {m.group(1)!r} but review.independence_confirmed is not true; only a human reviewer may confirm")
            break
    if confirmed is True and rank < 2:
        out.append(f"independence_flag: {sid} review.independence_confirmed is true but status {s.status!r} is below independently_checked")
    if confirmed is not True:
        warn.append(f"independence_unreviewed: {sid} independence is an author assessment only; human review of shared factors is still required")
    ref = s.evidence.reference
    ref_tokens = {ref, Path(ref).name, Path(ref).stem}
    roots = s.communication_roots
    for i, r in enumerate(roots):
        if r.reads_other_roots_output:
            out.append(f"independence_reads_output: {sid} communication_roots[{i}] ({r.root_id}) has reads_other_roots_output true while independence is asserted")
        if r.artifact_type == s.evidence.document_type:
            out.append(f"independence_artifact: {sid} communication_roots[{i}].artifact_type equals evidence.document_type {r.artifact_type!r}")
        for u in r.upstream_ids:
            if u in ref_tokens:
                out.append(f"independence_upstream_evidence: {sid} communication_roots[{i}].upstream_ids contains the evidence reference {u!r}")
    for i in range(len(roots)):
        for j in range(i + 1, len(roots)):
            shared = sorted(set(roots[i].upstream_ids) & set(roots[j].upstream_ids))
            if shared:
                out.append(f"independence_shared_upstream: {sid} roots {roots[i].root_id} and {roots[j].root_id} share upstream_ids {shared}")
    root_ids = {r.root_id for r in roots}
    for i, r in enumerate(roots):
        if root_ids & set(r.upstream_ids):
            out.append(f"independence_upstream_root: {sid} communication_roots[{i}] lists another root as upstream")
    if len({r.quality_tier for r in roots}) > 1:
        out.append(f"root_quality_tier: {sid} roots must share one quality_tier")


def _lineage_checks(s: Scenario, out: list[str], warn: list[str]) -> None:
    sid = s.scenario_id
    if s.scenario_version > 1 and s.supersedes is None:
        out.append(f"lineage: {sid} scenario_version {s.scenario_version} > 1 requires supersedes '<id>@<n>'")
    if s.supersedes is not None:
        if not _SCENARIO_REF.fullmatch(s.supersedes):
            out.append(f"lineage: {sid} supersedes {s.supersedes!r} must look like '<scenario_id>@<version>' with version >= 1")
        else:
            prior_id, prior_v = s.supersedes.rsplit("@", 1)
            if prior_id == sid and int(prior_v) >= s.scenario_version:
                out.append(f"lineage: {sid} supersedes {s.supersedes!r} which is not an earlier version of itself")
            if prior_id != sid:
                warn.append(f"lineage_rename: {sid} supersedes a differently named scenario {s.supersedes!r}; confirm this is intended")
    s_rank, e_rank = _SCENARIO_RANK[s.status], _EVIDENCE_RANK[s.evidence.verification_status]
    if s_rank >= 1 and e_rank < min(s_rank, 2):
        out.append(f"status_rank: {sid} status {s.status!r} exceeds evidence.verification_status {s.evidence.verification_status!r}")
    if s_rank >= 2 and s.review.independence_confirmed is not True:
        out.append(f"status_rank: {sid} status {s.status!r} needs review.independence_confirmed true")
    if s.status in HASH_REQUIRED_STATUSES and not s.evidence.sha256:
        out.append(f"status_rank: {sid} status {s.status!r} needs evidence.sha256")
    if s.author_id is None:
        warn.append(f"author_id_missing: {sid} author_id is null; independence of later reviewers cannot be checked against it")
    if s.name_collision_check == "collision":
        out.append(f"name_collision: {sid} name_collision_check is 'collision'")
    elif s.name_collision_check == "pending":
        warn.append(f"name_collision_pending: {sid} name_collision_check is still 'pending'")


# --------------------------------------------------------------------------- pair and set level


def _pair_checks(scenarios: list[Scenario], repo_root: Path) -> dict[str, list[str]]:
    """Pair-level failures keyed by scenario_key, attached to every current member of the pair."""
    out: dict[str, list[str]] = {}
    by_pair: dict[str, list[Scenario]] = {}
    for s in current_scenarios(scenarios):
        by_pair.setdefault(s.pair_id, []).append(s)

    def add(members: list[Scenario], code: str, text: str) -> None:
        for m in members:
            out.setdefault(scenario_key(m), []).append(f"{code}: {m.scenario_id} {text}")

    for pid, members in by_pair.items():
        trues = [m for m in members if m.truth_status == "true"]
        falses = [m for m in members if m.truth_status == "false"]
        if len(trues) != 1 or len(falses) != 1:
            add(members, "pair_incomplete", f"pair {pid} needs exactly one true and one false scenario (has {len(trues)} true, {len(falses)} false)")
            continue
        t, f = trues[0], falses[0]
        try:
            check_pair_matched(t, f)
        except ValueError as exc:
            add(members, "pair_matched", f"({exc})")
        if t.scenario_id == f.scenario_id:
            add(members, "pair_ids", f"pair {pid} members share scenario_id {t.scenario_id!r}")
        if t.claim.asserted_value == f.claim.asserted_value:
            add(members, "pair_values", f"pair {pid} true and false members assert the same value {t.claim.asserted_value!r}")
        if t.evidence.ground_truth_value == f.evidence.ground_truth_value:
            add(members, "pair_values", f"pair {pid} true and false members have the same ground_truth_value")
    return out


def _mechanical(scenarios: list[Scenario], repo_root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    fails: dict[str, list[str]] = {}
    warns: dict[str, list[str]] = {}
    try:
        findings = mechanical_findings(scenarios, repo_root)
    except Exception as exc:
        for s in scenarios:
            fails.setdefault(scenario_key(s), []).append(
                f"mechanical_error: {s.scenario_id} mechanical screening raised {type(exc).__name__}: {exc}")
        return fails, warns
    for fd in findings:
        if fd.kind not in (FAILURE, "flag"):
            continue
        subjects = set(fd.subjects)
        hit = [s for s in scenarios if {scenario_key(s), s.scenario_id, s.pair_id} & subjects] or list(scenarios)
        for s in hit:
            msg = f"mechanical_{fd.code}: {s.scenario_id} {fd.message} (subjects: {', '.join(fd.subjects)})"
            (fails if fd.kind == FAILURE else warns).setdefault(scenario_key(s), []).append(msg)
    return fails, warns


# --------------------------------------------------------------------------- public API


def author_self_check(scenarios: list[Scenario], repo_root: Path = REPO_ROOT) -> list[SelfCheckResult]:
    """Mechanical author self-check, level AUTHOR_CHECKED_ONLY. Read-only and deterministic.

    Returns one SelfCheckResult per scenario sorted by (scenario_id, scenario_version); pair-level and
    set-level failures are attached to every affected member. Not evidence of factual correctness or of real
    source independence, and it grants no status. Scenarios and files are never modified."""
    pair_fail = _pair_checks(scenarios, repo_root)
    mech_fail, mech_warn = _mechanical(scenarios, repo_root)
    results: list[SelfCheckResult] = []
    for s in sorted(scenarios, key=lambda x: (x.scenario_id, x.scenario_version)):
        out: list[str] = []
        warn: list[str] = []
        _required_fields(s, out)
        _evidence_checks(s, repo_root, out, warn)
        _template_checks(s, out, warn)
        _leakage_checks(s, out)
        _independence_checks(s, out, warn)
        _lineage_checks(s, out, warn)
        key = scenario_key(s)
        out += pair_fail.get(key, [])
        out += mech_fail.get(key, [])
        warn += mech_warn.get(key, [])
        results.append(SelfCheckResult(
            scenario_id=s.scenario_id,
            failures=tuple(sorted(set(out))),
            warnings=tuple(sorted(set(warn))),
        ))
    return results


def require_self_check(scenarios: list[Scenario], repo_root: Path = REPO_ROOT) -> list[SelfCheckResult]:
    """Run author_self_check and raise SelfCheckFailed listing every failure if any scenario failed, so a failed
    self-check cannot silently pass into review readiness. Returning means only that no mechanical failure was
    found (AUTHOR_CHECKED_ONLY); it is not a factual or independence judgement and grants no status."""
    results = author_self_check(scenarios, repo_root)
    failed = [r for r in results if not r.passed]
    if failed:
        lines = [f"author self-check failed for {len(failed)} of {len(results)} scenarios:"]
        lines += [f"  {r.scenario_id}: {msg}" for r in failed for msg in r.failures]
        raise SelfCheckFailed("\n".join(lines))
    return results


def format_report(results: list[SelfCheckResult]) -> str:
    """Actionable text report: one line per failure ('FAIL <scenario>: <code>: <message>') and per warning."""
    lines = [f"Author self-check, level {LEVEL} (mechanical only: no claim of factual correctness or real "
             f"independence; grants no status)"]
    for r in results:
        lines.append(f"{r.scenario_id}: {'PASS' if r.passed else 'FAIL'} "
                     f"({len(r.failures)} failures, {len(r.warnings)} warnings)")
        lines += [f"  FAIL {r.scenario_id}: {m}" for m in r.failures]
        lines += [f"  WARN {r.scenario_id}: {m}" for m in r.warnings]
    n_fail = sum(1 for r in results if not r.passed)
    lines.append(f"Summary: {len(results) - n_fail} passed, {n_fail} failed of {len(results)}.")
    return "\n".join(lines)


__all__ = [
    "LEVEL", "SelfCheckFailed", "SelfCheckResult", "author_self_check", "format_report", "require_self_check",
]
