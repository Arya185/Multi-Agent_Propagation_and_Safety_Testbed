"""CLI preflight order and safety for ``--live`` (v2.3.74, Stage 4E). Offline; ends in the FINAL REFUSAL.

Each case runs ``main`` with spies on the policy loader and the endpoint validator and tripwires on everything the preflight
must not reach: the key lookup, ``.env``, the client constructor, the run guard, the runner and both executors.
"""

from __future__ import annotations

import builtins
import json
import socket
import sys
import types
from pathlib import Path

import pytest

import maps.config as maps_config
import maps.experiments.receiver as receiver
import maps.llm_client as maps_llm_client
import maps.runs.guard as maps_guard

from lc_support import ps_support, write_config
from maps.runs.policy_source import policy_digest


@pytest.fixture
def world(tmp_path, monkeypatch, capsys):
    order: list[str] = []
    events: list[str] = []

    def refuse(label):
        def _raise(*a, **k):
            events.append(label)
            raise AssertionError(f"{label} was reached")
        return _raise

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = refuse("load_dotenv")
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setattr(socket, "socket", refuse("socket.socket"))
    monkeypatch.setattr(socket, "create_connection", refuse("socket.create_connection"))
    monkeypatch.setattr(maps_llm_client.OpenRouterClient, "__init__", refuse("OpenRouterClient()"))
    monkeypatch.setattr(maps_config, "get_api_key", refuse("get_api_key"))
    monkeypatch.setattr(maps_guard, "initialize_run_dir", refuse("initialize_run_dir"))
    monkeypatch.setattr(maps_guard, "check_run_dir", refuse("check_run_dir"))
    for name in ("run_experiment", "execute_mock_run", "execute_live_run", "run_live_after_preflight"):
        monkeypatch.setattr(receiver, name, refuse(name))
    real_open = builtins.open

    def watching_open(file, *a, **k):
        if Path(str(file)).name.startswith(".env"):
            events.append("open(.env)")
            raise AssertionError("an .env file was opened")
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", watching_open)
    real_load, real_validate, real_digests = receiver.load_policy, receiver.validate_base_url, receiver.compute_content_digests
    monkeypatch.setattr(receiver, "compute_content_digests", lambda *a, **k: order.append("content") or real_digests(*a, **k))
    monkeypatch.setattr(receiver, "load_policy", lambda *a, **k: order.append("policy") or real_load(*a, **k))
    monkeypatch.setattr(receiver, "validate_base_url", lambda *a, **k: order.append("endpoint") or real_validate(*a, **k))

    class World:
        def __init__(self):
            self.tmp, self.order, self.events = tmp_path, order, events

        def prepare(self, *, mutate=None, base_url=None, name="policy.json"):
            config = write_config(tmp_path)
            if base_url is not None:
                data = json.loads(config.read_text(encoding="utf-8"))
                data["api"]["base_url"] = base_url
                config.write_text(json.dumps(data), encoding="utf-8")
            cfg, _s, specs, digests = ps_support.load_inputs(config)
            doc = ps_support.make_doc(cfg, specs, digests)
            if mutate:
                mutate(doc)
            path = ps_support.write_policy(tmp_path, doc, name)
            return config, ["--policy", str(path), "--profile", ps_support.PROFILE, "--expected-policy-digest", policy_digest(doc)], doc

        def run(self, config, *args):
            code = receiver.main(["--config", str(config), "--live", *args])
            captured = capsys.readouterr()
            return code, captured.out, captured.err

    yield World()
    assert events == []                                              # nothing forbidden was reached, in any test
    assert not (tmp_path / "results").exists()


def swap(args, flag, value):
    out = list(args)
    out[out.index(flag) + 1] = value
    return out


def test_a_valid_preflight_runs_policy_then_endpoint_then_the_final_refusal(world):
    config, args, _doc = world.prepare()
    code, out, err = world.run(config, "--confirm-spend", *args)
    assert code == 2 and "FINAL REFUSAL" in err and world.order == ["content", "policy", "endpoint"]


