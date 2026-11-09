"""The filesystem package provider against ``importlib.metadata`` (SYNTHETIC layouts in temporary directories).

The production module must not import ``importlib`` (the static import-closure check rejects it), so
these tests use the standard library only as a REFERENCE: the old provider is reproduced here, and the
new one is compared with it on the same layouts. Expected values are also stated explicitly so that
equality cannot hold vacuously. Nothing here installs or modifies packages.
"""

from __future__ import annotations

import ast
import importlib.metadata as reference_metadata
import inspect
import sys
import warnings
import zipfile
from pathlib import Path

import pytest

import maps.runs.provenance as prov
from maps.runs.provenance import collect_packages, collect_provenance, default_package_provider

from ri_support import tree_hashes


def reference(paths) -> list[tuple]:
    """What the replaced provider returned for these search-path entries."""
    reference_metadata.MetadataPathFinder.invalidate_caches()
    items = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for dist in reference_metadata.distributions(path=[str(p) for p in paths]):
            try:
                name = dist.metadata["Name"]
            except Exception:
                name = None
            try:
                version = dist.version
            except Exception:
                version = None
            items.append((name, version))
    return items


def same(paths) -> list[tuple]:
    """The new provider's result, asserted equal (as a sorted multiset) to the reference's."""
    ours = default_package_provider(paths)
    assert sorted(ours, key=repr) == sorted(reference(paths), key=repr), paths
    return ours


