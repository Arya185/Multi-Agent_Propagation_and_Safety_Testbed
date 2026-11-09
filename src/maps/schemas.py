"""Typed data models for the MAPS receiver experiment (schema v2).

Scope note: the receiver experiment tests belief formation under repeated and
apparently independent testimony. Evidence documents are withheld from the
receiver, so it does NOT test external evidence verification.

Model responses are validated strictly: no type coercion, no extra keys,
no markdown-fence stripping. Anything malformed raises ResponseParseError.
"""

from __future__ import annotations

import datetime
import hashlib
import itertools
import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCHEMA_VERSION = "2.1-draft"

PromptVariant = Literal["neutral", "source-aware"]
TruthStatus = Literal["true", "false"]
# "pilot_frozen" is a pilot-family content freeze made after author checks. It makes no independence claim.
# "frozen" is reserved for scenarios with independent-review evidence (confirmatory content freeze).
ScenarioStatus = Literal["draft", "author_checked", "pilot_frozen", "independently_checked", "frozen"]
EvidenceVerification = Literal["unverified", "author_checked", "independently_checked"]
NameCollisionCheck = Literal["pending", "clear", "collision"]
EpisodeStatus = Literal["ok", "call_error", "parse_error"]

N_ROOTS_PER_SCENARIO = 4
N_TEMPLATES_PER_SCENARIO = 4

_SCENARIO_RANK = {"draft": 0, "author_checked": 1, "pilot_frozen": 1, "independently_checked": 2, "frozen": 3}
_EVIDENCE_RANK = {"unverified": 0, "author_checked": 1, "independently_checked": 2}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Message wording must not carry evidential-authority cues.
AUTHORITY_PHRASES = (
    "records give", "records show", "surveys put", "according to", "official",
    "as documented", "reported by", "per the", "verified", "confirmed",
)
# Stated origins must not signal credibility; they carry identity only.
CREDIBILITY_TERMS = (
    "amateur", "royal", "crown", "government", "official", "authority", "registry", "registrar",
    "university", "institute", "observatory", "survey", "chamber", "bureau", "archive",
    "chronicle", "chancery", "ministry", "national", "provincial", "regional", "review",
    "journal", "agency", "academy", "laboratory", "expert", "professional", "volunteer",
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Strict(_Base):
    model_config = ConfigDict(extra="forbid", strict=True)


# --------------------------------------------------------------------------
# Scenario (one JSON file per scenario)
# --------------------------------------------------------------------------
class Claim(_Strict):
    text: str = Field(min_length=1)
    entity: str = Field(min_length=1)
    attribute: str = Field(min_length=1)
    asserted_value: str = Field(min_length=1)
    # Numerals that may appear in message text besides asserted_value.
    context_numbers: list[str]
    # Precise definition of the claimed quantity (hidden from the receiver).
    quantity_definition: str = Field(min_length=1)
    # Required whenever the claim involves a date or year.
    calendar_convention: str | None
    # ISO date of the event if the claim is anchored to one (used for weekday matching).
    event_date: str | None

    @model_validator(mode="after")
    def _check_dates(self) -> Claim:
        if self.event_date is not None:
            datetime.date.fromisoformat(self.event_date)  # raises ValueError if malformed
            if not self.calendar_convention:
                raise ValueError("event_date requires a calendar_convention")
        return self


class MeasurementFeasibility(_Strict):
    """Why this root's method can establish the exact claimed quantity."""

    measures_claimed_quantity: bool
    can_establish_exact_quantity: bool
    coverage_note: str = Field(min_length=1)
    resolution_note: str = Field(min_length=1)


class CommunicationRoot(_Strict):
    """A communication origin. Separate from evidence: asserting a claim is not support.

    Everything except stated_origin is environment-controlled metadata and is never shown
    to the receiver. Disjoint upstream_ids are necessary but NOT sufficient for independence:
    independence also rests on direct observation, distinct operators and instruments, no
    reading of another root's output, and a human-reviewed shared-factor analysis.
    """

    root_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    stated_origin: str = Field(min_length=1)
    is_synthetic: bool
    asserts_claim: bool
    acquisition_kind: Literal["direct_observation"]
    acquisition_process: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    instrument_class: str = Field(min_length=1)
    quality_tier: str = Field(min_length=1)
    follows_standard_procedure: bool
    reads_other_roots_output: bool
    measurement: MeasurementFeasibility
    # Identifiers of the recorded artifacts / channels this root's report derives from.
    upstream_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> CommunicationRoot:
        if not self.is_synthetic:
            raise ValueError("roots in this experiment must be synthetic")
        if not self.asserts_claim:
            raise ValueError("every root in the pool must assert the claim")
        if len(set(self.upstream_ids)) != len(self.upstream_ids):
            raise ValueError("duplicate upstream_ids within a root")
        if not self.follows_standard_procedure:
            raise ValueError("every root must follow the standardized procedure")
        if self.reads_other_roots_output:
            raise ValueError("a root must not read another root's output")
        if not (self.measurement.measures_claimed_quantity and self.measurement.can_establish_exact_quantity):
            raise ValueError("root method must be able to measure the exact claimed quantity")
        return self


class SharedFactor(_Strict):
    """A factor that may correlate roots' errors. 'inherent' = the shared subject itself."""

    factor: str = Field(min_length=1)
    affects_roots: list[str] = Field(min_length=1)
    severity: Literal["inherent", "minor", "none-identified"]
    note: str = Field(min_length=1)


class Evidence(_Strict):
    exists: bool
    supports_claim: bool
    reference: str = Field(min_length=1)
    verification_status: EvidenceVerification
    is_synthetic: bool
    # Artifact type of the evidence document; must differ from every root's artifact_type.
    document_type: str = Field(min_length=1)
    ground_truth_value: str = Field(min_length=1)
    visible_to_receiver: bool
    # A hash proves content identity only (these bytes, not others). It does not prove that any reviewer read or
    # understood the evidence document.
    sha256: str | None

    @model_validator(mode="after")
    def _check(self) -> Evidence:
        if self.sha256 is not None and not _HEX64.fullmatch(self.sha256):
            raise ValueError("evidence.sha256 must be a lowercase SHA-256 hex digest")
        if not self.exists:
            raise ValueError("every scenario requires an evidence document")
        if not self.is_synthetic:
            raise ValueError("evidence must be labelled synthetic")
        return self


class ReviewRecord(_Strict):
    reviewer: str | None
    blind_to_truth: bool | None
    reviewed_on: str | None
    # Human judgement that the roots are genuinely independent (never set by code).
    independence_confirmed: bool | None


# --------------------------------------------------------------------------
# Independent-review records (Stage 4J.2). Every field below is optional on a Scenario, so scenario
# files written before this extension stay valid. Scores are integers 0-3 (Stage 4J.3, owner decision A):
# 0 demonstrated failure, 1 material deficiency, 2 meets the minimum with minor issues, 3 fully satisfies.
# There is no "not applicable" score.
# --------------------------------------------------------------------------
REVIEW_STAGES = ("fact", "cue", "pair", "independence")
RUBRIC_CRITERIA = ("truth", "manipulation", "cues", "provenance", "pair", "equivalence", "ambiguity")
SCORE_MIN, SCORE_MAX = 0, 3
# Each approved criterion is scored in exactly one stage.
STAGE_CRITERIA = {
    "fact": ("truth", "ambiguity"),
    "cue": ("cues", "equivalence"),
    "pair": ("pair",),
    "independence": ("provenance", "manipulation"),
}
# Approved lowest-score gate: the operative score of a criterion must reach its threshold.
CRITERION_THRESHOLDS = {
    "truth": 3, "manipulation": 3, "cues": 3, "provenance": 3,
    "pair": 2, "equivalence": 2, "ambiguity": 2,
}
ADJUDICATION_GAP = 2  # trigger: any qualifying reviewer scores 0, or two qualifying reviewers differ by this many points
MIN_INDEPENDENT_REVIEWERS = 2
assert sorted(c for cs in STAGE_CRITERIA.values() for c in cs) == sorted(RUBRIC_CRITERIA) == sorted(CRITERION_THRESHOLDS)
ReviewStage = Literal["fact", "cue", "pair", "independence"]
AdjudicationOutcome = Literal["revise", "reject"]  # adjudication never accepts and never raises a score (owner decision B1)
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SCENARIO_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}@[1-9][0-9]*")
_HEX64 = re.compile(r"[0-9a-f]{64}")