@pytest.mark.parametrize("flag", ["--policy", "--profile", "--expected-policy-digest"])
def test_missing_arguments_stop_before_the_policy_is_touched(world, flag):
    config, args, _doc = world.prepare()
    index = args.index(flag)
    code, out, err = world.run(config, *args[:index], *args[index + 2:])
    assert code == 2 and "--live requires" in err and world.order == []


def test_a_missing_policy_file_is_refused_before_the_endpoint_is_examined(world):
    config, args, _doc = world.prepare()
    code, out, err = world.run(config, *swap(args, "--policy", str(world.tmp / "nope.json")))
    assert code == 2 and "does not exist" in err and "endpoint" not in world.order


def test_an_invalid_policy_is_refused_before_the_endpoint_is_examined(world):
    config, args, _doc = world.prepare(mutate=lambda d: d["scope"].update(seed="x"))
    code, out, err = world.run(config, *args)
    assert code == 2 and "FINAL REFUSAL" not in err and world.order == ["content", "policy"]


def test_an_unknown_profile_is_refused(world):
    config, args, _doc = world.prepare()
    code, out, err = world.run(config, *swap(args, "--profile", "no-such-profile"))
    assert code == 2 and "profile" in err and "endpoint" not in world.order


@pytest.mark.parametrize("digest,fragment", [("0" * 64, "does not match"), ("abc", "not a SHA-256"), ("G" * 64, "not a SHA-256"), ("", "not a SHA-256"), ("A" * 64, "not a SHA-256")])
def test_a_mismatched_or_malformed_expected_digest_is_refused_before_the_endpoint(world, digest, fragment):
    config, args, _doc = world.prepare()
    code, out, err = world.run(config, *swap(args, "--expected-policy-digest", digest))
    assert code == 2 and fragment in err and "endpoint" not in world.order and "FINAL REFUSAL" not in err


def test_a_digest_that_is_valid_for_a_different_policy_is_refused(world):
    config, args, doc = world.prepare()
    other = json.loads(json.dumps(doc))
    other["policy_id"] = "another-policy"
    code, out, err = world.run(config, *swap(args, "--expected-policy-digest", policy_digest(other)))
    assert code == 2 and "does not match" in err


def test_the_expected_digest_is_never_taken_from_the_policy_file_or_the_environment(world, monkeypatch):
    config, args, doc = world.prepare(mutate=lambda d: d["approval"].update(approved_policy_digest="0" * 64))
    code, out, err = world.run(config, *args)
    assert code == 2 and "unknown field" in err                     # a digest inside the file is refused outright
    monkeypatch.setenv("MAPS_EXPECTED_POLICY_DIGEST", "0" * 64)
    config, args, doc = world.prepare(name="second.json")
    assert world.run(config, *args)[2].count("FINAL REFUSAL") == 1  # the environment value is ignored


@pytest.mark.parametrize("url", ["http://example.invalid/api/v1", "https://example.invalid/api/v1", "ftp://x", "", "https://localhost/api/v1"])
def test_an_invalid_endpoint_is_refused_after_the_policy_and_before_the_final_refusal(world, url):
    config, args, _doc = world.prepare(base_url=url)
    code, out, err = world.run(config, *args)
    assert code == 2 and world.order == ["content", "policy", "endpoint"] and "FINAL REFUSAL" not in err
    assert url not in err or url == ""                               # the configured URL is never echoed


def test_error_messages_do_not_echo_the_digest_or_the_policy_path(world):
    config, args, _doc = world.prepare()
    bad = "0" * 64
    code, out, err = world.run(config, *swap(args, "--expected-policy-digest", bad))
    assert bad not in out + err and args[1] not in out + err


def test_live_only_arguments_without_live_are_refused(world, capsys):
    config, args, _doc = world.prepare()
    code = receiver.main(["--config", str(config), "--mock", *args])
    assert code == 2 and "only valid with --live" in capsys.readouterr().err and world.order == []


def test_no_run_directory_is_created_even_after_a_fully_passing_preflight(world):
    config, args, _doc = world.prepare()
    world.run(config, "--confirm-spend", "--run-id", "would-be-run", *args)
    assert not (world.tmp / "results").exists() and not list(world.tmp.glob("**/would-be-run"))
