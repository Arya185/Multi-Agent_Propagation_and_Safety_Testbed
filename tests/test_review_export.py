import json
import re
from pathlib import Path

import pytest

from maps.review_export import STAGES, ExportRefused, export_stage_packages, new_salt, opaque_id
from maps.scenarios import load_scenario_dir

# Stage 4J.4: the export now writes one package per review stage with a fresh random salt and refuses a key
# directory inside the repository. The committed `data/review/blinded` package was made by the earlier
# single-package export with a public salt; it is OBSOLETE, is not distributed and is left untouched. The tests
# below that read it only scan it for leaks. No test in this module reads the repository's answer key.
ROOT = Path(__file__).resolve().parents[1]
BLINDED = ROOT / "data/review/blinded"
SALT = "ab" * 32

FORBIDDEN_KEYS = {"truth_status", "supports_claim", "ground_truth_value", "scenario_id", "pair_id",
                  "construction_note", "root_id", "status", "name_collision_check", "visible_to_receiver",
                  "sha256", "verification_status"}
FORBIDDEN_TEXT = ("truth_status", "supports_claim", "ground_truth_value", "construction", "deliberately differs",
                  "equals the value", "pair_id", "scenario_id", "answer_key.json")


@pytest.fixture(scope="module")
def scenarios():
    return load_scenario_dir(ROOT / "data/scenarios/v2")


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def _all_blinded_files():
    return [p for p in BLINDED.rglob("*") if p.is_file()]


def test_committed_obsolete_blinded_package_has_one_item_and_evidence_copy_per_scenario(scenarios):
    items = sorted((BLINDED / "items").glob("*.json"))
    evid = sorted((BLINDED / "evidence").glob("*.md"))
    assert len(items) == len(evid) == 10
    for p in items:
        assert re.fullmatch(r"rv-[0-9a-f]{8}\.json", p.name)
    for p in evid:
        assert re.fullmatch(r"ev-[0-9a-f]{8}\.md", p.name)


def test_blinded_files_leak_no_truth_labels_or_internal_ids(scenarios):
    internal = {s.scenario_id for s in scenarios} | {r.root_id for s in scenarios for r in s.communication_roots}
    pair_ids = {s.pair_id for s in scenarios}
    for p in _all_blinded_files():
        text = p.read_text(encoding="utf-8")
        for needle in FORBIDDEN_TEXT:
            assert needle not in text, (p.name, needle)
        for ident in internal:
            assert ident not in text, (p.name, ident)
        for pid in pair_ids:  # whole-word match so "sw" is not found inside "answers"
            assert not re.search(rf"(?<![A-Za-z]){pid}(?![A-Za-z])", text), (p.name, pid)
        if p.suffix == ".json":
            assert not (set(_walk_keys(json.loads(text))) & FORBIDDEN_KEYS), p.name
        assert not re.search(r"(?<![A-Za-z])(biz|sci|sw|geo|hist)-[abTF]\b", text), p.name


def test_blinded_item_contents_are_complete_and_form_is_empty(scenarios):
    for p in (BLINDED / "items").glob("*.json"):
        it = json.loads(p.read_text())
        assert it["claim"]["text"] and it["claim"]["quantity_definition"]
        assert len(it["message_templates"]) == 4 and len(it["communication_roots"]) == 4
        assert [r["label"] for r in it["communication_roots"]] == ["R1", "R2", "R3", "R4"]
        assert it["evidence"]["document_text"].startswith("SYNTHETIC DOCUMENT")
        assert (BLINDED / "evidence" / f"{it['evidence']['evidence_id']}.md").read_text() == it["evidence"]["document_text"]
        assert all(r["measurement"]["can_establish_exact_quantity"] for r in it["communication_roots"])
        assert it["shared_factors"] and it["independence_assessment"]
        form = it["reviewer_form"]
        assert form["reviewer"] is None and form["document_judgement"] is None
        assert form["roots_independent"] is None and form["ambiguities"] == ""


def test_answer_key_from_a_fresh_export_is_separate_and_complete(tmp_path, scenarios):
    out, key_dir = tmp_path / "packages", tmp_path / "key"
    export_stage_packages(scenarios, out, key_dir, salt=SALT)
    key = json.loads((key_dir / "answer_key.json").read_text())
    assert key["salt"] == SALT
    fact_items = key["stages"]["fact"]["items"]
    assert len(fact_items) == 10 and sum(v["truth_status"][v["scenario_ids"][0]] == "true" for v in fact_items.values()) == 5
    by_id = {s.scenario_id: s for s in scenarios}
    for rid, v in fact_items.items():
        sid = v["scenario_ids"][0]
        assert opaque_id(SALT, "fact", "review", sid) == rid
        assert by_id[sid].truth_status == v["truth_status"][sid]
        assert (out / "fact" / "items" / f"{rid}.json").is_file()
    # the key sits outside the packages and no package file is the key
    assert out not in key_dir.parents and key_dir not in out.parents
    assert not any(p.name == "answer_key.json" for p in out.rglob("*"))


def test_export_is_deterministic_for_an_explicit_salt_and_differs_for_a_fresh_one(tmp_path, scenarios):
    a = export_stage_packages(scenarios, tmp_path / "a", tmp_path / "ka", salt=SALT)
    b = export_stage_packages(scenarios, tmp_path / "b", tmp_path / "kb", salt=SALT)
    assert a == b
    read = lambda root: {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert read(tmp_path / "a") == read(tmp_path / "b")
    c = export_stage_packages(scenarios, tmp_path / "c", tmp_path / "kc")
    d = export_stage_packages(scenarios, tmp_path / "d", tmp_path / "kd")
    assert c["salt"] != d["salt"] and c["salt"] != SALT and len(c["salt"]) == 64
    assert set(c["stages"]["fact"]["files"]) != set(d["stages"]["fact"]["files"])  # ids differ with the salt


def test_export_refuses_key_inside_or_equal_to_the_package_directory(tmp_path, scenarios):
    for key_dir in (tmp_path / "b" / "key", tmp_path / "b"):
        with pytest.raises(ExportRefused, match="separate"):
            export_stage_packages(scenarios, tmp_path / "b", key_dir, salt=SALT)
    assert not (tmp_path / "b").exists()


def test_export_refuses_a_key_directory_inside_the_repository(tmp_path, scenarios):
    inside = ROOT / "data" / "review" / "pytest_key_dir_that_must_not_exist"
    with pytest.raises(ExportRefused, match="outside the repository"):
        export_stage_packages(scenarios, tmp_path / "b", inside, salt=SALT)
    assert not inside.exists() and not (tmp_path / "b").exists()


def test_opaque_ids_do_not_reveal_pairing_or_truth_and_are_not_reusable_across_salts(scenarios):
    ids = [opaque_id(SALT, "fact", "review", s.scenario_id) for s in scenarios]
    assert len(set(ids)) == 10
    for s in scenarios:
        rid = opaque_id(SALT, "fact", "review", s.scenario_id)
        assert s.scenario_id not in rid and s.truth_status not in rid and s.pair_id not in rid
        assert opaque_id(new_salt(), "fact", "review", s.scenario_id) != rid
        assert len({opaque_id(SALT, stage, "review", s.scenario_id) for stage in STAGES}) == len(STAGES)