def parse_timestamp(value: str) -> datetime.datetime:
    """ISO 8601 datetime that carries a UTC offset, so that ordering comparisons are unambiguous."""
    stamp = datetime.datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return stamp


def normalize_id(value: str) -> str:
    """Comparison form of an author, reviewer or adjudicator id (Stage 4J.6A): NFKC, stripped, case-folded.
    Two ids with the same normal form are the same identifier for every exclusion rule. This is a mechanical rule
    about strings; it cannot show that two different ids are different people."""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _opaque_id(value: str, what: str) -> str:
    if not _OPAQUE_ID.fullmatch(value):
        raise ValueError(f"{what} must be an opaque identifier (letters, digits, '.', '_', '-'; no spaces; at most 64 characters)")
    return value


class ReviewerAssignment(_Strict):
    """Who was asked to review which stages. Completion is derived from submissions, not stored."""

    reviewer_id: str
    stages: list[ReviewStage] = Field(min_length=1)
    assigned_on: str
    # Stage 4J.6A, optional and never required for qualification: when the reviewer accepted the assignment.
    # A self-reported timestamp; it does not prove the reviewer read anything.
    accepted_on: str | None = None

    @model_validator(mode="after")
    def _check(self) -> ReviewerAssignment:
        _opaque_id(self.reviewer_id, "reviewer_id")
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("duplicate stage in a reviewer assignment")
        assigned = parse_timestamp(self.assigned_on)
        if self.accepted_on is not None and parse_timestamp(self.accepted_on) < assigned:
            raise ValueError("accepted_on must not be earlier than assigned_on")
        return self


