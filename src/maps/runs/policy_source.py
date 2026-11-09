"""Live policy source (Stage 4D): a strict, versioned policy file, loaded and checked fail-closed.

STATUS: implemented and tested OFFLINE only. Nothing calls this module yet (the CLI still refuses ``--live``; wiring is
Stage 4E). It reads no credentials and no environment, never builds a client, never touches a network and never creates
a run directory. Its only I/O is reading the one policy file it is given. It does not authorize or enable a live run,
and a loaded policy is not an approval.

THE FILE (schema ``maps-live-policy``, version 1). Strict JSON: UTF-8, no duplicate keys, no floats, every field required,
unknown fields refused, no defaults, no "unlimited". Lists are in canonical order (ascending, unique)::

    {
      "schema": "maps-live-policy",  "schema_version": 1,  "policy_id": "<id>",
      "scope": {
        "experiment_id", "config_version", "prompt_version", "stage" ("pilot"|"main"), "seed" (int),
        "models": [{"alias", "family", "model_id"}, ...]          sorted by alias
        "conditions": [{"id", "n_messages", "n_roots"}, ...]       sorted by id
        "prompt_variants": [...]                                   sorted
        "scenario_ids": [...]                                      sorted
        "repetitions" (int), "rotate_templates_and_roots" (bool),
        "planned_episodes" (int), "max_tokens_per_request" (int, must equal cfg.sampling.max_tokens),
        "design_digest": "<sha256 of the design part of the configuration>",
        "content": {"<scenario_id>": {"scenario_sha256", "evidence_sha256"}, ...}
      },
      "profiles": {"<profile_id>": {"max_episodes", "max_request_attempts", "max_retries", "deadline_seconds",
                                    "max_consecutive_nonfatal_errors", "accounting_basis",
                                    "nonfatal_4xx_statuses" (ascending unique), "fatal_3xx"}, ...},
      "approval": {"approval_reference": "<text>"}
    }

The numeric limits are the owner's decisions; this module checks only that they are present, typed and coherent (all
range and relation checks are ``LivePolicy``'s: this module adds none of its own for them).

PROFILES. The caller must name a profile explicitly: there is no default and there are no overrides of individual
limits from the command line or the environment. A profile is a complete, fixed set of limits; it cannot change the scope.

SCOPE BINDING. The scope must equal the configuration and the actual planned grid EXACTLY: the set of
(model, scenario, variant, condition, repetition) tuples of the grid must be the full product of the policy's lists, so a
same-size substitution (one scenario or model swapped) is refused; the 240 count alone is never sufficient. Scenario and
evidence file contents are bound by SHA-256 (``content``), so an edit under an unchanged scenario id is detected. The
caller computes the actual digests (``compute_content_digests``) and passes them in.

DIGESTS. ``policy_digest`` is SHA-256 of the canonical JSON of the document WITHOUT its ``approval`` block, so the
approval reference is outside the hashed content. Canonical JSON: ``json.dumps(content, sort_keys=True,
separators=(",", ":"), ensure_ascii=True)`` encoded as ASCII; independently recomputable. ``effective_digest`` covers the
selected profile's limits plus the scope. ``design_digest`` covers the design part of the configuration (models, design,
sampling, seed, versions, stage) and the request ``timeout_s`` and retry ``backoff_s`` (Stage 4G, TIMEOUT-BACKOFF option A);
it excludes the rest of ``api`` (endpoint, key variable name, enabled flag, retry count, which has its own check) and ``output``
paths. ``timeout_s`` is a per-socket-operation timeout in ``requests``, not a total wall-clock bound.

WHAT A DIGEST IS NOT. A digest shows content equals a value; it does not authenticate who wrote the policy and is not
proof of owner approval. ``expected_digest`` is an optional, CALLER-supplied value; the file itself carries none. Where a
trusted expected value is stored is deferred to the later authorization stage, and a value read from the same untrusted
source as the policy must not be treated as authenticated. ``LoadedPolicy.trust`` states this on every result.

Errors are ``PolicySourceError`` (a ``PolicyError``) with a bounded ``reason`` code and fixed text; they never contain
policy values, file content or paths. Invalid input is refused before anything else happens; ``REFUSAL_EXIT_CODE`` is the
exit code the CLI should use when it is wired (Stage 4E). Endpoint validation and the composite authorization
fingerprint are NOT part of this module.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from maps.config import ExperimentConfig
from maps.runs.artifact_hashes import ArtifactError, read_artifact
from maps.runs.live_policy import LivePolicy, PolicyError

SCHEMA_ID = "maps-live-policy"
SCHEMA_VERSION = 1
REFUSAL_EXIT_CODE = 2
MAX_POLICY_BYTES = 1 << 20
TRUST_NOTE = "content integrity only; not authenticated and not proof of owner approval"

TOP_FIELDS = ("schema", "schema_version", "policy_id", "scope", "profiles", "approval")
SCOPE_FIELDS = (
    "experiment_id", "config_version", "prompt_version", "stage", "seed", "models", "conditions", "prompt_variants",
    "scenario_ids", "repetitions", "rotate_templates_and_roots", "planned_episodes", "max_tokens_per_request",
    "design_digest", "content",
)
MODEL_FIELDS = ("alias", "family", "model_id")
CONDITION_FIELDS = ("id", "n_messages", "n_roots")
CONTENT_FIELDS = ("scenario_sha256", "evidence_sha256")
LIMIT_FIELDS = (
    "max_episodes", "max_request_attempts", "max_retries", "deadline_seconds", "max_consecutive_nonfatal_errors",
    "accounting_basis", "nonfatal_4xx_statuses", "fatal_3xx",
)
APPROVAL_FIELDS = ("approval_reference",)

REASONS = {
    "input_invalid": "a loader argument is missing or of the wrong type",
    "file_missing": "the policy file does not exist",
    "file_not_regular": "the policy path is not a regular file (a link, directory or special file)",
    "file_too_large": "the policy file is larger than the supported size",
    "file_unreadable": "the policy file could not be read",
    "bad_encoding": "the policy file is not valid UTF-8",
    "bad_json": "the policy file is not valid JSON",
    "duplicate_key": "the policy file contains a duplicate key",
    "bad_number": "the policy file contains a non-integer number",
    "schema_unsupported": "the policy schema or version is not supported",
    "field_unknown": "the policy has unknown field(s)",
    "field_missing": "the policy is missing required field(s)",
    "type_invalid": "a policy field has the wrong type or form",
    "range_invalid": "a policy field is outside its allowed range",
    "not_canonical_order": "a policy list is not in canonical (ascending, unique) order",
    "duplicate_identifier": "a policy list contains a duplicate identifier",
    "profile_unknown": "the named profile is not in the policy",
    "limits_invalid": "the profile limits were refused by the live policy validator",
    "scope_mismatch": "the policy scope does not match the configuration",
    "grid_mismatch": "the planned grid does not match the policy scope exactly",
    "design_mismatch": "the policy design digest does not match the configuration",
    "content_mismatch": "scenario or evidence content does not match the policy",
    "content_unreadable": "scenario or evidence content could not be digested",
    "config_conflict": "the configuration conflicts with the selected profile",
    "expected_digest_invalid": "the expected digest is not a SHA-256 hex string",
    "digest_mismatch": "the policy digest does not match the expected digest",
}
_HEX64 = re.compile(r"[0-9a-f]{64}")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_MAX_TEXT = 200


class PolicySourceError(PolicyError):
    """The policy file, its scope or the configuration was refused. ``reason`` is a code from ``REASONS``."""

    def __init__(self, reason: str, field: str | None = None):
        text = REASONS[reason] + (f" ({field})" if field else "")
        super().__init__(text)
        self.reason = reason
        self.field = field


def _refuse(reason: str, field: str | None = None):
    raise PolicySourceError(reason, field)


@dataclass(frozen=True)
class LoadedPolicy:
    """The result of a successful load. Immutable; holds no file text and no secrets."""

    policy: LivePolicy
    policy_id: str
    profile: str
    schema_version: int
    policy_digest: str
    effective_digest: str
    design_digest: str
    planned_episodes: int
    max_tokens_per_request: int
    content_bound: bool
    expected_digest_checked: bool
    trust: str = TRUST_NOTE

    def record(self) -> dict:
        """A plain, secret-free record for later provenance use (Stage 4E)."""
        return {
            "schema": SCHEMA_ID, "schema_version": self.schema_version, "policy_id": self.policy_id, "profile": self.profile,
            "policy_digest": self.policy_digest, "effective_digest": self.effective_digest, "design_digest": self.design_digest,
            "planned_episodes": self.planned_episodes, "max_tokens_per_request": self.max_tokens_per_request,
            "content_bound": self.content_bound, "expected_digest_checked": self.expected_digest_checked, "trust": self.trust,
        }


# ---------------------------------------------------------------------------------------------------------------------
# reading and parsing
# ---------------------------------------------------------------------------------------------------------------------
def read_policy_file(path) -> bytes:
    """The raw bytes of a regular, non-link file of at most ``MAX_POLICY_BYTES`` (via the hash-binding reader)."""
    try:
        read = read_artifact(Path(path), keep_bytes=True, max_bytes=MAX_POLICY_BYTES)
    except ArtifactError as exc:
        mapped = {
            "artifact_missing": "file_missing", "artifact_not_regular_file": "file_not_regular",
            "artifact_too_large": "file_too_large",
        }.get(exc.reason, "file_unreadable")
        raise PolicySourceError(mapped) from None
    except (TypeError, ValueError):
        raise PolicySourceError("input_invalid", "path") from None
    return read.data or b""


def _no_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise PolicySourceError("duplicate_key")
        seen[key] = value
    return seen


def _reject_number(_text):
    raise PolicySourceError("bad_number")


def parse_policy_bytes(data: bytes) -> dict:
    """Strict parse: UTF-8, valid JSON, a top-level object, no duplicate keys, integers only (no floats)."""
    if not isinstance(data, (bytes, bytearray)):
        _refuse("input_invalid", "data")
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        _refuse("bad_encoding")
    if text.startswith("﻿"):
        _refuse("bad_encoding")
    try:
        doc = json.loads(text, object_pairs_hook=_no_duplicates, parse_float=_reject_number, parse_constant=_reject_number)
    except PolicySourceError:
        raise
    except (ValueError, RecursionError):
        _refuse("bad_json")
    if not isinstance(doc, dict):
        _refuse("type_invalid", "document")
    return doc


# ---------------------------------------------------------------------------------------------------------------------
# canonical form and digests
# ---------------------------------------------------------------------------------------------------------------------
def _check_canonical_types(value) -> None:
    if isinstance(value, bool) or isinstance(value, (int, str)):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _refuse("type_invalid", "key")
            _check_canonical_types(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _check_canonical_types(item)
        return
    _refuse("type_invalid", "value")


def canonical_bytes(content) -> bytes:
    """Canonical JSON bytes: sorted keys, compact separators, ASCII-escaped. Floats, None and other types are refused."""
    _check_canonical_types(content)
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def policy_digest(doc: Mapping) -> str:
    """SHA-256 of the canonical document WITHOUT its ``approval`` block."""
    return _sha256(canonical_bytes({key: value for key, value in doc.items() if key != "approval"}))


def effective_digest(doc: Mapping, profile: str) -> str:
    """SHA-256 over the scope plus the selected profile's limits (the effective policy of one run)."""
    return _sha256(canonical_bytes({
        "schema": doc["schema"], "schema_version": doc["schema_version"], "policy_id": doc["policy_id"],
        "scope": doc["scope"], "profile": profile, "limits": doc["profiles"][profile],
    }))


