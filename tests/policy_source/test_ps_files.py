"""Reading and parsing the policy file: every file-level failure refuses with a bounded reason (v2.3.66, Stage 4D). Offline."""

from __future__ import annotations

import pytest

from maps.runs.policy_source import MAX_POLICY_BYTES, PolicySourceError, load_policy, parse_policy_bytes, read_policy_file

from ps_support import PROFILE, SENTINEL, load_inputs, make_doc, tripwires, write_policy  # noqa: F401  (tripwires is an autouse fixture)


@pytest.fixture(scope="module")
def inputs():
    return load_inputs()


def load(path, inputs, **kw):
    cfg, _scenarios, specs, digests = inputs
    return load_policy(path, cfg=cfg, specs=specs, content_digests=digests, profile=kw.pop("profile", PROFILE), **kw)


def reason(excinfo) -> str:
    return excinfo.value.reason


def test_a_valid_policy_loads(tmp_path, inputs):
    cfg, _s, specs, digests = inputs
    loaded = load(write_policy(tmp_path, make_doc(cfg, specs, digests)), inputs)
    assert loaded.policy.planned_episodes == 96 and loaded.profile == PROFILE and loaded.content_bound is True


def test_a_missing_file_is_refused(tmp_path, inputs):
    with pytest.raises(PolicySourceError) as e:
        load(tmp_path / "nope.json", inputs)
    assert reason(e) == "file_missing"


def test_a_directory_is_refused(tmp_path, inputs):
    with pytest.raises(PolicySourceError) as e:
        load(tmp_path, inputs)
    assert reason(e) == "file_not_regular"


def test_a_symlink_is_refused(tmp_path, inputs):
    cfg, _s, specs, digests = inputs
    real = write_policy(tmp_path, make_doc(cfg, specs, digests))
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(PolicySourceError) as e:
        load(link, inputs)
    assert reason(e) == "file_not_regular"


def test_an_oversized_file_is_refused(tmp_path, inputs):
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (MAX_POLICY_BYTES + 1))
    with pytest.raises(PolicySourceError) as e:
        load(big, inputs)
    assert reason(e) == "file_too_large"


def test_an_unreadable_file_is_refused(tmp_path, inputs):
    path = tmp_path / "locked.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0)
    try:
        with pytest.raises(PolicySourceError) as e:
            load(path, inputs)
        assert reason(e) in ("file_unreadable", "file_missing")
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize("data,expected", [
    (b"\xff\xfe\x00bad", "bad_encoding"),
    (b"\xef\xbb\xbf{}", "bad_encoding"),
    (b"{not json", "bad_json"),
    (b"", "bad_json"),
    (b"[]", "type_invalid"),
    (b"3", "type_invalid"),
    (b'{"a": 1, "a": 2}', "duplicate_key"),
    (b'{"a": {"b": 1, "b": 2}}', "duplicate_key"),
    (b'{"a": 1.5}', "bad_number"),
    (b'{"a": 1e3}', "bad_number"),
    (b'{"a": NaN}', "bad_number"),
    (b'{"a": Infinity}', "bad_number"),
    (b"{" * 100000, "bad_json"),
])
def test_malformed_content_is_refused_with_a_bounded_reason(data, expected):
    with pytest.raises(PolicySourceError) as e:
        parse_policy_bytes(data)
    assert e.value.reason == expected


def test_non_bytes_input_is_refused():
    with pytest.raises(PolicySourceError) as e:
        parse_policy_bytes("{}")                      # type: ignore[arg-type]
    assert e.value.reason == "input_invalid"


def test_a_bad_path_argument_is_refused():
    with pytest.raises(PolicySourceError) as e:
        read_policy_file(None)
    assert e.value.reason == "input_invalid"


def test_messages_never_contain_paths_or_file_content(tmp_path, inputs):
    path = tmp_path / f"{SENTINEL}.json"
    path.write_text('{"%s": 1}' % SENTINEL, encoding="utf-8")
    with pytest.raises(PolicySourceError) as e:
        load(path, inputs)
    assert SENTINEL not in str(e.value)                # the unknown field NAME and the path are both withheld
    with pytest.raises(PolicySourceError) as e2:
        load(tmp_path / f"{SENTINEL}-missing.json", inputs)
    assert SENTINEL not in str(e2.value)
