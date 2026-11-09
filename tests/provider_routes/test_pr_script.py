"""scripts/test_openrouter.py: a labelled diagnostic that makes at most one request (v2.3.56, Stage 4C, PR1/PR2).

OFFLINE. The real client class is exercised only through the script's ``session`` seam with a fake transport, a DUMMY
credential, a fake ``dotenv`` module (so no ``.env`` file is read) and a socket tripwire.
"""

from __future__ import annotations

import ast
import json
import socket
import sys
import types
from pathlib import Path

import pytest
import requests   # imported first: it pulls in ssl, which must not be first imported while socket.socket is patched

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "test_openrouter.py"
SYNTHETIC_CONFIG = REPO_ROOT / "tests" / "synthetic" / "data" / "config_synthetic.json"
KEY_ENV = "MAPS_DIAGNOSTIC_TEST_KEY_ENV"
DUMMY_KEY = "DUMMY-NOT-A-SECRET-0123456789"
BANNER = "DIAGNOSTIC — NOT AN EXPERIMENT RUN"


class FakeResp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code, self._body = status, body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    def __init__(self, outcomes=()):
        self.outcomes, self.calls, self.redirects = list(outcomes), [], []

    def post(self, url, headers, json, timeout, allow_redirects=True):
        self.calls.append({"url": url, "headers": dict(headers), "json": json, "timeout": timeout})
        self.redirects.append(allow_redirects)
        if not self.outcomes:
            raise AssertionError("an unexpected extra provider request")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


