"""Diagnostics, the rule registry and the lint entry points."""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path as FsPath

from .loader import Document, LoadError, Path, extract_from_sql, load_yaml


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    line: int | None = None
    path: Path = ()
    file: str | None = None

    @property
    def location(self) -> str:
        return ".".join(str(p) if isinstance(p, str) else f"[{p}]" for p in self.path).replace(
            ".[", "["
        )

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "path": self.location,
        }


@dataclass(frozen=True)
class Rule:
    code: str
    severity: Severity
    summary: str
    check: Callable[[Document], Iterator[tuple[str, Path]]]


RULES: dict[str, Rule] = {}


def rule(code: str, severity: Severity, summary: str):
    """Register a check. The check yields `(message, path)` pairs."""

    def decorator(fn: Callable[[Document], Iterator[tuple[str, Path]]]):
        if code in RULES:
            raise ValueError(f"duplicate rule code {code}")
        RULES[code] = Rule(code, severity, summary, fn)
        return fn

    return decorator


# Codes produced outside the rule registry.
PARSE_ERROR = "MV000"
DUPLICATE_KEY = "MV001"


def lint_document(doc: Document, disabled: frozenset[str] = frozenset()) -> list[Diagnostic]:
    from . import rules  # noqa: F401  (registers rules on import)

    out: list[Diagnostic] = []
    for r in RULES.values():
        if r.code in disabled:
            continue
        for message, path in r.check(doc):
            out.append(Diagnostic(r.code, r.severity, message, doc.line_of(path), path))
    return out


def lint_text(
    text: str, *, line_offset: int = 0, disabled: frozenset[str] = frozenset()
) -> list[Diagnostic]:
    """Lint a single metric view YAML body."""
    try:
        doc, dupes = load_yaml(text, line_offset)
    except LoadError as exc:
        return [Diagnostic(PARSE_ERROR, Severity.ERROR, exc.message, exc.line)]
    diags = []
    if DUPLICATE_KEY not in disabled:
        diags = [
            Diagnostic(
                DUPLICATE_KEY,
                Severity.ERROR,
                f"duplicate key '{path[-1]}' (the later value silently wins)",
                line,
                path,
            )
            for path, line in dupes
        ]
    return sorted(diags + lint_document(doc, disabled), key=lambda d: (d.line or 0, d.code))


_MARKERS = ("source", "fields", "dimensions", "measures")


def looks_like_metric_view(text: str) -> bool:
    """True when a YAML document has a top-level key only metric views use.

    Lets the CLI and pre-commit hook run over a whole repo without flagging
    unrelated YAML (CI configs, docker-compose files, ...).
    """
    try:
        doc, _ = load_yaml(text)
    except LoadError:
        return True  # report the parse error rather than hiding the file
    return isinstance(doc.data, dict) and any(k in doc.data for k in _MARKERS)


def lint_file(
    path: str | FsPath,
    disabled: frozenset[str] = frozenset(),
    *,
    skip_non_metric_views: bool = False,
) -> list[Diagnostic]:
    """Lint a `.yaml`/`.yml` metric view or every metric view inside a `.sql` file."""
    p = FsPath(path)
    text = p.read_text(encoding="utf-8")
    if skip_non_metric_views and p.suffix.lower() != ".sql" and not looks_like_metric_view(text):
        return []
    if p.suffix.lower() == ".sql":
        diags: list[Diagnostic] = []
        for snippet in extract_from_sql(text):
            diags += lint_text(snippet.text, line_offset=snippet.line_offset, disabled=disabled)
    else:
        diags = lint_text(text, disabled=disabled)
    return [Diagnostic(d.code, d.severity, d.message, d.line, d.path, str(path)) for d in diags]
