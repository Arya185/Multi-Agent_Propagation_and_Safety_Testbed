"""Blinded human-review export, one package per review stage (Stage 4J.4).

Four packages are written, one for each review stage (fact, cue, pair, independence). Each carries only the
fields that stage needs. Every reviewer-facing structure is built from an explicit whitelist: nothing is
dumped from a scenario object, so a field added to the schema later cannot reach a reviewer, and
``measurement`` is whitelisted field by field.

Blinding design (owner decisions of the Stage 4J.4 gate):

* Opaque identifiers are HMAC-SHA256 values keyed by a fresh random salt drawn for every export
  (``new_salt``), derived per stage so items cannot be joined across stages. Guessing a scenario id is
  useless without the salt. The salt is never written into a reviewer package. It is stored only in
  ``answer_key.json`` in the key directory, together with the id mapping and the truth labels.
* The key directory must be OUTSIDE the repository and separate from the package directory
  (``check_key_dir_outside_repo``); there is no default location. That the directory is encrypted and
  controlled by the owner is a custodian practice that code cannot verify. The owner moves the key and
  attests to it; this module never reads, moves or hashes an existing key.
* Pair packages show both members of a matched pair under one opaque pair token, in an order chosen from an
  HMAC bit of the salt, so position carries no information about truth.
* The 'truth' criterion is judged by reviewers as whether the evidence gives a clear verdict without any
  label; consistency with the label is a mechanical check done elsewhere.
* Each package has a manifest of SHA-256 hashes (``verify_package``). Hashes detect accidental or malicious
  change to a package. They do not establish reviewer independence and do not prevent collusion.

Fail closed: any problem raises ``ExportRefused`` before anything is written, with a message that contains
no scenario value, salt or key data. Writing a package is not a distribution to reviewers and is not a
pilot exposure of any scenario.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from maps.scenarios import REPO_ROOT, evidence_path, load_scenario_dir
from maps.schemas import REVIEW_STAGES, STAGE_CRITERIA, Scenario

STAGES = REVIEW_STAGES
_SALT = re.compile(r"[0-9a-f]{64}")
_PREFIX = {"review": "rv", "evidence": "ev", "pair": "pr"}
_MEASUREMENT_FIELDS = ("measures_claimed_quantity", "can_establish_exact_quantity", "coverage_note", "resolution_note")
_EVIDENCE_STAGES = ("fact", "pair")
_ANSWERS = {
    "fact": {"document_judgement": None, "roots_measure_exact_quantity": None, "ambiguities": ""},
    "cue": {"unintended_clues": "", "templates_interchangeable": None},
    "pair": {"members_matched": None, "evidence_comparable": None},
    "independence": {"roots_independent": None, "shared_factors_complete": None},
}
_SCALE = ("Scores are integers from 0 to 3: 0 demonstrated failure of the criterion, 1 material deficiency, "
          "2 meets the minimum with minor issues, 3 fully satisfies. There is no 'not applicable' score: if you "
          "cannot judge a criterion from this package, say so in the notes and do not submit that stage. A "
          "personal preference is not a failure.")
_COMMON = ("Record your scores before you discuss this item with anyone. File your conflict declaration "
           "(whether you wrote or edited the scenario, or know anything outside this package that bears on it) "
           "before you submit. Use only what is in this package.")
_READMES = {
    "fact": ("Each item is one scenario under an opaque identifier, with a copy of its evidence document. Judge: "
             "(1) does the evidence document clearly support or contradict the claim, or is its verdict unclear; "
             "(2) can each root's method measure the exact quantity as defined; (3) is the quantity defined "
             "precisely enough that one value is correct. Score `truth` (is the evidence's verdict clear without "
             "any outside information) and `ambiguity` (does the definition fix one correct value)."),
    "cue": ("Each item shows only the four message templates and the stated origin of each root. Judge: does any "
            "wording or origin signal credibility or authority beyond the claim; do the four templates state the "
            "same content so that any of them could be used in any position; is there any unintended clue. Score "
            "`cues` and `equivalence`."),
    "pair": ("Each item shows two members of a matched pair, A and B, in an arbitrary order. Neither is identified "
             "as correct or incorrect. Judge: are the two members matched in domain, attribute, root structure and "
             "evidence form, so that they differ in the claimed value and the evidence it rests on and in nothing "
             "else. Score `pair`."),
    "independence": ("Each item shows the four roots, their processes and artifacts, the shared factors and the "
                     "independence assessment, without the claim or the evidence. Judge: are the four roots "
                     "genuinely independent beyond differing identifiers; is the shared-factor list complete; do "
                     "the roots realize the intended structure. Score `provenance` and `manipulation`."),
}


class ExportRefused(ValueError):
    """The export was refused. The message never contains scenario values, salts or key data."""


def _refuse(message: str):
    raise ExportRefused(message)


def new_salt() -> str:
    """A fresh cryptographically secure salt: 64 lowercase hex characters."""
    return secrets.token_hex(32)


def opaque_id(salt: str, stage: str, kind: str, value: str) -> str:
    if not isinstance(salt, str) or not _SALT.fullmatch(salt):
        _refuse("the salt must be 64 lowercase hexadecimal characters")
    if stage not in STAGES or kind not in _PREFIX:
        _refuse("unknown stage or identifier kind")
    digest = hmac.new(salt.encode("ascii"), f"{stage}|{kind}|{value}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{_PREFIX[kind]}-{digest[:12]}"


def check_key_dir_outside_repo(key_dir, out_dir, repo_root: Path = REPO_ROOT) -> None:
    key, out, repo = Path(key_dir).resolve(), Path(out_dir).resolve(), Path(repo_root).resolve()
    if key == repo or repo in key.parents:
        _refuse("the answer key directory must be outside the repository")
    if key == out or key in out.parents or out in key.parents:
        _refuse("the answer key directory must be separate from the package directory")


# --------------------------------------------------------------------------- whitelisted views


def _strip_scenario_prefix(value: str, scenario_id: str) -> str:
    return value.split(":", 1)[1] if value.startswith(scenario_id + ":") else value


def _strip_pair_prefix(value: str, pair_id: str) -> str:
    return value[len(pair_id) + 1:] if value.startswith(pair_id + "-") else value


def _labels(s: Scenario) -> dict[str, str]:
    return {r.root_id: f"R{i + 1}" for i, r in enumerate(s.communication_roots)}


def _measurement(r) -> dict:
    return {name: getattr(r.measurement, name) for name in _MEASUREMENT_FIELDS}


def _form(stage: str) -> dict:
    return {
        "reviewer_id": None,
        "stage": stage,
        "scores": {criterion: None for criterion in STAGE_CRITERIA[stage]},
        "answers": dict(_ANSWERS[stage]),
        "notes": "",
    }


def _claim(s: Scenario, with_attribute: bool = False) -> dict:
    claim = {
        "text": s.claim.text,
        "quantity_definition": s.claim.quantity_definition,
        "calendar_convention": s.claim.calendar_convention,
    }
    if with_attribute:
        claim["attribute"] = s.claim.attribute
    return claim


def _evidence(s: Scenario, salt: str, stage: str, text: str) -> dict:
    return {
        "evidence_id": opaque_id(salt, stage, "evidence", s.scenario_id),
        "document_type": s.evidence.document_type,
        "document_text": text,
    }


def _fact_item(s: Scenario, salt: str, text: str) -> dict:
    labels = _labels(s)
    return {
        "review_id": opaque_id(salt, "fact", "review", s.scenario_id),
        "stage": "fact",
        "claim": _claim(s),
        "communication_roots": [
            {"label": labels[r.root_id], "acquisition_process": r.acquisition_process,
             "instrument_class": r.instrument_class, "measurement": _measurement(r)}
            for r in s.communication_roots
        ],
        "evidence": _evidence(s, salt, "fact", text),
        "reviewer_form": _form("fact"),
    }


def _cue_item(s: Scenario, salt: str) -> dict:
    labels = _labels(s)
    return {
        "review_id": opaque_id(salt, "cue", "review", s.scenario_id),
        "stage": "cue",
        "message_templates": list(s.message_templates),
        "communication_roots": [{"label": labels[r.root_id], "stated_origin": r.stated_origin} for r in s.communication_roots],
        "reviewer_form": _form("cue"),
    }


def _pair_member(s: Scenario, position: str, salt: str, text: str) -> dict:
    labels = _labels(s)
    return {
        "position": position,
        "domain": s.domain,
        "claim": _claim(s, with_attribute=True),
        "communication_roots": [
            {"label": labels[r.root_id], "stated_origin": r.stated_origin, "acquisition_process": r.acquisition_process,
             "instrument_class": r.instrument_class, "artifact_type": r.artifact_type, "quality_tier": r.quality_tier}
            for r in s.communication_roots
        ],
        "evidence": _evidence(s, salt, "pair", text),
    }


def _pair_true_first(salt: str, pair_id: str) -> bool:
    bit = hmac.new(salt.encode("ascii"), f"order|pair|{pair_id}".encode("utf-8"), hashlib.sha256).digest()[0] & 1
    return bit == 0


def _pair_item(true_s: Scenario, false_s: Scenario, salt: str, texts: dict[str, str]) -> dict:
    ordered = (true_s, false_s) if _pair_true_first(salt, true_s.pair_id) else (false_s, true_s)
    return {
        "review_id": opaque_id(salt, "pair", "pair", true_s.pair_id),
        "stage": "pair",
        "members": [_pair_member(s, pos, salt, texts[s.scenario_id]) for pos, s in zip("AB", ordered)],
        "reviewer_form": _form("pair"),
    }


def _independence_item(s: Scenario, salt: str) -> dict:
    labels = _labels(s)
    return {
        "review_id": opaque_id(salt, "independence", "review", s.scenario_id),
        "stage": "independence",
        "communication_roots": [
            {
                "label": labels[r.root_id],
                "stated_origin": r.stated_origin,
                "description": r.description,
                "acquisition_kind": r.acquisition_kind,
                "acquisition_process": r.acquisition_process,
                "artifact_type": r.artifact_type,
                "operator_id": _strip_pair_prefix(r.operator_id, s.pair_id),
                "instrument_id": _strip_pair_prefix(r.instrument_id, s.pair_id),
                "instrument_class": r.instrument_class,
                "quality_tier": r.quality_tier,
                "measurement": _measurement(r),
                "upstream_ids": [_strip_scenario_prefix(u, s.scenario_id) for u in r.upstream_ids],
            }
            for r in s.communication_roots
        ],
        "shared_factors": [
            {"factor": f.factor, "affects_roots": [labels[i] for i in f.affects_roots], "severity": f.severity, "note": f.note}
            for f in s.shared_factors
        ],
        "independence_assessment": s.independence_assessment,
        "reviewer_form": _form("independence"),
    }


# --------------------------------------------------------------------------- guards


def _strings(obj, skip_evidence_text: bool = True):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if skip_evidence_text and key == "document_text":
                continue
            yield from _strings(value, skip_evidence_text)
    elif isinstance(obj, list):
        for value in obj:
            yield from _strings(value, skip_evidence_text)
    elif isinstance(obj, str):
        yield obj


def _contains(text: str, value: str) -> bool:
    return bool(value) and re.search(rf"(?<![\w.]){re.escape(value)}(?![\w])", text) is not None


def _check_item_text(stage: str, scenario: Scenario, item: dict) -> None:
    """Refuse an item whose non-evidence text states a value it must not carry. The ground-truth value of a false
    scenario may only appear in the evidence document; in the independence stage neither the ground-truth value
    nor the claimed value may appear at all (that stage carries no claim). The claimed value legitimately appears
    in claims and message templates elsewhere."""
    texts = list(_strings(item))
    values = [scenario.evidence.ground_truth_value]
    if stage == "independence":
        values.append(scenario.claim.asserted_value)
    for value in values:
        if value != scenario.claim.asserted_value or stage == "independence":
            if any(_contains(t, value) for t in texts):
                _refuse(f"a {stage}-stage package would carry a value it must not carry")


# --------------------------------------------------------------------------- build and write


def _group_pairs(scenarios: list[Scenario]) -> list[tuple[Scenario, Scenario]]:
    groups: dict[str, list[Scenario]] = {}
    for s in scenarios:
        groups.setdefault(s.pair_id, []).append(s)
    pairs = []
    for pair_id in sorted(groups):
        if sorted(s.truth_status for s in groups[pair_id]) != ["false", "true"]:
            _refuse("every pair must have exactly one true and one false scenario")
        by_truth = {s.truth_status: s for s in groups[pair_id]}
        pairs.append((by_truth["true"], by_truth["false"]))
    return pairs


def _readme(stage: str) -> str:
    return f"# Review package — stage: {stage}\n\n{_READMES[stage]}\n\n{_SCALE}\n\n{_COMMON}\n\nRecord your answers and scores in `reviewer_form` of each item.\n"


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _build(scenarios: list[Scenario], salt: str, repo_root: Path) -> dict[str, dict[str, str]]:
    """stage -> {relative path: file text}, plus the key material. Raises ExportRefused before any file exists."""
    ids = [s.scenario_id for s in scenarios]
    if not scenarios:
        _refuse("there are no scenarios to export")
    if len(set(ids)) != len(ids):
        _refuse("duplicate scenario ids")
    texts: dict[str, str] = {}
    for s in scenarios:
        path = evidence_path(s, repo_root)
        if not path.is_file():
            _refuse("an evidence file is missing")
        texts[s.scenario_id] = path.read_text(encoding="utf-8")
    pairs = _group_pairs(scenarios)

    files: dict[str, dict[str, str]] = {stage: {} for stage in STAGES}
    mapping: dict[str, dict[str, dict]] = {stage: {} for stage in STAGES}

    def put(stage: str, item: dict, scenario_list: list[Scenario], evidence_ids: bool) -> None:
        files[stage][f"items/{item['review_id']}.json"] = _dump(item)
        if evidence_ids:
            for s in scenario_list:
                files[stage][f"evidence/{opaque_id(salt, stage, 'evidence', s.scenario_id)}.md"] = texts[s.scenario_id]
        mapping[stage][item["review_id"]] = {
            "scenario_ids": sorted(s.scenario_id for s in scenario_list),
            "pair_id": scenario_list[0].pair_id,
            "truth_status": {s.scenario_id: s.truth_status for s in scenario_list},
        }

    for s in sorted(scenarios, key=lambda x: x.scenario_id):
        for stage, builder in (("fact", lambda: _fact_item(s, salt, texts[s.scenario_id])),
                               ("cue", lambda: _cue_item(s, salt)),
                               ("independence", lambda: _independence_item(s, salt))):
            item = builder()
            _check_item_text(stage, s, item)
            put(stage, item, [s], stage in _EVIDENCE_STAGES)
    for true_s, false_s in pairs:
        item = _pair_item(true_s, false_s, salt, texts)
        for s in (true_s, false_s):
            _check_item_text("pair", s, item)
        put("pair", item, [true_s, false_s], True)

    for stage in STAGES:
        files[stage]["README.md"] = _readme(stage)
    return {"files": files, "mapping": mapping}


def _manifest(stage: str, files: dict[str, bytes]) -> tuple[str, dict]:
    entries = [{"path": p, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for p, b in sorted(files.items())]
    combined = hashlib.sha256("\n".join(f"{e['path']}:{e['sha256']}" for e in entries).encode("utf-8")).hexdigest()
    return combined, {"manifest_version": 1, "stage": stage, "files": entries, "combined_digest": combined}


def export_stage_packages(scenarios, out_dir, key_dir, *, salt: str | None = None, repo_root: Path = REPO_ROOT) -> dict:
    """Write the four stage packages to ``out_dir/<stage>/`` and the key material to ``key_dir/answer_key.json``.

    Returns {"salt", "stages": {stage: {"combined_digest", "files": {relative path: sha256}}}}."""
    check_key_dir_outside_repo(key_dir, out_dir, repo_root)
    salt = new_salt() if salt is None else salt
    if not _SALT.fullmatch(salt):
        _refuse("the salt must be 64 lowercase hexadecimal characters")
    out, key_out = Path(out_dir), Path(key_dir)
    for stage in STAGES:
        stage_dir = out / stage
        if stage_dir.exists() and any(stage_dir.iterdir()):
            _refuse("a target stage directory already exists and is not empty")
    built = _build(list(scenarios), salt, Path(repo_root))

    result: dict = {"salt": salt, "stages": {}}
    for stage in STAGES:
        stage_dir = out / stage
        raw = {path: text.encode("utf-8") for path, text in built["files"][stage].items()}
        for path, data in raw.items():
            target = stage_dir / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        combined, manifest = _manifest(stage, raw)
        (stage_dir / "package_manifest.json").write_text(_dump(manifest), encoding="utf-8")
        result["stages"][stage] = {"combined_digest": combined, "files": {e["path"]: e["sha256"] for e in manifest["files"]}}

    key_out.mkdir(parents=True, exist_ok=True)
    os.chmod(key_out, 0o700)
    key_file = key_out / "answer_key.json"
    key_file.write_text(_dump({
        "key_version": 1,
        "salt": salt,
        "created_on": datetime.now(timezone.utc).isoformat(),
        "stages": {stage: {"items": built["mapping"][stage]} for stage in STAGES},
        "package_digests": {stage: result["stages"][stage]["combined_digest"] for stage in STAGES},
    }), encoding="utf-8")
    os.chmod(key_file, 0o600)
    return result


def verify_package(stage_dir) -> list[str]:
    """Problems found in a written package (empty list means intact): bad manifest, missing, extra or changed files."""
    stage_dir = Path(stage_dir)
    manifest_path = stage_dir / "package_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        listed = {e["path"]: e["sha256"] for e in manifest["files"]}
        recorded = manifest["combined_digest"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["the package manifest is missing or malformed"]
    problems = []
    actual = {str(p.relative_to(stage_dir)): p for p in stage_dir.rglob("*") if p.is_file() and p != manifest_path}
    for path in sorted(listed):
        if path not in actual:
            problems.append(f"listed file is missing: {path}")
        elif hashlib.sha256(actual[path].read_bytes()).hexdigest() != listed[path]:
            problems.append(f"file content differs from the manifest: {path}")
    for path in sorted(set(actual) - set(listed)):
        problems.append(f"file is not listed in the manifest: {path}")
    combined = hashlib.sha256("\n".join(f"{p}:{h}" for p, h in sorted(listed.items())).encode("utf-8")).hexdigest()
    if combined != recorded:
        problems.append("the combined digest does not match the listed hashes")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenario-dir", default=str(REPO_ROOT / "data/scenarios/v2"))
    p.add_argument("--out", required=True, help="directory for the four stage packages (there is no default)")
    p.add_argument("--key-dir", required=True, help="directory OUTSIDE the repository for answer_key.json (there is no default)")
    args = p.parse_args(argv)
    try:
        result = export_stage_packages(load_scenario_dir(args.scenario_dir), args.out, args.key_dir)
    except ExportRefused as exc:
        print(f"refused: {exc}")
        return 2
    for stage in STAGES:
        print(f"{stage}: {len(result['stages'][stage]['files'])} files, digest {result['stages'][stage]['combined_digest']}")
    print("answer key and salt written to the key directory; the salt is not printed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
