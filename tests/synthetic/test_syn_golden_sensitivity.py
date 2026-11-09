"""SYNTHETIC golden sensitivity, provenance fail-closed and recorder-safety tests.

Every mutation happens in memory or in pytest temporary directories. The accepted golden files and
the manifest are only read. A mutant that survives (is not detected) fails its test, and the final
report test lists detected and surviving mutants (visible with `-s`).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import platform
import re

import pytest

from maps.experiments.receiver import build_grid, grid_tsv
from maps.mock_client import MockClient

from synthetic_support import (  # noqa: F401
    GOLDEN_FILE_NAMES,
    LEGACY_SOURCE_FILES,
    MANIFEST_NAME,
    REQUIRED_MANIFEST_KEYS,
    REQUIRED_PROVENANCE_KEYS,
    SYN_ROOT,
    TOOLS_DIR,
    build_run_summary,
    compare_golden,
    current_provenance,
    dump_summary,
    golden_write_guard,
    load_manifest,
    load_syn_config,
    load_syn_scenarios,
    read_golden,
    run_mock_experiment,
    source_provenance,
    verify_provenance,
    verify_receipt,
)

_RESULTS: list[tuple[str, str, bool]] = []  # (kind, name, detected)


def _record(kind: str, name: str, detected: bool) -> None:
    _RESULTS.append((kind, name, detected))


# ---------------------------------------------------------------------------
# Text and structured mutations of the accepted golden contents (in memory only)
# ---------------------------------------------------------------------------
def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def m_char_flip(t: str) -> str:
    i = next(k for k in range(len(t) // 2, len(t)) if t[k].isalnum())
    return t[:i] + ("X" if t[i] != "X" else "Y") + t[i + 1 :]


def m_swap_rows(t: str) -> str:
    rows = _lines(t)
    assert rows[2] != rows[3]
    rows[2], rows[3] = rows[3], rows[2]
    return "".join(rows)


def m_delete_row(t: str) -> str:
    rows = _lines(t)
    del rows[len(rows) // 2]
    return "".join(rows)


def m_drop_final_newline(t: str) -> str:
    assert t.endswith("\n")
    return t[:-1]


def m_crlf(t: str) -> str:
    return t.replace("\n", "\r\n")


def m_truncate(t: str) -> str:
    return t[: len(t) // 2]


def m_episode_id(t: str) -> str:
    m = re.search(r"ep_[0-9a-f]{12}", t)
    assert m
    old = m.group(0)
    return t[: m.start()] + old[:-1] + ("0" if old[-1] != "0" else "1") + t[m.end() :]


def m_seed_jsonl(t: str) -> str:
    m = re.search(r'"seed":\s*(\d+)', t)
    assert m
    return t[: m.start(1)] + str(int(m.group(1)) + 1) + t[m.end(1) :]


def m_numeric_jsonl(t: str) -> str:
    m = re.search(r'"confidence":\s*(\d+)', t)
    assert m
    return t[: m.start(1)] + str(int(m.group(1)) + 1) + t[m.end(1) :]


def _tsv_bump(t: str, column: str) -> str:
    lines = t.split("\n")
    col = lines[0].split("\t").index(column)
    fields = lines[1].split("\t")
    fields[col] = str(int(fields[col]) + 1)
    lines[1] = "\t".join(fields)
    return "\n".join(lines)


def m_seed_tsv(t: str) -> str:
    return _tsv_bump(t, "seed")


def m_numeric_tsv(t: str) -> str:
    return _tsv_bump(t, "n_messages")


def _json_mutation(edit):
    def apply(t: str) -> str:
        doc = json.loads(t)
        edit(doc)
        return dump_summary(doc)

    return apply


def _edit_float(doc: dict) -> None:
    for row in doc["summary"]:
        for key, value in row.items():
            if isinstance(value, float):
                row[key] = value + 1e-6
                return
    raise AssertionError("no float found")


def _edit_int(doc: dict) -> None:
    doc["summary"][0]["n_episodes"] += 1


def _edit_reorder(doc: dict) -> None:
    rows = doc["summary"]
    assert rows[0] != rows[1]
    rows[0], rows[1] = rows[1], rows[0]


def _edit_delete_row(doc: dict) -> None:
    del doc["contrast_gaps"][0]


def _edit_delete_key(doc: dict) -> None:
    del doc["manifest"]["n_episodes"]


def _edit_string(doc: dict) -> None:
    doc["summary"][0]["model_alias"] += "x"


def _edit_digest(doc: dict) -> None:
    d = doc["calls"]["normalized_digest"]
    doc["calls"]["normalized_digest"] = ("0" if d[0] != "0" else "1") + d[1:]


# (golden, name) -> (category, mutation). Format-only mutations are not applied to the summary,
# whose comparison is semantic JSON (whitespace and line endings are not meaningful there).
MUTANTS = {
    ("grid", "char_flip"): ("char", m_char_flip),
    ("grid", "swap_rows"): ("row_reorder", m_swap_rows),
    ("grid", "delete_row"): ("row_delete", m_delete_row),
    ("grid", "truncate"): ("row_delete", m_truncate),
    ("grid", "drop_final_newline"): ("format", m_drop_final_newline),
    ("grid", "crlf_line_endings"): ("format", m_crlf),
    ("grid", "numeric_n_messages"): ("numeric", m_numeric_tsv),
    ("grid", "episode_id"): ("episode_id", m_episode_id),
    ("grid", "seed"): ("seed", m_seed_tsv),
    ("episodes", "char_flip"): ("char", m_char_flip),
    ("episodes", "swap_rows"): ("row_reorder", m_swap_rows),
    ("episodes", "delete_row"): ("row_delete", m_delete_row),
    ("episodes", "truncate"): ("row_delete", m_truncate),
    ("episodes", "drop_final_newline"): ("format", m_drop_final_newline),
    ("episodes", "crlf_line_endings"): ("format", m_crlf),
    ("episodes", "numeric_confidence"): ("numeric", m_numeric_jsonl),
    ("episodes", "episode_id"): ("episode_id", m_episode_id),
    ("episodes", "seed"): ("seed", m_seed_jsonl),
    ("summary", "char_flip"): ("char", m_char_flip),
    ("summary", "truncate"): ("row_delete", m_truncate),
    ("summary", "row_reorder"): ("row_reorder", _json_mutation(_edit_reorder)),
    ("summary", "row_delete"): ("row_delete", _json_mutation(_edit_delete_row)),
    ("summary", "key_delete"): ("row_delete", _json_mutation(_edit_delete_key)),
    ("summary", "float_perturbation"): ("numeric", _json_mutation(_edit_float)),
    ("summary", "int_change"): ("numeric", _json_mutation(_edit_int)),
    ("summary", "string_change"): ("char", _json_mutation(_edit_string)),
    ("summary", "calls_digest_change"): ("char", _json_mutation(_edit_digest)),
}
REQUIRED_CATEGORIES = {"char", "row_reorder", "row_delete", "numeric", "episode_id", "seed"}


@pytest.mark.parametrize("golden,name", sorted(MUTANTS), ids=[f"{g}-{n}" for g, n in sorted(MUTANTS)])
def test_text_mutation_is_detected(golden, name):
    _, mutate = MUTANTS[(golden, name)]
    accepted = read_golden(golden)
    mutated = mutate(accepted)
    assert mutated != accepted, "the mutation did not change the text (invalid mutant)"
    diff = compare_golden(golden, accepted, mutated)
    _record("text", f"{golden}:{name}", diff is not None)
    assert diff is not None, f"SURVIVING MUTANT: {golden}:{name}"


def test_comparison_is_not_trivially_failing():
    for golden in GOLDEN_FILE_NAMES:
        text = read_golden(golden)
        assert compare_golden(golden, text, text) is None


def test_mutation_set_covers_the_required_categories():
    assert {category for category, _ in MUTANTS.values()} >= REQUIRED_CATEGORIES
    for golden in GOLDEN_FILE_NAMES:
        assert sum(1 for g, _ in MUTANTS if g == golden) >= 7


def test_summary_comparison_ignores_legacy_embedded_provenance_only():
    text = read_golden("summary")
    doc = json.loads(text)
    doc.pop("provenance", None)
    assert compare_golden("summary", text, dump_summary(doc)) is None
    doc["provenance"] = {"anything": 1}
    assert compare_golden("summary", text, dump_summary(doc)) is None


# ---------------------------------------------------------------------------
# Behavioral mutations of mock-run inputs: rerun into a temporary directory, compare with goldens
# ---------------------------------------------------------------------------
def _golden_differences(out_dir, cfg, scenarios) -> dict[str, str]:
    found = {
        "grid": compare_golden("grid", read_golden("grid"), grid_tsv(build_grid(cfg, scenarios))),
        "episodes": compare_golden("episodes", read_golden("episodes"), (out_dir / "episodes.jsonl").read_text(encoding="utf-8")),
        "summary": compare_golden("summary", read_golden("summary"), dump_summary(build_run_summary(out_dir, False))),
    }
    return {k: v for k, v in found.items() if v}


def _rerun(tmp_path, cfg=None, scenarios=None, client=None) -> dict[str, str]:
    cfg = load_syn_config() if cfg is None else cfg
    scenarios = load_syn_scenarios() if scenarios is None else scenarios
    out = tmp_path / "behavioral_run"
    run_mock_experiment(out, client=client, cfg=cfg, scenarios=scenarios)
    return _golden_differences(out, cfg, scenarios)


def _scripted_client():
    payload = json.dumps(
        {"accepts_claim": True, "confidence": 51, "estimated_independent_roots": 2, "evidence_used": [], "reasoning": "SYNTHETIC"}
    )
    return MockClient("scripted", scripted=[payload])


def _cfg_update(cfg, **changes):
    return cfg.model_copy(update=changes)


def _model_id_changed(cfg):
    first = cfg.models[0].model_copy(update={"model_id": cfg.models[0].model_id + "-mutated"})
    return _cfg_update(cfg, models=[first, *cfg.models[1:]])


def _template_changed(scenarios):
    out = [s.model_copy(deep=True) for s in scenarios]
    out[0].message_templates[0] += " Mutated."
    return out


BEHAVIORAL = {
    "config_seed_plus_one": lambda c, s: (_cfg_update(c, seed=c.seed + 1), s, None),
    "experiment_id_changed": lambda c, s: (_cfg_update(c, experiment_id=c.experiment_id + "_mutated"), s, None),
    "repetitions_two": lambda c, s: (_cfg_update(c, design=c.design.model_copy(update={"repetitions": 2})), s, None),
    "temperature_changed": lambda c, s: (_cfg_update(c, sampling=c.sampling.model_copy(update={"temperature": 0.5})), s, None),
    "model_id_changed": lambda c, s: (_model_id_changed(c), s, None),
    "message_template_changed": lambda c, s: (c, _template_changed(s), None),
    "scripted_mock_answers": lambda c, s: (c, s, _scripted_client()),
    "mock_error_mode": lambda c, s: (c, s, MockClient("error")),
}


@pytest.mark.parametrize("name", sorted(BEHAVIORAL))
def test_behavioral_mutation_is_detected(tmp_path, name):
    cfg, scenarios, client = BEHAVIORAL[name](load_syn_config(), load_syn_scenarios())
    differences = _rerun(tmp_path, cfg, scenarios, client)
    _record("behavioral", name, bool(differences))
    assert differences, f"SURVIVING MUTANT: {name}"


@pytest.mark.parametrize("which", ["SYSTEM_PROMPT", "SOURCE_AWARE_INSTRUCTION"])
def test_prompt_mutation_is_detected(tmp_path, monkeypatch, which):
    import maps.prompts.receiver as prompts

    monkeypatch.setattr(prompts, which, getattr(prompts, which) + " Mutated.")
    differences = _rerun(tmp_path)
    _record("behavioral", f"prompt:{which}", bool(differences))
    assert differences, f"SURVIVING MUTANT: prompt {which}"


def test_unmutated_rerun_matches_every_golden(tmp_path):
    assert _rerun(tmp_path) == {}


# ---------------------------------------------------------------------------
# Provenance fail-closed (mutations of an in-memory copy of the manifest)
# ---------------------------------------------------------------------------
def _flip(hex_digest: str) -> str:
    return ("0" if hex_digest[0] != "0" else "1") + hex_digest[1:]


def _first_key(d: dict) -> str:
    return sorted(d)[0]


def _prov(m, name, fn):
    fn(m["provenance"][name])


PROVENANCE_MUTATIONS = {
    "unknown_digest_format_version": lambda m: m["provenance"].__setitem__("digest_format_version", 2),
    "unknown_manifest_format": lambda m: m.__setitem__("manifest_format", 2),
    "unsupported_algorithm": lambda m: m["provenance"].__setitem__("digest_algorithm", "md5"),
    "canonicalization_declaration_changed": lambda m: m.__setitem__("canonicalization", "sha256 over text lines"),
    "python_minor_version_mismatch": lambda m: m["provenance"].__setitem__("python_version", "2.7.18"),
    "source_file_added_since_recording": lambda m: m["provenance"]["source_files"].pop(_first_key(m["provenance"]["source_files"])),
    "source_file_removed_since_recording": lambda m: m["provenance"]["source_files"].__setitem__("zz_extra.py", "0" * 64),
    "source_file_digest_changed": lambda m: _prov(m, "source_files", lambda d: d.__setitem__(_first_key(d), _flip(d[_first_key(d)]))),
    "source_combined_digest_changed": lambda m: m["provenance"].__setitem__("source_digest", _flip(m["provenance"]["source_digest"])),
    "fixture_file_added_since_recording": lambda m: m["provenance"]["fixture_files"].pop(_first_key(m["provenance"]["fixture_files"])),
    "fixture_file_removed_since_recording": lambda m: m["provenance"]["fixture_files"].__setitem__("zz_extra.md", "0" * 64),
    "fixture_file_digest_changed": lambda m: _prov(m, "fixture_files", lambda d: d.__setitem__(_first_key(d), _flip(d[_first_key(d)]))),
    "fixture_combined_digest_changed": lambda m: m["provenance"].__setitem__("fixture_digest", _flip(m["provenance"]["fixture_digest"])),
    "helper_file_digest_changed": lambda m: _prov(m, "helper_files", lambda d: d.__setitem__(_first_key(d), _flip(d[_first_key(d)]))),
    "helper_combined_digest_changed": lambda m: m["provenance"].__setitem__("helper_digest", _flip(m["provenance"]["helper_digest"])),
    "golden_hash_changed": lambda m: m["goldens"].__setitem__(_first_key(m["goldens"]), _flip(m["goldens"][_first_key(m["goldens"])])),
    "golden_entry_removed": lambda m: m["goldens"].pop(_first_key(m["goldens"])),
    "goldens_digest_changed": lambda m: m.__setitem__("goldens_digest", _flip(m["goldens_digest"])),
}


def test_unmutated_manifest_verifies():
    assert verify_provenance(load_manifest()) == []


@pytest.mark.parametrize("key", REQUIRED_MANIFEST_KEYS)
def test_missing_manifest_field_fails_closed(key):
    manifest = copy.deepcopy(load_manifest())
    del manifest[key]
    problems = verify_provenance(manifest)
    _record("provenance", f"drop:{key}", bool(problems))
    assert problems, f"SURVIVING MUTANT: dropped manifest field {key}"


@pytest.mark.parametrize("key", REQUIRED_PROVENANCE_KEYS)
def test_missing_provenance_field_fails_closed(key):
    manifest = copy.deepcopy(load_manifest())
    del manifest["provenance"][key]
    problems = verify_provenance(manifest)
    _record("provenance", f"drop:provenance.{key}", bool(problems))
    assert problems, f"SURVIVING MUTANT: dropped provenance field {key}"


@pytest.mark.parametrize("name", sorted(PROVENANCE_MUTATIONS))
def test_provenance_mutation_fails_closed(name):
    manifest = copy.deepcopy(load_manifest())
    PROVENANCE_MUTATIONS[name](manifest)
    problems = verify_provenance(manifest)
    _record("provenance", name, bool(problems))
    assert problems, f"SURVIVING MUTANT: {name}"


def test_manifest_that_is_not_an_object_fails_closed():
    problems = verify_provenance([load_manifest()])
    _record("provenance", "manifest_is_not_an_object", bool(problems))
    assert problems


# ---------------------------------------------------------------------------
# Recorder safety (works only on temporary copies; the accepted goldens are never touched)
# ---------------------------------------------------------------------------
def _load_recorder():
    spec = importlib.util.spec_from_file_location("syn_record_goldens", TOOLS_DIR / "record_goldens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_golden_dir(dst):
    """A temporary copy of the accepted goldens. The legacy provenance block embedded in the accepted
    summary names the nine production files of the original recording; once any of them changes it can
    never match again, so the COPY's block is re-embedded for the current files (the accepted file on
    disk is never touched). Everything else, grid and episodes included, is a byte copy."""
    dst.mkdir(parents=True, exist_ok=True)
    for key, fname in GOLDEN_FILE_NAMES.items():
        (dst / fname).write_bytes(read_golden(key).encode("utf-8"))
    summary = dst / GOLDEN_FILE_NAMES["summary"]
    doc = json.loads(summary.read_text(encoding="utf-8"))
    doc["provenance"] = {
        **source_provenance(LEGACY_SOURCE_FILES),
        "python_version": platform.python_version(),
        "recorded_by": "test copy: legacy block re-embedded for the current source files",
    }
    summary.write_bytes(dump_summary(doc).encode("utf-8"))
    return dst


def _tree_hashes(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.rglob("*")) if p.is_file()}


def test_recorder_requires_explicit_confirmation(tmp_path):
    recorder = _load_recorder()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert recorder.main([], golden_dir=empty) == 2
    assert recorder.main(["--manifest-only"], golden_dir=empty) == 2
    assert list(empty.iterdir()) == []


def test_replace_requires_reason_and_expected_digest(tmp_path):
    recorder = _load_recorder()
    gdir = _seed_golden_dir(tmp_path / "golden")
    before = _tree_hashes(gdir)
    assert recorder.main(["--confirm-authorized", "--replace"], golden_dir=gdir) == 2
    assert recorder.main(["--confirm-authorized", "--replace", "--reason", "x"], golden_dir=gdir) == 2
    assert _tree_hashes(gdir) == before


def test_recorder_refuses_to_overwrite_existing_goldens(tmp_path):
    recorder = _load_recorder()
    gdir = _seed_golden_dir(tmp_path / "golden")
    before = _tree_hashes(gdir)
    assert recorder.main(["--confirm-authorized"], golden_dir=gdir) == 3
    assert _tree_hashes(gdir) == before


def test_manifest_only_hashes_accepted_goldens_and_is_write_once(tmp_path):
    recorder = _load_recorder()
    gdir = _seed_golden_dir(tmp_path / "golden")
    goldens_before = _tree_hashes(gdir)
    assert recorder.main(["--manifest-only", "--confirm-authorized"], golden_dir=gdir) == 0
    written = json.loads((gdir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert verify_provenance(written, golden_dir=gdir) == []
    assert written["legacy_embedded_provenance"]["matches_current_files"] is True
    assert {k: v for k, v in _tree_hashes(gdir).items() if k != MANIFEST_NAME} == goldens_before
    again = _tree_hashes(gdir)
    assert recorder.main(["--manifest-only", "--confirm-authorized"], golden_dir=gdir) == 3
    assert _tree_hashes(gdir) == again
    accepted = load_manifest()["goldens"]            # grid and episodes are byte copies; the summary copy differs only in its legacy block
    for fname in (GOLDEN_FILE_NAMES["grid"], GOLDEN_FILE_NAMES["episodes"]):
        assert written["goldens"][fname] == accepted[fname]
    summary_name = GOLDEN_FILE_NAMES["summary"]
    assert written["goldens"][summary_name] == hashlib.sha256((gdir / summary_name).read_bytes()).hexdigest()
    assert compare_golden("summary", read_golden("summary"), (gdir / summary_name).read_text(encoding="utf-8")) is None
    assert written["provenance"] == current_provenance()
    assert (gdir.parent / "audit" / "manifest_receipt.json").is_file()


def test_manifest_only_stops_when_a_golden_does_not_match(tmp_path):
    recorder = _load_recorder()
    gdir = _seed_golden_dir(tmp_path / "golden")
    episodes = gdir / GOLDEN_FILE_NAMES["episodes"]
    episodes.write_bytes(m_swap_rows(episodes.read_text(encoding="utf-8")).encode("utf-8"))
    assert recorder.main(["--manifest-only", "--confirm-authorized"], golden_dir=gdir) == 3
    assert not (gdir / MANIFEST_NAME).exists()


def test_recording_into_an_empty_directory_reproduces_the_accepted_goldens(tmp_path):
    recorder = _load_recorder()
    gdir = tmp_path / "fresh"
    assert recorder.main(["--confirm-authorized"], golden_dir=gdir) == 0
    assert (gdir / GOLDEN_FILE_NAMES["grid"]).read_text(encoding="utf-8") == read_golden("grid")
    assert (gdir / GOLDEN_FILE_NAMES["episodes"]).read_text(encoding="utf-8") == read_golden("episodes")
    assert compare_golden("summary", read_golden("summary"), (gdir / GOLDEN_FILE_NAMES["summary"]).read_text(encoding="utf-8")) is None
    fresh = json.loads((gdir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert verify_provenance(fresh, golden_dir=gdir) == []
    assert fresh["provenance"] == current_provenance()
    assert verify_receipt(gdir / MANIFEST_NAME, gdir.parent / "audit" / "manifest_receipt.json", gdir.parent / "audit" / "manifests") == []


def test_replace_needs_the_matching_old_manifest_digest_and_archives_old_files(tmp_path):
    recorder = _load_recorder()
    gdir = _seed_golden_dir(tmp_path / "golden")
    assert recorder.main(["--manifest-only", "--confirm-authorized"], golden_dir=gdir) == 0
    episodes = gdir / GOLDEN_FILE_NAMES["episodes"]
    tampered = m_swap_rows(episodes.read_text(encoding="utf-8")).encode("utf-8")
    episodes.write_bytes(tampered)
    before = _tree_hashes(gdir)
    wrong = ["--confirm-authorized", "--replace", "--reason", "test", "--expect-old-manifest-sha256", "0" * 64]
    assert recorder.main(wrong, golden_dir=gdir) == 3
    assert _tree_hashes(gdir) == before
    old_sha = hashlib.sha256((gdir / MANIFEST_NAME).read_bytes()).hexdigest()
    right = ["--confirm-authorized", "--replace", "--reason", "test", "--expect-old-manifest-sha256", old_sha]
    assert recorder.main(right, golden_dir=gdir) == 0
    assert episodes.read_text(encoding="utf-8") == read_golden("episodes")
    audit = gdir.parent / "audit"
    assert (audit / "replaced" / old_sha[:12] / GOLDEN_FILE_NAMES["episodes"]).read_bytes() == tampered
    assert (audit / "manifests" / f"golden_manifest.{old_sha}.json").is_file()
    assert not (gdir / "superseded").exists()
    assert verify_provenance(json.loads((gdir / MANIFEST_NAME).read_text(encoding="utf-8")), golden_dir=gdir) == []


def test_accepted_goldens_and_manifest_are_unchanged_by_this_module():
    assert verify_provenance(load_manifest()) == []


def test_zz_mutation_report(capsys):
    detected = [(k, n) for k, n, ok in _RESULTS if ok]
    survived = [(k, n) for k, n, ok in _RESULTS if not ok]
    with capsys.disabled():
        print(f"\nMUTATION REPORT: {len(_RESULTS)} mutants evaluated, {len(detected)} detected, {len(survived)} surviving")
        for kind in ("text", "behavioral", "provenance"):
            names = [n for k, n in detected if k == kind]
            print(f"  {kind}: {len(names)} detected")
        for k, n in survived:
            print(f"  SURVIVED: {k}:{n}")
    assert survived == []
