"""JSON Schema for metric view YAML, for editor autocompletion and hover docs.

The schema is deliberately lenient (no `additionalProperties: false`, no
regexes over the window/SQL mini-languages): editors use it to suggest keys
and show documentation, while `metricview-lint` does the strict checking.
Published to SchemaStore as `databricks-metric-view.json`.
"""

from __future__ import annotations

import json
from typing import Any

DOCS = "https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference"
SCHEMA_ID = "https://www.schemastore.org/databricks-metric-view.json"


def _s(description: str, **extra: Any) -> dict[str, Any]:
    return {"type": "string", "description": description, **extra}


def _numeric_format_props() -> dict[str, Any]:
    return {
        "decimal_places": {"$ref": "#/definitions/decimalPlaces"},
        "hide_group_separator": {
            "type": "boolean",
            "description": "hide the thousands separator",
        },
    }


ABBREVIATION = {
    "description": "how large numbers are abbreviated",
    "enum": ["none", "compact", "scientific"],
}
DATE_FORMATS = [
    "locale_short_month",
    "locale_long_month",
    "year_month_day",
    "locale_number_month",
    "year_week",
]


def _format_branch(kind: str, props: dict[str, Any], required: list[str] | None = None):
    branch: dict[str, Any] = {
        "if": {"properties": {"type": {"const": kind}}, "required": ["type"]},
        "then": {"properties": props},
    }
    if required:
        branch["then"]["required"] = required
    return branch


