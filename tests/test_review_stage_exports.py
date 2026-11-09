"""Stage 4J.4 per-stage blind review package exports.

All output goes to pytest tmp_path (outside the repository). The repository's real answer key
is never opened; the answer_key.json read here is the exporter's own output in tmp_path.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from maps.review_export import (
    STAGES, ExportRefused, check_key_dir_outside_repo, export_stage_packages, new_salt, opaque_id,
    verify_package,
)
from maps.scenarios import REPO_ROOT, load_scenario_dir
from maps.schemas import STAGE_CRITERIA, Scenario

SCEN_DIR = REPO_ROOT / "data" / "scenarios" / "v2"
SALT = "ab" * 32
SALT2 = "01" * 32
KIND_PREFIX = {"review": "rv", "evidence": "ev", "pair": "pr"}
ID_RE = re.compile(r"^(rv|ev|pr)-[0-9a-f]{12}$")

FORBIDDEN_KEYS = {
    "truth_status", "supports_claim", "ground_truth_value", "scenario_id", "pair_id", "root_id",
    "construction_note", "status", "name_collision_check", "visible_to_receiver", "sha256",
    "verification_status", "author_id", "scenario_version", "supersedes", "reviewer_assignments",
    "conflict_declarations", "review_submissions", "adjudication", "asserted_value", "entity", "salt",
}
MEAS = {"measures_claimed_quantity", "can_establish_exact_quantity", "coverage_note", "resolution_note"}


@pytest.fixture(scope="module")
def scenarios() -> list[Scenario]:
    return load_scenario_dir(SCEN_DIR)


def dirs(tmp_path: Path, name: str = "x") -> tuple[Path, Path]:
    out, key = tmp_path / f"out_{name}", tmp_path / f"key_{name}"
    return out, key


def run(tmp_path, scenarios, salt=SALT, name="x"):
    out, key = dirs(tmp_path, name)
    res = export_stage_packages(scenarios, out, key, salt=salt)
    return out, key, res


def load_key(key: Path) -> dict:
    return json.loads((key / "answer_key.json").read_text(encoding="utf-8"))


def items_of(out: Path, stage: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / stage / "items").glob("*.json"))]


def all_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


def test_tmp_paths_outside_repo(tmp_path):
    assert REPO_ROOT.resolve() not in [tmp_path.resolve(), *tmp_path.resolve().parents]


# 1 ---------------------------------------------------------------------------------------------
def form_keys(stage):
    return {"reviewer_id", "stage", "scores", "answers", "notes"}


def check_form(item, stage):
    form = item["reviewer_form"]
    assert set(form) == form_keys(stage)
    assert form["reviewer_id"] is None and form["stage"] == stage and form["notes"] == ""
    assert form["scores"] == {c: None for c in STAGE_CRITERIA[stage]}
    assert isinstance(form["answers"], dict)
    assert all(v is None or v == "" for v in form["answers"].values())


def test_exact_key_sets_per_stage(tmp_path, scenarios):
    out, _, _ = run(tmp_path, scenarios)
    for it in items_of(out, "fact"):
        assert set(it) == {"review_id", "stage", "claim", "communication_roots", "evidence", "reviewer_form"}
        assert it["stage"] == "fact"
        assert set(it["claim"]) == {"text", "quantity_definition", "calendar_convention"}
        assert set(it["evidence"]) == {"evidence_id", "document_type", "document_text"}
        assert len(it["communication_roots"]) == 4
        assert [r["label"] for r in it["communication_roots"]] == ["R1", "R2", "R3", "R4"]
        for r in it["communication_roots"]:
            assert set(r) == {"label", "acquisition_process", "instrument_class", "measurement"}
            assert set(r["measurement"]) == MEAS
        check_form(it, "fact")
    for it in items_of(out, "cue"):
        assert set(it) == {"review_id", "stage", "message_templates", "communication_roots", "reviewer_form"}
        assert len(it["message_templates"]) == 4 and all(isinstance(t, str) for t in it["message_templates"])
        for r in it["communication_roots"]:
            assert set(r) == {"label", "stated_origin"}
        check_form(it, "cue")
    for it in items_of(out, "pair"):
        assert set(it) == {"review_id", "stage", "members", "reviewer_form"}
        assert [m["position"] for m in it["members"]] == ["A", "B"]
        for m in it["members"]:
            assert set(m) == {"position", "domain", "claim", "communication_roots", "evidence"}
            assert set(m["claim"]) == {"text", "quantity_definition", "calendar_convention", "attribute"}
            assert set(m["evidence"]) == {"evidence_id", "document_type", "document_text"}
            for r in m["communication_roots"]:
                assert set(r) == {"label", "stated_origin", "acquisition_process", "instrument_class",
                                  "artifact_type", "quality_tier"}
        check_form(it, "pair")
    for it in items_of(out, "independence"):
        assert set(it) == {"review_id", "stage", "communication_roots", "shared_factors",
                           "independence_assessment", "reviewer_form"}
        for r in it["communication_roots"]:
            assert set(r) == {"label", "stated_origin", "description", "acquisition_kind", "acquisition_process",
                              "artifact_type", "operator_id", "instrument_id", "instrument_class",
                              "quality_tier", "measurement", "upstream_ids"}
            assert set(r["measurement"]) == MEAS
        for f in it["shared_factors"]:
            assert set(f) == {"factor", "affects_roots", "severity", "note"}
            assert all(re.fullmatch(r"R[1-4]", a) for a in f["affects_roots"])
        check_form(it, "independence")


# 2 ---------------------------------------------------------------------------------------------
def test_no_forbidden_keys_or_identifiers(tmp_path, scenarios):
    out, key, _ = run(tmp_path, scenarios)
    files = all_files(out)
    assert files
    assert not [p for p in files if p.name == "answer_key.json"]
    names = {s.scenario_id for s in scenarios} | {s.pair_id for s in scenarios}
    names |= {r.root_id for s in scenarios for r in s.communication_roots}
    for p in files:
        text = p.read_text(encoding="utf-8")
        assert SALT not in text, p
        if p.suffix == ".json" and p.name != "package_manifest.json":
            bad = set(walk_keys(json.loads(text))) & FORBIDDEN_KEYS
            assert not bad, (p, bad)
        for n in names:
            assert not re.search(rf"(?<![A-Za-z0-9_-]){re.escape(n)}(?![A-Za-z0-9_-])", text), (p, n)
    assert (key / "answer_key.json").is_file()


# 3 ---------------------------------------------------------------------------------------------
def test_namespaces_distinct_and_documented(tmp_path, scenarios):
    out, key, _ = run(tmp_path, scenarios)
    k = load_key(key)
    seen: dict[str, str] = {}
    for stage in STAGES:
        for it in items_of(out, stage):
            assert ID_RE.match(it["review_id"])
            ids = [it["review_id"]]
            if stage == "pair":
                ids += [m["evidence"]["evidence_id"] for m in it["members"]]
            elif stage == "fact":
                ids.append(it["evidence"]["evidence_id"])
            for i in ids:
                assert i not in seen, (i, stage, seen.get(i))
                seen[i] = stage
    for stage in ("fact", "cue", "independence"):
        expect = {opaque_id(SALT, stage, "review", s.scenario_id) for s in scenarios}
        assert {it["review_id"] for it in items_of(out, stage)} == expect
        assert set(k["stages"][stage]["items"]) == expect
    assert {it["review_id"] for it in items_of(out, "pair")} == {
        opaque_id(SALT, "pair", "pair", p) for p in {s.pair_id for s in scenarios}}
    # same scenario, different id per stage
    for s in scenarios:
        assert len({opaque_id(SALT, st, "review", s.scenario_id) for st in STAGES}) == 4
    fact = {it["review_id"]: it for it in items_of(out, "fact")}
    for s in scenarios:
        it = fact[opaque_id(SALT, "fact", "review", s.scenario_id)]
        assert it["evidence"]["evidence_id"] == opaque_id(SALT, "fact", "evidence", s.scenario_id)
    for stage in ("fact", "pair"):
        eids = {p.stem for p in (out / stage / "evidence").glob("ev-*.md")}
        assert eids and all(ID_RE.match(e) for e in eids)
    for stage in ("cue", "independence"):
        assert not (out / stage / "evidence").exists()


def test_opaque_id_properties():
    a = opaque_id(SALT, "fact", "review", "sw-a")
    assert a == opaque_id(SALT, "fact", "review", "sw-a")
    assert a.startswith("rv-") and ID_RE.match(a)
    assert opaque_id(SALT, "fact", "evidence", "sw-a").startswith("ev-")
    assert opaque_id(SALT, "pair", "pair", "sw").startswith("pr-")
    assert a != opaque_id(SALT2, "fact", "review", "sw-a")
    assert a != opaque_id(SALT, "cue", "review", "sw-a")
    assert a != opaque_id(SALT, "fact", "review", "sw-b")


# 4 ---------------------------------------------------------------------------------------------
def test_pair_token_linkage(tmp_path, scenarios):
    out, key, _ = run(tmp_path, scenarios)
    k = load_key(key)["stages"]["pair"]["items"]
    pair_items = items_of(out, "pair")
    assert len(pair_items) == 5 and len(k) == 5
    by_pair = {}
    for s in scenarios:
        by_pair.setdefault(s.pair_id, {})[s.scenario_id] = s.truth_status
    for pid, members in by_pair.items():
        token = opaque_id(SALT, "pair", "pair", pid)
        assert pid not in token.split("-")[1:]
        entry = k[token]
        assert set(entry["scenario_ids"]) == set(members)
        assert entry["pair_id"] == pid
        assert entry["truth_status"] == members
        assert sorted(entry["truth_status"].values()) == ["false", "true"]
    for it in pair_items:
        assert len(it["members"]) == 2


# 5 ---------------------------------------------------------------------------------------------
def a_is_true_map(out, key):
    k = load_key(key)["stages"]["pair"]["items"]
    res = {}
    for it in items_of(out, "pair"):
        entry = k[it["review_id"]]
        a_text = it["members"][0]["claim"]["text"]
        sid = next(s for s in entry["scenario_ids"] if a_text == SCEN_TEXT[s])
        res[it["review_id"]] = entry["truth_status"][sid] == "true"
    return res


SCEN_TEXT: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _fill_text(scenarios):
    SCEN_TEXT.update({s.scenario_id: s.claim.text for s in scenarios})


def test_pair_order_deterministic_and_balanced(tmp_path, scenarios):
    o1, k1, _ = run(tmp_path, scenarios, SALT, "a")
    o2, _, _ = run(tmp_path, scenarios, SALT, "b")
    for p in (o1 / "pair" / "items").glob("*.json"):
        assert p.read_bytes() == (o2 / "pair" / "items" / p.name).read_bytes()
    orders = set()
    per_pair: dict[str, set] = {}
    for i in range(12):
        out, key, _ = run(tmp_path, scenarios, new_salt(), f"s{i}")
        for tok, a_true in a_is_true_map(out, key).items():
            orders.add(a_true)
        pid_map = {e["pair_id"]: t for t, e in load_key(key)["stages"]["pair"]["items"].items()}
        amap = a_is_true_map(out, key)
        for pid, tok in pid_map.items():
            per_pair.setdefault(pid, set()).add(amap[tok])
    assert orders == {True, False}
    assert any(v == {True, False} for v in per_pair.values())


# 6 / 7 / 14 -------------------------------------------------------------------------------------
def test_default_salts_differ(tmp_path, scenarios):
    o1, k1 = dirs(tmp_path, "1")
    o2, k2 = dirs(tmp_path, "2")
    r1 = export_stage_packages(scenarios, o1, k1)
    r2 = export_stage_packages(scenarios, o2, k2)
    assert r1["salt"] != r2["salt"]
    for r in (r1, r2):
        assert re.fullmatch(r"[0-9a-f]{64}", r["salt"])
    ids1 = {it["review_id"] for st in STAGES for it in items_of(o1, st)}
    ids2 = {it["review_id"] for st in STAGES for it in items_of(o2, st)}
    assert not ids1 & ids2
    assert load_key(k1)["salt"] == r1["salt"]


def test_new_salt_format():
    s = new_salt()
    assert re.fullmatch(r"[0-9a-f]{64}", s) and s != new_salt()


@pytest.mark.parametrize("bad", ["abc", "AB" * 32, "zz" * 32, "ab" * 31, "ab" * 33, ""])
def test_invalid_salt_refused(tmp_path, scenarios, bad):
    out, key = dirs(tmp_path)
    with pytest.raises(ExportRefused) as e:
        export_stage_packages(scenarios, out, key, salt=bad)
    if bad:
        assert bad not in str(e.value)
    assert not out.exists() or not all_files(out)


def test_same_salt_identical_bytes(tmp_path, scenarios):
    o1, _, r1 = run(tmp_path, scenarios, SALT, "a")
    o2, _, r2 = run(tmp_path, scenarios, SALT, "b")
    f1 = {p.relative_to(o1).as_posix(): p.read_bytes() for p in all_files(o1)}
    f2 = {p.relative_to(o2).as_posix(): p.read_bytes() for p in all_files(o2)}
    assert f1 == f2
    assert r1["stages"] == r2["stages"] and r1["salt"] == r2["salt"] == SALT
    o3, _, _ = run(tmp_path, scenarios, SALT2, "c")
    f3 = {p.relative_to(o3).as_posix(): p.read_bytes() for p in all_files(o3)}
    assert f3 != f1


def test_salt_only_in_key_file(tmp_path, scenarios):
    out, key, res = run(tmp_path, scenarios)
    assert load_key(key)["salt"] == SALT and res["salt"] == SALT
    assert [p.name for p in all_files(key)] == ["answer_key.json"]
    assert not list(out.rglob("answer_key.json"))
    for p in all_files(out):
        assert SALT not in p.read_text(encoding="utf-8")
    k = load_key(key)
    assert k["key_version"] == 1 and set(k["stages"]) == set(STAGES)
    assert set(k["package_digests"]) == set(STAGES)
    for st in STAGES:
        assert k["package_digests"][st] == res["stages"][st]["combined_digest"]
    assert re.search(r"[+-]\d\d:\d\d$|Z$", k["created_on"])


def test_old_public_salt_absent_from_source():
    src = (REPO_ROOT / "src" / "maps" / "review_export.py").read_text(encoding="utf-8")
    assert "maps-review-v1" not in src


def test_whole_export_deterministic(tmp_path, scenarios):
    _, k1, r1 = run(tmp_path, scenarios, SALT, "a")
    _, k2, r2 = run(tmp_path, scenarios, SALT, "b")
    a, b = load_key(k1), load_key(k2)
    a.pop("created_on"), b.pop("created_on")
    assert a == b and r1 == r2


# 8 ---------------------------------------------------------------------------------------------
def test_measurement_whitelist(tmp_path, scenarios):
    out, _, _ = run(tmp_path, scenarios)
    n = 0
    for st in ("fact", "independence"):
        for it in items_of(out, st):
            for r in it["communication_roots"]:
                assert set(r["measurement"]) == MEAS
                n += 1
    assert n == 80
    extra = set(type(scenarios[0].communication_roots[0].measurement).model_fields) - MEAS
    for st in STAGES:
        for p in (out / st / "items").glob("*.json"):
            for name in extra:
                assert name not in set(walk_keys(json.loads(p.read_text(encoding="utf-8"))))


# 9 / 10 ----------------------------------------------------------------------------------------
def test_manifest_hashes_and_verify(tmp_path, scenarios):
    out, key, res = run(tmp_path, scenarios)
    for st in STAGES:
        d = out / st
        m = json.loads((d / "package_manifest.json").read_text(encoding="utf-8"))
        assert set(m) == {"manifest_version", "stage", "files", "combined_digest"}
        assert m["manifest_version"] == 1 and m["stage"] == st
        paths = [f["path"] for f in m["files"]]
        assert paths == sorted(paths) and "package_manifest.json" not in paths
        assert "README.md" in paths and any(p.startswith("items/") for p in paths)
        on_disk = {p.relative_to(d).as_posix() for p in all_files(d)} - {"package_manifest.json"}
        assert on_disk == set(paths)
        for f in m["files"]:
            data = (d / f["path"]).read_bytes()
            assert f["sha256"] == hashlib.sha256(data).hexdigest() and f["bytes"] == len(data)
        digest = hashlib.sha256("\n".join(f"{f['path']}:{f['sha256']}" for f in m["files"]).encode()).hexdigest()
        assert m["combined_digest"] == digest == res["stages"][st]["combined_digest"]
        assert res["stages"][st]["files"] == {f["path"]: f["sha256"] for f in m["files"]}
        assert verify_package(d) == []


def test_manifest_deterministic(tmp_path, scenarios):
    o1, _, _ = run(tmp_path, scenarios, SALT, "a")
    o2, _, _ = run(tmp_path, scenarios, SALT, "b")
    for st in STAGES:
        assert (o1 / st / "package_manifest.json").read_bytes() == (o2 / st / "package_manifest.json").read_bytes()


def test_tamper_detected(tmp_path, scenarios):
    def fresh(name):
        out, _, _ = run(tmp_path, scenarios, SALT, name)
        return out / "fact"

    d = fresh("t1")
    item = sorted((d / "items").glob("*.json"))[0]
    item.write_bytes(item.read_bytes() + b" ")
    assert verify_package(d)

    d = fresh("t2")
    sorted((d / "items").glob("*.json"))[0].unlink()
    assert verify_package(d)

    d = fresh("t3")
    sorted((d / "evidence").glob("ev-*.md"))[0].unlink()
    assert verify_package(d)

    d = fresh("t4")
    (d / "items" / "extra.json").write_text("{}", encoding="utf-8")
    assert verify_package(d)

    d = fresh("t5")
    mf = d / "package_manifest.json"
    m = json.loads(mf.read_text(encoding="utf-8"))
    m["files"][0]["sha256"] = "0" * 64
    mf.write_text(json.dumps(m), encoding="utf-8")
    assert verify_package(d)

    d = fresh("t6")
    (d / "package_manifest.json").write_text("not json", encoding="utf-8")
    assert verify_package(d)

    d = fresh("t7")
    (d / "package_manifest.json").unlink()
    assert verify_package(d)


# 11 --------------------------------------------------------------------------------------------
def test_key_dir_inside_repo_refused(tmp_path, scenarios):
    out = tmp_path / "out"
    kd = REPO_ROOT / "data" / "review" / "test_key_dir_that_must_not_exist"
    with pytest.raises(ExportRefused):
        check_key_dir_outside_repo(kd, out)
    with pytest.raises(ExportRefused):
        export_stage_packages(scenarios, out, kd, salt=SALT)
    assert not kd.exists() and not out.exists()
    with pytest.raises(ExportRefused):
        check_key_dir_outside_repo(REPO_ROOT, out)


def test_key_out_relation_refused(tmp_path):
    base = tmp_path / "base"
    for k, o in [(base / "out" / "k", base / "out"), (base / "k", base / "k" / "out"),
                 (base / "same", base / "same"), (base / "out" / "k", base / "out")]:
        with pytest.raises(ExportRefused):
            check_key_dir_outside_repo(k, o)


def test_symlink_into_repo_refused_and_tmp_accepted(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(REPO_ROOT / "data")
    with pytest.raises(ExportRefused):
        check_key_dir_outside_repo(link, tmp_path / "out")
    with pytest.raises(ExportRefused):
        check_key_dir_outside_repo(link / "sub", tmp_path / "out")
    assert check_key_dir_outside_repo(tmp_path / "keys", tmp_path / "out") is None


# 12 --------------------------------------------------------------------------------------------
def assert_clean_refusal(exc, scenarios, out, key):
    msg = str(exc.value)
    for s in scenarios:
        assert s.claim.asserted_value not in msg.split() and f" {s.claim.asserted_value} " not in f" {msg} "
    assert SALT not in msg
    assert not re.search(r"[0-9a-f]{64}", msg)
    assert not out.exists() or not all_files(out)
    assert not (key / "answer_key.json").exists()


def test_refuse_no_scenarios(tmp_path, scenarios):
    out, key = dirs(tmp_path)
    with pytest.raises(ExportRefused) as e:
        export_stage_packages([], out, key, salt=SALT)
    assert_clean_refusal(e, scenarios, out, key)


def test_refuse_incomplete_pair(tmp_path, scenarios):
    out, key = dirs(tmp_path)
    with pytest.raises(ExportRefused) as e:
        export_stage_packages([s for s in scenarios if s.scenario_id != "sw-b"], out, key, salt=SALT)
    assert_clean_refusal(e, scenarios, out, key)


def test_refuse_duplicate_scenario(tmp_path, scenarios):
    out, key = dirs(tmp_path)
    with pytest.raises(ExportRefused) as e:
        export_stage_packages([*scenarios, scenarios[0]], out, key, salt=SALT)
    assert_clean_refusal(e, scenarios, out, key)


def test_refuse_missing_evidence(tmp_path, scenarios):
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    out, key = tmp_path / "out_m", tmp_path / "key_m"
    with pytest.raises(ExportRefused) as e:
        export_stage_packages(scenarios, out, key, salt=SALT, repo_root=fake_repo)
    assert_clean_refusal(e, scenarios, out, key)


def test_refuse_existing_nonempty_stage_dir(tmp_path, scenarios):
    out, key = dirs(tmp_path)
    (out / "pair").mkdir(parents=True)
    (out / "pair" / "stale.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ExportRefused) as e:
        export_stage_packages(scenarios, out, key, salt=SALT)
    assert not (e.value is None)
    assert [p.name for p in all_files(out)] == ["stale.txt"]
    assert not (key / "answer_key.json").exists()
    assert SALT not in str(e.value)


def test_refuse_reexport_into_same_out(tmp_path, scenarios):
    out, key, _ = run(tmp_path, scenarios)
    before = {p: p.read_bytes() for p in all_files(out)}
    with pytest.raises(ExportRefused):
        export_stage_packages(scenarios, out, tmp_path / "key_other", salt=SALT2)
    assert {p: p.read_bytes() for p in all_files(out)} == before


def test_refuse_key_dir_inside_repo_via_export(tmp_path, scenarios):
    out = tmp_path / "o"
    with pytest.raises(ExportRefused):
        export_stage_packages(scenarios, out, tmp_path / "o" / "k", salt=SALT)
    assert not out.exists() or not all_files(out)


def test_independence_leak_guard(tmp_path, scenarios):
    for field_value in ("asserted_value", "ground_truth_value"):
        target = next(s for s in scenarios if s.scenario_id == "sw-a")
        d = target.model_dump(mode="json")
        val = (d["claim"]["asserted_value"] if field_value == "asserted_value"
               else d["evidence"]["ground_truth_value"])
        d["communication_roots"][0]["description"] = f"Counted {val} entries in the archive."
        leaky = Scenario.model_validate(d)
        mixed = [leaky if s.scenario_id == "sw-a" else s for s in scenarios]
        out, key = dirs(tmp_path, field_value)
        with pytest.raises(ExportRefused) as e:
            export_stage_packages(mixed, out, key, salt=SALT)
        assert_clean_refusal(e, scenarios, out, key)
        assert val not in str(e.value).split()


# 13 --------------------------------------------------------------------------------------------
def test_readmes(tmp_path, scenarios):
    out, _, _ = run(tmp_path, scenarios)
    for st in STAGES:
        text = (out / st / "README.md").read_text(encoding="utf-8")
        low = text.lower()
        assert "do not open the answer key" not in low
        assert "answer key" not in low and "answer_key" not in low
        assert text.strip()
        for crit in STAGE_CRITERIA[st]:
            assert crit in low
        if st != "fact":
            assert "truth" not in low
