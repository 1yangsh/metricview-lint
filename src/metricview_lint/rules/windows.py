"""Window measure specs (MV5xx)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from ..core import Severity, rule
from ..loader import Document, Path
from ..model import fields, measures, root
from ..sql import NON_DETERMINISTIC, function_calls

E, W = Severity.ERROR, Severity.WARNING
Finding = Iterator[tuple[str, Path]]

_UNIT = r"(?:day|days|month|months|year|years)"
_VALUE = r"(?:\d+|[A-Za-z_]\w*)"  # literal or parameter name
_RANGE = re.compile(
    rf"^(?:current|cumulative|all|(?:trailing|leading)\s+{_VALUE}(?:\s+{_UNIT})?(?:\s+(?:inclusive|exclusive))?)$",
    re.I,
)
_OFFSET = re.compile(rf"^(?:-?\d+(?:\s+{_UNIT})?|{_VALUE}(?:\s+{_UNIT})?)$", re.I)
_KEYWORDS = {
    "trailing",
    "leading",
    "current",
    "cumulative",
    "all",
    "day",
    "days",
    "month",
    "months",
    "year",
    "years",
    "inclusive",
    "exclusive",
    "offset",
}


def _specs(doc: Document) -> Iterator[tuple[Any, Path, str]]:
    for m in measures(doc):
        win = m.data.get("window")
        if win is None:
            continue
        if not isinstance(win, list):
            yield win, (*m.path, "window"), m.name or "?"
            continue
        for i, w in enumerate(win):
            yield w, (*m.path, "window", i), m.name or "?"


@rule("MV501", E, "`window` must be a list of specs with `order` and `range`")
def window_shape(doc: Document) -> Finding:
    for w, p, name in _specs(doc):
        if not isinstance(w, dict):
            yield f"measure '{name}': each window spec must be a mapping (use '- order: ...')", p
            continue
        for k in ("order", "range"):
            if k not in w:
                yield f"measure '{name}': window spec is missing '{k}'", p


@rule("MV502", E, "window `range` syntax")
def window_range(doc: Document) -> Finding:
    for w, p, name in _specs(doc):
        rng = w.get("range") if isinstance(w, dict) else None
        if rng is None:
            continue
        text = " ".join(str(rng).split())
        if not _RANGE.match(text):
            yield (
                f"measure '{name}': invalid range {rng!r}; expected current, cumulative, all, "
                "or 'trailing|leading <n> [day|month|year] [inclusive|exclusive]'",
                (*p, "range"),
            )
        elif (m := re.match(r"^(?:trailing|leading)\s+([A-Za-z_]\w*)", text, re.I)) and m.group(
            1
        ).lower() in _KEYWORDS:
            yield (
                f"measure '{name}': '{m.group(1)}' is a window keyword, not a value",
                (*p, "range"),
            )


@rule("MV503", E, "window `order` must name a field defined in this view")
def window_order(doc: Document) -> Finding:
    by_name = {f.name.lower(): f for f in fields(doc) if f.name}
    for w, p, name in _specs(doc):
        order = w.get("order") if isinstance(w, dict) else None
        if not isinstance(order, str):
            continue
        key = order.strip().strip("`").lower()
        if by_name and key not in by_name:
            yield (
                f"measure '{name}': window order '{order}' is not a field of this metric view; "
                "define a field for it and reference the field name",
                (*p, "order"),
            )
            continue
        f = by_name.get(key)
        bad = sorted(function_calls(f.expr or "") & NON_DETERMINISTIC) if f else []
        if bad:
            yield (
                f"measure '{name}': window order field '{order}' uses non-deterministic "
                f"{', '.join(b + '()' for b in bad)}",
                (*p, "order"),
            )


@rule("MV504", E, "window `semiadditive` must be first or last")
def window_semiadditive(doc: Document) -> Finding:
    for w, p, name in _specs(doc):
        if isinstance(w, dict) and "semiadditive" in w:
            v = w["semiadditive"]
            if not (isinstance(v, str) and v.lower() in ("first", "last")):
                yield (
                    f"measure '{name}': semiadditive must be 'first' or 'last', got {v!r}",
                    (
                        *p,
                        "semiadditive",
                    ),
                )


@rule("MV505", E, "window `offset` syntax")
def window_offset(doc: Document) -> Finding:
    for w, p, name in _specs(doc):
        if not isinstance(w, dict) or "offset" not in w:
            continue
        off = w["offset"]
        text = str(off).strip() if isinstance(off, (str, int)) and not isinstance(off, bool) else ""
        if not _OFFSET.match(" ".join(text.split())):
            yield (
                f"measure '{name}': invalid offset {off!r}; expected e.g. '-12 month', '-1 day' or -1",
                (*p, "offset"),
            )
        elif isinstance(w.get("range"), str) and w["range"].strip().lower() == "all":
            yield f"measure '{name}': offset has no effect with range: all", (*p, "offset")


@rule("MV506", E, "window size parameters must be declared and integral")
def window_parameters(doc: Document) -> Finding:
    params = {
        p["name"].lower(): p
        for p in root(doc).get("parameters") or []
        if isinstance(p, dict) and isinstance(p.get("name"), str)
    }
    integral = ("tinyint", "smallint", "int", "integer", "bigint", "byte", "short", "long")
    for w, p, name in _specs(doc):
        if not isinstance(w, dict):
            continue
        for key, pattern in (
            ("range", r"^(?:trailing|leading)\s+([A-Za-z_]\w*)"),
            ("offset", r"^([A-Za-z_]\w*)"),
        ):
            v = w.get(key)
            m = re.match(pattern, " ".join(str(v).split()), re.I) if isinstance(v, str) else None
            if not m or m.group(1).lower() in _KEYWORDS:
                continue
            ident = m.group(1).lower()
            if ident not in params:
                yield (
                    f"measure '{name}': window {key} uses undeclared parameter '{m.group(1)}'",
                    (*p, key),
                )
            elif str(params[ident].get("data_type", "")).strip().lower() not in integral:
                yield (
                    f"measure '{name}': parameter '{m.group(1)}' used as a window size must have an "
                    "integral data_type (INT, BIGINT, ...)",
                    (*p, key),
                )
