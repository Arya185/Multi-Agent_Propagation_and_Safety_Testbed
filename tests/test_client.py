import json
import socket

import pytest
import requests

from maps.llm_client import ApiDisabledError, OpenRouterClient
from maps.logging_utils import JsonlWriter, redact
from maps.mock_client import MockClient
from maps.schemas import ChatMessage, ChatRequest, ResponseParseError, parse_receiver_response

KEY = "sk-or-v1-supersecretkey1234567890"   # a dummy literal, not a credential


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """PR6: these tests build the real OpenRouterClient with a fake session and a dummy key; any attempt to open a
    socket (a client built without the fake session, or a fake that falls through) fails the test."""
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during a client test")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _req(seed=1):
    return ChatRequest(
        model="a/b", messages=[ChatMessage(role="user", content="hi")],
        temperature=0.0, max_tokens=10, seed=seed,
    )


class FakeResp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.redirect_flags = []

    def post(self, url, headers, json, timeout, allow_redirects=True):
        self.calls.append((url, headers, json, timeout))
        self.redirect_flags.append(allow_redirects)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


OK = {
    "model": "a/b-actual",
    "choices": [{"message": {"content": "hello"}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
}


def _client(outcomes, **kw):
    sess = FakeSession(outcomes)
    c = OpenRouterClient(KEY, base_url="https://x/api/v1", enabled=True, session=sess,
                         sleep=lambda s: None, max_retries=2, **kw)
    return c, sess


def test_disabled_client_never_calls_network():
    sess = FakeSession([])
    c = OpenRouterClient(KEY, base_url="https://x", enabled=False, session=sess)
    with pytest.raises(ApiDisabledError):
        c.complete(_req())
    assert sess.calls == []


def test_missing_key_refuses():
    c = OpenRouterClient(None, base_url="https://x", enabled=True, session=FakeSession([]))
    with pytest.raises(ApiDisabledError):
        c.complete(_req())


def test_success_captures_usage_model_latency():
    c, sess = _client([FakeResp(200, OK)])
    r = c.complete(_req())
    assert r.error is None and r.content == "hello"
    assert (r.prompt_tokens, r.completion_tokens, r.total_tokens) == (3, 2, 5)
    assert r.response_model_id == "a/b-actual" and r.latency_s >= 0 and r.attempts == 1
    url, headers, payload, _ = sess.calls[0]
    assert url == "https://x/api/v1/chat/completions" and payload["seed"] == 1
    assert headers["Authorization"] == f"Bearer {KEY}"


def test_retry_then_success():
    c, sess = _client([FakeResp(429, text="slow down"), FakeResp(200, OK)])
    r = c.complete(_req())
    assert r.error is None and r.attempts == 2


def test_retries_exhausted_returns_error_not_raise():
    c, sess = _client([FakeResp(503, text="down")] * 3)
    r = c.complete(_req())
    assert r.content is None and r.attempts == 3 and r.error.startswith("http_503")


def test_non_retryable_status_stops_immediately():
    c, sess = _client([FakeResp(401, text="bad key")])
    r = c.complete(_req())
    assert r.attempts == 1 and r.error.startswith("http_401")


def test_network_exception_is_retried_and_reported():
    c, sess = _client([requests.ConnectionError("boom")] * 3)
    r = c.complete(_req())
    assert r.attempts == 3 and "ConnectionError" in r.error


@pytest.mark.parametrize(
    "body",
    [{"choices": []}, {"choices": [{"message": {}}]}, {"choices": [{"message": {"content": 5}}]}, [1]],
)
def test_malformed_api_body_is_error(body):
    c, _ = _client([FakeResp(200, body)])
    r = c.complete(_req())
    assert r.content is None and r.error.startswith("malformed_api_response")


def test_200_with_error_object_is_error():
    c, _ = _client([FakeResp(200, {"error": {"message": "nope"}})])
    assert c.complete(_req()).error.startswith("api_error")


def test_non_json_body_is_error():
    c, _ = _client([FakeResp(200, None, text="<html>")])
    assert c.complete(_req()).error.startswith("malformed_api_response")


def test_key_never_in_repr_or_error():
    c, _ = _client([FakeResp(401, text=f"invalid key {KEY}")])
    assert KEY not in repr(c)
    assert KEY not in c.complete(_req()).error


def test_redact_and_writer_scrub_secrets(tmp_path):
    assert KEY not in redact(f"token {KEY}")
    assert "abc123" not in redact("Authorization: Bearer abc123")
    assert "custom-secret-value" not in redact("x custom-secret-value", ["custom-secret-value"])
    w = JsonlWriter(tmp_path / "o.jsonl", secrets=["custom-secret-value"])
    w.write({"a": {"b": ["custom-secret-value", KEY]}})
    text = (tmp_path / "o.jsonl").read_text()
    assert "custom-secret-value" not in text and KEY not in text


def test_mock_valid_is_deterministic_and_schema_valid():
    a, b = MockClient(), MockClient()
    ra, rb = a.complete(_req()), b.complete(_req())
    assert ra.content == rb.content
    parse_receiver_response(ra.content)
    assert ra.total_tokens == ra.prompt_tokens + ra.completion_tokens


def test_mock_malformed_fails_strict_parse():
    r = MockClient("malformed").complete(_req())
    with pytest.raises(ResponseParseError):
        parse_receiver_response(r.content)


def test_mock_error_mode():
    r = MockClient("error").complete(_req())
    assert r.content is None and r.error


def test_mock_scripted_cycles_and_records_calls():
    m = MockClient("scripted", scripted=["a", "b"])
    assert [m.complete(_req()).content for _ in range(3)] == ["a", "b", "a"]
    assert len(m.calls) == 3


# ---------------------------------------------------------------------------------------------------------------
# Stage 4G (PR4-PROXY): the DEFAULT session ignores environment-derived behavior. Offline: nothing is sent, and the
# client is built only to inspect the session it creates. Not tried against a real proxy or network.
# ---------------------------------------------------------------------------------------------------------------
PROXY_URL = "http://proxy.invalid:3128"
CA_FILE_NAME = "ca.pem"


def _approved_url():
    from maps.runs.endpoint_policy import APPROVED_HOSTS, APPROVED_PATH

    return f"https://{APPROVED_HOSTS[0]}{APPROVED_PATH}/chat/completions"


def _write_netrc(tmp_path, monkeypatch):
    from maps.runs.endpoint_policy import APPROVED_HOSTS

    path = tmp_path / "netrc"
    path.write_text(f"machine {APPROVED_HOSTS[0]} login dummy-user password dummy-password\n", encoding="utf-8")
    monkeypatch.setenv("NETRC", str(path))


def test_default_session_is_the_stock_class_with_environment_trust_off():
    client = OpenRouterClient(KEY, base_url="https://x/api/v1", enabled=True, session=None)
    assert type(client._session) is requests.Session and client._session.trust_env is False
    assert client.redirects_disabled is True                                  # strict-mode compatibility is preserved


def test_default_session_does_not_inherit_proxy_variables(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, PROXY_URL)
    url = _approved_url()
    control = requests.Session()                                              # trust_env True: the control shows the test can fail
    assert control.merge_environment_settings(url, {}, None, None, None)["proxies"].get("https") == PROXY_URL
    client = OpenRouterClient(KEY, base_url="https://x/api/v1", enabled=True, session=None)
    assert client._session.merge_environment_settings(url, {}, None, None, None)["proxies"] == {}


def test_default_session_does_not_consult_netrc(tmp_path, monkeypatch):
    _write_netrc(tmp_path, monkeypatch)
    url = _approved_url()
    control = requests.Session().prepare_request(requests.Request("POST", url))
    assert "Authorization" in control.headers                                  # the control: .netrc credentials would be applied
    client = OpenRouterClient(KEY, base_url="https://x/api/v1", enabled=True, session=None)
    prepared = client._session.prepare_request(requests.Request("POST", url))
    assert "Authorization" not in prepared.headers


def test_default_session_does_not_inherit_ca_bundle_variables(tmp_path, monkeypatch):
    bundle = tmp_path / CA_FILE_NAME
    bundle.write_text("not a certificate", encoding="utf-8")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(bundle))
    monkeypatch.setenv("CURL_CA_BUNDLE", str(bundle))
    url = _approved_url()
    control = requests.Session().merge_environment_settings(url, {}, None, None, None)
    assert control["verify"] == str(bundle)
    client = OpenRouterClient(KEY, base_url="https://x/api/v1", enabled=True, session=None)
    assert client._session.merge_environment_settings(url, {}, None, None, None)["verify"] is True


def test_default_session_is_not_changed_for_a_session_the_caller_supplies():
    supplied = FakeSession([])
    client = OpenRouterClient(KEY, base_url="https://x/api/v1", enabled=True, session=supplied)
    assert client._session is supplied
    stock = requests.Session()
    client = OpenRouterClient(KEY, base_url="https://x/api/v1", enabled=True, session=stock)
    assert client._session is stock and stock.trust_env is True               # used exactly as given


def test_default_session_environment_trust_is_set_off_in_exactly_one_place_and_never_on():
    import ast
    import inspect

    import maps.llm_client as module

    tree = ast.parse(inspect.getsource(module))
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) and t.attr == "trust_env" for t in n.targets)]
    assert len(assigns) == 1 and isinstance(assigns[0].value, ast.Constant) and assigns[0].value.value is False
