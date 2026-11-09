"""Provider endpoint validation (Stage 4E): the configured ``api.base_url`` must be exactly the approved endpoint.

STATUS: implemented and tested OFFLINE only. It parses a string; it never resolves a name, opens a socket, reads the
environment or touches a credential. It must run BEFORE any credential is read or a provider client is built (the CLI
preflight does this); passing it does not authorize a live run.

THE RULE (owner decision PR4: ``APPROVE HOST: openrouter.ai``). The URL must be exactly::

    https://openrouter.ai/api/v1            (one trailing "/" is tolerated: the client strips it)

so: HTTPS only; exact, lowercase host equality (never a suffix or substring match); the path ``/api/v1``; no explicit
port, user or password, query or fragment; no IP literal (v4 or v6), ``localhost``, ``.local`` or other host; no trailing-dot
host; no non-ASCII or percent-encoded character; no whitespace or control character; no backslash. The value validated is the
one the provider client uses: ``client_request_url`` repeats the client's own normalization (strip trailing "/", append
``/chat/completions``) and the result must equal the approved request URL.

LIMITS, stated plainly. Hostname validation does NOT prevent DNS resolution to an unexpected address, and it does not stop
a proxy (``HTTP(S)_PROXY`` environment variables, ``~/.netrc``) from carrying the request: ``requests`` honors those by
default and handling them is a separate, still-pending decision (PR4-PROXY). It checks the configured string only.

Errors are ``EndpointPolicyError`` with a bounded ``reason`` and FIXED text; they never contain the supplied URL, host or any
fragment of it.
"""

from __future__ import annotations

from dataclasses import dataclass

APPROVED_SCHEME = "https"
APPROVED_HOSTS = ("openrouter.ai",)
APPROVED_PATH = "/api/v1"
REQUEST_SUFFIX = "/chat/completions"
MAX_URL_CHARS = 2048
LIMITATION_NOTE = "hostname validation does not prevent DNS or proxy redirection"

REASONS = {
    "not_a_string": "the endpoint is not a string",
    "too_long": "the endpoint is longer than the supported length",
    "bad_characters": "the endpoint contains a character that is not allowed",
    "percent_encoding": "the endpoint contains percent-encoding",
    "scheme_not_https": "the endpoint must use https",
    "userinfo": "the endpoint must not contain a user or password",
    "query_or_fragment": "the endpoint must not contain a query or fragment",
    "port_or_ip_literal": "the endpoint must not contain a port or an IP literal",
    "host_not_approved": "the endpoint host is not on the approved list",
    "path_not_approved": "the endpoint path is not the approved path",
    "request_url_mismatch": "the URL the client would use is not the approved URL",
}


class EndpointPolicyError(ValueError):
    """The configured endpoint was refused. ``reason`` is a code from ``REASONS``; the message is fixed text."""

    def __init__(self, reason: str):
        super().__init__(REASONS[reason])
        self.reason = reason


def _refuse(reason: str):
    raise EndpointPolicyError(reason)


@dataclass(frozen=True)
class Endpoint:
    """A validated endpoint. Holds only the approved scheme, host and path."""

    scheme: str
    host: str
    path: str

    @property
    def request_url(self) -> str:
        return f"{self.scheme}://{self.host}{self.path}{REQUEST_SUFFIX}"

    def record(self) -> dict:
        """A plain, secret-free record for the run report."""
        return {"scheme": self.scheme, "host": self.host, "path": self.path, "validated": True, "limitation": LIMITATION_NOTE}


def client_request_url(base_url: str) -> str:
    """The URL the provider client posts to for a ``base_url``: its own normalization, repeated here (not imported)."""
    return f"{base_url.rstrip('/')}{REQUEST_SUFFIX}"


def validate_base_url(value) -> Endpoint:
    """Return the approved ``Endpoint`` for ``value`` or raise ``EndpointPolicyError`` (fail closed)."""
    if type(value) is not str:
        _refuse("not_a_string")
    if len(value) > MAX_URL_CHARS:
        _refuse("too_long")
    if not value.isascii() or any(not 0x21 <= ord(c) <= 0x7E for c in value) or "\\" in value:
        _refuse("bad_characters")                       # whitespace, control characters, non-ASCII, backslash
    if "%" in value:
        _refuse("percent_encoding")
    prefix = f"{APPROVED_SCHEME}://"
    if not value.startswith(prefix):
        _refuse("scheme_not_https")
    rest = value[len(prefix):]
    authority, slash, path = rest.partition("/")
    if "@" in authority:
        _refuse("userinfo")
    if "?" in rest or "#" in rest:
        _refuse("query_or_fragment")
    if ":" in authority or "[" in authority or "]" in authority:
        _refuse("port_or_ip_literal")
    if authority not in APPROVED_HOSTS:                  # exact equality: no suffix, substring, case-folding or trailing dot
        _refuse("host_not_approved")
    path = slash + path
    if path.endswith("/"):
        path = path[:-1]                                 # at most ONE trailing slash is tolerated
    if path != APPROVED_PATH:
        _refuse("path_not_approved")
    endpoint = Endpoint(scheme=APPROVED_SCHEME, host=authority, path=path)
    if client_request_url(value) != endpoint.request_url:
        _refuse("request_url_mismatch")
    return endpoint
