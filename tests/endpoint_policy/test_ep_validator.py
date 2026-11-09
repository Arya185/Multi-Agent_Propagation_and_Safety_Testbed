"""Endpoint validator (v2.3.74, Stage 4E): the configured base URL must be exactly the approved endpoint. Offline.

The approved URL is assembled from the module's own constants so this file holds no provider URL literal. Nothing here
resolves a name or opens a socket; the one test that builds the real client uses a dummy key and a fake session.
"""

from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest
import requests   # imported first: it pulls in ssl, which must not be first imported while socket.socket is patched

import maps.runs.endpoint_policy as ep
from maps.llm_client import OpenRouterClient
from maps.runs.endpoint_policy import APPROVED_HOSTS, APPROVED_PATH, Endpoint, EndpointPolicyError, client_request_url, validate_base_url

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST = APPROVED_HOSTS[0]
GOOD = f"https://{HOST}{APPROVED_PATH}"
DUMMY_KEY = "DUMMY-NOT-A-SECRET"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted by the endpoint-policy tests")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)           # no name resolution either


def refused(value) -> str:
    with pytest.raises(EndpointPolicyError) as e:
        validate_base_url(value)
    assert str(e.value) == ep.REASONS[e.value.reason]            # fixed text only
    return e.value.reason


def test_the_configured_endpoint_is_accepted():
    endpoint = validate_base_url(GOOD)
    assert endpoint == Endpoint(scheme="https", host=HOST, path=APPROVED_PATH)
    assert endpoint.request_url == f"{GOOD}/chat/completions"


def test_one_trailing_slash_is_tolerated_and_normalized():
    assert validate_base_url(GOOD + "/").path == APPROVED_PATH
    assert validate_base_url(GOOD + "/").request_url == validate_base_url(GOOD).request_url


@pytest.mark.parametrize("suffix", ["//", "///", "/ ", "/."])
def test_more_than_one_trailing_slash_or_dot_segments_are_refused(suffix):
    assert refused(GOOD + suffix) in ("path_not_approved", "bad_characters")


@pytest.mark.parametrize("value,reason", [
    (f"http://{HOST}{APPROVED_PATH}", "scheme_not_https"),
    (f"HTTPS://{HOST}{APPROVED_PATH}", "scheme_not_https"),
    (f"ftp://{HOST}{APPROVED_PATH}", "scheme_not_https"),
    (f"//{HOST}{APPROVED_PATH}", "scheme_not_https"),
    (f"{HOST}{APPROVED_PATH}", "scheme_not_https"),
    ("", "scheme_not_https"),
    ("https://", "host_not_approved"),
    (f"https://{HOST}", "path_not_approved"),
    (f"https://{HOST}/", "path_not_approved"),
    (f"https://{HOST}/api", "path_not_approved"),
    (f"https://{HOST}/api/v2", "path_not_approved"),
    (f"https://{HOST}/api/v1/extra", "path_not_approved"),
    (f"https://{HOST}/API/V1", "path_not_approved"),
])
def test_scheme_and_path_rules(value, reason):
    assert refused(value) == reason


@pytest.mark.parametrize("value", [
    f"https://other.example{APPROVED_PATH}", f"https://{HOST}.evil.example{APPROVED_PATH}", f"https://evil-{HOST}{APPROVED_PATH}",
    f"https://sub.{HOST}{APPROVED_PATH}", f"https://{HOST[:-1]}{APPROVED_PATH}", f"https://{HOST.upper()}{APPROVED_PATH}",
    f"https://{HOST}.{APPROVED_PATH}", f"https://x{HOST}{APPROVED_PATH}", f"https://evil.example/{HOST}{APPROVED_PATH}",
    f"https://localhost{APPROVED_PATH}", f"https://printer.local{APPROVED_PATH}", f"https://127.0.0.1{APPROVED_PATH}",
    f"https://10.0.0.5{APPROVED_PATH}", f"https://169.254.169.254{APPROVED_PATH}", f"https://2130706433{APPROVED_PATH}",
    f"https://{HOST}.{APPROVED_PATH.lstrip('/')}",
])
def test_exact_host_equality_rejects_suffix_substring_case_dot_and_private_hosts(value):
    assert refused(value) == "host_not_approved"


def test_a_trailing_dot_host_is_refused():
    assert refused(f"https://{HOST}.{APPROVED_PATH}") == "host_not_approved"


@pytest.mark.parametrize("value", [
    f"https://{HOST}:443{APPROVED_PATH}", f"https://{HOST}:80{APPROVED_PATH}", f"https://{HOST}:{APPROVED_PATH}",
    f"https://[::1]{APPROVED_PATH}", f"https://[2001:db8::1]:443{APPROVED_PATH}", f"https://[{HOST}]{APPROVED_PATH}",
])
def test_ports_and_ip_literals_are_refused(value):
    assert refused(value) == "port_or_ip_literal"


@pytest.mark.parametrize("value", [
    f"https://user@{HOST}{APPROVED_PATH}", f"https://user:pass@{HOST}{APPROVED_PATH}", f"https://{HOST}@evil.example{APPROVED_PATH}",
    f"https://@{HOST}{APPROVED_PATH}",
])
def test_userinfo_is_refused(value):
    assert refused(value) == "userinfo"


