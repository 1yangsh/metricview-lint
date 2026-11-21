"""Join definitions (MV4xx)."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..core import Severity, rule
from ..loader import Document, Path
from ..model import joins
from ..sql import strip_literals

E, W = Severity.ERROR, Severity.WARNING
Finding = Iterator[tuple[str, Path]]

CARDINALITIES = ("many_to_one", "one_to_many")


@rule("MV401", E, "joins need `name` and `source`")
def join_required(doc: Document) -> Finding:
    for j in joins(doc):
        for k in ("name", "source"):
            if not j.data.get(k):
                yield f"join is missing required '{k}'", j.path


@rule("MV402", E, "joins need exactly one of `on` or `using`")
def join_condition(doc: Document) -> Finding:
    for j in joins(doc):
        has_on, has_using = "on" in j.data, "using" in j.data
        if has_on and has_using:
            yield f"join '{j.alias}' sets both 'on' and 'using'; keep one", (*j.path, "using")
        elif not has_on and not has_using:
            yield f"join '{j.alias}' needs an 'on' condition or a 'using' column list", j.path


@rule("MV403", E, "join names must be unique among siblings")
def join_unique(doc: Document) -> Finding:
    seen: set[str] = set()
    for j in joins(doc):
        if j.alias is None:
            continue
        if j.alias.lower() in seen:
            yield f"join name '{j.alias}' is used more than once", (*j.path, "name")
        seen.add(j.alias.lower())


@rule("MV404", E, "`cardinality` must be many_to_one or one_to_many")
def join_cardinality(doc: Document) -> Finding:
    for j in joins(doc):
        c = j.data.get("cardinality")
        if c is not None and c not in CARDINALITIES:
            yield (
                f"invalid cardinality {c!r}; use one of: {', '.join(CARDINALITIES)}",
                (*j.path, "cardinality"),
            )


@rule("MV405", E, "a join subtree can't mix cardinalities")
def join_subtree_cardinality(doc: Document) -> Finding:
    for j in joins(doc):
        if j.parent is not None and j.cardinality != j.parent.cardinality:
            yield (
                f"join '{j.alias}' is {j.cardinality} but its parent '{j.parent.alias}' is "
                f"{j.parent.cardinality}; every join nested under a join must share its cardinality",
                (*j.path, "cardinality") if "cardinality" in j.data else j.path,
            )


_SELF_EQ = re.compile(r"(?<![\w.`])([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)(?![\w.(`])")


@rule("MV406", E, "`on` compares an unqualified column with itself")
def join_on_self_compare(doc: Document) -> Finding:
    for j in joins(doc):
        on = j.data.get("on")
        if not isinstance(on, str) or j.alias is None:
            continue
        parent = j.parent.alias if j.parent else "source"
        for m in _SELF_EQ.finditer(strip_literals(on)):
            a, b = m.group(1), m.group(2)
            if a.lower() == b.lower() and a.lower() not in ("true", "false", "null"):
                yield (
                    f"join '{j.alias}' 'on' compares {a} = {b}; unqualified columns resolve to the "
                    f"joined table, so this is always true. Write {parent}.{a} = {j.data.get('name')}.{b} "
                    f"or use 'using: [{a}]'",
                    (*j.path, "on"),
                )
