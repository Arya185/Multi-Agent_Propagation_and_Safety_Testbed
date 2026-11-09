"""Cohort and pilot-exposure registry (Stage 4J.2).

Why a separate registry: cohort membership and pilot exposure happen AFTER a scenario's content is
frozen, so they must not be stored in scenario files (that would change the frozen content). A registry
records, outside the scenario files:

  * cohorts: an identifier, a family (``pilot`` or ``confirmatory``), whole-scenario membership and the
    time the cohort was fixed;
  * pilot-exposure events: a scenario version was used in a pilot run (append-only in practice);
  * lineage: which scenario version supersedes which, so a revised version cannot shed its history.

Rule enforced (decisions A4 and B3, and the approved pilot scenario policy): a confirmatory cohort must
not contain a pilot-cohort scenario, a pilot-exposed scenario, or any scenario that descends, through
``supersedes``, from either. Creating a new version, or moving a scenario between cohorts, cannot erase
exposure history because the history is checked through the lineage.

What this module does NOT do. A registry entry is not proof of independent review; ``check_registry`` reads
the scenario's own review evidence. It does not decide that any scenario is frozen, does not implement a
design freeze, never assigns a scenario to a cohort and never writes a registry (pilot exposure is recorded by
hand). It reads no answer key. Pure functions, no I/O other than ``load_registry`` and, through
``maps.validation``, the evidence files of the scenarios it is given.

Stage 4J.5 adds the pair-level gate, ``pair_review_problems``: a confirmatory true/false pair is eligible only if BOTH
members are frozen with bound independent-review evidence (each submission carries the hash of the content it saw,
pair-stage ones the partner's hash too), neither carries any adjudication record (one record on either member
retires or reopens the whole pair; a frozen partner cannot bypass a blocked one), nobody who authored, reviewed or
adjudicated either member adjudicated either member, and each pair-stage submission still matches the partner's
current content. ``check_registry`` applies it to every complete pair of every confirmatory cohort and, for lineage,
requires a registry entry for every loaded scenario whose file sets ``supersedes`` (a new version never inherits the
review validity of its parent: the content hash includes version and supersedes). Nothing here assigns, freezes or writes.

Stage 4J.3 adds ``confirmatory_run_problems`` and ``pilot_run_problems``: the checks a runner applies at its
boundary. They are fail-closed: any problem, including an unassigned scenario, is a refusal.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maps.scenarios import REPO_ROOT, evidence_integrity_problems, evidence_path, file_sha256
from maps.schemas import (
    Scenario,
    independent_review_problems,
    normalize_id,
    parse_timestamp,
    qualifying_independent_reviewers,
    scenario_content_sha256,
)
from maps.validation import ScreeningException, mechanical_failures

CohortFamily = Literal["pilot", "confirmatory"]
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _identifier(value: str, what: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError(f"{what} must be an identifier (letters, digits, '.', '_', '-'; no spaces; at most 64 characters)")
    return value


class ScenarioRef(_Strict):
    scenario_id: str
    scenario_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _check(self) -> ScenarioRef:
        _identifier(self.scenario_id, "scenario_id")
        return self

    @property
    def key(self) -> str:
        return f"{self.scenario_id}@{self.scenario_version}"


class Cohort(_Strict):
    cohort_id: str
    family: CohortFamily
    members: list[ScenarioRef] = Field(min_length=1)
    fixed_on: str

    @model_validator(mode="after")
    def _check(self) -> Cohort:
        _identifier(self.cohort_id, "cohort_id")
        keys = [m.key for m in self.members]
        if len(set(keys)) != len(keys):
            raise ValueError(f"cohort {self.cohort_id!r} lists a scenario more than once")
        parse_timestamp(self.fixed_on)
        return self


class PilotExposure(_Strict):
    """A scenario version was exposed to a pilot run. Exposure disqualifies it, and everything that
    descends from it, from any confirmatory cohort."""

    scenario: ScenarioRef
    run_id: str
    recorded_on: str
    note: str = ""
    # Stage 4J.7, all optional and informational (they do not change eligibility): which pilot cohort the run used
    # and the digests of the scenario content and evidence bytes that were exposed. A digest is content identity only.
    cohort_id: str | None = None
    scenario_sha256: str | None = None
    evidence_sha256: str | None = None

    @model_validator(mode="after")
    def _check(self) -> PilotExposure:
        _identifier(self.run_id, "run_id")
        parse_timestamp(self.recorded_on)
        return self


class Supersession(_Strict):
    scenario: ScenarioRef
    supersedes: ScenarioRef


def _parents(registry: Registry, extra: dict[str, str] | None = None) -> dict[str, str]:
    parents = {s.scenario.key: s.supersedes.key for s in registry.lineage}
    for child, parent in (extra or {}).items():
        parents.setdefault(child, parent)
    return parents


def ancestors(key: str, parents: dict[str, str]) -> list[str]:
    """Versions that ``key`` descends from, nearest first. Stops on a cycle."""
    chain: list[str] = []
    seen = {key}
    while key in parents:
        key = parents[key]
        if key in seen:
            break
        chain.append(key)
        seen.add(key)
    return chain


def pilot_cohort_keys(registry: Registry) -> set[str]:
    return {m.key for c in registry.cohorts if c.family == "pilot" for m in c.members}


def pilot_exposed_keys(registry: Registry) -> set[str]:
    return {e.scenario.key for e in registry.exposures}


def confirmatory_violations(registry: Registry, extra_parents: dict[str, str] | None = None) -> list[str]:
    """Every reason a confirmatory cohort member is not eligible. Empty means eligible."""
    parents = _parents(registry, extra_parents)
    in_pilot, exposed = pilot_cohort_keys(registry), pilot_exposed_keys(registry)
    problems = []
    for cohort in registry.cohorts:
        if cohort.family != "confirmatory":
            continue
        for member in cohort.members:
            if member.key in in_pilot:
                problems.append(f"{cohort.cohort_id}: {member.key} is in a pilot cohort")
            if member.key in exposed:
                problems.append(f"{cohort.cohort_id}: {member.key} is pilot-exposed")
            for ancestor in ancestors(member.key, parents):
                if ancestor in in_pilot:
                    problems.append(f"{cohort.cohort_id}: {member.key} descends from pilot-cohort scenario {ancestor}")
                if ancestor in exposed:
                    problems.append(f"{cohort.cohort_id}: {member.key} descends from pilot-exposed scenario {ancestor}")
    return problems


class Registry(_Strict):
    registry_version: Literal[1] = 1
    cohorts: list[Cohort]
    exposures: list[PilotExposure] = Field(default_factory=list)
    lineage: list[Supersession] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Registry:
        ids = [c.cohort_id for c in self.cohorts]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate cohort_id")

        children = [s.scenario.key for s in self.lineage]
        if len(set(children)) != len(children):
            raise ValueError("a scenario version can supersede only one earlier version")
        for s in self.lineage:
            if s.scenario.key == s.supersedes.key:
                raise ValueError(f"{s.scenario.key} cannot supersede itself")
        parents = _parents(self)
        for start in parents:
            walked, cursor = {start}, start
            while cursor in parents:
                cursor = parents[cursor]
                if cursor in walked:
                    raise ValueError(f"supersession cycle through {start}")
                walked.add(cursor)

        family_of: dict[str, set[str]] = {}
        fixed: dict[str, list] = {}
        for c in self.cohorts:
            for m in c.members:
                family_of.setdefault(m.key, set()).add(c.family)
                if c.family == "pilot":
                    fixed.setdefault(m.key, []).append(parse_timestamp(c.fixed_on))
        mixed = sorted(k for k, fams in family_of.items() if len(fams) > 1)
        if mixed:
            raise ValueError(f"scenario version(s) in both a pilot and a confirmatory cohort: {mixed}")

        events = [(e.scenario.key, e.run_id) for e in self.exposures]
        if len(set(events)) != len(events):
            raise ValueError("duplicate pilot-exposure event")
        for e in self.exposures:
            if e.scenario.key in fixed and parse_timestamp(e.recorded_on) < min(fixed[e.scenario.key]):
                raise ValueError(f"{e.scenario.key} was exposed before its pilot cohort was fixed")

        problems = confirmatory_violations(self)
        if problems:
            raise ValueError("confirmatory eligibility violated: " + "; ".join(problems))
        return self


def load_registry(path: str | Path) -> Registry:
    return Registry.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def _key(s: Scenario) -> str:
    return f"{s.scenario_id}@{s.scenario_version}"


def _reviewer_ids(s: Scenario) -> set[str]:
    """Normalised ids of everyone who acted as a reviewer of ``s``: submitter, assignee or declarant."""
    return {
        normalize_id(x.reviewer_id)
        for x in (*s.review_submissions, *s.reviewer_assignments, *s.conflict_declarations)
    }


def _adjudicator(s: Scenario) -> str | None:
    adj = s.adjudication
    if adj is None or not adj.resolved or adj.adjudicator_id is None:
        return None
    return normalize_id(adj.adjudicator_id)


def _evidence_problems(s: Scenario, repo_root: Path) -> list[str]:
    return [f"{_key(s)}: {reason}" for reason in evidence_integrity_problems(s, repo_root)]


def pair_review_problems(true_s: Scenario, false_s: Scenario, *, repo_root: Path | None = None) -> list[str]:
    """Every reason the matched pair is NOT eligible for a confirmatory cohort (empty means eligible).

    Deterministic, no mutation; messages carry scenario keys and ids, never claim or asserted values. Checks, in
    order: membership sanity (fail safe: a single problem and stop); each member frozen with bound
    independent-review evidence; any adjudication record on either member blocks the pair (unresolved, reject =
    retired, revise = a new version of both members is needed); identity separation across BOTH members with ids
    compared through ``normalize_id`` (NFKC, strip, case-fold): the author of either member is not a reviewer
    (submitter, assignee or declarant) of either member, and an adjudicator of either member is neither author
    nor reviewer of either member nor the other member's adjudicator; each pair-stage submission bound to the
    partner's current content; and, when ``repo_root`` is given, the current evidence bytes of BOTH members
    match their recorded hashes (the partner's evidence matters to a pair review).

    Allowed on purpose: the same reviewer on both members; the same author on both members. Not checked here:
    reviewers shared across different pairs (a ``maps.validation`` human-review flag).

    Pair symmetry (owner Decision A, Stage 4J.6B): the SAME qualifying reviewer set, compared on normalised ids,
    must be present on both members; a reviewer who qualifies on only one member does not make the pair eligible."""
    tk, fk = _key(true_s), _key(false_s)
    if true_s.pair_id != false_s.pair_id:
        return [f"pair membership invalid: {tk} and {fk} have different pair_id"]
    if (true_s.truth_status, false_s.truth_status) != ("true", "false"):
        return [f"pair membership invalid: {tk} and {fk} are not one true and one false member"]
    if true_s.scenario_id == false_s.scenario_id:
        return [f"pair membership invalid: {tk} and {fk} are the same scenario"]

    members = [(true_s, false_s), (false_s, true_s)]
    problems: list[str] = []
    for s, _ in members:
        if s.status != "frozen":
            problems.append(f"{_key(s)} has status {s.status!r}, not 'frozen'")
        for reason in independent_review_problems(s, bound=True):
            problems.append(f"{_key(s)}: {reason}")

    for s, _ in members:
        adj = s.adjudication
        if adj is None:
            continue
        if not adj.resolved:
            problems.append(f"adjudication unresolved on {_key(s)}")
        elif adj.outcome == "reject":
            problems.append(f"pair retired: reject outcome on {_key(s)}")
        else:
            problems.append(f"pair needs a new version of both members: revise outcome on {_key(s)}")

    for s, _ in members:
        if s.author_id is None:
            continue  # independent_review_problems already reports a missing author
        author = normalize_id(s.author_id)
        for t in (true_s, false_s):
            if author in _reviewer_ids(t):
                problems.append(f"author of {_key(s)} ({s.author_id}) is a reviewer of {_key(t)}")

    for s, partner in members:
        x = _adjudicator(s)
        if x is None:
            continue
        for t in (s, partner):
            if t.author_id is not None and normalize_id(t.author_id) == x:
                problems.append(f"adjudicator of {_key(s)} is the author of {_key(t)}")
            if x in _reviewer_ids(t):
                problems.append(f"adjudicator of {_key(s)} is a reviewer of {_key(t)}")
        if _adjudicator(partner) == x:
            problems.append(f"adjudicator of {_key(s)} is also the adjudicator of {_key(partner)}")

    for s, partner in members:
        current = scenario_content_sha256(partner)
        for sub in s.review_submissions:
            if sub.stage == "pair" and sub.partner_content_sha256 is not None and sub.partner_content_sha256 != current:
                problems.append(f"pair-stage submission by {sub.reviewer_id} on {_key(s)} is bound to different partner content (stale)")

    problems += _symmetry_problems(true_s, false_s)

    if repo_root is not None:
        for s, _ in members:
            problems += _evidence_problems(s, repo_root)
    return list(dict.fromkeys(problems))


def _symmetry_problems(true_s: Scenario, false_s: Scenario) -> list[str]:
    """Decision A (Stage 4J.6B): the matched pair is reviewed by the SAME qualifying reviewer set on both members.

    The sets are compared on ``normalize_id`` forms and are computed in bound mode (current content, current
    partner content). A reviewer who qualifies on only one member does not make the pair eligible; the message
    says which member lacks the reviewer and whether that reviewer took part there at all."""
    sets = {
        _key(s): {normalize_id(r) for r in qualifying_independent_reviewers(s, bound=True)}
        for s in (true_s, false_s)
    }
    problems: list[str] = []
    for s, partner in ((true_s, false_s), (false_s, true_s)):
        for reviewer in sorted(sets[_key(s)] - sets[_key(partner)]):
            seen = "has records for them but they do not qualify" if reviewer in _reviewer_ids(partner) else "has no record of them"
            problems.append(
                f"pair symmetry: reviewer {reviewer} qualifies on {_key(s)} but not on {_key(partner)}, which {seen}"
            )
    return problems


def _lineage_problems(registry: Registry, by_key: dict[str, Scenario], from_files: dict[str, str]) -> list[str]:
    problems: list[str] = []
    recorded = {s.scenario.key: s.supersedes.key for s in registry.lineage}
    for key, s in sorted(by_key.items()):
        parent = from_files.get(key)
        if s.scenario_version > 1 and parent is None:
            problems.append(f"{key} has scenario_version above 1 but its file sets no supersedes")
            if key not in recorded:
                problems.append(f"{key} has scenario_version above 1 but the registry has no lineage entry")
        if parent is not None:
            if parent == key:
                problems.append(f"{key} supersedes itself")
            elif parent not in by_key:
                problems.append(f"{key} supersedes {parent}, which is not among the loaded scenarios")
            else:
                p = by_key[parent]
                if p.pair_id != s.pair_id:
                    # Decision B (Stage 4J.6B): an existing scenario identity never changes its pair_id through an
                    # ordinary revision. A different pairing needs a NEW scenario id (recorded through lineage, no
                    # inherited reviews, fresh authoring and review); there is no special re-pairing exception.
                    if p.scenario_id == s.scenario_id:
                        problems.append(f"{key} and its parent {parent} have different pair_id")
                elif p.truth_status != s.truth_status:
                    problems.append(f"{key} and its parent {parent} have different truth_status")
    for key, parent in sorted(recorded.items()):
        if key in by_key and parent not in by_key:
            problems.append(f"{key}: registry lineage names parent {parent}, which is not among the loaded scenarios")
    merged = {**recorded, **from_files}
    for start in sorted(by_key):
        cursor, walked = start, {start}
        while cursor in merged:
            cursor = merged[cursor]
            if cursor in walked:
                if cursor != start or merged[start] != start:
                    problems.append(f"supersession cycle through {start}")
                break
            walked.add(cursor)
    return problems


def check_registry(registry: Registry, scenarios: list[Scenario], repo_root: Path = REPO_ROOT) -> list[str]:
    """Cross-checks against the loaded scenario files. Returns problems (empty means consistent).

    Checks that cohort members exist and form whole true/false pairs, that lineage agrees with each
    scenario's own ``supersedes`` field in both directions AND that every loaded scenario whose file sets
    ``supersedes`` has a registry lineage entry and a loaded parent, that every loaded scenario with
    ``scenario_version`` above 1 has both, that a child shares ``pair_id`` and ``truth_status`` with its parent,
    that eligibility still holds when those fields are merged in, that every confirmatory member carries
    independent-review evidence whose current evidence bytes match the recorded hash (fail closed, single
    members included), and that every complete pair in a confirmatory cohort passes ``pair_review_problems``
    (with ``repo_root``). Pilot cohorts get no independent-review requirement. A revised child never inherits
    its parent's review validity: the content hash includes version and supersedes."""
    by_key = {f"{s.scenario_id}@{s.scenario_version}": s for s in scenarios}
    problems: list[str] = []
    for cohort in registry.cohorts:
        pair_truths: dict[str, list[str]] = {}
        pair_members: dict[str, list[Scenario]] = {}
        for m in cohort.members:
            s = by_key.get(m.key)
            if s is None:
                problems.append(f"{cohort.cohort_id}: {m.key} is not among the loaded scenarios")
                continue
            pair_truths.setdefault(s.pair_id, []).append(s.truth_status)
            pair_members.setdefault(s.pair_id, []).append(s)
            if cohort.family == "confirmatory":
                if s.status != "frozen":
                    problems.append(f"{cohort.cohort_id}: {m.key} has status {s.status!r}, not 'frozen'")
                for reason in independent_review_problems(s):
                    problems.append(f"{cohort.cohort_id}: {m.key}: {reason}")
                problems += [f"{cohort.cohort_id}: {p}" for p in _evidence_problems(s, repo_root)]
        for pair_id, truths in sorted(pair_truths.items()):
            if sorted(truths) != ["false", "true"]:
                problems.append(f"{cohort.cohort_id}: pair {pair_id} is not a complete true/false pair")
            elif cohort.family == "confirmatory":
                a, b = pair_members[pair_id]
                true_s, false_s = (a, b) if a.truth_status == "true" else (b, a)
                problems += [f"{cohort.cohort_id}: {p}" for p in pair_review_problems(true_s, false_s, repo_root=repo_root)]
        problems = list(dict.fromkeys(problems))

    from_files = {k: s.supersedes for k, s in by_key.items() if s.supersedes is not None}
    recorded = {s.scenario.key: s.supersedes.key for s in registry.lineage}
    for key, parent in from_files.items():
        if key not in recorded:
            problems.append(f"{key} supersedes {parent} but the registry has no lineage entry")
        elif recorded[key] != parent:
            problems.append(f"{key}: scenario file says it supersedes {parent}, registry says {recorded[key]}")
    for key, parent in recorded.items():
        if key in by_key and from_files.get(key) != parent:
            problems.append(f"{key}: registry says it supersedes {parent}, scenario file says {from_files.get(key)}")
    problems += _lineage_problems(registry, by_key, from_files)
    try:
        problems += confirmatory_violations(registry, from_files)
    except Exception as exc:  # defensive: a malformed merged graph must fail closed, not crash
        problems.append(f"lineage could not be evaluated: {type(exc).__name__}")
    return list(dict.fromkeys(problems))


class CohortGateError(ValueError):
    """The registry or the scenarios do not permit this run. ``problems`` lists every reason."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


def _assigned(registry: Registry, family: str) -> dict[str, str]:
    """scenario key -> cohort id, for cohorts of one family."""
    return {m.key: c.cohort_id for c in registry.cohorts if c.family == family for m in c.members}


def confirmatory_run_problems(
    registry: Registry,
    scenarios: list[Scenario],
    repo_root: Path = REPO_ROOT,
    exceptions: list[ScreeningException] | None = None,
) -> list[str]:
    """Every reason a confirmatory (``main``) run must be refused. Empty means the run may proceed.

    Fail-closed: every loaded scenario must be assigned to a confirmatory cohort by the registry (nothing is
    assigned here), the registry must be consistent with the scenario files (whole true/false pairs, lineage,
    real independent-review evidence, no pilot cohort, exposure or descent from either), and the mechanical
    checks on the scenario set (evidence length, false-value bounds, direction balance, names) must have no
    automatic failure. Human-review flags do not block."""
    problems = check_registry(registry, scenarios, repo_root)
    assigned = _assigned(registry, "confirmatory")
    for s in sorted(scenarios, key=lambda x: (x.scenario_id, x.scenario_version)):
        key = f"{s.scenario_id}@{s.scenario_version}"
        if key not in assigned:
            problems.append(f"{key} is not assigned to any confirmatory cohort in the registry")
    if not registry.cohorts or not any(c.family == "confirmatory" for c in registry.cohorts):
        problems.append("the registry has no confirmatory cohort")
    problems += mechanical_failures(scenarios, repo_root, exceptions)
    return problems


PILOT_ELIGIBLE_STATUSES = ("author_checked", "pilot_frozen")


def pilot_eligibility_problems(scenarios: list[Scenario], repo_root: Path = REPO_ROOT) -> list[str]:
    """Every reason a scenario may not enter a pilot cohort (Stage 4J.7). Empty means eligible.

    Per scenario: status must be ``author_checked`` or ``pilot_frozen`` (a ``draft`` fails); ``author_id`` is
    present; the recorded ``evidence.sha256`` is present, well formed and equals the CURRENT evidence bytes
    (``evidence_integrity_problems``); ``evidence.verification_status`` is not ``unverified``.

    ``author_checked`` is an AUTHOR self-check status only. It is not independent review, adjudication, protocol
    approval or a freeze, and this gate never treats it as any of those. Deterministic, no mutation; messages carry
    scenario keys and ids only, never claim values."""
    problems: list[str] = []
    for s in sorted(scenarios, key=lambda x: (x.scenario_id, x.scenario_version)):
        key = _key(s)
        if s.status not in PILOT_ELIGIBLE_STATUSES:
            problems.append(f"{key}: pilot gate needs status 'author_checked' or 'pilot_frozen', found {s.status!r}")
        if not s.author_id or not s.author_id.strip():
            problems.append(f"{key}: pilot gate needs an author_id")
        problems += _evidence_problems(s, repo_root)
        if s.evidence.verification_status == "unverified":
            problems.append(f"{key}: evidence verification_status is 'unverified'")
    return list(dict.fromkeys(problems))


def pilot_run_problems(registry: Registry, scenarios: list[Scenario], repo_root: Path = REPO_ROOT) -> list[str]:
    """Checks for a pilot run that was given a registry: every loaded scenario is in a pilot cohort, the
    registry agrees with the scenario files, and every assigned scenario passes ``pilot_eligibility_problems``.
    Pilot exposure is NOT recorded by this check."""
    problems = check_registry(registry, scenarios, repo_root)
    assigned = _assigned(registry, "pilot")
    for s in sorted(scenarios, key=lambda x: (x.scenario_id, x.scenario_version)):
        key = f"{s.scenario_id}@{s.scenario_version}"
        if key not in assigned:
            problems.append(f"{key} is not assigned to any pilot cohort in the registry")
    problems += pilot_eligibility_problems([s for s in scenarios if _key(s) in assigned], repo_root)
    return list(dict.fromkeys(problems))


def require_confirmatory_run(
    registry: Registry,
    scenarios: list[Scenario],
    repo_root: Path = REPO_ROOT,
    exceptions: list[ScreeningException] | None = None,
) -> None:
    problems = confirmatory_run_problems(registry, scenarios, repo_root, exceptions)
    if problems:
        raise CohortGateError(problems)


def require_pilot_registry(registry: Registry, scenarios: list[Scenario], repo_root: Path = REPO_ROOT) -> None:
    problems = pilot_run_problems(registry, scenarios, repo_root)
    if problems:
        raise CohortGateError(problems)


# ---- Stage 4J.7: cohort PROPOSAL (not a freeze, not a registry) -------------------------------------------------
PROPOSAL_STATUS = "PROPOSED — NOT FIXED"


class ProposalMember(_Strict):
    scenario: ScenarioRef
    scenario_sha256: str
    evidence_sha256: str | None = None


class CohortProposal(_Strict):
    """A proposed pilot cohort. It fixes nothing: ``fixed_on`` must be null, and the only path to a ``Registry`` is
    ``proposal_to_registry`` with an owner-supplied timestamp. Recorded hashes go stale when a scenario or its
    evidence changes and must then be regenerated."""

    proposal_id: str
    status: Literal["PROPOSED — NOT FIXED"]
    family: Literal["pilot"]
    fixed_on: None
    members: list[ProposalMember]
    note: str

    @model_validator(mode="after")
    def _check(self) -> CohortProposal:
        _identifier(self.proposal_id, "proposal_id")
        return self


def build_cohort_proposal(scenarios: list[Scenario], proposal_id: str, repo_root: Path = REPO_ROOT) -> CohortProposal:
    members = []
    for s in sorted(scenarios, key=lambda x: (x.scenario_id, x.scenario_version)):
        try:
            ev = file_sha256(evidence_path(s, repo_root))
        except OSError:
            ev = None
        members.append(
            ProposalMember(
                scenario=ScenarioRef(scenario_id=s.scenario_id, scenario_version=s.scenario_version),
                scenario_sha256=scenario_content_sha256(s),
                evidence_sha256=ev,
            )
        )
    return CohortProposal(
        proposal_id=proposal_id,
        status=PROPOSAL_STATUS,
        family="pilot",
        fixed_on=None,
        members=members,
        note="Proposal only; not a cohort freeze and not a registry. Hashes are recorded at proposal time (draft-state "
        "hashes when the scenarios are drafts) and go stale when a scenario or its evidence changes, in particular at "
        "the author_checked transition; regenerate the proposal then, never patch it.",
    )


def load_cohort_proposal(path: str | Path) -> CohortProposal:
    return CohortProposal.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def _proposal_self_problems(proposal: CohortProposal) -> list[str]:
    problems: list[str] = []
    keys = [m.scenario.key for m in proposal.members]
    for k in sorted({k for k in keys if keys.count(k) > 1}):
        problems.append(f"proposal lists {k} more than once")
    if not proposal.members:
        problems.append("proposal has no members")
    if proposal.fixed_on is not None:
        problems.append("proposal fixed_on must be null")
    return problems


def cohort_proposal_problems(proposal: CohortProposal, scenarios: list[Scenario], repo_root: Path = REPO_ROOT) -> list[str]:
    """Every reason the proposal is invalid or stale against the loaded scenarios. Empty means consistent."""
    problems = _proposal_self_problems(proposal)
    by_key = {_key(s): s for s in scenarios}
    pair_truths: dict[str, list[str]] = {}
    for m in proposal.members:
        k = m.scenario.key
        s = by_key.get(k)
        if s is None:
            problems.append(f"{k}: not among the loaded scenarios at the stated version")
            continue
        pair_truths.setdefault(s.pair_id, []).append(s.truth_status)
        if m.scenario_sha256 != scenario_content_sha256(s):
            problems.append(f"{k}: recorded scenario_sha256 is stale")
        try:
            current = file_sha256(evidence_path(s, repo_root))
        except OSError:
            current = None
        if m.evidence_sha256 != current:
            problems.append(f"{k}: recorded evidence_sha256 is stale")
    for pair_id, truths in sorted(pair_truths.items()):
        if sorted(truths) != ["false", "true"]:
            problems.append(f"pair {pair_id} is not a complete true/false pair in the proposal")
    listed = {m.scenario.key for m in proposal.members}
    for k in sorted(set(by_key) - listed):
        problems.append(f"{k}: loaded scenario is not in the proposal")
    return list(dict.fromkeys(problems))


def proposal_to_registry(proposal: CohortProposal, cohort_id: str, fixed_on: str) -> Registry:
    """The only path from a proposal to a registry. Refuses a blank ``fixed_on`` (the owner supplies it) and a
    proposal whose own content is invalid. Staleness against scenario files is NOT visible here; callers must run
    ``cohort_proposal_problems`` first. Nothing calls this yet."""
    if not isinstance(fixed_on, str) or not fixed_on.strip():
        raise ValueError("fixed_on must be a non-blank owner-supplied timestamp")
    problems = _proposal_self_problems(proposal)
    if problems:
        raise ValueError("proposal is invalid: " + "; ".join(problems))
    return Registry(
        cohorts=[
            Cohort(
                cohort_id=cohort_id,
                family="pilot",
                members=[m.scenario for m in proposal.members],
                fixed_on=fixed_on,
            )
        ]
    )