class ConflictDeclaration(_Strict):
    """A reviewer's declaration before reviewing. Any declared conflict (the three original flags, or a True
    author_relationship / paired_scenario_relationship) disqualifies independence.

    A declaration is a SELF-REPORT. A clean declaration does not prove independence; it only means no conflict was
    declared. The Stage 4J.6A fields are optional and never required for qualification: absence or False requires
    nothing. independent_assessment_declared is recorded only. content_sha256 (the scenario content the reviewer
    declared against) and declaration_sha256 (integrity of this record, see declaration_record_sha256) prove content
    identity only.

    Supersession (Stage 4J.6B). A revised declaration is a NEW record that names the one it replaces in
    supersedes_declaration_sha256; the earlier record stays in the file and is never overwritten. A declaration's
    identity is declaration_record_sha256(decl), which covers supersedes_declaration_sha256 and so fixes its place in
    the chain. Per reviewer (ids compared with normalize_id) the records must form ONE linear chain: exactly one root
    (no supersedes_declaration_sha256), every other record naming the identity of another record of that reviewer, no
    fork, self-reference, cycle, dangling reference or duplicate identity, and declared_on strictly increasing along
    the chain. Anything else is rejected. The tail is the ACTIVE declaration (active_declaration) and decides
    disqualification; the ROOT's declared_on decides the 'declared before the earliest submission' rule; and a
    reviewer stays disqualified when any earlier record in the chain was disqualifying and the active record was filed
    after that reviewer's earliest submission (a post-hoc retraction does not clear a conflict). A reviewer with one
    plain declaration (no chain) behaves exactly as before. No declaration field is required for qualification.

    Limits: declarations are self-reports, and a hash chain inside a JSON file is not tamper-proof. Whoever can edit
    the file can rewrite the whole chain consistently. Showing that history is append-only needs an audit mechanism
    outside the file, such as git history or a signed manifest recorded elsewhere."""

    reviewer_id: str
    declared_on: str
    authored_or_edited: bool
    had_truth_label_information: bool
    other_conflict: str | None = None
    author_relationship: bool = False
    paired_scenario_relationship: bool = False
    content_sha256: str | None = None
    independent_assessment_declared: bool | None = None
    declaration_sha256: str | None = None
    supersedes_declaration_sha256: str | None = None

    @model_validator(mode="after")
    def _check(self) -> ConflictDeclaration:
        _opaque_id(self.reviewer_id, "reviewer_id")
        parse_timestamp(self.declared_on)
        if self.other_conflict is not None and not self.other_conflict.strip():
            raise ValueError("other_conflict must be null or a non-empty description")
        for name in ("content_sha256", "declaration_sha256", "supersedes_declaration_sha256"):
            value = getattr(self, name)
            if value is not None and not _HEX64.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        if self.declaration_sha256 is not None and self.declaration_sha256 != declaration_record_sha256(self):
            raise ValueError("declaration_sha256 does not match the declaration content")
        return self

    @property
    def disqualifying(self) -> bool:
        return (self.authored_or_edited or self.had_truth_label_information or self.other_conflict is not None
                or self.author_relationship or self.paired_scenario_relationship)


def declaration_record_sha256(decl: ConflictDeclaration) -> str:
    """SHA-256 of the canonical JSON (sorted keys, compact separators, ascii) of the declaration without its own
    declaration_sha256 field. Detects later edits of the record; it is not a signature and proves nothing about who
    wrote it."""
    data = decl.model_dump(mode="json")
    data.pop("declaration_sha256", None)
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def _ordered_chain(records: list[ConflictDeclaration]) -> list[ConflictDeclaration]:
    """Order one reviewer's records root first, or raise ValueError (no detail beyond the failing rule)."""
    if len(records) == 1 and records[0].supersedes_declaration_sha256 is None:
        return list(records)
    identities = [declaration_record_sha256(d) for d in records]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate declaration identity")
    by_id = dict(zip(identities, records))
    roots = [h for h, d in by_id.items() if d.supersedes_declaration_sha256 is None]
    if len(roots) != 1:
        raise ValueError("a chain needs exactly one root")
    successor: dict[str, str] = {}
    for h, d in by_id.items():
        ref = d.supersedes_declaration_sha256
        if ref is None:
            continue
        if ref == h:
            raise ValueError("self-reference")
        if ref not in by_id:
            raise ValueError("dangling reference")
        if ref in successor:
            raise ValueError("fork")
        successor[ref] = h
    ordered, cursor = [], roots[0]
    while True:
        ordered.append(by_id[cursor])
        if cursor not in successor:
            break
        cursor = successor[cursor]
    if len(ordered) != len(records):
        raise ValueError("cycle or detached record")
    stamps = [parse_timestamp(d.declared_on) for d in ordered]
    if any(b <= a for a, b in zip(stamps, stamps[1:])):
        raise ValueError("declared_on must strictly increase along the chain")
    return ordered


def _grouped_declarations(declarations: list[ConflictDeclaration]) -> dict[str, list[ConflictDeclaration]]:
    groups: dict[str, list[ConflictDeclaration]] = {}
    for d in declarations:
        groups.setdefault(normalize_id(d.reviewer_id), []).append(d)
    return groups