@pytest.mark.parametrize("value", [GOOD + "?x=1", GOOD + "#frag", GOOD + "/?x", f"https://{HOST}?{APPROVED_PATH}", GOOD + "/#"])
def test_query_and_fragment_are_refused(value):
    assert refused(value) == "query_or_fragment"


@pytest.mark.parametrize("value", [f"https://%6frouter.example{APPROVED_PATH}", GOOD + "%2f", f"https://{HOST}%00{APPROVED_PATH}", f"https://{HOST}{APPROVED_PATH}%20"])
def test_percent_encoding_is_refused(value):
    assert refused(value) == "percent_encoding"


@pytest.mark.parametrize("value", [
    GOOD + " ", " " + GOOD, GOOD + "\n", GOOD + "\t", GOOD + "\x00", GOOD + "\x7f", f"https://{HOST} {APPROVED_PATH}",
    f"https://{HOST}\\{APPROVED_PATH.lstrip('/')}", f"https://{HOST}{APPROVED_PATH}​", f"https://opеnrouter.example{APPROVED_PATH}",
    f"https://{HOST}{APPROVED_PATH}é",
])
def test_whitespace_control_non_ascii_and_backslash_are_refused(value):
    assert refused(value) == "bad_characters"


@pytest.mark.parametrize("value", [None, 5, b"x", ["a"], {"a": 1}, object()])
def test_non_strings_are_refused(value):
    assert refused(value) == "not_a_string"


def test_overlong_input_is_refused():
    assert refused(GOOD + "a" * 3000) == "too_long"


def test_errors_never_echo_the_supplied_value():
    sentinel = "SENTINEL-VALUE-4242"
    for value in (f"https://{sentinel}{APPROVED_PATH}", f"https://user:{sentinel}@{HOST}{APPROVED_PATH}", GOOD + f"?k={sentinel}",
                  f"https://{HOST}/{sentinel}", sentinel, f"http://{sentinel}"):
        with pytest.raises(EndpointPolicyError) as e:
            validate_base_url(value)
        assert sentinel not in str(e.value) and sentinel not in repr(e.value) and sentinel not in repr(e.value.args)


def test_the_record_is_plain_and_states_the_limitation():
    record = validate_base_url(GOOD).record()
    assert record == {"scheme": "https", "host": HOST, "path": APPROVED_PATH, "validated": True,
                      "limitation": "hostname validation does not prevent DNS or proxy redirection"}


# ---- the URL the client really uses ---------------------------------------------------------------------------
class RecordingSession:
    def __init__(self):
        self.urls = []

    def post(self, url, headers, json, timeout, allow_redirects=True):
        self.urls.append(url)
        raise requests.ConnectionError("stop")           # no response is needed; the URL is what is being checked


@pytest.mark.parametrize("value", [GOOD, GOOD + "/"])
def test_the_validated_request_url_equals_what_the_real_client_posts_to(value):
    from maps.schemas import ChatMessage, ChatRequest

    endpoint = validate_base_url(value)
    session = RecordingSession()
    client = OpenRouterClient(DUMMY_KEY, base_url=value, enabled=True, session=session, max_retries=0, sleep=lambda s: None)
    client.complete(ChatRequest(model="a/b", messages=[ChatMessage(role="user", content="x")], temperature=0.0, max_tokens=5, seed=1))
    assert session.urls == [endpoint.request_url] == [client_request_url(value)]


def test_every_refused_url_that_looks_close_would_have_been_posted_elsewhere():
    """Documents why the exact comparison matters: the client posts to whatever it is given."""
    from maps.schemas import ChatMessage, ChatRequest

    for value in (f"http://{HOST}{APPROVED_PATH}", f"https://{HOST}.evil.example{APPROVED_PATH}"):
        session = RecordingSession()
        client = OpenRouterClient(DUMMY_KEY, base_url=value, enabled=True, session=session, max_retries=0, sleep=lambda s: None)
        client.complete(ChatRequest(model="a/b", messages=[ChatMessage(role="user", content="x")], temperature=0.0, max_tokens=5, seed=1))
        assert session.urls == [client_request_url(value)] and value not in [GOOD, GOOD + "/"]
        assert refused(value) in ("scheme_not_https", "host_not_approved")


# ---- static boundaries ----------------------------------------------------------------------------------------------
def test_the_module_is_a_pure_string_checker():
    tree = ast.parse(Path(ep.__file__).read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    assert imports <= {"__future__", "dataclasses"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"os", "environ", "getenv", "socket", "urllib", "requests", "open", "exec", "eval", "OpenRouterClient", "dotenv"}


def test_the_approved_list_is_exactly_one_host():
    assert APPROVED_HOSTS == (HOST,) and len(APPROVED_HOSTS) == 1 and ep.APPROVED_SCHEME == "https" and APPROVED_PATH == "/api/v1"


def test_the_shipped_configuration_value_is_accepted():
    import json

    config = json.loads((REPO_ROOT / "configs" / "receiver_experiment.json").read_text(encoding="utf-8"))
    assert validate_base_url(config["api"]["base_url"]).host == HOST