def dist(root: Path, dirname: str, text: str | bytes | None = "Metadata-Version: 2.1\nName: Foo\nVersion: 1.2\n", *, filename="METADATA", as_file=False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / dirname
    if as_file:
        target.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return target
    target.mkdir()
    if text is not None:
        (target / filename).write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    return target


def metadata(name="Foo", version="1.2") -> str:
    lines = ["Metadata-Version: 2.1"]
    if name is not None:
        lines.append(f"Name: {name}")
    if version is not None:
        lines.append(f"Version: {version}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The real environment
# ---------------------------------------------------------------------------
def test_matches_importlib_metadata_in_the_current_environment():
    ours = default_package_provider()
    theirs = reference(sys.path)
    assert len(ours) == len(theirs) > 0
    assert sorted(ours, key=repr) == sorted(theirs, key=repr)           # sorted (name, version) pairs
    assert all(isinstance(n, str) and isinstance(v, str) for n, v in ours) or any(n is None or v is None for n, v in ours)


def test_the_default_search_path_is_sys_path(tmp_path, monkeypatch):
    dist(tmp_path / "site", "Foo-1.2.dist-info")
    monkeypatch.setattr(sys, "path", [str(tmp_path / "site")])
    assert default_package_provider() == [("Foo", "1.2")]


def test_the_signature_is_backward_compatible():
    parameters = inspect.signature(default_package_provider).parameters
    assert list(parameters) == ["paths"] and parameters["paths"].default is None


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------
def test_a_dist_info_directory(tmp_path):
    dist(tmp_path / "site", "Foo-1.2.dist-info")
    assert same([tmp_path / "site"]) == [("Foo", "1.2")]


def test_an_egg_info_directory_with_pkg_info(tmp_path):
    dist(tmp_path / "site", "Bar-0.5-py3.12.egg-info", metadata("Bar", "0.5"), filename="PKG-INFO")
    assert same([tmp_path / "site"]) == [("Bar", "0.5")]


def test_an_egg_info_file(tmp_path):
    dist(tmp_path / "site", "Baz-3.egg-info", metadata("Baz", "3"), as_file=True)
    assert same([tmp_path / "site"]) == [("Baz", "3")]


def test_an_egg_directory_with_an_egg_info_child(tmp_path):
    egg = tmp_path / "site" / "Qux-1.egg"
    dist(egg, "EGG-INFO", metadata("Qux", "1"), filename="PKG-INFO")
    assert same([egg]) == [("Qux", "1")]
    assert same([tmp_path / "site"]) == []                              # the egg is not a distribution of its parent


def test_metadata_wins_over_pkg_info_and_an_empty_metadata_file_falls_back(tmp_path):
    both = dist(tmp_path / "a", "One-1.dist-info", metadata("One", "1"))
    (both / "PKG-INFO").write_text(metadata("Other", "9"), encoding="utf-8")
    empty = dist(tmp_path / "b", "Two-2.dist-info", "")
    (empty / "PKG-INFO").write_text(metadata("Two", "2"), encoding="utf-8")
    assert same([tmp_path / "a"]) == [("One", "1")] and same([tmp_path / "b"]) == [("Two", "2")]


def test_case_of_the_suffix_and_of_header_names_is_ignored(tmp_path):
    dist(tmp_path / "site", "Foo-1.DIST-INFO", "metadata-version: 2.1\nNAME: Foo\nversion: 1.2\n")
    assert same([tmp_path / "site"]) == [("Foo", "1.2")]


def test_a_folded_multi_line_value_is_redented_like_the_standard_library(tmp_path):
    dist(tmp_path / "site", "Fold-1.dist-info", "Name: Fold\nVersion: 1\n  .post2\n")
    same([tmp_path / "site"])


def test_a_zip_archive_entry(tmp_path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("Zed-4.dist-info/METADATA", metadata("Zed", "4"))
        handle.writestr("Old-2.egg-info", metadata("Old", "2"))
        handle.writestr("Bad-1.dist-info/METADATA", b"\xff\xfe not utf-8")
        handle.writestr("pkg/module.py", "x = 1\n")
    result = same([archive])
    # a single-file egg-info inside a zip has no readable metadata under the standard library either
    assert sorted(result, key=repr) == sorted([("Zed", "4"), (None, None), (None, None)], key=repr)


def test_a_zipped_egg_with_an_egg_info_child(tmp_path):
    archive = tmp_path / "Pack-1.egg"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("EGG-INFO/PKG-INFO", metadata("Pack", "1"))
    assert same([archive]) == [("Pack", "1")]


# ---------------------------------------------------------------------------
# Missing, malformed or unreadable metadata
# ---------------------------------------------------------------------------
def test_malformed_metadata(tmp_path):
    dist(tmp_path / "site", "Junk-1.dist-info", "this is not a header block\n\x00\x01 garbage")
    assert same([tmp_path / "site"]) == [(None, None)]


def test_missing_name(tmp_path):
    dist(tmp_path / "site", "NoName-1.dist-info", metadata(None, "7"))
    assert same([tmp_path / "site"]) == [(None, "7")]


def test_missing_version(tmp_path):
    dist(tmp_path / "site", "NoVer-1.dist-info", metadata("NoVer", None))
    assert same([tmp_path / "site"]) == [("NoVer", None)]


def test_an_empty_name_or_version_is_returned_as_an_empty_string(tmp_path):
    dist(tmp_path / "site", "Empty-1.dist-info", "Name:\nVersion:\n")
    assert same([tmp_path / "site"]) == [("", "")]


def test_non_utf8_metadata(tmp_path):
    dist(tmp_path / "site", "Latin-1.dist-info", b"Name: Caf\xe9\nVersion: 1\n")
    assert same([tmp_path / "site"]) == [(None, None)]


def test_a_distribution_directory_without_metadata_files(tmp_path):
    dist(tmp_path / "site", "Hollow-1.dist-info", None)
    assert same([tmp_path / "site"]) == [(None, None)]


def test_an_unreadable_metadata_file(tmp_path):
    target = dist(tmp_path / "site", "Locked-1.dist-info") / "METADATA"
    target.chmod(0)
    try:
        if target.exists() and _readable(target):
            pytest.skip("permissions are not enforced for this user")
        assert same([tmp_path / "site"]) == [(None, None)]
    finally:
        target.chmod(0o644)


def test_an_unreadable_search_path_directory(tmp_path):
    site = tmp_path / "site"
    dist(site, "Foo-1.dist-info")
    site.chmod(0)
    try:
        if _listable(site):
            pytest.skip("permissions are not enforced for this user")
        assert same([site]) == []
    finally:
        site.chmod(0o755)


def _readable(path: Path) -> bool:
    try:
        path.read_bytes()
        return True
    except OSError:
        return False


def _listable(path: Path) -> bool:
    try:
        list(path.iterdir())
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Search-path edge cases
# ---------------------------------------------------------------------------
def test_duplicates_across_entries_and_repeated_entries_are_kept(tmp_path):
    dist(tmp_path / "one", "Foo-1.2.dist-info")
    dist(tmp_path / "two", "Foo-1.2.dist-info")
    assert same([tmp_path / "one", tmp_path / "two"]) == [("Foo", "1.2"), ("Foo", "1.2")]
    assert len(same([tmp_path / "one", tmp_path / "one"])) == 2
    dist(tmp_path / "three", "Foo-1.3.dist-info", metadata("Foo", "1.3"))
    assert sorted(same([tmp_path / "one", tmp_path / "three"])) == [("Foo", "1.2"), ("Foo", "1.3")]


def test_a_nonexistent_entry_a_plain_file_entry_and_an_empty_list(tmp_path):
    plain = tmp_path / "notes.txt"
    plain.write_text("not an archive\n", encoding="utf-8")
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"PK\x03\x04 truncated")
    dist(tmp_path / "site", "Foo-1.2.dist-info")
    assert same([tmp_path / "missing"]) == [] and same([plain]) == [] and same([broken]) == []
    assert same([]) == []
    assert same([tmp_path / "missing", plain, tmp_path / "site", broken]) == [("Foo", "1.2")]


def test_the_empty_string_entry_means_the_current_directory(tmp_path, monkeypatch):
    dist(tmp_path, "Here-1.dist-info", metadata("Here", "1"))
    monkeypatch.chdir(tmp_path)
    assert same([""]) == [("Here", "1")]


def test_non_path_entries_are_ignored(tmp_path):
    dist(tmp_path / "site", "Foo-1.2.dist-info")
    assert default_package_provider([None, 5, str(tmp_path / "site")]) == [("Foo", "1.2")]


def test_ordinary_directories_and_files_are_not_distributions(tmp_path):
    site = tmp_path / "site"
    (site / "package").mkdir(parents=True)
    (site / "package" / "__init__.py").write_text("", encoding="utf-8")
    (site / "module.py").write_text("x = 1\n", encoding="utf-8")
    (site / "foo.dist-info.bak").write_text(metadata(), encoding="utf-8")
    assert same([site]) == []


def test_the_provider_writes_nothing(tmp_path):
    dist(tmp_path / "site", "Foo-1.2.dist-info")
    before = tree_hashes(tmp_path)
    default_package_provider([tmp_path / "site"])
    assert tree_hashes(tmp_path) == before and not list(tmp_path.rglob("__pycache__"))


# ---------------------------------------------------------------------------
# Provenance semantics are unchanged
# ---------------------------------------------------------------------------
def test_partial_and_unavailable_statuses_follow_the_provider_output(tmp_path):
    site = tmp_path / "site"
    dist(site, "Zeta-2.dist-info", metadata("Zeta", "2"))
    dist(site, "alpha-1.dist-info", metadata("alpha", "1"))
    ok = collect_packages(lambda: default_package_provider([site]))
    assert ok["status"] == "ok" and ok["n_unreadable"] == 0
    assert [i["name"] for i in ok["items"]] == ["alpha", "Zeta"]                        # ordering is collect_packages's
    dist(site, "NoName-1.dist-info", metadata(None, "9"))
    dist(site, "NoVer-1.dist-info", metadata("NoVer", None))
    partial = collect_packages(lambda: default_package_provider([site]))
    assert partial["status"] == "partial" and partial["n_unreadable"] == 1
    assert {"name": "NoVer", "version": None} in partial["items"]

    def broken():
        raise RuntimeError("provider failed")

    assert collect_packages(broken) == {"status": "unavailable", "reason": "RuntimeError", "n_unreadable": 0, "items": []}


def test_a_provenance_record_with_this_provider_keeps_its_schema(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src" / "maps").mkdir(parents=True)
    (repo / "src" / "maps" / "a.py").write_text("x = 1\n", encoding="utf-8")
    site = tmp_path / "site"
    dist(site, "Foo-1.2.dist-info")
    record = collect_provenance(run_id="r1", repo_root=repo, lock_file=None, include_git=False,
                                package_provider=lambda: default_package_provider([site]))
    assert record["packages"] == {"status": "ok", "n_unreadable": 0, "items": [{"name": "Foo", "version": "1.2"}]}
    assert set(record) == {"schema", "version", "note", "run_id", "created_utc", "python", "platform", "git", "source_files",
                           "lock_file", "packages", "unavailable_fields"}


# ---------------------------------------------------------------------------
# Static safety
# ---------------------------------------------------------------------------
def test_the_provenance_module_has_no_dynamic_loading_marker_and_no_os_network_or_subprocess_import():
    tree = ast.parse(Path(prov.__file__).read_text(encoding="utf-8"))
    imported, calls = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
    assert not imported & {"importlib", "runpy", "pkgutil", "imp"}
    assert not calls & {"__import__", "exec", "eval"}
    assert not imported & {"os", "socket", "urllib", "http", "requests", "subprocess", "shutil"}