def design_digest(cfg: ExperimentConfig) -> str:
    """SHA-256 of the design part of the configuration plus ``api.timeout_s`` and ``api.backoff_s``.

    The rest of ``api`` and the ``output`` paths are excluded; the stage is included. Floats (the sampling temperature and the
    two api values) are serialized with Python's JSON representation, which is deterministic."""
    dumped = cfg.model_dump(mode="json")
    subset = {
        "experiment_id": dumped["experiment_id"], "config_version": dumped["config_version"],
        "prompt_version": dumped["prompt_version"], "seed": dumped["seed"], "stage": dumped["output"]["stage"],
        "models": dumped["models"], "design": dumped["design"], "sampling": dumped["sampling"],
        "api": {"timeout_s": dumped["api"]["timeout_s"], "backoff_s": dumped["api"]["backoff_s"]},
    }
    return _sha256(json.dumps(subset, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii"))


def compute_content_digests(scenario_dir, repo_root) -> dict:
    """``{scenario_id: {"scenario_sha256", "evidence_sha256"}}`` for every ``*.json`` scenario in a directory.

    Reads and hashes the scenario files and the evidence files they reference; returns digests only, never content.
    For the Stage 4E caller; the tests use synthetic fixtures."""
    from maps.scenarios import evidence_path, file_sha256, load_scenario

    out: dict = {}
    try:
        for path in sorted(Path(scenario_dir).glob("*.json")):
            scenario = load_scenario(path)
            if scenario.scenario_id in out:
                _refuse("duplicate_identifier", "scenario_ids")
            out[scenario.scenario_id] = {
                "scenario_sha256": file_sha256(path),
                "evidence_sha256": file_sha256(evidence_path(scenario, Path(repo_root))),
            }
    except PolicySourceError:
        raise
    except (OSError, ValueError):
        raise PolicySourceError("content_unreadable") from None
    return out


# ---------------------------------------------------------------------------------------------------------------------
# structure validation
# ---------------------------------------------------------------------------------------------------------------------
def _exact(mapping, fields, where):
    if not isinstance(mapping, dict):
        _refuse("type_invalid", where)
    unknown = [key for key in mapping if key not in fields]
    if unknown:
        raise PolicySourceError("field_unknown", f"{where}: {len(unknown)} unknown")
    missing = [name for name in fields if name not in mapping]
    if missing:
        raise PolicySourceError("field_missing", f"{where}: {', '.join(missing)}")


def _is_int(value) -> bool:
    return type(value) is int


def _text(value, where):
    if type(value) is not str or not value or len(value) > _MAX_TEXT or any(ord(c) < 32 or ord(c) == 127 for c in value):
        _refuse("type_invalid", where)
    return value


def _ident(value, where):
    if type(value) is not str or not _IDENT.fullmatch(value):
        _refuse("type_invalid", where)
    return value


def _hex(value, where):
    if type(value) is not str or not _HEX64.fullmatch(value):
        _refuse("type_invalid", where)
    return value


def _nonneg_int(value, where):
    if not _is_int(value):
        _refuse("type_invalid", where)
    if value < 0:
        _refuse("range_invalid", where)
    return value


def _canonical_list(items, where, key=lambda x: x):
    """The list must be non-empty, unique and ascending by ``key``."""
    if not isinstance(items, list) or not items:
        _refuse("type_invalid", where)
    keys = [key(item) for item in items]
    if len(set(keys)) != len(keys):
        _refuse("duplicate_identifier", where)
    if keys != sorted(keys):
        _refuse("not_canonical_order", where)


def validate_document(doc) -> dict:
    """Check the document's structure and types (limit semantics are ``LivePolicy``'s). Returns the same mapping."""
    if not isinstance(doc, dict):
        _refuse("type_invalid", "document")
    if doc.get("schema") != SCHEMA_ID or not _is_int(doc.get("schema_version")) or doc.get("schema_version") != SCHEMA_VERSION:
        _refuse("schema_unsupported")
    _exact(doc, TOP_FIELDS, "document")
    _ident(doc["policy_id"], "policy_id")
    scope = doc["scope"]
    _exact(scope, SCOPE_FIELDS, "scope")
    for name in ("experiment_id", "config_version", "prompt_version"):
        _text(scope[name], f"scope.{name}")
    if scope["stage"] not in ("pilot", "main") or type(scope["stage"]) is not str:
        _refuse("type_invalid", "scope.stage")
    if not _is_int(scope["seed"]):
        _refuse("type_invalid", "scope.seed")
    for name in ("repetitions", "planned_episodes", "max_tokens_per_request"):
        if not _is_int(scope[name]):
            _refuse("type_invalid", f"scope.{name}")
        if scope[name] < 1:
            _refuse("range_invalid", f"scope.{name}")
    if type(scope["rotate_templates_and_roots"]) is not bool:
        _refuse("type_invalid", "scope.rotate_templates_and_roots")
    _hex(scope["design_digest"], "scope.design_digest")
    _canonical_list(scope["models"], "scope.models", key=lambda m: m.get("alias") if isinstance(m, dict) and type(m.get("alias")) is str else "")
    for model in scope["models"]:
        _exact(model, MODEL_FIELDS, "scope.models")
        for name in MODEL_FIELDS:
            _text(model[name], f"scope.models.{name}")
    if len({m["model_id"] for m in scope["models"]}) != len(scope["models"]):
        _refuse("duplicate_identifier", "scope.models")
    _canonical_list(scope["conditions"], "scope.conditions", key=lambda c: c.get("id") if isinstance(c, dict) and type(c.get("id")) is str else "")
    for cond in scope["conditions"]:
        _exact(cond, CONDITION_FIELDS, "scope.conditions")
        _text(cond["id"], "scope.conditions.id")
        _nonneg_int(cond["n_messages"], "scope.conditions.n_messages")
        _nonneg_int(cond["n_roots"], "scope.conditions.n_roots")
    for name in ("prompt_variants", "scenario_ids"):
        _canonical_list(scope[name], f"scope.{name}", key=lambda x: x if type(x) is str else "")
        for item in scope[name]:
            _text(item, f"scope.{name}")
    content = scope["content"]
    if not isinstance(content, dict) or not content:
        _refuse("type_invalid", "scope.content")
    if sorted(content) != scope["scenario_ids"]:
        _refuse("scope_mismatch", "scope.content")
    for entry in content.values():
        _exact(entry, CONTENT_FIELDS, "scope.content")
        for name in CONTENT_FIELDS:
            _hex(entry[name], f"scope.content.{name}")
    profiles = doc["profiles"]
    if not isinstance(profiles, dict) or not profiles or len(profiles) > 32:
        _refuse("type_invalid", "profiles")
    for profile_id, limits in profiles.items():
        _ident(profile_id, "profiles")
        _exact(limits, LIMIT_FIELDS, "profile")
        for name in ("max_episodes", "max_request_attempts", "max_retries", "deadline_seconds", "max_consecutive_nonfatal_errors"):
            if not _is_int(limits[name]):
                _refuse("type_invalid", f"profile.{name}")
        if type(limits["accounting_basis"]) is not str:
            _refuse("type_invalid", "profile.accounting_basis")
        if type(limits["fatal_3xx"]) is not bool:
            _refuse("type_invalid", "profile.fatal_3xx")
        statuses = limits["nonfatal_4xx_statuses"]
        if not isinstance(statuses, list) or not all(_is_int(s) for s in statuses):
            _refuse("type_invalid", "profile.nonfatal_4xx_statuses")
        if len(set(statuses)) != len(statuses):
            _refuse("duplicate_identifier", "profile.nonfatal_4xx_statuses")
        if statuses != sorted(statuses):
            _refuse("not_canonical_order", "profile.nonfatal_4xx_statuses")
    _exact(doc["approval"], APPROVAL_FIELDS, "approval")
    _text(doc["approval"]["approval_reference"], "approval.approval_reference")
    return doc


def select_profile(doc: Mapping, profile) -> dict:
    """The named profile's limits. An unknown or malformed name is refused; there is no default profile."""
    if type(profile) is not str or not _IDENT.fullmatch(profile) or profile not in doc["profiles"]:
        _refuse("profile_unknown")
    return doc["profiles"][profile]


# ---------------------------------------------------------------------------------------------------------------------
# scope binding
# ---------------------------------------------------------------------------------------------------------------------
def check_scope(doc: Mapping, cfg: ExperimentConfig, specs, content_digests: Mapping) -> None:
    """Refuse unless the policy scope equals the configuration, the planned grid and the actual content digests EXACTLY."""
    scope = doc["scope"]
    if scope["experiment_id"] != cfg.experiment_id or scope["config_version"] != cfg.config_version:
        _refuse("scope_mismatch", "experiment_id/config_version")
    if scope["prompt_version"] != cfg.prompt_version:
        _refuse("scope_mismatch", "prompt_version")
    if scope["stage"] != cfg.output.stage:
        _refuse("scope_mismatch", "stage")
    if scope["seed"] != cfg.seed:
        _refuse("scope_mismatch", "seed")
    if scope["repetitions"] != cfg.design.repetitions or scope["rotate_templates_and_roots"] != cfg.design.rotate_templates_and_roots:
        _refuse("scope_mismatch", "repetitions/rotation")
    if scope["max_tokens_per_request"] != cfg.sampling.max_tokens:
        _refuse("scope_mismatch", "max_tokens_per_request")
    if sorted(scope["models"], key=lambda m: m["alias"]) != sorted(
        ({"alias": m.alias, "family": m.family, "model_id": m.model_id} for m in cfg.models), key=lambda m: m["alias"]
    ):
        _refuse("scope_mismatch", "models")
    if scope["conditions"] != sorted(
        ({"id": c.id, "n_messages": c.n_messages, "n_roots": c.n_roots} for c in cfg.design.conditions), key=lambda c: c["id"]
    ):
        _refuse("scope_mismatch", "conditions")
    if scope["prompt_variants"] != sorted(cfg.design.prompt_variants):
        _refuse("scope_mismatch", "prompt_variants")
    if scope["design_digest"] != design_digest(cfg):
        _refuse("design_mismatch")

    # the planned grid must be exactly the full product of the policy's lists
    grid = list(specs)
    models, scenarios = [m["model_id"] for m in scope["models"]], scope["scenario_ids"]
    variants, conditions = scope["prompt_variants"], scope["conditions"]
    expected_size = len(models) * len(scenarios) * len(variants) * len(conditions) * scope["repetitions"]
    if scope["planned_episodes"] != expected_size or len(grid) != scope["planned_episodes"]:
        _refuse("grid_mismatch", "planned_episodes")
    cond_shape = {c["id"]: (c["n_messages"], c["n_roots"]) for c in conditions}
    try:
        actual = [(s.model_id, s.scenario_id, s.prompt_variant, s.condition_id, s.repetition) for s in grid]
        shapes_ok = all(cond_shape.get(s.condition_id) == (s.n_messages, s.n_roots) for s in grid)
    except AttributeError:
        _refuse("input_invalid", "specs")
    if len(set(actual)) != len(actual):
        _refuse("grid_mismatch", "duplicate episodes")
    wanted = set(itertools.product(models, scenarios, variants, [c["id"] for c in conditions], range(scope["repetitions"])))
    if set(actual) != wanted or not shapes_ok:
        _refuse("grid_mismatch", "episode set")

    # scenario and evidence content
    if not isinstance(content_digests, Mapping):
        _refuse("input_invalid", "content_digests")
    if sorted(content_digests) != scenarios:
        _refuse("content_mismatch", "scenario ids")
    for scenario_id in scenarios:
        have = content_digests[scenario_id]
        if not isinstance(have, Mapping) or {k: have.get(k) for k in CONTENT_FIELDS} != scope["content"][scenario_id]:
            _refuse("content_mismatch", "digests")


# ---------------------------------------------------------------------------------------------------------------------
# the entry point
# ---------------------------------------------------------------------------------------------------------------------
def load_policy(
    path,
    *,
    cfg: ExperimentConfig,
    specs: Iterable,
    content_digests: Mapping,
    profile: str,
    expected_digest: str | None = None,
) -> LoadedPolicy:
    """Load, validate and bind a policy file; raise ``PolicySourceError`` on any problem (fail closed).

    ``profile`` must be named (no default). ``expected_digest`` is optional and CALLER-supplied: when given it is compared
    with ``policy_digest``; a match shows only that the content equals that value, not who approved it."""
    if not isinstance(cfg, ExperimentConfig):
        _refuse("input_invalid", "cfg")
    if expected_digest is not None and (type(expected_digest) is not str or not _HEX64.fullmatch(expected_digest)):
        _refuse("expected_digest_invalid")
    doc = validate_document(parse_policy_bytes(read_policy_file(path)))
    limits = select_profile(doc, profile)
    digest = policy_digest(doc)
    if expected_digest is not None and digest != expected_digest:
        _refuse("digest_mismatch")
    check_scope(doc, cfg, specs, content_digests)
    try:
        live = LivePolicy.from_mapping({
            **limits, "planned_episodes": doc["scope"]["planned_episodes"],
            "approval_reference": doc["approval"]["approval_reference"],
        })
    except PolicyError as exc:
        raise PolicySourceError("limits_invalid", str(exc)[:120]) from None
    if cfg.api.max_retries != live.max_retries:
        _refuse("config_conflict", "max_retries")
    return LoadedPolicy(
        policy=live, policy_id=doc["policy_id"], profile=profile, schema_version=doc["schema_version"], policy_digest=digest,
        effective_digest=effective_digest(doc, profile), design_digest=doc["scope"]["design_digest"],
        planned_episodes=doc["scope"]["planned_episodes"], max_tokens_per_request=doc["scope"]["max_tokens_per_request"],
        content_bound=True, expected_digest_checked=expected_digest is not None,
    )
