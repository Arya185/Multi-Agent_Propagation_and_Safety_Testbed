"""Error classification from the existing client error strings (pure)."""

from __future__ import annotations

import pytest

from maps.runs.live_budget import ErrorClass, classify_result
from maps.schemas import LLMResult

from lp_support import SENTINEL, err, make_policy, ok

POLICY = make_policy()


def classify(result, policy=POLICY):
    return classify_result(result, policy)


def test_the_existing_result_type_has_no_typed_error_fields_so_strings_are_the_only_source():
    names = {f for f in LLMResult.model_fields}
    assert not {"error_kind", "status_code", "http_status"} & names


def test_success_and_empty_response():
    assert classify(ok()) == (ErrorClass.SUCCESS, "ok")
    assert classify(LLMResult(content="")) == (ErrorClass.SUCCESS, "ok")                 # an empty string is still content
    assert classify(LLMResult()) == (ErrorClass.NONFATAL, "empty_response")


@pytest.mark.parametrize("code", [c for c in range(400, 500) if c not in (408, 429)])
def test_every_4xx_outside_the_nonfatal_set_is_fatal(code):
    assert classify(err(f"http_{code}: some body")) == (ErrorClass.FATAL, f"http_{code}")


@pytest.mark.parametrize("code", [408, 429])
def test_configured_nonfatal_4xx_statuses_are_nonfatal(code):
    assert classify(err(f"http_{code}: slow down")) == (ErrorClass.NONFATAL, f"http_{code}")


def test_the_nonfatal_set_is_taken_from_the_policy():
    policy = make_policy(nonfatal_4xx_statuses=frozenset({422}))
    assert classify(err("http_422: x"), policy)[0] is ErrorClass.NONFATAL
    assert classify(err("http_429: x"), policy)[0] is ErrorClass.FATAL
    assert classify(err("http_408: x"), make_policy(nonfatal_4xx_statuses=frozenset()))[0] is ErrorClass.FATAL


@pytest.mark.parametrize("fatal_3xx,expected", [(True, ErrorClass.FATAL), (False, ErrorClass.NONFATAL)])
@pytest.mark.parametrize("code", [300, 301, 302, 307, 308, 399])
def test_3xx_follows_the_policy_flag(code, fatal_3xx, expected):
    assert classify(err(f"http_{code}: moved"), make_policy(fatal_3xx=fatal_3xx)) == (expected, f"http_{code}")


@pytest.mark.parametrize("code", [500, 502, 503, 504, 599, 100, 204])
def test_5xx_and_other_recognized_statuses_are_nonfatal(code):
    assert classify(err(f"http_{code}: body")) == (ErrorClass.NONFATAL, f"http_{code}")


def test_redirect_loops_are_fatal_and_other_request_exceptions_are_not():
    assert classify(err("request_exception: TooManyRedirects")) == (ErrorClass.FATAL, "request_exception_too_many_redirects")
    for name in ("Timeout", "ConnectionError", "ReadTimeout", "TooManyRedirectsExtra"):
        assert classify(err(f"request_exception: {name}")) == (ErrorClass.NONFATAL, "request_exception")


def test_provider_error_objects_and_malformed_responses_are_nonfatal_with_no_code_claimed():
    assert classify(err("api_error: {'code': 402, 'message': 'insufficient credits'}")) == (ErrorClass.NONFATAL, "api_error")
    assert classify(err("malformed_api_response: body is not JSON")) == (ErrorClass.NONFATAL, "malformed_api_response")


@pytest.mark.parametrize("text", ["", "boom", "HTTP_404: x", "http_4040: x", "http_40: x", "http_404 x", " http_404: x", "http_404", "unknown_error"])
def test_unknown_formats_are_nonfatal_and_unclassified(text):
    assert classify(err(text)) == (ErrorClass.NONFATAL, "unclassified")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("http_500: http_404: request_exception: TooManyRedirects", (ErrorClass.NONFATAL, "http_500")),
        ("http_429: api_error: fatal http_401: bad key", (ErrorClass.NONFATAL, "http_429")),
        ("http_401: http_200: ok success api_error:", (ErrorClass.FATAL, "http_401")),
        ("request_exception: Timeout http_404: x", (ErrorClass.NONFATAL, "request_exception")),
        ("api_error: http_404: request_exception: TooManyRedirects", (ErrorClass.NONFATAL, "api_error")),
        ("malformed_api_response: http_401: fatal", (ErrorClass.NONFATAL, "malformed_api_response")),
        ("junk http_401: x", (ErrorClass.NONFATAL, "unclassified")),
        ("request_exception: TooManyRedirects\nhttp_200", (ErrorClass.NONFATAL, "request_exception")),
    ],
)
def test_only_the_leading_prefix_decides_the_class(text, expected):
    assert classify(err(text)) == expected


def test_provider_text_never_appears_in_the_category_token():
    for text in (f"http_503: {SENTINEL}", f"api_error: {SENTINEL}", f"{SENTINEL}", f"request_exception: {SENTINEL}"):
        assert SENTINEL not in classify(err(text))[1]


def test_a_non_string_error_is_unclassified_and_nonfatal():
    result = ok()
    object.__setattr__(result, "error", 404)
    assert classify(result) == (ErrorClass.NONFATAL, "unclassified")


def test_classification_does_not_depend_on_attempts_or_content():
    base = err("http_404: x")
    assert classify(base.model_copy(update={"attempts": 3})) == (ErrorClass.FATAL, "http_404")
    assert classify(LLMResult(content="text", error="http_404: x")) == (ErrorClass.FATAL, "http_404")