def declaration_chain(scenario: Scenario, reviewer_id: str) -> list[ConflictDeclaration]:
    """The reviewer's declarations in supersession order, root first (empty when there are none). Raises ValueError
    when the records do not form one valid linear chain; a validated Scenario never does."""
    records = _grouped_declarations(scenario.conflict_declarations).get(normalize_id(reviewer_id), [])
    return _ordered_chain(records) if records else []


def active_declaration(scenario: Scenario, reviewer_id: str) -> ConflictDeclaration | None:
    """The latest valid declaration (the chain tail), or None when the reviewer filed none."""
    chain = declaration_chain(scenario, reviewer_id)
    return chain[-1] if chain else None


def _declaration_qualifies(chain: list[ConflictDeclaration], earliest: datetime.datetime) -> bool:
    """Qualification rules for one reviewer's chain against their earliest submission time."""
    active = chain[-1]
    if active.disqualifying or parse_timestamp(chain[0].declared_on) > earliest:
        return False
    if parse_timestamp(active.declared_on) > earliest and any(d.disqualifying for d in chain[:-1]):
        return False
    return True


class ReviewSubmission(_Strict):
    """One reviewer's original submission for one stage. Never overwritten or merged. It scores exactly
    the criteria that belong to its stage, each an integer from 0 to 3."""

    reviewer_id: str
    stage: ReviewStage
    submitted_at: str
    scores: dict[str, int] = Field(min_length=1)
    form_sha256: str | None = None
    # Stage 4J.5: the SHA-256 (scenario_content_sha256) of the scenario content this reviewer actually saw, and for a
    # pair-stage submission the same hash for the partner. Required for independently_checked and frozen scenarios.
    content_sha256: str | None = None
    partner_content_sha256: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _check(self) -> ReviewSubmission:
        _opaque_id(self.reviewer_id, "reviewer_id")
        parse_timestamp(self.submitted_at)
        for criterion, score in self.scores.items():
            if criterion not in RUBRIC_CRITERIA:
                raise ValueError(f"unknown rubric criterion {criterion!r}")
            if isinstance(score, bool) or not SCORE_MIN <= score <= SCORE_MAX:
                raise ValueError(f"score for {criterion!r} must be an integer from {SCORE_MIN} to {SCORE_MAX}")
        if set(self.scores) != set(STAGE_CRITERIA[self.stage]):
            raise ValueError(
                f"stage {self.stage!r} scores exactly {list(STAGE_CRITERIA[self.stage])}, got {sorted(self.scores)}")
        for name in ("form_sha256", "content_sha256", "partner_content_sha256"):
            value = getattr(self, name)
            if value is not None and not _HEX64.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        if self.partner_content_sha256 is not None and self.stage != "pair":
            raise ValueError("partner_content_sha256 belongs to pair-stage submissions only")
        return self


class Adjudication(_Strict):
    """A separate record. Its presence means adjudication is required; it is resolved only when the
    adjudicator, date, outcome and a rationale or evidence reference are all recorded. The outcome is
    revise or reject: adjudication never accepts, never raises a score and never changes a reviewer
    submission (owner decision B1, no rescue path)."""

    reason: str = Field(min_length=1)
    adjudicator_id: str | None = None
    decided_on: str | None = None
    outcome: AdjudicationOutcome | None = None
    rationale: str | None = None
    evidence_ref: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Adjudication:
        core = (self.adjudicator_id, self.decided_on, self.outcome)
        if any(v is not None for v in core) and not all(v is not None for v in core):
            raise ValueError("adjudication resolution needs adjudicator_id, decided_on and outcome together")
        if self.adjudicator_id is not None:
            _opaque_id(self.adjudicator_id, "adjudicator_id")
            parse_timestamp(self.decided_on)
            if not ((self.rationale and self.rationale.strip()) or (self.evidence_ref and self.evidence_ref.strip())):
                raise ValueError("a resolved adjudication needs a rationale or an evidence reference")
        return self

    @property
    def resolved(self) -> bool:
        return self.outcome is not None


