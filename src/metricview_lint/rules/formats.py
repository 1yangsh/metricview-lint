"""`format` metadata on fields and measures (MV6xx)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from ..core import Severity, rule
from ..loader import Document, Path
from ..model import fields, measures

E = Severity.ERROR
Finding = Iterator[tuple[str, Path]]

_DATE_FORMATS = {
    "locale_short_month",
    "locale_long_month",
    "year_month_day",
    "locale_number_month",
    "year_week",
}
_TIME_FORMATS = {"no_time", "locale_hour_minute", "locale_hour_minute_second"}
_ABBREVIATIONS = {"none", "compact", "scientific"}
_NUMERIC_COMMON = {"type", "decimal_places", "hide_group_separator"}
_ALLOWED = {
    "number": _NUMERIC_COMMON | {"abbreviation"},
    "currency": _NUMERIC_COMMON | {"abbreviation", "currency_code"},
    "percentage": _NUMERIC_COMMON,
    "byte": _NUMERIC_COMMON,
    "date": {"type", "date_format", "leading_zeros"},
    "date_time": {"type", "date_format", "time_format", "leading_zeros"},
}


def _decimal_places(dp: Any, p: Path) -> Finding:
    if not isinstance(dp, dict):
        yield "decimal_places must be a mapping with a 'type'", p
        return
    t = dp.get("type")
    if t not in ("max", "exact", "all"):
        yield f"decimal_places.type must be max, exact or all, got {t!r}", (*p, "type")
        return
    if t in ("max", "exact"):
        places = dp.get("places")
        if not isinstance(places, int) or isinstance(places, bool) or not 0 <= places <= 10:
            yield (
                f"decimal_places.places must be an integer from 0 to 10 when type is {t}",
                (*p, "places"),
            )


def _check(fmt: dict[str, Any], p: Path) -> Finding:
    t = fmt.get("type")
    if t not in _ALLOWED:
        yield f"format.type must be one of {', '.join(_ALLOWED)}, got {t!r}", (*p, "type")
        return
    for k in fmt:
        if k not in _ALLOWED[t]:
            yield f"'{k}' is not valid for format type '{t}'", (*p, k)
    if t == "currency":
        code = fmt.get("currency_code")
        if code is None:
            yield "currency format requires 'currency_code' (ISO 4217, e.g. USD)", p
        elif not (isinstance(code, str) and re.fullmatch(r"[A-Z]{3}", code)):
            yield (
                f"currency_code must be a 3-letter ISO 4217 code like USD, got {code!r}",
                (*p, "currency_code"),
            )
    if "decimal_places" in fmt:
        yield from _decimal_places(fmt["decimal_places"], (*p, "decimal_places"))
    if "abbreviation" in fmt and fmt["abbreviation"] not in _ABBREVIATIONS:
        yield (
            f"abbreviation must be none, compact or scientific, got {fmt['abbreviation']!r}",
            (*p, "abbreviation"),
        )
    for k in ("hide_group_separator", "leading_zeros"):
        if k in fmt and not isinstance(fmt[k], bool):
            yield f"'{k}' must be true or false", (*p, k)
    if t in ("date", "date_time"):
        allowed = _DATE_FORMATS | ({"no_date"} if t == "date_time" else set())
        df = fmt.get("date_format")
        if df is not None and df not in allowed:
            yield (
                f"invalid date_format {df!r}; use one of {', '.join(sorted(allowed))}",
                (*p, "date_format"),
            )
        if t == "date" and df is None:
            yield "date format requires 'date_format'", p
    if t == "date_time":
        tf = fmt.get("time_format")
        if tf is not None and tf not in _TIME_FORMATS:
            yield (
                f"invalid time_format {tf!r}; use one of {', '.join(sorted(_TIME_FORMATS))}",
                (*p, "time_format"),
            )
        if (
            fmt.get("date_format", "no_date") == "no_date"
            and fmt.get("time_format", "no_time") == "no_time"
        ):
            yield (
                "date_time format needs a date_format other than no_date or a time_format other than no_time",
                p,
            )


@rule("MV601", E, "`format` spec is invalid")
def format_spec(doc: Document) -> Finding:
    for it in fields(doc) + measures(doc):
        fmt = it.data.get("format")
        if isinstance(fmt, dict):
            yield from _check(fmt, (*it.path, "format"))
