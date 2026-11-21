"""Names, expressions and references between fields and measures (MV2xx, MV3xx)."""

from __future__ import annotations

from collections.abc import Iterator

from ..core import Severity, rule
from ..loader import Document, Path
from ..model import Item, fields, joins, measures, root
from ..sql import (
    AGGREGATES,
    aggregated_identifiers,
    function_calls,
    has_window_function,
    is_wildcard,
    measure_refs,
)

E, W = Severity.ERROR, Severity.WARNING
Finding = Iterator[tuple[str, Path]]

_METADATA = ("comment", "display_name", "format", "synonyms")


def _all(doc: Document) -> list[Item]:
    return fields(doc) + measures(doc)


# --- names -----------------------------------------------------------------


@rule("MV201", W, "field/measure has no `name` (derived names need DBR 19+)")
def name_missing(doc: Document) -> Finding:
    for it in _all(doc):
        if "name" not in it.data and not is_wildcard(it.expr):
            yield (
                f"{it.kind} has no 'name'; names are only derived automatically on DBR 19+",
                it.path,
            )


@rule("MV202", E, "`name` must not be empty")
def name_empty(doc: Document) -> Finding:
    for it in _all(doc):
        if isinstance(it.data.get("name"), str) and not it.data["name"].strip():
            yield f"{it.kind} name is empty", (*it.path, "name")


@rule("MV203", E, "names must be unique across fields and measures (case-insensitive)")
def name_unique(doc: Document) -> Finding:
    seen: dict[str, Item] = {}
    for it in _all(doc):
        if not it.name or not it.name.strip():
            continue
        key = it.name.strip().lower()
        if key in seen:
            first = seen[key]
            yield (
                f"{it.kind} name '{it.name}' collides with {first.kind} '{first.name}' "
                "(names are compared case-insensitively across fields and measures)",
                (*it.path, "name"),
            )
        else:
            seen[key] = it


@rule("MV204", E, "wildcard expressions can't have a name or metadata")
def wildcard_props(doc: Document) -> Finding:
    for it in _all(doc):
        if not is_wildcard(it.expr):
            continue
        for k in ("name", *_METADATA):
            if k in it.data:
                yield (
                    f"'{k}' is not allowed on a wildcard expression ({(it.expr or '').strip()})",
                    (*it.path, k),
                )


@rule("MV205", E, "`display_name`/`synonyms` length limits")
def metadata_limits(doc: Document) -> Finding:
    for it in _all(doc):
        dn = it.data.get("display_name")
        if isinstance(dn, str) and len(dn) > 255:
            yield (
                f"display_name is {len(dn)} characters; the limit is 255",
                (*it.path, "display_name"),
            )
        syn = it.data.get("synonyms")
        if isinstance(syn, list):
            if len(syn) > 10:
                yield f"{len(syn)} synonyms; the limit is 10", (*it.path, "synonyms")
            for i, s in enumerate(syn):
                if isinstance(s, str) and len(s) > 255:
                    yield "synonym longer than 255 characters", (*it.path, "synonyms", i)


# --- expressions -----------------------------------------------------------


@rule("MV301", E, "fields and measures need an `expr`")
def expr_required(doc: Document) -> Finding:
    for it in _all(doc):
        e = it.data.get("expr")
        if e is None or (isinstance(e, str) and not e.strip()):
            yield f"{it.kind} '{it.name or '?'}' is missing 'expr'", it.path


@rule("MV302", E, "measure `expr` must use an aggregate function")
def measure_needs_aggregate(doc: Document) -> Finding:
    for m in measures(doc):
        if m.expr is None or is_wildcard(m.expr):
            continue
        if not (function_calls(m.expr) & AGGREGATES):
            yield (
                f"measure '{m.name or '?'}' has no aggregate function (SUM, COUNT, AVG, MEASURE, ...); "
                "a non-aggregated expression belongs in 'fields'. "
                "If it calls a user-defined aggregate, disable MV302",
                (*m.path, "expr"),
            )


@rule("MV303", W, "field `expr` should not aggregate")
def field_aggregate(doc: Document) -> Finding:
    for f in fields(doc):
        if f.expr is None:
            continue
        aggs = sorted(function_calls(f.expr) & AGGREGATES)
        if aggs:
            yield (
                f"field '{f.name or '?'}' uses aggregate {', '.join(a.upper() for a in aggs)}(); "
                "fields must return one value per row, so this probably belongs in 'measures'",
                (*f.path, "expr"),
            )