OK_BODY = {"model": "a/b-actual", "choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}


def make_config(tmp_path, *, enabled=True, retries=5) -> Path:
    config = json.loads(SYNTHETIC_CONFIG.read_text(encoding="utf-8"))
    config["api"].update({"enabled": enabled, "api_key_env": KEY_ENV, "max_retries": retries, "backoff_s": 0.0,
                          "base_url": "https://example.invalid/api/v1"})
    config["output"]["results_dir"] = str(tmp_path / "results")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted by the diagnostic-script tests")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def script(monkeypatch):
    calls = {"dotenv": [], "sleep": []}
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *a, **k: calls["dotenv"].append(a) or False       # never reads a real .env file
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    monkeypatch.setattr("time.sleep", lambda s: calls["sleep"].append(s))      # a retry backoff would be visible here
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    sys.modules.pop("test_openrouter", None)
    import test_openrouter

    test_openrouter.calls = calls
    yield test_openrouter
    sys.modules.pop("test_openrouter", None)


def listing(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if "__pycache__" not in p.parts)


def run(script, capsys, tmp_path, *args, session=None, enabled=True, retries=5, env=None):
    session = session if session is not None else FakeSession()
    argv = ["--config", str(make_config(tmp_path, enabled=enabled, retries=retries)), *args]
    code = script.main(argv, session=session, environ={KEY_ENV: DUMMY_KEY} if env is None else env)
    captured = capsys.readouterr()
    return code, captured.out, captured.err, session


# ---- the label --------------------------------------------------------------------------------------------
def test_the_banner_is_the_first_output_in_every_outcome(script, capsys, tmp_path):
    for args, kwargs in ((("--confirm-spend",), {"session": FakeSession([FakeResp(200, OK_BODY)])}), ((), {}), (("--confirm-spend",), {"enabled": False})):
        code, out, err, _ = run(script, capsys, tmp_path, *args, **kwargs)
        assert out.splitlines()[0] == BANNER, (args, kwargs)
    assert script.DIAGNOSTIC_BANNER == BANNER


def test_the_module_docstring_labels_the_script_as_diagnostic():
    doc = ast.get_docstring(ast.parse(SCRIPT.read_text(encoding="utf-8"))) or ""
    assert "DIAGNOSTIC ONLY" in doc and "NOT AN EXPERIMENT RUN" in doc and "AT MOST ONE" in doc


# ---- gates: no confirmation / disabled config / no key => no request ---------------------------------------
def test_without_confirmation_there_is_no_request_and_no_client(script, capsys, tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(script, "OpenRouterClient", lambda *a, **k: built.append(1) or (_ for _ in ()).throw(AssertionError("client built")))
    code, out, err, session = run(script, capsys, tmp_path)
    assert code == 2 and "--confirm-spend" in err and session.calls == [] and built == []
    assert script.calls["dotenv"] == []                                     # refused before even the .env step


def test_with_a_disabled_configuration_there_is_no_request_and_no_client(script, capsys, tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(script, "OpenRouterClient", lambda *a, **k: built.append(1) or (_ for _ in ()).throw(AssertionError("client built")))
    code, out, err, session = run(script, capsys, tmp_path, "--confirm-spend", enabled=False)
    assert code == 2 and "api.enabled=true" in err and session.calls == [] and built == []
    assert script.calls["dotenv"] == []


def test_without_a_key_there_is_no_request(script, capsys, tmp_path):
    code, out, err, session = run(script, capsys, tmp_path, "--confirm-spend", env={})
    assert code == 2 and "is not set" in err and KEY_ENV in err and session.calls == []


# ---- at most one request, retries forced to zero ----------------------------------------------------------------
def test_the_retry_constant_is_zero():
    assert ast.literal_eval(next(
        n.value for n in ast.parse(SCRIPT.read_text(encoding="utf-8")).body
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "DIAGNOSTIC_MAX_RETRIES" for t in n.targets)
    )) == 0


def test_the_client_is_built_with_zero_retries_whatever_the_configuration_says(script, capsys, tmp_path, monkeypatch):
    seen = {}
    real = script.OpenRouterClient

    def spy(*args, **kwargs):
        assert args == (DUMMY_KEY,)
        seen.update(kwargs)
        return real(DUMMY_KEY, session=kwargs.pop("session"), **kwargs)      # the fake transport is passed on explicitly

    monkeypatch.setattr(script, "OpenRouterClient", spy)
    code, out, err, session = run(script, capsys, tmp_path, "--confirm-spend", session=FakeSession([FakeResp(200, OK_BODY)]), retries=7)
    assert code == 0 and seen["max_retries"] == 0 and seen["enabled"] is True
    assert len(session.calls) == 1 and script.calls["sleep"] == []


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_a_retryable_http_failure_is_not_retried(script, capsys, tmp_path, status):
    session = FakeSession([FakeResp(status, text="busy"), FakeResp(200, OK_BODY)])      # a second attempt WOULD succeed
    code, out, err, session = run(script, capsys, tmp_path, "--confirm-spend", session=session, retries=5)
    assert code == 1 and len(session.calls) == 1 and len(session.outcomes) == 1
    assert script.calls["sleep"] == [] and f"http_{status}" in out


def test_a_connection_error_is_not_retried(script, capsys, tmp_path):
    session = FakeSession([requests.ConnectionError("down"), FakeResp(200, OK_BODY)])
    code, out, err, session = run(script, capsys, tmp_path, "--confirm-spend", session=session, retries=5)
    assert code == 1 and len(session.calls) == 1 and "request_exception" in out and script.calls["sleep"] == []


def test_a_malformed_response_ends_with_one_request_and_a_clean_error(script, capsys, tmp_path):
    code, out, err, session = run(script, capsys, tmp_path, "--confirm-spend", session=FakeSession([FakeResp(200, body=None, text="<html>")]))
    assert code == 1 and len(session.calls) == 1 and "malformed_api_response" in out and "Traceback" not in out + err


def test_a_successful_run_makes_exactly_one_request_without_following_redirects(script, capsys, tmp_path):
    code, out, err, session = run(script, capsys, tmp_path, "--confirm-spend", session=FakeSession([FakeResp(200, OK_BODY)]))
    assert code == 0 and len(session.calls) == 1 and session.redirects == [False]
    request = session.calls[0]
    assert request["url"] == "https://example.invalid/api/v1/chat/completions" and request["json"]["max_tokens"] == 16
    assert '"content": "ok"' in out


def test_the_script_calls_the_client_exactly_once_in_its_source():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "complete"]
    assert len(calls) == 1
    loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While, ast.AsyncFor))]
    assert loops == []                                                       # no loop can repeat the request


