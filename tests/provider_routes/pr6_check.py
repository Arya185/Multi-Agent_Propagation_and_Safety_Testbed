"""PR6 detector (v2.3.56, Stage 4C): a test that constructs the REAL ``OpenRouterClient`` must do so only with a fake
transport, a literal dummy credential and a socket tripwire, and must not touch the environment or ``.env``.

Static (AST) and offline. ``construction_calls`` finds direct calls, calls through an alias (``F = OpenRouterClient``,
``from m import OpenRouterClient as F``, ``real = mod.OpenRouterClient``) and ``getattr(mod, "OpenRouterClient")(...)``.
A test that only REFUSES or spies on the class (replaces ``__init__``, names it in a static check) constructs nothing
and has no requirements here. This is a tripwire for careless tests, not proof that a test is safe.
"""

from __future__ import annotations

import ast
import re

CLIENT = "OpenRouterClient"
_PROVIDER_HOST = re.compile(r"openrouter\.ai", re.IGNORECASE)


def _mentions_client(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == CLIENT:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == CLIENT:
            return True
        if isinstance(sub, ast.Constant) and sub.value == CLIENT:
            return True
        if isinstance(sub, ast.alias) and CLIENT in (sub.name, sub.asname):
            return True
    return False


def _aliases(tree: ast.AST) -> set[str]:
    names = {CLIENT}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == CLIENT and a.asname and a.asname not in names:
                        names.add(a.asname)
                        changed = True
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                uses = _mentions_client(node.value) or any(isinstance(s, ast.Name) and s.id in names for s in ast.walk(node.value))
                if uses:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for t in targets:
                        if isinstance(t, ast.Name) and t.id not in names:
                            names.add(t.id)
                            changed = True
    return names


def construction_calls(tree: ast.AST) -> list[ast.Call]:
    names = _aliases(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in names:
            out.append(node)
        elif isinstance(func, ast.Attribute) and func.attr == CLIENT:
            out.append(node)
        elif isinstance(func, ast.Call) and isinstance(func.func, ast.Name) and func.func.id == "getattr" and _mentions_client(func):
            out.append(node)
    return out


def _default_session_constructions(tree: ast.AST) -> set[int]:
    """Constructions that may use the DEFAULT session (Stage 4G): inside a function named ``test_default_session*`` that never
    calls ``.complete(`` (so no request can be made), the client is only built to inspect the session it creates."""
    allowed: set[int] = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name.startswith("test_default_session"):
            calls_complete = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "complete" for c in ast.walk(fn))
            if not calls_complete:
                allowed |= {id(c) for c in construction_calls(fn)}
    return allowed


def _module_string_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return names


def _has_socket_tripwire(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        autouse = False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "fixture":
                autouse = autouse or any(k.arg == "autouse" and isinstance(k.value, ast.Constant) and k.value.value is True for k in dec.keywords)
        if autouse:
            body = ast.Module(body=node.body, type_ignores=[])
            if any(isinstance(n, ast.Name) and n.id == "socket" for n in ast.walk(body)) and any(
                isinstance(n, ast.Constant) and n.value in ("socket", "create_connection") for n in ast.walk(body)
            ):
                return True
    return False


def _touches_environment(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv") and isinstance(node.value, ast.Name) and node.value.id == "os":
            found.append(f"os.{node.attr}")
        if isinstance(node, ast.Name) and node.id in ("getenv", "load_dotenv", "dotenv_values", "find_dotenv"):
            found.append(node.id)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            if any(n.split(".")[0] == "dotenv" for n in names if n):
                found.append("dotenv import")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".env"):
            found.append(".env path")
    return found


def check_source(source: str) -> list[str]:
    """Problems with how a test source builds the real client; empty if it does not construct it or does so safely."""
    tree = ast.parse(source)
    calls = construction_calls(tree)
    if not calls:
        return []
    problems: list[str] = []
    string_names = _module_string_names(tree)
    default_session_ok = _default_session_constructions(tree)
    for call in calls:
        where = f"line {call.lineno}"
        session = next((k for k in call.keywords if k.arg == "session"), None)
        if session is None or (isinstance(session.value, ast.Constant) and session.value.value is None):
            if id(call) not in default_session_ok:
                problems.append(f"{where}: the real client is built without a fake session= (transport)")
        key = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "api_key"), None)
        key_ok = isinstance(key, ast.Constant) and (key.value is None or (isinstance(key.value, str) and key.value != ""))   # None: no credential at all
        key_ok = key_ok or (isinstance(key, ast.Name) and key.id in string_names)
        if not key_ok:
            problems.append(f"{where}: the credential is not a literal dummy string (a literal, None, or a module-level string constant)")
        for k in call.keywords:
            if k.arg == "base_url" and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str) and _PROVIDER_HOST.search(k.value.value):
                problems.append(f"{where}: base_url names the real provider host")
    if not _has_socket_tripwire(tree):
        problems.append("the file has no autouse fixture that patches socket.socket / socket.create_connection")
    for item in _touches_environment(tree):
        problems.append(f"the file touches the environment or .env ({item})")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _PROVIDER_HOST.search(node.value):
            problems.append(f"line {node.lineno}: a literal names the real provider host")
    return problems
