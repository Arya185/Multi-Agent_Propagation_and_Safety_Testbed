"""Validated loader for experiment result records (standalone; no statistics, no filtering).

Accepted format: exactly what the existing writer produces. ``JsonlWriter`` appends one
``json.dumps(record)`` line per record, and the runner writes ``EpisodeResult.model_dump(mode="json")``
to ``episodes.jsonl``. Each non-blank line is therefore parsed as JSON and validated with the real
``EpisodeResult`` model; the loader adds no field names of its own.

The loader never repairs, imputes, drops, merges or reorders records:
  * records are returned in file order, and every schema-valid line is returned, duplicates included;
  * malformed JSON, non-object lines and schema-invalid records are reported with line numbers;
  * a duplicate ``episode_id`` among valid records is reported with all its line numbers;
  * a missing record (an expected id that never appears), an invalid record (an expected id whose line
    failed validation) and a valid record whose values happen to be zero are three distinct things.
Blank lines are counted, not treated as records. The report never contains record content (only line
numbers, error types and field locations), and the loader does not derive or add hidden labels.

An expected inventory is OPTIONAL and must be supplied explicitly by the caller; the loader never builds
one. ``safe_for_analysis`` is True only when the file is present and non-empty, every line is valid, no
episode id is duplicated, and, if an inventory was supplied, it matches exactly (nothing missing,
invalid or unexpected). Callers that deliberately accept missing episodes should read the report instead
of ``require_safe``.

Two entry points share ONE scanning implementation (``_load``): ``load_episode_results`` reads a file by path, and
``parse_episode_results`` parses bytes the caller already holds. The integrity gate and the lifecycle use the byte
form so that the bytes whose SHA-256 was checked are exactly the bytes that are parsed; the file is not reopened.

Limitation: loading synthetic or mock records proves the loader's logic; it does not show that a real
run directory is complete or correct.
"""

from __future__ import annotations

import io
import json
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from maps.schemas import EpisodeResult

DEFAULT_FILENAME = "episodes.jsonl"
_MAX_ERRORS_PER_LINE = 5


class UnsafeRunError(ValueError):
    """The loaded run is not safe to pass to downstream analysis."""


@dataclass(frozen=True)
class LineProblem:
    line: int
    message: str
    episode_id: str | None = None  # best-effort, only for schema-invalid lines


@dataclass(frozen=True)
class DuplicateId:
    episode_id: str
    lines: tuple[int, ...]


@dataclass(frozen=True)
class LoadReport:
    path: str
    file_exists: bool
    file_empty: bool
    read_error: str | None
    total_lines: int
    blank_lines: int
    valid_records: int
    invalid_json: tuple[LineProblem, ...]
    schema_invalid: tuple[LineProblem, ...]
    duplicate_ids: tuple[DuplicateId, ...]
    expected_supplied: bool
    duplicate_expected_ids: tuple[str, ...]
    missing_expected: tuple[str, ...]
    invalid_expected: tuple[str, ...]
    unexpected: tuple[str, ...]
    structurally_valid: bool
    inventory_matches: bool | None  # None when no expected inventory was supplied
    safe_for_analysis: bool
    problems: tuple[str, ...]


@dataclass(frozen=True)
class LoadResult:
    records: tuple[EpisodeResult, ...]  # all schema-valid records in file order, duplicates included
    line_numbers: tuple[int, ...]  # the file line of each record
    report: LoadReport

    def require_safe(self) -> tuple[EpisodeResult, ...]:
        if not self.report.safe_for_analysis:
            raise UnsafeRunError("; ".join(self.report.problems) or "run is not safe for analysis")
        return self.records


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-standard JSON constant: {name}")


def _describe(exc: ValidationError) -> str:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    shown = [f"{'.'.join(str(part) for part in e['loc']) or '<record>'}: {e['type']}" for e in errors[:_MAX_ERRORS_PER_LINE]]
    extra = len(errors) - len(shown)
    return "schema violation: " + "; ".join(shown) + (f" (+{extra} more)" if extra > 0 else "")


def _episode_id_hint(obj: dict) -> str | None:
    spec = obj.get("spec")
    value = spec.get("episode_id") if isinstance(spec, dict) else None
    return value if isinstance(value, str) and value else None