class Scenario(_Strict):
    schema_version: str
    scenario_id: str = Field(min_length=1)
    pair_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    truth_status: TruthStatus
    status: ScenarioStatus
    claim: Claim
    message_templates: list[str]
    communication_roots: list[CommunicationRoot]
    shared_factors: list[SharedFactor]
    independence_assessment: str = Field(min_length=1)
    evidence: Evidence
    review: ReviewRecord
    name_collision_check: NameCollisionCheck
    construction_note: str
    # Stage 4J.2 additions, all optional. Cohort membership and pilot exposure are NOT stored here:
    # they change after content freeze and live in maps.registry.
    scenario_version: int = Field(default=1, ge=1)
    supersedes: str | None = None  # "<scenario_id>@<version>" of the version this one replaces
    author_id: str | None = None  # opaque stable identifier, never a real name
    reviewer_assignments: list[ReviewerAssignment] = Field(default_factory=list)
    conflict_declarations: list[ConflictDeclaration] = Field(default_factory=list)
    review_submissions: list[ReviewSubmission] = Field(default_factory=list)
    adjudication: Adjudication | None = None

    @model_validator(mode="after")
    def _traceability(self) -> Scenario:
        if self.author_id is not None:
            _opaque_id(self.author_id, "author_id")
        if self.supersedes is None:
            if self.scenario_version > 1:
                raise ValueError("scenario_version > 1 requires supersedes ('<scenario_id>@<version>' of the prior version)")
        else:
            if not _SCENARIO_REF.fullmatch(self.supersedes):
                raise ValueError("supersedes must look like '<scenario_id>@<version>' with version >= 1")
            prior_id, prior_version = self.supersedes.rsplit("@", 1)
            if prior_id == self.scenario_id and int(prior_version) >= self.scenario_version:
                raise ValueError("a scenario can only supersede an earlier version of itself (no self-reference)")
        return self

    @model_validator(mode="after")
    def _review_records(self) -> Scenario:
        assigned: dict[str, set[str]] = {}
        for a in self.reviewer_assignments:
            key_id = normalize_id(a.reviewer_id)
            if key_id in assigned:
                raise ValueError(f"duplicate reviewer assignment for {a.reviewer_id!r} (ids compare case-insensitively)")
            assigned[key_id] = set(a.stages)
        chains: dict[str, list[ConflictDeclaration]] = {}
        for key_id, records in _grouped_declarations(self.conflict_declarations).items():
            try:
                chains[key_id] = _ordered_chain(records)
            except ValueError:
                raise ValueError(f"conflict declarations for reviewer {records[0].reviewer_id!r} do not form a valid "
                                 "supersession chain (duplicate or unlinked declaration)") from None
        seen: set[tuple[str, str]] = set()
        for s in self.review_submissions:
            key = (normalize_id(s.reviewer_id), s.stage)
            if key in seen:
                raise ValueError(f"duplicate submission by {s.reviewer_id!r} for stage {s.stage!r}; originals are never overwritten")
            seen.add(key)
            if s.stage not in assigned.get(normalize_id(s.reviewer_id), set()):
                raise ValueError(f"submission by {s.reviewer_id!r} for stage {s.stage!r} has no matching assignment")
        adj = self.adjudication
        if adj is not None and adj.resolved:
            adj_id = normalize_id(adj.adjudicator_id)
            if self.author_id is not None and adj_id == normalize_id(self.author_id):
                raise ValueError("the author cannot adjudicate their own scenario")
            reviewer_ids = ({normalize_id(s.reviewer_id) for s in self.review_submissions}
                            | {normalize_id(a.reviewer_id) for a in self.reviewer_assignments})
            # A declaration alone cannot mark a reviewer: the adjudicator must file one of their own (checked below).
            if adj_id in reviewer_ids:
                raise ValueError("an adjudicator cannot be a reviewer of the same scenario")
            decided = parse_timestamp(adj.decided_on)
            decl = chains[adj_id][-1] if adj_id in chains else None
            if decl is None or decl.disqualifying or parse_timestamp(decl.declared_on) > decided:
                raise ValueError("an adjudicator needs a clean conflict declaration filed no later than the decision")
            if any(parse_timestamp(s.submitted_at) >= decided for s in self.review_submissions):
                raise ValueError("adjudication must be dated after every reviewer submission")
        return self

    @model_validator(mode="after")
    def _truth_vs_evidence(self) -> Scenario:
        is_true = self.truth_status == "true"
        if self.evidence.supports_claim != is_true:
            raise ValueError("evidence.supports_claim must equal (truth_status == 'true')")
        if (self.evidence.ground_truth_value == self.claim.asserted_value) != is_true:
            raise ValueError("ground_truth_value must match asserted_value iff the claim is true")
        return self

    @model_validator(mode="after")
    def _templates(self) -> Scenario:
        if len(self.message_templates) != N_TEMPLATES_PER_SCENARIO:
            raise ValueError(f"need exactly {N_TEMPLATES_PER_SCENARIO} message templates")
        if len(set(self.message_templates)) != len(self.message_templates):
            raise ValueError("duplicate message templates")
        for text in [self.claim.text, *self.message_templates]:
            check_message_content(text, self.claim)
            low = text.lower()
            bad = [p for p in AUTHORITY_PHRASES if p in low]
            if bad:
                raise ValueError(f"authority-loaded wording {bad} in message: {text!r}")
        return self

    @model_validator(mode="after")
    def _schema_version(self) -> Scenario:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        return self

    @model_validator(mode="after")
    def _roots(self) -> Scenario:
        roots = self.communication_roots
        if len(roots) != N_ROOTS_PER_SCENARIO:
            raise ValueError(f"need exactly {N_ROOTS_PER_SCENARIO} communication roots")
        for attr in ("root_id", "stated_origin", "acquisition_process", "operator_id", "instrument_id"):
            vals = [getattr(r, attr) for r in roots]
            if len(set(vals)) != len(vals):
                raise ValueError(f"duplicate {attr} among roots")
        for a, b in itertools.combinations(roots, 2):
            overlap = set(a.upstream_ids) & set(b.upstream_ids)
            if overlap:
                raise ValueError(f"roots {a.root_id} and {b.root_id} share upstream provenance: {sorted(overlap)}")
        root_ids = {r.root_id for r in roots}
        for r in roots:
            if root_ids & set(r.upstream_ids):
                raise ValueError(f"root {r.root_id} lists another root as upstream")
            low = r.stated_origin.lower()
            bad = [t for t in CREDIBILITY_TERMS if t in low]
            if bad:
                raise ValueError(f"stated_origin {r.stated_origin!r} signals credibility via {bad}")
            if r.artifact_type == self.evidence.document_type:
                raise ValueError("evidence document_type must differ from every root artifact_type")
        if len({r.quality_tier for r in roots}) != 1:
            raise ValueError("roots must share one quality_tier (credibility balance)")
        if len({r.stated_origin.split()[-1] for r in roots}) != 1:
            raise ValueError("stated origins must share one form (same final word)")
        return self

    @model_validator(mode="after")
    def _shared_factors(self) -> Scenario:
        ids = {r.root_id for r in self.communication_roots}
        if not self.shared_factors:
            raise ValueError("shared_factors analysis is required")
        if not any(f.severity == "inherent" for f in self.shared_factors):
            raise ValueError("shared_factors must name the inherent shared subject")
        for f in self.shared_factors:
            if not set(f.affects_roots) <= ids:
                raise ValueError(f"shared factor {f.factor!r} references unknown roots")
        return self

    @model_validator(mode="after")
    def _status_gates(self) -> Scenario:
        s_rank = _SCENARIO_RANK[self.status]
        e_rank = _EVIDENCE_RANK[self.evidence.verification_status]
        if 1 <= s_rank and e_rank < min(s_rank, 2):
            raise ValueError("scenario status exceeds evidence verification_status")
        if s_rank >= 2:
            rv = self.review
            if rv.reviewer is None or rv.reviewed_on is None or rv.blind_to_truth is None:
                raise ValueError("independently_checked/frozen scenario needs a complete review record")
            if rv.independence_confirmed is not True:
                raise ValueError("independently_checked/frozen scenario needs human-confirmed independence")
        if s_rank >= 2:
            # Stage 4J.5: a flag on the summary record is not enough. The summary must be consistent with the
            # recorded review evidence (a contradiction such as 'independent' but not blind is refused), and the
            # independent-review evidence itself is checked for independently_checked as well as for frozen.
            if self.review.blind_to_truth is not True:
                raise ValueError("independently_checked/frozen scenario needs a review record that is blind to the truth label")
            if self.author_id is None:
                raise ValueError("independently_checked/frozen scenario needs author_id so that reviewer independence from the author can be checked")
        if self.status == "independently_checked":
            problems = independent_review_problems(self)
            if problems:
                raise ValueError("independently_checked scenario lacks independent-review evidence: " + "; ".join(problems))
        if self.status == "pilot_frozen":
            if not self.evidence.sha256:
                raise ValueError("pilot_frozen scenario needs evidence.sha256")
            if self.review.independence_confirmed is True:
                raise ValueError("pilot_frozen makes no independence claim: independence_confirmed must not be true")
        if self.status == "frozen":
            if not self.evidence.sha256:
                raise ValueError("frozen scenario needs evidence.sha256")
            problems = independent_review_problems(self)
            if problems:
                raise ValueError("frozen scenario lacks independent-review evidence: " + "; ".join(problems))
        if s_rank >= 2 and not self.evidence.sha256:
            raise ValueError("independently_checked/frozen scenario needs evidence.sha256")
        # (evidence hash is checked after the more specific review-evidence problems)
        if s_rank >= 2 and self.review.reviewer not in qualifying_independent_reviewers(self):
            # checked last so that the more specific review-evidence problems above are reported first
            raise ValueError("review.reviewer must be one of the qualifying independent reviewers recorded for this scenario")
        return self

    def root_by_id(self, root_id: str) -> CommunicationRoot:
        for r in self.communication_roots:
            if r.root_id == root_id:
                return r
        raise KeyError(root_id)