@rule("MV304", E, "window functions (OVER) are not allowed; use a `window` measure")
def no_window_functions(doc: Document) -> Finding:
    for it in _all(doc):
        if it.expr and has_window_function(it.expr):
            yield (
                f"{it.kind} '{it.name or '?'}' uses a window function (OVER ...), which metric views "
                "reject; express it as a measure with a 'window' spec instead",
                (*it.path, "expr"),
            )
    flt = root(doc).get("filter")
    if isinstance(flt, str) and has_window_function(flt):
        yield "the filter uses a window function (OVER ...), which metric views reject", ("filter",)


def _unqualified(ref: str) -> str:
    return ref.split(".", 1)[1] if ref.lower().startswith("source.") else ref


@rule("MV305", E, "MEASURE() must reference an earlier measure")
def measure_ref_order(doc: Document) -> Finding:
    ms = measures(doc)
    index = {m.name.lower(): i for i, m in enumerate(ms) if m.name}
    field_names = {f.name.lower() for f in fields(doc) if f.name}
    for i, m in enumerate(ms):
        for ref in measure_refs(m.expr or ""):
            if ref.lower().startswith("source."):
                continue  # explicitly the source metric view's measure
            key = ref.lower()
            if key == (m.name or "").lower():
                yield (
                    f"measure '{m.name}' references itself; to reference a source metric view's "
                    f"measure with the same name write MEASURE(source.{ref})",
                    (*m.path, "expr"),
                )
            elif key in index and index[key] > i:
                yield (
                    f"MEASURE({ref}) references a measure defined later; move '{ref}' above '{m.name}'",
                    (*m.path, "expr"),
                )
            elif key not in index and key in field_names:
                yield (
                    f"MEASURE({ref}) references a field; MEASURE() only takes measures",
                    (*m.path, "expr"),
                )
    for f in fields(doc):
        if f.expr and measure_refs(f.expr):
            yield (
                f"field '{f.name or '?'}' calls MEASURE(); measures can't be used as field values",
                (*f.path, "expr"),
            )


@rule("MV306", W, "aggregating a measure by name; use MEASURE(name)")
def aggregating_measure_name(doc: Document) -> Finding:
    names = {m.name.lower(): m.name for m in measures(doc) if m.name}
    for m in measures(doc):
        for fn, ident in aggregated_identifiers(m.expr or ""):
            if ident.lower() in names and ident.lower() != (m.name or "").lower():
                yield (
                    f"{fn.upper()}({ident}) aggregates the measure '{names[ident.lower()]}'; "
                    f"reference it with MEASURE(`{names[ident.lower()]}`) instead",
                    (*m.path, "expr"),
                )


@rule("MV307", E, "a window measure can't reference another window measure")
def window_on_window(doc: Document) -> Finding:
    windowed = {m.name.lower() for m in measures(doc) if m.name and m.data.get("window")}
    for m in measures(doc):
        if not m.data.get("window"):
            continue
        for ref in measure_refs(m.expr or ""):
            if _unqualified(ref).lower() in windowed and ref.lower() != (m.name or "").lower():
                yield (
                    f"window measure '{m.name}' references window measure '{ref}'; "
                    "compose window measures from a regular (non-window) measure",
                    (*m.path, "expr"),
                )


@rule("MV308", E, "fields can't reference columns of a one_to_many join")
def field_refs_one_to_many(doc: Document) -> Finding:
    from ..sql import qualified_refs

    fan_out = [j.alias.lower() for j in joins(doc) if j.alias and j.cardinality == "one_to_many"]
    if not fan_out:
        return
    for f in fields(doc):
        for parts in qualified_refs(f.expr or ""):
            dotted = ".".join(parts).lower()
            hit = next((a for a in fan_out if dotted.startswith(a + ".")), None)
            if hit:
                yield (
                    f"field '{f.name or '?'}' references '{'.'.join(parts)}' from one_to_many join "
                    f"'{hit}'; only measures may use a one_to_many join's columns",
                    (*f.path, "expr"),
                )
