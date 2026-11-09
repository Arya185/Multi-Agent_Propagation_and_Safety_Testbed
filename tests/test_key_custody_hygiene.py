"""Stage 4J.7: non-secret checks around answer-key custody. Path-only: no test opens, reads or hashes the answer key or
.env. The key itself must live in owner-held encrypted storage outside the repository; the ignore pattern only stops an
accidental `git add` of a stray in-repository copy and is not a custody control."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0


@pytest.mark.parametrize("path", ["data/review/answer_key.json", "data/review/answer_key", "data/review/answer_key_backup.json", ".env"])
def test_key_and_secret_paths_are_git_ignored(path):
    assert _ignored(path)


def test_review_packages_are_not_ignored_by_the_key_pattern():
    # the pattern must not hide ordinary review material from review
    assert not _ignored("data/review/blinded/items/rv-00000000.json")


def test_no_tracked_file_matches_the_key_pattern():
    tracked = subprocess.run(["git", "ls-files", "data"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert [t for t in tracked if "answer_key" in t] == []