def build_schema() -> dict[str, Any]:
    item_props = {
        "name": _s("unique name of the column (case-insensitive across fields and measures)"),
        "expr": _s(
            "SQL expression; may reference source columns, join columns (alias.column) "
            "and earlier fields\n" + DOCS
        ),
        "comment": _s("description of the column (spec 1.1)"),
        "display_name": _s("human-readable label shown in tools (spec 1.1)", maxLength=255),
        "format": {"$ref": "#/definitions/format"},
        "synonyms": {
            "type": "array",
            "description": "alternative names that help AI tools such as Genie find this column (spec 1.1)",
            "maxItems": 10,
            "items": {"type": "string", "maxLength": 255},
        },
    }
    window = {
        "type": "object",
        "description": "window spec for a measure\n"
        "https://docs.databricks.com/aws/en/uc-semantics/metric-views/advanced-techniques",
        "required": ["order", "range"],
        "properties": {
            "order": _s("name of the field that orders the window (usually a date field)"),
            "range": _s(
                "current, cumulative, all, or trailing|leading <n> [day|month|year] "
                "[inclusive|exclusive]",
                examples=["current", "cumulative", "trailing 7 day", "leading 3 month inclusive"],
            ),
            "semiadditive": {
                "description": "which value to keep when the measure can't be summed over the order field",
                "enum": ["first", "last"],
                "default": "last",
            },
            "offset": {
                "description": "shift the window, e.g. -12 month for year over year (spec 1.1)",
                "anyOf": [{"type": "string"}, {"type": "integer"}],
                "examples": ["-1 year", "-12 month", -1],
            },
        },
    }
    join: dict[str, Any] = {
        "type": "object",
        "description": "LEFT OUTER join to another table\n"
        "https://docs.databricks.com/aws/en/uc-semantics/metric-views/joins",
        "required": ["name", "source"],
        "properties": {
            "name": _s("alias used to reference the joined table as <name>.<column>"),
            "source": _s("catalog.schema.table name or SQL query"),
            "on": _s(
                "join condition; qualify the parent side with source. (or the parent join name)"
            ),
            "using": {
                "type": "array",
                "description": "columns that exist on both sides of the join",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "cardinality": {
                "description": "relationship from the parent to this table (spec 1.1 for one_to_many)",
                "enum": ["many_to_one", "one_to_many"],
                "default": "many_to_one",
            },
            "rely": {
                "type": "object",
                "description": "optimizer hints that are trusted, not validated",
                "properties": {
                    "at_most_one_match": {
                        "type": "boolean",
                        "description": "each row matches at most one row on the other side",
                        "default": False,
                    }
                },
            },
            "joins": {
                "type": "array",
                "description": "nested (snowflake) joins",
                "items": {"$ref": "#/definitions/join"},
            },
        },
    }
    format_def = {
        "type": "object",
        "description": "display format used by BI and AI tools (spec 1.1)\n"
        "https://docs.databricks.com/aws/en/uc-semantics/agent-metadata",
        "required": ["type"],
        "properties": {
            "type": {
                "description": "kind of value being formatted",
                "enum": ["number", "currency", "percentage", "byte", "date", "date_time"],
            },
        },
        "allOf": [
            _format_branch("number", {**_numeric_format_props(), "abbreviation": ABBREVIATION}),
            _format_branch(
                "currency",
                {
                    **_numeric_format_props(),
                    "abbreviation": ABBREVIATION,
                    "currency_code": _s(
                        "ISO 4217 currency code", pattern="^[A-Z]{3}$", examples=["USD"]
                    ),
                },
                ["currency_code"],
            ),
            _format_branch("percentage", _numeric_format_props()),
            _format_branch("byte", _numeric_format_props()),
            _format_branch(
                "date",
                {
                    "date_format": {"enum": DATE_FORMATS},
                    "leading_zeros": {"type": "boolean"},
                },
                ["date_format"],
            ),
            _format_branch(
                "date_time",
                {
                    "date_format": {"enum": [*DATE_FORMATS, "no_date"]},
                    "time_format": {
                        "enum": ["no_time", "locale_hour_minute", "locale_hour_minute_second"]
                    },
                    "leading_zeros": {"type": "boolean"},
                },
            ),
        ],
    }
    decimal_places = {
        "type": "object",
        "description": "how many decimal places to show",
        "required": ["type"],
        "properties": {
            "type": {"enum": ["max", "exact", "all"]},
            "places": {"type": "integer", "minimum": 0, "maximum": 10},
        },
    }
    mv_entry = {
        "type": "object",
        "required": ["name", "type"],
        "properties": {
            "name": _s("name of the materialized view"),
            "type": {"enum": ["aggregated", "unaggregated"]},
            "dimensions": {
                "type": "array",
                "description": "field names to pre-aggregate by; '*' or '* EXCEPT (a, b)' for all",
                "items": {"type": "string"},
            },
            "measures": {
                "type": "array",
                "description": "measure names to pre-aggregate; '*' or '* EXCEPT (a, b)' for all",
                "items": {"type": "string"},
            },
            "cluster_by": {
                "type": "object",
                "properties": {
                    "cols": {"type": "array", "items": {"type": "string"}},
                    "auto": {"type": "boolean"},
                },
            },
            "partition_by": {"type": "array", "items": {"type": "string"}},
            "refresh_policy": _s(
                "auto, incremental, incremental strict or full (spec 1.1)",
                examples=["auto", "incremental", "incremental strict", "full"],
            ),
        },
    }
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": SCHEMA_ID,
        "title": "Databricks Unity Catalog metric view",
        "description": "YAML definition of a Databricks Unity Catalog metric view "
        "(CREATE VIEW ... WITH METRICS LANGUAGE YAML)\n" + DOCS,
        "type": "object",
        "required": ["version", "source"],
        "anyOf": [
            {"properties": {k: True}, "required": [k]} for k in ("fields", "dimensions", "measures")
        ],
        "properties": {
            "version": {
                "description": "metric view spec version",
                "anyOf": [{"enum": [0.1, 1.1]}, {"enum": ["0.1", "1.1"]}],
                "default": 1.1,
            },
            "comment": _s("description of the metric view (spec 1.1)"),
            "source": _s(
                "catalog.schema.table (table, view or metric view) or a SQL query",
                examples=["main.sales.orders"],
            ),
            "filter": _s("SQL boolean expression applied to every query"),
            "parameters": {
                "type": "array",
                "description": "query parameters referenced by name in expressions",
                "items": {
                    "type": "object",
                    "required": ["name", "data_type"],
                    "properties": {
                        "name": _s("parameter name"),
                        "data_type": _s("SQL type, e.g. INT, DATE, STRING"),
                        "default": {"description": "default value, castable to data_type"},
                        "comment": _s("description of the parameter"),
                    },
                },
            },
            "joins": {"type": "array", "items": {"$ref": "#/definitions/join"}},
            "fields": {
                "type": "array",
                "description": "dimensions to group and filter by",
                "items": {"$ref": "#/definitions/field"},
            },
            "dimensions": {
                "type": "array",
                "description": "synonym of fields, kept for backward compatibility",
                "items": {"$ref": "#/definitions/field"},
            },
            "measures": {
                "type": "array",
                "description": "aggregated values",
                "items": {"$ref": "#/definitions/measure"},
            },
            "materialization": {
                "type": "object",
                "description": "pre-computed aggregations\n"
                "https://docs.databricks.com/aws/en/uc-semantics/metric-views/materialization",
                "required": ["mode", "materialized_views"],
                "properties": {
                    "mode": {"const": "relaxed"},
                    "schedule": _s("refresh schedule, e.g. every 6 hours"),
                    "materialized_views": {"type": "array", "items": mv_entry},
                },
            },
        },
        "definitions": {
            "field": {
                "type": "object",
                "description": "dimension column",
                "required": ["expr"],
                "properties": item_props,
            },
            "measure": {
                "type": "object",
                "description": "aggregated column; expr must use an aggregate function or MEASURE()",
                "required": ["expr"],
                "properties": {**item_props, "window": {"type": "array", "items": window}},
            },
            "join": join,
            "format": format_def,
            "decimalPlaces": decimal_places,
        },
    }


def dumps() -> str:
    return json.dumps(build_schema(), indent=2) + "\n"
