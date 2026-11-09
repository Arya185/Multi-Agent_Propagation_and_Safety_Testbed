"""Pilot-readiness report (Stage 4J.7, Agent D): engineering checks plus a list of what the OWNER still has to decide.

NOT PART OF ANY RUN. Nothing imports this module; it stays outside the mock-run import closure. It never calls a
provider, never writes a file, never reads ``.env`` or any answer-key file (key custody is judged ONLY from the
policy-proposal file), and never approves anything. A report is READY only when it has no blocker, and even then the
text says that owner authorization is still required.

The policy proposal (``configs/pilot_policy_proposal.json``) is NOT a live policy: it has a value, a status and a
source per field and cannot be loaded by ``maps.runs.policy_source``. A field may be 'approved' only when
``approval_reference`` carries an owner-supplied value; nothing in this repository sets one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from maps.config import ExperimentConfig, load_config
from maps.scenarios import HASH_REQUIRED_STATUSES, REPO_ROOT, evidence_integrity_problems, load_scenario

PROPOSAL_STATUS = "PROPOSAL — NOT APPROVED"
APPROVED_TOP_STATUS = "APPROVED"
FIELD_STATUSES = ("proposed", "pending_owner", "approved")
PROPOSAL_SCHEMA = "maps-pilot-policy-proposal"


FIELD_NAMES = (
    "ps12_approach", "ps12_consec", "nonfatal_4xx_statuses", "fatal_3xx", "ps05a_max_episodes",
    "ps05b_max_request_attempts", "ps11", "ps13", "ps09_formula", "theta_fraction", "pi", "pi_breach_rule",
    "pi_breach_consequence", "policy_id", "profile_name", "approval_reference",
)
UNSET_PENDING = ("theta_fraction", "pi", "pi_breach_rule", "pi_breach_consequence")
OWNER_DECISION_NAMES = ("cohort", "hist_a_year_1612", "hist_b_wording", "near_duplicate_geo_sci", "author_id")
TOP_KEYS = ("schema", "schema_version", "status", "note", "fields", "owner_decisions", "custody", "attestation_file",
            "evidence_binding_route", "pilot_intent")
PILOT_INTENT_VALUES = ("NOT AUTHORIZED", "AUTHORIZED")
CUSTODY_STATUSES = ("pending_owner_action", "complete")
CUSTODY_COUNT = 5
ATTEMPT_FACTOR = 3
DEADLINE_SECONDS_PER_CALL = 183
MANIFEST_DRAFT = "DRAFT — NOT APPROVED"
READY_TEXT = "PILOT READINESS: READY (engineering checks only; owner authorization still required)"
NOT_READY_TEXT = "PILOT READINESS: NOT READY"


class ProposalError(ValueError):
    """The policy-proposal file is malformed, or claims an approval it cannot have."""


@dataclass(frozen=True)
class ReadinessItem:
    code: str
    severity: str  # 'blocker' | 'warning'
    message: str

    def __post_init__(self) -> None:
        if self.severity not in ("blocker", "warning"):
            raise ValueError("severity must be 'blocker' or 'warning'")


@dataclass(frozen=True)
class ReadinessReport:
    items: tuple[ReadinessItem, ...] = field(default_factory=tuple)

    @property
    def blockers(self) -> tuple[ReadinessItem, ...]:
        return tuple(i for i in self.items if i.severity == "blocker")

    @property
    def warnings(self) -> tuple[ReadinessItem, ...]:
        return tuple(i for i in self.items if i.severity == "warning")

    @property
    def ready(self) -> bool:
        return not self.blockers


# --------------------------------------------------------------------------- proposal loading


def _nonempty(x: object) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _validate_proposal(doc: object) -> dict:
    if not isinstance(doc, dict):
        raise ProposalError("proposal must be a JSON object")
    unknown = sorted(set(doc) - set(TOP_KEYS))
    if unknown:
        raise ProposalError("unknown top-level field(s): " + ", ".join(unknown))
    for key in ("schema", "schema_version", "status", "fields", "owner_decisions", "custody", "attestation_file",
                "evidence_binding_route", "pilot_intent"):
        if key not in doc:
            raise ProposalError(f"missing top-level field: {key}")
    if doc["schema"] != PROPOSAL_SCHEMA or doc["schema_version"] != 1:
        raise ProposalError("schema must be 'maps-pilot-policy-proposal' version 1")
    if doc["status"] not in (PROPOSAL_STATUS, APPROVED_TOP_STATUS):
        raise ProposalError("status must be the proposal status or APPROVED")

    fields = doc["fields"]
    if not isinstance(fields, dict):
        raise ProposalError("fields must be an object")
    unknown = sorted(set(fields) - set(FIELD_NAMES))
    if unknown:
        raise ProposalError("unknown policy field(s): " + ", ".join(unknown))
    missing = sorted(set(FIELD_NAMES) - set(fields))
    if missing:
        raise ProposalError("missing policy field(s): " + ", ".join(missing))
    for name, f in fields.items():
        if not isinstance(f, dict) or set(f) != {"value", "status", "source"}:
            raise ProposalError(f"field {name} must have exactly value, status and source")
        if f["status"] not in FIELD_STATUSES:
            raise ProposalError(f"field {name} has an invalid status")
        if not _nonempty(f["source"]):
            raise ProposalError(f"field {name} needs a source")
        if f["status"] == "pending_owner" and f["value"] is not None and name not in ("approval_reference",):
            raise ProposalError(f"field {name} is pending_owner and must have a null value")
        if f["status"] in ("proposed", "approved") and f["value"] is None:
            raise ProposalError(f"field {name} is {f['status']} and needs a value")

    ref = fields["approval_reference"]["value"]
    approved = sorted(n for n, f in fields.items() if f["status"] == "approved")
    if approved and not (_nonempty(ref) and fields["approval_reference"]["status"] == "approved"):
        raise ProposalError("fields marked approved need an approved, non-null approval_reference: " + ", ".join(approved))
    if doc["status"] == APPROVED_TOP_STATUS and len(approved) != len(FIELD_NAMES):
        raise ProposalError("status APPROVED requires every field approved")

    decisions = doc["owner_decisions"]
    if not isinstance(decisions, dict) or set(decisions) != set(OWNER_DECISION_NAMES):
        raise ProposalError("owner_decisions must have exactly: " + ", ".join(OWNER_DECISION_NAMES))
    for name, d in decisions.items():
        if not isinstance(d, dict) or not _nonempty(d.get("status")):
            raise ProposalError(f"owner_decisions.{name} needs a status")
    custody = doc["custody"]
    if not isinstance(custody, list) or len(custody) != CUSTODY_COUNT:
        raise ProposalError(f"custody must list {CUSTODY_COUNT} items")
    for c in custody:
        if not isinstance(c, dict) or set(c) != {"item", "status"} or not _nonempty(c["item"]):
            raise ProposalError("each custody item needs exactly item and status")
        if c["status"] not in CUSTODY_STATUSES:
            raise ProposalError("invalid custody status")
    if doc["attestation_file"] is not None and not _nonempty(doc["attestation_file"]):
        raise ProposalError("attestation_file must be null or a path")
    if doc["pilot_intent"] not in PILOT_INTENT_VALUES:
        raise ProposalError("pilot_intent must be 'NOT AUTHORIZED' or 'AUTHORIZED'")
    if doc["pilot_intent"] == "AUTHORIZED" and not (_nonempty(ref) and fields["approval_reference"]["status"] == "approved"):
        raise ProposalError("pilot_intent AUTHORIZED needs an approved approval_reference")
    return doc


def load_policy_proposal(path: str | Path = REPO_ROOT / "configs/pilot_policy_proposal.json") -> dict:
    """Strictly validated proposal document (a plain dict). Raises ProposalError. Reads only the given file."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProposalError(f"proposal unreadable ({type(exc).__name__})") from None
    return _validate_proposal(doc)