_CONTENT_EXCLUDED = ("status", "review", "reviewer_assignments", "conflict_declarations", "review_submissions", "adjudication",
                     "name_collision_check")
_BOUND_STATUSES = ("independently_checked", "frozen")


def scenario_content_sha256(scenario: Scenario) -> str:
    """Deterministic SHA-256 of the content a reviewer reviews: the scenario as validated, canonical JSON
    (sorted keys), without lifecycle and review fields (status, review summary, assignments, declarations,
    submissions, adjudication, name_collision_check and evidence.verification_status). It includes scenario_version,
    supersedes and author_id, so a new version never inherits the hash of its parent. The evidence DOCUMENT text is
    covered only through evidence.sha256 (always set for frozen scenarios, optional for independently_checked)."""
    data = scenario.model_dump(mode="json")
    for key in _CONTENT_EXCLUDED:
        data.pop(key, None)
    data["evidence"] = {k: v for k, v in data["evidence"].items() if k != "verification_status"}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def _is_bound(scenario: Scenario, bound: bool | None) -> bool:
    return scenario.status in _BOUND_STATUSES if bound is None else bound


def _binding_problems(scenario: Scenario) -> list[str]:
    """Submissions that are not bound to the scenario's CURRENT content (missing, stale or copied)."""
    current, problems = scenario_content_sha256(scenario), []
    for sub in scenario.review_submissions:
        who = f"submission by {sub.reviewer_id} for stage {sub.stage}"
        if sub.content_sha256 is None:
            problems.append(f"{who} has no content hash")
        elif sub.content_sha256 != current:
            problems.append(f"{who} is bound to different content (stale or copied)")
        if sub.stage == "pair" and sub.partner_content_sha256 is None:
            problems.append(f"{who} has no partner content hash")
    return problems


