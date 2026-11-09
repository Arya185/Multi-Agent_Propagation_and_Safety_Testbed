"""The current repository against the explicit provider-route allow-list (v2.3.56, Stage 4C). Offline, static."""

from __future__ import annotations

from pathlib import Path

from allowlist import ALLOWLIST
from route_check import check_tree, validate_entries
from route_scanner import KINDS, scan_tree

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRIES = {e["path"]: e for e in ALLOWLIST}


def test_the_allow_list_is_well_formed():
    assert validate_entries(ALLOWLIST, REPO_ROOT) == []


def test_the_current_repository_matches_the_allow_list_exactly():
    assert check_tree(REPO_ROOT, ALLOWLIST) == []


def test_there_are_no_directory_wildcard_or_duplicate_entries():
    paths = [e["path"] for e in ALLOWLIST]
    assert len(paths) == len(set(paths))
    assert all(p.endswith((".py", ".sh", ".ipynb", ".bash", ".zsh")) and not any(c in p for c in "*?[]{}") for p in paths)
    assert all((REPO_ROOT / p).is_file() for p in paths)


def test_the_guarded_experiment_set_is_exactly_the_reviewed_files():
    guarded = {p for p, e in ENTRIES.items() if e["classification"] == "guarded_experiment"}
    assert guarded == {
        "src/maps/llm_client.py", "src/maps/runs/live_budget.py", "src/maps/experiments/receiver.py", "src/maps/runs/endpoint_policy.py",
    }


def test_the_only_diagnostic_route_is_the_labelled_script():
    diag = {p for p, e in ENTRIES.items() if e["classification"] == "diagnostic_only"}
    assert diag == {"scripts/test_openrouter.py"}
    assert ENTRIES["scripts/test_openrouter.py"]["category"] == "script"
    assert "DIAGNOSTIC" in ENTRIES["scripts/test_openrouter.py"]["purpose"]


def test_no_non_provider_network_exceptions_exist_today():
    assert [p for p, e in ENTRIES.items() if e["classification"] == "non_provider_network"] == []


def test_no_file_outside_the_listed_sources_references_the_client_class_or_endpoint():
    """Every production (non-test) file that references the provider client or an endpoint is one of the four reviewed ones."""
    scans = scan_tree(REPO_ROOT)
    production = {p for p, s in scans.items() if not p.startswith("tests/") and s.kinds & {"provider_client_ref", "endpoint_literal", "network_import"}}
    # v2.3.74: plus the endpoint validator, which holds the approved host and path as constants.
    assert production == {"src/maps/llm_client.py", "scripts/test_openrouter.py", "src/maps/runs/endpoint_policy.py"}


def test_receiver_no_longer_references_the_provider_client_class():
    scan = scan_tree(REPO_ROOT)["src/maps/experiments/receiver.py"]
    assert "provider_client_ref" not in scan.kinds and "network_import" not in scan.kinds
    assert "provider_client_ref" not in ENTRIES["src/maps/experiments/receiver.py"]["kinds"]


def test_there_are_no_notebooks_in_the_repository():
    notebooks = [p for p, s in scan_tree(REPO_ROOT).items() if s.is_notebook]
    assert notebooks == []


def test_every_allow_listed_kind_is_a_known_kind():
    assert all(set(e["kinds"]) <= set(KINDS) for e in ALLOWLIST)


def test_the_allow_list_records_the_unvalidated_base_url_limit():
    text = " ".join(e["justification"] for e in ALLOWLIST if e["path"] in ("src/maps/llm_client.py", "scripts/test_openrouter.py"))
    assert "not validated" in text.lower() or "NOT validated" in text
