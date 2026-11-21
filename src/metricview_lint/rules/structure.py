"""Top-level shape, versions, unknown keys and value types (MV1xx)."""

from __future__ import annotations

import difflib
from collections.abc import Iterator
from typing import Any

from ..core import Severity, rule
from ..loader import Document, Path
from ..model import SUPPORTED_VERSIONS, joins, root, version
from ..sql import is_wildcard

E, W = Severity.ERROR, Severity.WARNING

TOP_KEYS = {
    "version",
    "comment",
    "source",
    "parameters",
    "filter",
    "joins",
    "fields",
    "dimensions",
    "measures",
    "materialization",
}
ITEM_KEYS = {"name", "expr", "comment", "display_name", "format", "synonyms"}
MEASURE_KEYS = ITEM_KEYS | {"window"}
JOIN_KEYS = {"name", "source", "on", "using", "cardinality", "joins", "rely"}
RELY_KEYS = {"at_most_one_match"}
WINDOW_KEYS = {"order", "range", "semiadditive", "offset"}
MAT_KEYS = {"mode", "schedule", "materialized_views"}
MV_ENTRY_KEYS = {
    "name",
    "type",
    "dimensions",
    "measures",
    "cluster_by",
    "partition_by",
    "refresh_policy",
}
CLUSTER_KEYS = {"cols", "auto"}
PARAM_KEYS = {"name", "data_type", "default", "comment"}

Finding = Iterator[tuple[str, Path]]


@rule("MV100", E, "the document must be a YAML mapping")
def root_is_mapping(doc: Document) -> Finding:
    if not isinstance(doc.data, dict):
        yield "a metric view definition must be a YAML mapping (key: value pairs)", ()


@rule("MV101", E, "`version` is required")
def version_required(doc: Document) -> Finding:
    if isinstance(doc.data, dict) and "version" not in doc.data:
        yield "missing required key 'version' (use 1.1)", ()


@rule("MV102", E, "`version` must be a supported spec version")
def version_supported(doc: Document) -> Finding:
    if not isinstance(doc.data, dict) or "version" not in doc.data:
        return
    v = version(doc)
    if v not in SUPPORTED_VERSIONS:
        yield (
            f"unsupported version {doc.data['version']!r}; supported: {', '.join(SUPPORTED_VERSIONS)}",
            ("version",),
        )


@rule("MV103", E, "`source` is required")
def source_required(doc: Document) -> Finding:
    if isinstance(doc.data, dict) and not doc.data.get("source"):
        yield "missing required key 'source' (a catalog.schema.table name or a SQL query)", ()


@rule("MV104", E, "at least one of `fields` or `measures` is required")
def fields_or_measures(doc: Document) -> Finding:
    r = root(doc)
    if isinstance(doc.data, dict) and not any(
        r.get(k) for k in ("fields", "dimensions", "measures")
    ):
        yield "define at least one of 'fields' or 'measures'", ()


@rule("MV105", E, "`fields` and `dimensions` are synonyms; use only one")
def fields_and_dimensions(doc: Document) -> Finding:
    r = root(doc)
    if "fields" in r and "dimensions" in r:
        yield "'fields' and 'dimensions' are synonyms; merge them into 'fields'", ("dimensions",)


def _unknown(keys: dict[str, Any], allowed: set[str], path: Path, where: str) -> Finding:
    for k in keys:
        if k not in allowed:
            guess = difflib.get_close_matches(str(k), sorted(allowed), n=1)
            hint = f"; did you mean '{guess[0]}'?" if guess else ""
            yield f"unknown key '{k}' in {where}{hint}", (*path, k)


def _each(seq: Any, path: Path) -> Iterator[tuple[dict[str, Any], Path]]:
    if isinstance(seq, list):
        for i, it in enumerate(seq):
            if isinstance(it, dict):
                yield it, (*path, i)


@rule("MV106", W, "unknown key (likely a typo)")
def unknown_keys(doc: Document) -> Finding:
    r = root(doc)
    yield from _unknown(r, TOP_KEYS, (), "the metric view")
    for key in ("fields", "dimensions"):
        for it, p in _each(r.get(key), (key,)):
            # `window` on a field is reported by MV109 instead.
            yield from _unknown(it, ITEM_KEYS | {"window"}, p, "a field")
    for it, p in _each(r.get("measures"), ("measures",)):
        yield from _unknown(it, MEASURE_KEYS, p, "a measure")
        for w, wp in _each(it.get("window"), (*p, "window")):
            yield from _unknown(w, WINDOW_KEYS, wp, "a window spec")
    for j in joins(doc):
        yield from _unknown(j.data, JOIN_KEYS, j.path, "a join")
        if isinstance(j.data.get("rely"), dict):
            yield from _unknown(j.data["rely"], RELY_KEYS, (*j.path, "rely"), "rely")
    for it, p in _each(r.get("parameters"), ("parameters",)):
        yield from _unknown(it, PARAM_KEYS, p, "a parameter")
    mat = r.get("materialization")
    if isinstance(mat, dict):
        yield from _unknown(mat, MAT_KEYS, ("materialization",), "materialization")
        mvs = mat.get("materialized_views")
        for it, p in _each(mvs, ("materialization", "materialized_views")):
            yield from _unknown(it, MV_ENTRY_KEYS | {"fields"}, p, "a materialized view")
            if isinstance(it.get("cluster_by"), dict):
                yield from _unknown(
                    it["cluster_by"], CLUSTER_KEYS, (*p, "cluster_by"), "cluster_by"
                )