# --------------------------------------------------------------------------- arithmetic


def planned_episodes(config: ExperimentConfig, n_scenarios: int) -> int:
    d = config.design
    return n_scenarios * len(d.conditions) * len(d.prompt_variants) * len(config.models) * d.repetitions


def c0_episodes(config: ExperimentConfig, n_scenarios: int) -> int:
    d = config.design
    return n_scenarios * len(d.prompt_variants) * len(config.models) * d.repetitions


def derived_policy_values(planned: int) -> dict:
    return {
        "ps05a_max_episodes": planned,
        "ps05b_max_request_attempts": ATTEMPT_FACTOR * planned,
        "ps09_deadline_seconds": DEADLINE_SECONDS_PER_CALL * (planned + 1),
    }


# --------------------------------------------------------------------------- report


def _scenario_paths(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.json"))


def _load_current(directory: Path, add) -> list:
    from maps.validation import current_scenarios

    scenarios = []
    for p in _scenario_paths(directory):
        try:
            scenarios.append(load_scenario(p))
        except Exception as exc:
            add("scenario_load_failed", "blocker", f"{p.name} does not load ({type(exc).__name__})")
    return current_scenarios(scenarios)


def _digest_pairs(policy: dict) -> dict:
    content = policy.get("scope", {}).get("content", {}) if isinstance(policy, dict) else {}
    return content if isinstance(content, dict) else {}


def readiness_report(
    repo_root: Path = REPO_ROOT,
    proposal_path: Path | None = None,
    policy_path: Path | None = None,
    config_path: Path | None = None,
    cohort_proposal_path: Path | None = None,
    registry_path: Path | None = None,
    manifest_path: Path | None = None,
) -> ReadinessReport:
    root = Path(repo_root)
    proposal_path = Path(proposal_path) if proposal_path else root / "configs/pilot_policy_proposal.json"
    policy_path = Path(policy_path) if policy_path else root / "configs/pilot_run_policy.json"
    config_path = Path(config_path) if config_path else root / "configs/receiver_experiment.json"
    cohort_proposal_path = Path(cohort_proposal_path) if cohort_proposal_path else root / "configs/pilot_cohort_proposal.json"
    registry_path = Path(registry_path) if registry_path else root / "configs/pilot_registry.json"
    manifest_path = Path(manifest_path) if manifest_path else root / "protocol/scenario_v1/PROTOCOL_MANIFEST.json"

    items: list[ReadinessItem] = []

    def add(code: str, severity: str, message: str) -> None:
        items.append(ReadinessItem(code, severity, message))

    # ---- inputs
    try:
        config = load_config(config_path)
    except Exception as exc:
        add("config_invalid", "blocker", f"experiment configuration does not load ({type(exc).__name__})")
        return ReadinessReport(tuple(items))
    scenarios = _load_current(root / config.design.scenario_dir, add)
    try:
        proposal = load_policy_proposal(proposal_path)
    except ProposalError as exc:
        add("proposal_invalid", "blocker", f"policy proposal rejected: {exc}")
        proposal = None

    # ---- (a) eligibility and self-check
    from maps import registry as reg

    if not hasattr(reg, "pilot_eligibility_problems"):
        add("eligibility_check_absent", "blocker", "registry.pilot_eligibility_problems does not exist; eligibility cannot be judged")
    else:
        try:
            for problem in reg.pilot_eligibility_problems(scenarios, root):
                add("not_pilot_eligible", "blocker", problem)
        except Exception as exc:
            add("eligibility_check_failed", "blocker", f"eligibility check raised {type(exc).__name__}")
    try:
        from maps.self_check import author_self_check

        results = author_self_check(scenarios, root)
        for r in results:
            for f in r.failures:
                add("self_check_failure", "blocker", f"{r.scenario_id}: {f}")
        agg: dict[str, int] = {}
        for r in results:
            for w in r.warnings:
                code = w.split(":", 1)[0].strip()
                agg[code] = agg.get(code, 0) + 1
        for code, n in sorted(agg.items()):
            add(f"self_check_warning:{code}", "warning", f"{n} self-check warning(s) with code {code}")
    except Exception as exc:
        add("self_check_failed", "blocker", f"author self-check raised {type(exc).__name__}")

    # ---- (e) evidence binding
    by_id = {s.scenario_id: s for s in scenarios}
    for s in scenarios:
        if s.status in HASH_REQUIRED_STATUSES:
            for p in evidence_integrity_problems(s, root):
                add("evidence_binding", "blocker", p)
    policy_doc = None
    if policy_path.is_file():
        try:
            policy_doc = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            add("policy_file_invalid", "blocker", "policy file is not valid JSON")
    else:
        add("policy_file_missing", "blocker", "no live policy file exists (policy_source file absent; owner approval pending)")
    if policy_doc is not None:
        for sid, digests in sorted(_digest_pairs(policy_doc).items()):
            s = by_id.get(sid)
            supplied = digests.get("evidence_sha256") if isinstance(digests, dict) else None
            if s is None:
                add("policy_digest_mismatch", "blocker", f"policy scope.content names {sid}, which is not a current scenario")
            elif s.evidence.sha256 is None or supplied != s.evidence.sha256:
                add("policy_digest_mismatch", "blocker", f"{sid}: policy evidence digest differs from scenario evidence.sha256")
        missing = sorted(set(by_id) - set(_digest_pairs(policy_doc)))
        if missing:
            add("policy_digest_mismatch", "blocker", "policy scope.content lacks: " + ", ".join(missing))

    # ---- (d) cohort proposal / registry
    cohort = None
    try:
        cohort = reg.load_cohort_proposal(cohort_proposal_path)
    except Exception as exc:
        add("cohort_proposal_invalid", "blocker", f"cohort proposal does not load ({type(exc).__name__})")
    if cohort is not None and hasattr(reg, "cohort_proposal_problems"):
        try:
            for p in reg.cohort_proposal_problems(cohort, scenarios, root):
                add("cohort_proposal_stale", "blocker", p)
        except Exception as exc:
            add("cohort_proposal_check_failed", "blocker", f"cohort proposal check raised {type(exc).__name__}")
    if not registry_path.is_file():
        add("cohort_not_fixed", "blocker", "the cohort is only a proposal: no registry file exists")
    else:
        try:
            reg.load_registry(registry_path)
        except Exception as exc:
            add("registry_invalid", "blocker", f"registry file does not load ({type(exc).__name__})")

    # ---- (f) planned episodes
    n = len(scenarios)
    planned = planned_episodes(config, n)
    derived = derived_policy_values(planned)
    if cohort is not None and len(cohort.members) != n:
        add("cohort_size_mismatch", "blocker", f"cohort proposal has {len(cohort.members)} members, {n} scenarios are current")
    if proposal is not None:
        f = proposal["fields"]
        for name, formula, key in (
            ("ps05a_max_episodes", "planned_episodes", "ps05a_max_episodes"),
            ("ps05b_max_request_attempts", "3 * planned_episodes", "ps05b_max_request_attempts"),
            ("ps09_formula", "183 * (planned_episodes + 1)", "ps09_deadline_seconds"),
        ):
            v = f[name]["value"]
            ok = v == formula or (type(v) is int and v == derived[key])
            if not ok:
                add("policy_value_mismatch", "blocker", f"{name} value {v!r} is neither {formula!r} nor {derived[key]} for {planned} planned episodes")
    if policy_doc is not None:
        sc = policy_doc.get("scope", {}) if isinstance(policy_doc, dict) else {}
        if isinstance(sc, dict):
            if sc.get("planned_episodes") != planned:
                add("policy_value_mismatch", "blocker", f"policy scope.planned_episodes {sc.get('planned_episodes')!r} != {planned}")
            if sorted(sc.get("scenario_ids", [])) != sorted(by_id):
                add("policy_value_mismatch", "blocker", "policy scope.scenario_ids differ from the current scenarios")

    # ---- proposal-dependent items
    if proposal is not None:
        f, d = proposal["fields"], proposal["owner_decisions"]
        # (g)
        if proposal["status"] != APPROVED_TOP_STATUS:
            add("policy_not_approved", "blocker", "policy proposal status is " + proposal["status"])
        not_approved = sorted(k for k, v in f.items() if v["status"] != "approved")
        if not_approved:
            add("policy_fields_not_approved", "blocker", f"{len(not_approved)} policy field(s) not approved: " + ", ".join(not_approved))
        for k in UNSET_PENDING:
            if f[k]["value"] is None:
                add("policy_value_unset", "blocker", f"{k} is unset (pending owner)")
        if f["approval_reference"]["value"] is None:
            add("approval_reference_missing", "blocker", "approval_reference is missing (owner supplied)")
        # (b)
        a = d["author_id"]
        if a["status"] != "confirmed" or not _nonempty(a.get("value")):
            add("author_id_unconfirmed", "blocker", f"author_id is not confirmed (status {a['status']})")
        # (c)
        if d["near_duplicate_geo_sci"]["status"] != "resolved":
            add("near_duplicate_unresolved", "blocker", "geo/sci near-duplicate decision is " + d["near_duplicate_geo_sci"]["status"])
        # cohort decision
        if d["cohort"]["status"] != "frozen":
            add("cohort_not_frozen", "blocker", "cohort decision status is " + d["cohort"]["status"])
        # (k)
        for name in ("hist_a_year_1612", "hist_b_wording"):
            st = d[name]["status"]
            if st == "provisionally_accepted":
                add("hist_decision_provisional", "warning", f"{name} is only provisionally accepted")
            elif st != "accepted":
                add("hist_decision_open", "blocker", f"{name} status is {st}")
        # (h)
        pending = [c["item"] for c in proposal["custody"] if c["status"] != "complete"]
        if pending:
            add("custody_pending", "blocker", f"{len(pending)} key-custody item(s) pending owner action: " + "; ".join(pending))
        att = proposal["attestation_file"]
        if att is None:
            add("attestation_missing", "blocker", "no custody attestation file is named")
        elif not (root / att).is_file():
            add("attestation_missing", "blocker", "named custody attestation file does not exist")
        # (i)
        if proposal["pilot_intent"] != "AUTHORIZED":
            add("pilot_intent_not_authorized", "blocker", "PILOT_INTENT is NOT AUTHORIZED")

    # ---- (j) protocol manifest
    try:
        mstatus = json.loads(manifest_path.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        mstatus = None
    if mstatus != "APPROVED":
        add("protocol_not_approved", "warning", f"protocol manifest status is {mstatus!r}; this blocks CONFIRMATORY use, not the pilot")
    return ReadinessReport(tuple(items))


def format_readiness(report: ReadinessReport) -> str:
    lines = ["PILOT READINESS REPORT (engineering checks; nothing here approves anything)", ""]
    for title, sev in (("BLOCKERS", "blocker"), ("WARNINGS", "warning")):
        sel = [i for i in report.items if i.severity == sev]
        lines.append(f"{title} ({len(sel)})")
        lines += [f"  [{i.code}] {i.message}" for i in sel] or ["  none"]
        lines.append("")
    lines.append(READY_TEXT if report.ready else NOT_READY_TEXT)
    return "\n".join(lines)