# ---- no artifacts ---------------------------------------------------------------------------------------------------
def test_no_files_or_run_artifacts_are_written(script, capsys, tmp_path, monkeypatch):
    config = make_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    watched = [REPO_ROOT / "experiments", REPO_ROOT / "scripts", REPO_ROOT / "configs"]
    before = {str(p): listing(p) for p in watched}
    top_before = sorted(p.name for p in REPO_ROOT.iterdir() if p.name not in {".pytest_cache", "__pycache__"})
    tmp_before = listing(tmp_path)
    for session, extra in ((FakeSession([FakeResp(200, OK_BODY)]), ["--confirm-spend"]), (FakeSession(), [])):
        script.main(["--config", str(config), *extra], session=session, environ={KEY_ENV: DUMMY_KEY})
    capsys.readouterr()
    assert listing(tmp_path) == tmp_before                                   # not even a results directory
    assert not (tmp_path / "results").exists()
    assert {str(p): listing(p) for p in watched} == before
    assert sorted(p.name for p in REPO_ROOT.iterdir() if p.name not in {".pytest_cache", "__pycache__"}) == top_before


def test_the_source_has_no_file_writes_or_run_machinery():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"maps.runs", "shutil", "tempfile", "subprocess", "requests", "socket"} and "runs" not in "".join(
        n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    )
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"write_text", "write_bytes", "mkdir", "open", "initialize_run_dir", "execute_live_run", "JsonlWriter", "run_experiment"}


# ---- credentials are never printed ----------------------------------------------------------------------------------
@pytest.mark.parametrize("outcome", ["success-echo", "http-error-echo", "refused-no-confirm"])
def test_credential_values_are_never_printed(script, capsys, tmp_path, outcome):
    echoing = dict(OK_BODY, model=f"{DUMMY_KEY}-model")                        # a provider that echoes the key back
    sessions = {
        "success-echo": FakeSession([FakeResp(200, echoing)]),
        "http-error-echo": FakeSession([FakeResp(500, text=f"upstream said {DUMMY_KEY} is bad")]),
        "refused-no-confirm": FakeSession(),
    }
    args = [] if outcome == "refused-no-confirm" else ["--confirm-spend"]
    code, out, err, session = run(script, capsys, tmp_path, *args, session=sessions[outcome])
    assert DUMMY_KEY not in out + err and "Bearer" not in out + err
    if outcome != "refused-no-confirm":
        assert session.calls[0]["headers"]["Authorization"] == f"Bearer {DUMMY_KEY}"     # the key was sent to the FAKE transport only


def test_a_key_shaped_value_in_the_variable_name_is_not_echoed_when_missing(script, capsys, tmp_path):
    code, out, err, _ = run(script, capsys, tmp_path, "--confirm-spend", env={})
    assert code == 2 and DUMMY_KEY not in out + err


def test_the_script_s_default_session_ignores_the_environment(script, capsys, tmp_path, monkeypatch):
    """Stage 4G (PR4-PROXY): with no injected session the script's client builds the default session, which no longer trusts the
    environment. ``Session.post`` is replaced on the class, so nothing is sent; it records the session it was called on."""
    seen = []

    def fake_post(self, url, **kwargs):
        seen.append((type(self), self.trust_env, kwargs.get("allow_redirects")))
        return FakeResp(200, OK_BODY)

    monkeypatch.setattr(requests.Session, "post", fake_post)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    argv = ["--config", str(make_config(tmp_path)), "--confirm-spend"]
    code = script.main(argv, environ={KEY_ENV: DUMMY_KEY})
    assert code == 0 and seen == [(requests.Session, False, False)]
    assert DUMMY_KEY not in capsys.readouterr().out
