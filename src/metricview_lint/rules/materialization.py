"""Materialization and parameters (MV7xx, MV8xx)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from ..core import Severity, rule
from ..loader import Document, Path
from ..model import fields, is_materialized, joins, measures, root
from ..sql import INVOKER_DEPENDENT, function_calls

E, W = Severity.ERROR, Severity.WARNING
Finding = Iterator[tuple[str, Path]]

_MV = ("materialization", "materialized_views")
_REFRESH = {"auto", "incremental", "incremental strict", "full"}
_WILDCARD = re.compile(r"^\*(?:\s+EXCEPT\s*\((?P<cols>[^)]*)\))?$", re.I)


def _entries(doc: Document) -> Iterator[tuple[dict[str, Any], Path]]:
    mat = root(doc).get("materialization")
    seq = mat.get("materialized_views") if isinstance(mat, dict) else None
    if isinstance(seq, list):
        for i, e in enumerate(seq):
            if isinstance(e, dict):
                yield e, (*_MV, i)


@rule("MV701", E, "materialization `mode` and `materialized_views` are required")
def mat_required(doc: Document) -> Finding:
    mat = root(doc).get("materialization")
    if not isinstance(mat, dict):
        return
    if mat.get("mode") != "relaxed":
        yield (
            f"materialization.mode must be 'relaxed', got {mat.get('mode')!r}",
            ("materialization",),
        )
    if not isinstance(mat.get("materialized_views"), list) or not mat["materialized_views"]:
        yield "materialization needs a non-empty 'materialized_views' list", ("materialization",)
    sched = mat.get("schedule")
    if isinstance(sched, str) and "trigger" in sched.lower():
        yield (
            "TRIGGER ON UPDATE is not supported for metric view schedules",
            ("materialization", "schedule"),
        )


@rule("MV702", E, "materialized view entries need a valid name and type")
def mat_entries(doc: Document) -> Finding:
    names: set[str] = set()
    unaggregated = 0
    for e, p in _entries(doc):
        n = e.get("name")
        if not isinstance(n, str) or not n.strip():
            yield "materialized view is missing 'name'", p
        elif n.lower() in names:
            yield f"materialized view name '{n}' is used more than once", (*p, "name")
        else:
            names.add(n.lower())
        t = e.get("type")
        if t not in ("aggregated", "unaggregated"):
            yield (
                f"materialized view type must be aggregated or unaggregated, got {t!r}",
                (*p, "type"),
            )
        if t == "unaggregated":
            unaggregated += 1
            if unaggregated > 1:
                yield "only one unaggregated materialized view is allowed", (*p, "type")
            for k in ("dimensions", "measures"):
                if k in e:
                    yield f"an unaggregated materialized view can't list '{k}'", (*p, k)
        if t == "aggregated" and not (e.get("dimensions") or e.get("measures")):
            yield "an aggregated materialized view needs 'dimensions' and/or 'measures'", p
        if "fields" in e:
            yield "use 'dimensions' (not 'fields') inside materialized_views", (*p, "fields")
        if "cluster_by" in e and "partition_by" in e:
            yield "cluster_by and partition_by can't be combined", (*p, "partition_by")
        rp = e.get("refresh_policy")
        if rp is not None and " ".join(str(rp).lower().split()) not in _REFRESH:
            yield (
                f"refresh_policy must be one of {', '.join(sorted(_REFRESH))}, got {rp!r}",
                (*p, "refresh_policy"),
            )


@rule("MV703", E, "materialized views must reference existing fields and measures")
def mat_references(doc: Document) -> Finding:
    known = {
        "dimensions": {f.name.lower() for f in fields(doc) if f.name},
        "measures": {m.name.lower() for m in measures(doc) if m.name},
    }
    label = {"dimensions": "field", "measures": "measure"}
    for e, p in _entries(doc):
        for k in ("dimensions", "measures"):
            seq = e.get(k)
            if not isinstance(seq, list):
                continue
            for i, ref in enumerate(seq):
                if not isinstance(ref, str):
                    continue
                w = _WILDCARD.match(ref.strip())
                if w:
                    if len(seq) > 1:
                        yield f"a wildcard must be the only entry in '{k}'", (*p, k, i)
                    cols = [
                        c.strip().strip("`")
                        for c in (w.group("cols") or "").split(",")
                        if c.strip()
                    ]
                    for c in cols:
                        if known[k] and c.lower() not in known[k]:
                            yield (
                                f"EXCEPT column '{c}' is not a {label[k]} of this view",
                                (*p, k, i),
                            )
                    if known[k] and cols and not (known[k] - {c.lower() for c in cols}):
                        yield f"'{ref}' excludes every {label[k]}", (*p, k, i)
                elif known[k] and ref.strip().strip("`").lower() not in known[k]:
                    yield f"'{ref}' is not a {label[k]} of this metric view", (*p, k, i)


@rule("MV704", E, "materialization is incompatible with this definition")
def mat_incompatible(doc: Document) -> Finding:
    if not is_materialized(doc):
        return
    r = root(doc)
    if r.get("parameters"):
        yield "a metric view with parameters can't be materialized", ("parameters",)
    if any(j.cardinality == "one_to_many" for j in joins(doc)):
        for e, p in _entries(doc):
            if e.get("type") == "unaggregated":
                yield (
                    "unaggregated materialization isn't supported with one_to_many joins",
                    (*p, "type"),
                )
    exprs: list[tuple[str, Path]] = []
    if isinstance(r.get("filter"), str):
        exprs.append((r["filter"], ("filter",)))
    exprs += [(it.expr, (*it.path, "expr")) for it in fields(doc) + measures(doc) if it.expr]
    for text, path in exprs:
        bad = sorted(function_calls(text) & INVOKER_DEPENDENT)
        if bad:
            yield (
                f"{', '.join(b + '()' for b in bad)} depends on who runs the query and blocks "
                "materialization",
                path,
            )


@rule("MV801", E, "parameters need `name` and `data_type`; defaults come last")
def parameters(doc: Document) -> Finding:
    seq = root(doc).get("parameters")
    if not isinstance(seq, list):
        return
    seen: set[str] = set()
    saw_default = False
    for i, prm in enumerate(seq):
        if not isinstance(prm, dict):
            continue
        p: Path = ("parameters", i)
        n = prm.get("name")
        if not isinstance(n, str) or not n.strip():
            yield "parameter is missing 'name'", p
        elif n.lower() in seen:
            yield f"parameter '{n}' is declared more than once", (*p, "name")
        else:
            seen.add(n.lower())
        if not prm.get("data_type"):
            yield f"parameter '{n or '?'}' is missing 'data_type'", p
        if "default" in prm:
            saw_default = True
            d = prm["default"]
            if isinstance(d, str) and re.search(r"\bselect\b", d, re.I):
                yield f"parameter '{n}' default can't contain a subquery", (*p, "default")
        elif saw_default:
            yield (
                f"parameter '{n or '?'}' has no default but an earlier parameter does; "
                "parameters with defaults must come last",
                p,
            )