def _load(
    path_text: str,
    exists: bool,
    non_regular: bool,
    read_raw: Callable[[], bytes],
    expected_episode_ids: Iterable[str] | None,
) -> LoadResult:
    """The single scanning implementation. ``read_raw`` returns the file's bytes (it may raise OSError)."""
    expected_counts: Counter[str] | None = None
    if expected_episode_ids is not None:
        expected_list = list(expected_episode_ids)
        if not all(isinstance(e, str) and e for e in expected_list):
            raise ValueError("expected_episode_ids must be non-empty strings")
        expected_counts = Counter(expected_list)

    records: list[EpisodeResult] = []
    lines_of_records: list[int] = []
    invalid_json: list[LineProblem] = []
    schema_invalid: list[LineProblem] = []
    ids: dict[str, list[int]] = {}
    total = blank = 0
    read_error: str | None = None

    if exists:
        try:
            with io.TextIOWrapper(io.BytesIO(read_raw()), encoding="utf-8") as handle:
                for total, raw in enumerate(handle, start=1):
                    text = raw.strip()
                    if not text:
                        blank += 1
                        continue
                    try:
                        obj = json.loads(text, parse_constant=_reject_constant)
                    except (ValueError, RecursionError) as exc:
                        message = getattr(exc, "msg", None) or str(exc)
                        invalid_json.append(LineProblem(total, f"invalid JSON: {message[:120]}"))
                        continue
                    if not isinstance(obj, dict):
                        schema_invalid.append(LineProblem(total, "record is not a JSON object"))
                        continue
                    try:
                        result = EpisodeResult.model_validate(obj)
                    except ValidationError as exc:
                        schema_invalid.append(LineProblem(total, _describe(exc), _episode_id_hint(obj)))
                        continue
                    records.append(result)
                    lines_of_records.append(total)
                    ids.setdefault(result.spec.episode_id, []).append(total)
        except UnicodeDecodeError:
            read_error = f"file is not valid UTF-8 (read stopped near line {total + 1})"
        except OSError as exc:
            read_error = f"file could not be read: {type(exc).__name__}"
    elif non_regular:
        read_error = "path exists but is not a regular file"

    duplicates = tuple(DuplicateId(i, tuple(lines)) for i, lines in sorted(ids.items()) if len(lines) > 1)
    file_empty = exists and read_error is None and total == blank
    structurally_valid = (
        exists and read_error is None and not file_empty and not invalid_json and not schema_invalid
        and not duplicates and bool(records)
    )

    missing: tuple[str, ...] = ()
    invalid_expected: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    duplicate_expected: tuple[str, ...] = ()
    inventory_matches: bool | None = None
    if expected_counts is not None:
        expected = set(expected_counts)
        valid_ids = set(ids)
        invalid_ids = {p.episode_id for p in schema_invalid if p.episode_id}
        duplicate_expected = tuple(sorted(i for i, c in expected_counts.items() if c > 1))
        missing = tuple(sorted(expected - valid_ids - invalid_ids))
        invalid_expected = tuple(sorted((expected & invalid_ids) - valid_ids))
        unexpected = tuple(sorted((valid_ids | invalid_ids) - expected))
        inventory_matches = not (missing or invalid_expected or unexpected)
    safe = structurally_valid and inventory_matches is not False

    problems: list[str] = []
    if not exists and read_error is None:
        problems.append(f"result file not found: {path_text}")
    if read_error:
        problems.append(read_error)
    if file_empty:
        problems.append("result file is empty")
    if invalid_json:
        problems.append(f"{len(invalid_json)} line(s) are not valid JSON (first at line {invalid_json[0].line})")
    if schema_invalid:
        problems.append(f"{len(schema_invalid)} record(s) are schema-invalid (first at line {schema_invalid[0].line})")
    if duplicates:
        problems.append(f"{len(duplicates)} duplicated episode id(s)")
    if missing:
        problems.append(f"{len(missing)} expected episode(s) missing")
    if invalid_expected:
        problems.append(f"{len(invalid_expected)} expected episode(s) present but invalid")
    if unexpected:
        problems.append(f"{len(unexpected)} unexpected episode id(s)")

    report = LoadReport(
        path=path_text, file_exists=exists, file_empty=file_empty, read_error=read_error, total_lines=total,
        blank_lines=blank, valid_records=len(records), invalid_json=tuple(invalid_json),
        schema_invalid=tuple(schema_invalid), duplicate_ids=duplicates, expected_supplied=expected_counts is not None,
        duplicate_expected_ids=duplicate_expected, missing_expected=missing, invalid_expected=invalid_expected,
        unexpected=unexpected, structurally_valid=structurally_valid, inventory_matches=inventory_matches,
        safe_for_analysis=safe, problems=tuple(problems),
    )
    return LoadResult(records=tuple(records), line_numbers=tuple(lines_of_records), report=report)


def load_episode_results(
    run_dir: str | Path,
    *,
    expected_episode_ids: Iterable[str] | None = None,
    filename: str = DEFAULT_FILENAME,
) -> LoadResult:
    """Load and validate ``run_dir/filename`` by path (read-only). See the module docstring for the contract."""
    path = Path(run_dir) / filename
    return _load(str(path), path.is_file(), path.exists(), path.read_bytes, expected_episode_ids)


def parse_episode_results(
    raw: bytes,
    *,
    expected_episode_ids: Iterable[str] | None = None,
    source: str = DEFAULT_FILENAME,
) -> LoadResult:
    """Validate episode records from bytes the caller already holds (same rules and report as the path loader).

    ``source`` is only the text shown as the report's ``path``; nothing is read from disk."""
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError("raw must be bytes")
    return _load(str(source), True, False, lambda: bytes(raw), expected_episode_ids)
