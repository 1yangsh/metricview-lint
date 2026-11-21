"""Load metric view YAML while keeping source line numbers.

Rules need to point at the line that caused a problem, so instead of
`yaml.safe_load` we compose the node graph and convert it ourselves,
recording the line of every mapping key and sequence item by its path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

Path = tuple[str | int, ...]


@dataclass
class Document:
    """A parsed metric view definition."""

    data: Any
    lines: dict[Path, int] = field(default_factory=dict)
    # Offset added to every line so diagnostics map back to the original
    # file when the YAML was extracted from a SQL statement.
    line_offset: int = 0

    def line_of(self, path: Path) -> int | None:
        """Return the 1-based line for `path`, falling back to its nearest parent."""
        while True:
            if path in self.lines:
                return self.lines[path] + self.line_offset
            if not path:
                return None
            path = path[:-1]


class LoadError(Exception):
    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that also reports duplicate mapping keys."""


def _convert(node: yaml.Node, path: Path, lines: dict[Path, int], dupes: list) -> Any:
    lines.setdefault(path, node.start_mark.line + 1)
    if isinstance(node, yaml.MappingNode):
        out: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            # Keys are always names here. Use the raw text so YAML 1.1 quirks
            # (an unquoted `on:` key resolving to boolean True) don't bite.
            key = key_node.value if isinstance(key_node, yaml.ScalarNode) else str(key_node.value)
            child = (*path, key)
            if key in out:
                dupes.append((child, key_node.start_mark.line + 1))
            lines[child] = key_node.start_mark.line + 1
            out[key] = _convert(value_node, child, lines, dupes)
        return out
    if isinstance(node, yaml.SequenceNode):
        return [_convert(item, (*path, i), lines, dupes) for i, item in enumerate(node.value)]
    return _UniqueKeyLoader(  # construct scalars with SafeLoader's resolver
        ""
    ).construct_object(node, deep=True)


def load_yaml(text: str, line_offset: int = 0) -> tuple[Document, list[tuple[Path, int]]]:
    """Parse YAML text. Returns the document and any duplicate keys found."""
    try:
        node = yaml.compose(text, Loader=_UniqueKeyLoader)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        line = mark.line + 1 + line_offset if mark else None
        raise LoadError(f"invalid YAML: {exc.problem or exc}{_hint(exc)}", line) from exc
    except yaml.YAMLError as exc:
        raise LoadError(f"invalid YAML: {exc}") from exc
    lines: dict[Path, int] = {}
    dupes: list[tuple[Path, int]] = []
    data = None if node is None else _convert(node, (), lines, dupes)
    dupes = [(p, ln + line_offset) for p, ln in dupes]
    return Document(data=data, lines=lines, line_offset=line_offset), dupes


def _hint(exc: yaml.MarkedYAMLError) -> str:
    problem = str(exc.problem or "")
    if "'`'" in problem:
        return " (a YAML value can't start with a backtick: wrap the whole expression in double quotes)"
    if "mapping values are not allowed" in problem:
        return " (an expression containing ': ' must be wrapped in double quotes, or use a | block)"
    if "'*'" in problem or "alias" in problem or "alphabetic or numeric" in problem:
        return ' (wildcards such as * must be quoted: "*")'
    return ""


# CREATE [OR REPLACE] VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$
# ALTER VIEW name AS $$ ... $$
_SQL_BODY = re.compile(
    r"(?:WITH\s+METRICS\s+LANGUAGE\s+YAML\s+AS|ALTER\s+VIEW\s+[\w.`]+\s+AS)\s*"
    r"(\$\w*\$)(?P<body>.*?)\1",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class Snippet:
    text: str
    line_offset: int


def extract_from_sql(sql: str) -> list[Snippet]:
    """Find every metric view YAML body inside a SQL script."""
    snippets = []
    for match in _SQL_BODY.finditer(sql):
        start = match.start("body")
        snippets.append(Snippet(match.group("body"), sql.count("\n", 0, start)))
    return snippets