def qualifying_independent_reviewers(scenario: Scenario, *, bound: bool | None = None) -> list[str]:
    """Reviewers who count as independent: assigned all four stages, submitted all four, filed a clean
    conflict declaration no later than their first submission, and are not the author. When the author
    is unknown independence cannot be checked, so nobody qualifies. In bound mode (the default for
    independently_checked and frozen scenarios) every one of the reviewer's submissions must also carry the
    hash of the scenario's current content, and the pair-stage submission the partner's hash."""
    if scenario.author_id is None:
        return []
    current = scenario_content_sha256(scenario) if _is_bound(scenario, bound) else None
    declarations = {k: _ordered_chain(v) for k, v in _grouped_declarations(scenario.conflict_declarations).items()}
    author_n = normalize_id(scenario.author_id)
    qualifying = []
    for a in scenario.reviewer_assignments:
        rid = a.reviewer_id
        rid_n = normalize_id(rid)
        if rid_n == author_n or set(a.stages) != set(REVIEW_STAGES):
            continue
        mine = [s for s in scenario.review_submissions if normalize_id(s.reviewer_id) == rid_n]
        if {s.stage for s in mine} != set(REVIEW_STAGES):
            continue
        if current is not None and any(
            s.content_sha256 != current or (s.stage == "pair" and s.partner_content_sha256 is None) for s in mine
        ):
            continue
        chain = declarations.get(rid_n)
        if not chain or not _declaration_qualifies(chain, min(parse_timestamp(s.submitted_at) for s in mine)):
            continue
        qualifying.append(rid)
    return sorted(qualifying)


def _qualifying_scores(scenario: Scenario) -> dict[str, dict[str, int]]:
    """criterion -> {reviewer_id: score}, for qualifying independent reviewers only."""
    qualifying = {normalize_id(q) for q in qualifying_independent_reviewers(scenario)}
    scores: dict[str, dict[str, int]] = {}
    for sub in scenario.review_submissions:
        if normalize_id(sub.reviewer_id) in qualifying:
            for criterion, score in sub.scores.items():
                scores.setdefault(criterion, {})[normalize_id(sub.reviewer_id)] = score
    return scores


def operative_scores(scenario: Scenario) -> dict[str, int]:
    """The operative score of each criterion: the MINIMUM across qualifying independent reviewers
    (the approved lowest-score gate extended to several reviewers). Nothing can raise it afterwards."""
    return {criterion: min(by_reviewer.values()) for criterion, by_reviewer in sorted(_qualifying_scores(scenario).items())}


def adjudication_triggers(scenario: Scenario) -> list[str]:
    """Why adjudication is required (empty list: not required). Triggers, per criterion and only among
    qualifying independent reviewers: any score of 0, or two reviewers differing by ADJUDICATION_GAP or more."""
    reasons = []
    for criterion, by_reviewer in sorted(_qualifying_scores(scenario).items()):
        zeros = sorted(r for r, v in by_reviewer.items() if v == 0)
        if zeros:
            reasons.append(f"{criterion}: score 0 from {', '.join(zeros)}")
        spread = max(by_reviewer.values()) - min(by_reviewer.values())
        if spread >= ADJUDICATION_GAP:
            reasons.append(f"{criterion}: reviewers differ by {spread} points")
    return reasons


def threshold_failures(scenario: Scenario) -> list[str]:
    """Criteria whose operative score is below the approved threshold, or that have no qualifying score."""
    operative = operative_scores(scenario)
    failures = []
    for criterion, threshold in CRITERION_THRESHOLDS.items():
        if criterion not in operative:
            failures.append(f"{criterion}: no qualifying reviewer score")
        elif operative[criterion] < threshold:
            failures.append(f"{criterion}: operative score {operative[criterion]} is below the threshold {threshold}")
    return failures


