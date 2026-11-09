"""Provider-route scanner (v2.3.56, Stage 4C): finds every code path in the repository that could reach a network
or the provider client, so each one can be matched against an explicit, per-file allow-list.

STATIC AND OFFLINE. The scanner reads source text (``.py``, ``.ipynb`` code cells, shell scripts) and parses
Python with ``ast``. It never imports, executes or evaluates anything it scans, never opens a file whose name
starts with ``.env``, and makes no network call. Comments and docstrings are ignored because the AST drops
comments and the scanner skips bare string statements (docstrings and attribute docstrings).

FINDING KINDS (``KINDS``)
  network_import          an import of a network-capable module (requests, urllib, http, socket, ...), with aliases
  provider_client_module  an import of ``maps.llm_client`` (any spelling, including relative imports)
  provider_client_ref     any reference to ``OpenRouterClient``: a name, attribute, import alias, class name or
                          string constant (so ``getattr(mod, "OpenRouterClient")`` and aliases are caught)
  complete_call           a call of ``<anything>.complete(...)`` or ``getattr(x, "complete")``; DEFINING a
                          ``complete`` method (a fake client) is not a finding
  endpoint_literal        a string constant that holds a URL scheme, the provider host or a provider path
  dynamic_load            ``__import__``, ``importlib.import_module``, ``exec``, ``eval``, builtin ``compile``,
                          ``spec_from_file_location``/``exec_module``/``load_module``, ``runpy`` entry points
  shell_fetch             ``curl`` or ``wget`` as a word in a shell script, a notebook ``!`` line or ``%%bash``
                          cell, or a Python string constant
  unscanned_source        source in a language this scanner cannot analyse (listed so a reviewer sees it)

``unparseable`` (a Python file or notebook that cannot be parsed) and ``unreadable`` are NEVER allow-listable:
the scanner fails closed on anything it cannot analyse. Every ``.ipynb`` file must be listed explicitly even if
its code cells are clean.

LIMITS. This is a static tripwire for accidental or careless additions, not a security boundary: a determined
author can build module names at run time, read code from data files, or use a mechanism not in the lists
(``subprocess`` running a downloaded binary, ``ctypes``, ``asyncio`` streams). It does not read configuration or
data files, so an endpoint in a JSON file (``api.base_url``) is not seen here: that value is not validated in this
stage (Stage 4E item).
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

KINDS = (
    "network_import", "provider_client_module", "provider_client_ref", "complete_call", "endpoint_literal",
    "dynamic_load", "shell_fetch", "unscanned_source",
)
NEVER_ALLOWLISTABLE = ("unparseable", "unreadable", "symlink")

NETWORK_MODULES = frozenset({
    "requests", "urllib", "urllib2", "urllib3", "http", "httpx", "httpcore", "aiohttp", "httplib2", "socket", "socketserver",
    "ssl", "websocket", "websockets", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "grpc", "pycurl",
    "paramiko", "boto3", "botocore", "openai", "anthropic", "treq", "twisted", "tornado", "scapy",
})
PROVIDER_MODULE_LEAF = "llm_client"
PROVIDER_CLIENT_NAME = "OpenRouterClient"
DYNAMIC_BUILTINS = frozenset({"__import__", "exec", "eval", "compile"})   # as a bare name; ``re.compile`` is an attribute and is not one
DYNAMIC_ATTRS = frozenset({"__import__", "import_module", "spec_from_file_location", "exec_module", "load_module", "run_path", "run_module"})
SHELL_EXTENSIONS = frozenset({".sh", ".bash", ".zsh", ".ksh", ".command"})
UNSCANNED_EXTENSIONS = frozenset({
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".rb", ".go", ".rs", ".pl", ".php", ".java", ".c", ".cc", ".cpp", ".h", ".cs", ".swift",
    ".lua", ".r", ".ps1", ".bat", ".cmd",
})
PRUNED_DIRS = frozenset({
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".idea", ".vscode", "build", "dist", ".eggs", "site-packages",
})
_FETCH_WORD = re.compile(r"(?<![\w.-])(curl|wget)(?![\w-])", re.IGNORECASE)
_ENDPOINT = re.compile(r"\b[a-z][a-z0-9+.\-]*://|openrouter\.ai|/chat/completions|/api/v1\b", re.IGNORECASE)
_SHEBANG_SHELL = re.compile(rb"^#!\s*\S*(?:/|\s)(?:ba|z|k|da|a)?sh\b")


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int
    detail: str   # a short fixed-vocabulary label or a matched module/name; never file content beyond that


@dataclass
class FileScan:
    path: str                                   # POSIX path relative to the scanned root
    findings: list[Finding] = field(default_factory=list)
    is_notebook: bool = False
    problem: str | None = None                  # one of NEVER_ALLOWLISTABLE when the file could not be analysed

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(f.kind for f in self.findings)


def _fold(node: ast.AST) -> str | None:
    """A string value for a constant expression built only from literals (``"a" + "b"``, ``"".join(["a", "b"])``), else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _fold(node.left), _fold(node.right)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.JoinedStr):
        parts = [_fold(v) if not isinstance(v, ast.FormattedValue) else "" for v in node.values]
        return "".join(p for p in parts if p is not None)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join" and len(node.args) == 1
            and isinstance(node.args[0], (ast.List, ast.Tuple))):
        sep, items = _fold(node.func.value), [_fold(e) for e in node.args[0].elts]
        if sep is not None and all(i is not None for i in items):
            return sep.join(items)   # type: ignore[arg-type]
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(self, kind: str, node: ast.AST, detail: str) -> None:
        self.findings.append(Finding(kind, getattr(node, "lineno", 0), detail))

    # imports -----------------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._module(node, alias.name)
            self._client_name(node, alias.name.rsplit(".", 1)[-1])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if node.level == 0:
            self._module(node, module)
        elif module.rsplit(".", 1)[-1] == PROVIDER_MODULE_LEAF:
            self.add("provider_client_module", node, "relative")
        for alias in node.names:
            if alias.name == PROVIDER_MODULE_LEAF:
                self.add("provider_client_module", node, "from-import")
            if alias.name == "*":
                if node.level == 0 and module.split(".")[0] in NETWORK_MODULES:
                    self.add("network_import", node, module.split(".")[0])
            elif node.level == 0 and not module:
                self._module(node, alias.name)
            self._client_name(node, alias.name)
            if alias.asname:
                self._client_name(node, alias.asname)
        self.generic_visit(node)

    def _module(self, node: ast.AST, name: str) -> None:
        root = name.split(".")[0]
        if root in NETWORK_MODULES:
            self.add("network_import", node, root)
        parts = name.split(".")
        if parts[-1] == PROVIDER_MODULE_LEAF or (PROVIDER_MODULE_LEAF in parts):
            self.add("provider_client_module", node, name)

    def _client_name(self, node: ast.AST, name: str) -> None:
        if name == PROVIDER_CLIENT_NAME:
            self.add("provider_client_ref", node, PROVIDER_CLIENT_NAME)

    # names, attributes, classes ----------------------------------------------
    def visit_Name(self, node: ast.Name) -> None:
        if node.id == PROVIDER_CLIENT_NAME:
            self.add("provider_client_ref", node, PROVIDER_CLIENT_NAME)
        if node.id in DYNAMIC_BUILTINS or node.id in DYNAMIC_ATTRS:
            self.add("dynamic_load", node, node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == PROVIDER_CLIENT_NAME:
            self.add("provider_client_ref", node, PROVIDER_CLIENT_NAME)
        if node.attr in DYNAMIC_ATTRS:
            self.add("dynamic_load", node, node.attr)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._client_name(node, node.name)
        self.generic_visit(node)

    # calls ---------------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "complete":
            self.add("complete_call", node, ".complete(")
        if isinstance(func, ast.Name) and func.id in ("getattr", "hasattr") and len(node.args) >= 2:
            if _fold(node.args[1]) == "complete":
                self.add("complete_call", node, "getattr complete")
        if isinstance(func, ast.Attribute) and func.attr == "join":
            folded = _fold(node)
            if folded is not None:
                self._string(node, folded)
        self.generic_visit(node)

    # strings -------------------------------------------------------------------
    def visit_Expr(self, node: ast.Expr) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return   # a docstring or a bare string statement: not code
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self._string(node, node.value)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        folded = _fold(node)
        if folded is not None:
            self._string(node, folded)
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        folded = _fold(node)
        if folded:
            self._string(node, folded)
        self.generic_visit(node)

    def _string(self, node: ast.AST, text: str) -> None:
        if text == PROVIDER_CLIENT_NAME or (PROVIDER_CLIENT_NAME in text and len(text) <= 80):
            self.add("provider_client_ref", node, PROVIDER_CLIENT_NAME)
        if _ENDPOINT.search(text):
            self.add("endpoint_literal", node, "url-or-provider-literal")
        if _FETCH_WORD.search(text):
            self.add("shell_fetch", node, "curl-or-wget")


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in sorted(findings, key=lambda f: (f.line, f.kind, f.detail)):
        if (f.kind, f.line, f.detail) not in seen:
            seen.add((f.kind, f.line, f.detail))
            out.append(f)
    return out


def scan_python_source(source: str) -> list[Finding]:
    """Findings for Python source text. Raises ``SyntaxError`` / ``ValueError`` if it cannot be parsed."""
    visitor = _Visitor()
    visitor.visit(ast.parse(source))
    return _dedupe(visitor.findings)


def scan_shell_source(source: str, *, notebook_bang: bool = False) -> list[Finding]:
    """Findings for shell text: ``curl``/``wget`` words and endpoint literals on non-comment lines."""
    findings: list[Finding] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _FETCH_WORD.search(line):
            findings.append(Finding("shell_fetch", number, "curl-or-wget"))
        if _ENDPOINT.search(line):
            findings.append(Finding("endpoint_literal", number, "url-or-provider-literal"))
    return _dedupe(findings)


def _notebook_cells(text: str) -> tuple[list[tuple[str, str]], str | None]:
    """(kind, source) for each code cell, or a problem code if the notebook is malformed."""
    try:
        data = json.loads(text)
        cells = data["cells"]
        if not isinstance(cells, list):
            raise TypeError
        out = []
        for cell in cells:
            if cell.get("cell_type") != "code":
                continue
            source = cell.get("source", "")
            source = "".join(source) if isinstance(source, list) else source
            if not isinstance(source, str):
                raise TypeError
            out.append(("code", source))
        return out, None
    except (ValueError, KeyError, TypeError, AttributeError):
        return [], "unparseable"


def scan_notebook_text(text: str) -> tuple[list[Finding], str | None]:
    """Findings for the code cells of a notebook. IPython ``!``/``%`` lines are scanned as shell text and replaced
    by ``pass`` before parsing; a ``%%bash``-style cell is scanned entirely as shell."""
    cells, problem = _notebook_cells(text)
    if problem:
        return [], problem
    findings: list[Finding] = []
    for index, (_kind, source) in enumerate(cells, start=1):
        if re.match(r"\s*%%\s*(bash|sh|zsh|script|system|!)", source):
            findings += [Finding(f.kind, index, f.detail) for f in scan_shell_source(source)]
            continue
        python_lines, shell_lines = [], []
        for raw in source.splitlines():
            stripped = raw.lstrip()
            if stripped.startswith(("!", "%")):
                shell_lines.append(stripped[1:])
                python_lines.append(raw[: len(raw) - len(stripped)] + "pass")
            else:
                python_lines.append(raw)
        try:
            findings += [Finding(f.kind, index, f.detail) for f in scan_python_source("\n".join(python_lines))]
        except (SyntaxError, ValueError):
            return [], "unparseable"
        findings += [Finding(f.kind, index, f.detail) for f in scan_shell_source("\n".join(shell_lines))]
    return _dedupe(findings), None


def _is_shell_file(path: Path, head: bytes) -> bool:
    return path.suffix in SHELL_EXTENSIONS or (path.suffix == "" and bool(_SHEBANG_SHELL.match(head)))


def scan_file(path: Path, root: Path) -> FileScan | None:
    """Scan one file, or None if it is not a source type the scanner covers. Never follows or reads a ``.env*`` file."""
    rel = path.relative_to(root).as_posix()
    if path.name.startswith(".env"):
        return None
    suffix = path.suffix
    if path.is_symlink():
        return FileScan(rel, problem="symlink") if (suffix in {".py", ".ipynb"} | SHELL_EXTENSIONS | UNSCANNED_EXTENSIONS) else None
    if suffix in UNSCANNED_EXTENSIONS:
        return FileScan(rel, [Finding("unscanned_source", 0, suffix)])
    try:
        if suffix == "":
            with path.open("rb") as handle:
                head = handle.read(64)
            if not head.startswith(b"#!"):
                return None
            if not _SHEBANG_SHELL.match(head) and b"python" not in head.splitlines()[0]:
                return FileScan(rel, [Finding("unscanned_source", 0, "shebang")])
            text = path.read_text(encoding="utf-8")
            if b"python" in head.splitlines()[0]:
                return _scan_python_file(rel, text)
            return FileScan(rel, scan_shell_source(text))
        if suffix == ".py":
            return _scan_python_file(rel, path.read_text(encoding="utf-8"))
        if suffix == ".ipynb":
            findings, problem = scan_notebook_text(path.read_text(encoding="utf-8"))
            return FileScan(rel, findings, is_notebook=True, problem=problem)
        if suffix in SHELL_EXTENSIONS:
            return FileScan(rel, scan_shell_source(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError):
        return FileScan(rel, problem="unreadable", is_notebook=suffix == ".ipynb")
    return None


def _scan_python_file(rel: str, text: str) -> FileScan:
    try:
        return FileScan(rel, scan_python_source(text))
    except (SyntaxError, ValueError, RecursionError):
        return FileScan(rel, problem="unparseable")


def iter_source_files(root: Path):
    """Files under ``root`` in sorted order, pruning well-known non-source directories (and never descending a symlinked directory)."""
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                if entry.is_dir():
                    continue
                yield entry
            elif entry.is_dir():
                if entry.name not in PRUNED_DIRS and not entry.name.endswith(".egg-info"):
                    stack.append(entry)
            else:
                yield entry


def scan_tree(root: str | Path) -> dict[str, FileScan]:
    """Scan every covered source file under ``root``; the result maps relative POSIX path to its scan, only for files
    that have findings, are notebooks, or could not be analysed."""
    base = Path(root)
    result: dict[str, FileScan] = {}
    for path in iter_source_files(base):
        scan = scan_file(path, base)
        if scan is not None and (scan.findings or scan.is_notebook or scan.problem):
            result[scan.path] = scan
    return result