_STRING_KEYS = {"source", "filter", "comment"}
_LIST_KEYS = {"fields", "dimensions", "measures", "joins", "parameters"}


@rule("MV107", E, "value has the wrong type")
def value_types(doc: Document) -> Finding:
    r = root(doc)
    for k in _STRING_KEYS & r.keys():
        if not isinstance(r[k], str):
            yield f"'{k}' must be a string", (k,)
    for k in _LIST_KEYS & r.keys():
        v = r[k]
        if not isinstance(v, list):
            yield f"'{k}' must be a list (each entry starts with '- ')", (k,)
            continue
        for i, it in enumerate(v):
            if not isinstance(it, dict):
                yield f"each entry of '{k}' must be a mapping, got {type(it).__name__}", (k, i)
    for k in ("fields", "dimensions", "measures"):
        for it, p in _each(r.get(k), (k,)):
            for sk in ("name", "expr", "comment", "display_name"):
                if sk in it and not isinstance(it[sk], str):
                    yield f"'{sk}' must be a string; quote it", (*p, sk)
            if "synonyms" in it and not (
                isinstance(it["synonyms"], list) and all(isinstance(s, str) for s in it["synonyms"])
            ):
                yield "'synonyms' must be a list of strings", (*p, "synonyms")
            if "format" in it and not isinstance(it["format"], dict):
                yield "'format' must be a mapping with a 'type'", (*p, "format")
    for j in joins(doc):
        for sk in ("name", "source", "on", "cardinality"):
            if sk in j.data and not isinstance(j.data[sk], str):
                yield f"join '{sk}' must be a string", (*j.path, sk)
        if "using" in j.data and not (
            isinstance(j.data["using"], list) and all(isinstance(c, str) for c in j.data["using"])
        ):
            yield "join 'using' must be a list of column names", (*j.path, "using")
        rely = j.data.get("rely")
        if rely is not None and not isinstance(rely, dict):
            yield "join 'rely' must be a mapping", (*j.path, "rely")
        elif (
            isinstance(rely, dict)
            and "at_most_one_match" in rely
            and not isinstance(rely["at_most_one_match"], bool)
        ):
            yield (
                "'rely.at_most_one_match' must be true or false",
                (*j.path, "rely", "at_most_one_match"),
            )
    if "materialization" in r and not isinstance(r["materialization"], dict):
        yield "'materialization' must be a mapping", ("materialization",)


@rule("MV108", E, "feature requires spec version 1.1")
def needs_v11(doc: Document) -> Finding:
    if version(doc) != "0.1":
        return
    r = root(doc)
    msg = "'{}' requires version 1.1 (this definition declares version 0.1)"
    if "comment" in r:
        yield msg.format("comment"), ("comment",)
    for key in ("fields", "dimensions", "measures"):
        for it, p in _each(r.get(key), (key,)):
            for k in ("comment", "display_name", "format", "synonyms"):
                if k in it:
                    yield msg.format(k), (*p, k)
            if is_wildcard(it.get("expr")):
                yield msg.format("wildcard expressions"), (*p, "expr")
            for w, wp in _each(it.get("window"), (*p, "window")):
                if "offset" in w:
                    yield msg.format("offset"), (*wp, "offset")
                rng = w.get("range")
                if isinstance(rng, str) and any(
                    m in rng.lower().split() for m in ("inclusive", "exclusive")
                ):
                    yield msg.format("inclusive/exclusive range modifiers"), (*wp, "range")
    for j in joins(doc):
        if "cardinality" in j.data:
            yield msg.format("cardinality"), (*j.path, "cardinality")
    mat = r.get("materialization")
    if isinstance(mat, dict):
        for it, p in _each(
            mat.get("materialized_views"), ("materialization", "materialized_views")
        ):
            if "refresh_policy" in it:
                yield msg.format("refresh_policy"), (*p, "refresh_policy")


@rule("MV109", E, "`window` is only allowed on measures")
def window_on_field(doc: Document) -> Finding:
    for key in ("fields", "dimensions"):
        for it, p in _each(root(doc).get(key), (key,)):
            if "window" in it:
                yield "'window' is only allowed on measures, not fields", (*p, "window")