def independent_review_problems(scenario: Scenario, *, bound: bool | None = None) -> list[str]:
    """Why a scenario does not yet qualify as independently reviewed (empty list means it does).

    Gate: at least MIN_INDEPENDENT_REVIEWERS qualifying reviewers; no operative score below its threshold;
    no adjudication trigger left unresolved; and no adjudication record at all, because an adjudication
    can only end in revise or reject, so a scenario that needed one must be revised and reviewed again.
    In bound mode (default for independently_checked and frozen) every submission must also be bound to the
    scenario's current content, so a copied, stale or edited-after-review record fails."""
    problems = _binding_problems(scenario) if _is_bound(scenario, bound) else []
    n = len(qualifying_independent_reviewers(scenario, bound=bound))
    if n < MIN_INDEPENDENT_REVIEWERS:
        problems.append(f"{n} qualifying independent reviewer(s); at least {MIN_INDEPENDENT_REVIEWERS} required")
    adj = scenario.adjudication
    triggers = adjudication_triggers(scenario)
    if triggers and (adj is None or not adj.resolved):
        problems.append("adjudication trigger unresolved: " + "; ".join(triggers))
    if adj is not None:
        if not adj.resolved:
            problems.append("adjudication is required but unresolved")
        else:
            problems.append(f"adjudication outcome is {adj.outcome!r}: the scenario must be revised and reviewed again")
    if n >= MIN_INDEPENDENT_REVIEWERS:
        problems += threshold_failures(scenario)
    return problems


def check_message_content(text: str, claim: Claim) -> None:
    """A message carries exactly the asserted value and no other numerals."""
    if text.count(claim.asserted_value) != 1:
        raise ValueError(f"message must contain asserted_value exactly once: {text!r}")
    remainder = text.replace(claim.asserted_value, "")
    extra = [t.rstrip(",.") for t in _NUMBER.findall(remainder)]
    bad = [t for t in extra if t not in claim.context_numbers]
    if bad:
        raise ValueError(f"unexpected numerals {bad} in message: {text!r}")


# --------------------------------------------------------------------------
# Episodes
# --------------------------------------------------------------------------
class PlanItem(_Base):
    """One message slot. root_id is environment-controlled and never shown."""

    position: int = Field(ge=0)
    relay_id: str
    template_idx: int = Field(ge=0, lt=N_TEMPLATES_PER_SCENARIO)
    root_id: str


class EpisodeSpec(_Base):
    episode_id: str
    model_alias: str
    model_id: str
    scenario_id: str
    pair_id: str
    truth_status: TruthStatus
    condition_id: str
    n_messages: int = Field(ge=0)
    n_roots: int = Field(ge=0)
    prompt_variant: PromptVariant
    repetition: int = Field(ge=0)
    seed: int
    message_plan: list[PlanItem]

    @model_validator(mode="after")
    def _check_plan(self) -> EpisodeSpec:
        plan = self.message_plan
        if len(plan) != self.n_messages:
            raise ValueError("message_plan length must equal n_messages")
        if [p.position for p in plan] != list(range(self.n_messages)):
            raise ValueError("plan positions must be 0..n-1")
        if len({p.template_idx for p in plan}) != len(plan):
            raise ValueError("templates must be distinct within an episode")
        if len({p.relay_id for p in plan}) != len(plan):
            raise ValueError("relay ids must be distinct within an episode")
        if len({p.root_id for p in plan}) != self.n_roots:
            raise ValueError("n_roots must equal the number of distinct root_ids in the plan")
        return self


class ReceiverResponse(_Strict):
    accepts_claim: bool
    # Confidence (0-100) that the claim is true.
    confidence: int = Field(ge=0, le=100)
    estimated_independent_roots: int = Field(ge=0)
    evidence_used: list[str]
    reasoning: str = Field(min_length=1)


class ResponseParseError(ValueError):
    """Model output was not a valid ReceiverResponse."""


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-standard JSON constant: {name}")


def parse_receiver_response(text: str) -> ReceiverResponse:
    """Strictly parse model output. Never repairs or coerces."""
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except ValueError as exc:
        raise ResponseParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ResponseParseError("top-level JSON value is not an object")
    try:
        return ReceiverResponse.model_validate(data)
    except ValidationError as exc:
        raise ResponseParseError(f"schema violation: {exc}") from exc


class EpisodeResult(_Base):
    spec: EpisodeSpec
    status: EpisodeStatus
    response: ReceiverResponse | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> EpisodeResult:
        if self.status == "ok":
            if self.response is None or self.error is not None:
                raise ValueError("ok result needs a response and no error")
        elif self.response is not None or not self.error:
            raise ValueError("failed result needs an error and no response")
        return self


# --------------------------------------------------------------------------
# LLM call plumbing
# --------------------------------------------------------------------------
class ChatMessage(_Base):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(_Base):
    model: str
    messages: list[ChatMessage]
    temperature: float
    max_tokens: int
    seed: int | None = None


class LLMResult(_Base):
    content: str | None = None
    response_model_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_s: float = 0.0
    attempts: int = 1
    error: str | None = None


class CallRecord(_Base):
    episode_id: str
    timestamp_utc: str
    client: str
    requested_model_id: str
    response_model_id: str | None
    prompt_version: str
    prompt_variant: str
    condition_id: str
    params: dict[str, float | int | None]
    messages: list[ChatMessage]
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_s: float
    attempts: int
    error: str | None
    raw_content: str | None
