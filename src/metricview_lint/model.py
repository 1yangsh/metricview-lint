"""Typed accessors over a loaded metric view so rules stay short."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .loader import Document, Path

SUPPORTED_VERSIONS = ("0.1", "1.1")


def version(doc: Document) -> str | None:
    """The spec version as a string ("1.1"), or None when missing/unreadable."""
    if not isinstance(doc.data, dict) or "version" not in doc.data:
        return None
    v = doc.data["version"]
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, float):
        return f"{v:g}" if v != int(v) else f"{int(v)}.0"
    return str(v).strip()


def root(doc: Document) -> dict[str, Any]:
    return doc.data if isinstance(doc.data, dict) else {}


def field_key(doc: Document) -> str:
    """`fields` is preferred; `dimensions` is the accepted synonym."""
    return "fields" if "fields" in root(doc) else "dimensions"


@dataclass(frozen=True)
class Item:
    kind: str  # "field" or "measure"
    path: Path
    data: dict[str, Any]

    @property
    def name(self) -> str | None:
        n = self.data.get("name")
        return n if isinstance(n, str) else None

    @property
    def expr(self) -> str | None:
        e = self.data.get("expr")
        return e if isinstance(e, str) else None


def _items(doc: Document, key: str, kind: str) -> Iterator[Item]:
    seq = root(doc).get(key)
    if isinstance(seq, list):
        for i, it in enumerate(seq):
            if isinstance(it, dict):
                yield Item(kind, (key, i), it)


def fields(doc: Document) -> list[Item]:
    out: list[Item] = []
    for key in ("fields", "dimensions"):
        out += _items(doc, key, "field")
    return out


def measures(doc: Document) -> list[Item]:
    return list(_items(doc, "measures", "measure"))


@dataclass(frozen=True)
class Join:
    path: Path
    data: dict[str, Any]
    alias: str | None  # full dot path, e.g. "customer.nation"
    parent: Join | None

    @property
    def cardinality(self) -> str:
        c = self.data.get("cardinality", "many_to_one")
        return c if isinstance(c, str) else "many_to_one"

    def ancestors(self) -> Iterator[Join]:
        j = self.parent
        while j is not None:
            yield j
            j = j.parent


def joins(doc: Document) -> list[Join]:
    out: list[Join] = []

    def walk(seq: Any, path: Path, parent: Join | None) -> None:
        if not isinstance(seq, list):
            return
        for i, j in enumerate(seq):
            if not isinstance(j, dict):
                continue
            name = j.get("name") if isinstance(j.get("name"), str) else None
            alias = None
            if name is not None:
                alias = f"{parent.alias}.{name}" if parent and parent.alias else name
            node = Join((*path, i), j, alias, parent)
            out.append(node)
            walk(j.get("joins"), (*path, i, "joins"), node)

    walk(root(doc).get("joins"), ("joins",), None)
    return out


def is_materialized(doc: Document) -> bool:
    return isinstance(root(doc).get("materialization"), dict)
