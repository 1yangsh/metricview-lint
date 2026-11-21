from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from metricview_lint.schema import build_schema

ROOT = Path(__file__).parent.parent
SCHEMA = build_schema()
VALIDATOR = jsonschema.Draft7Validator(SCHEMA)


def _load(path: Path):
    # Editors use YAML 1.2 (`on` is a string), so mirror that for unquoted `on:` keys.
    text = (
        path.read_text()
        .replace("\n    on:", "\n    'on':")
        .replace("\n        on:", "\n        'on':")
    )
    return yaml.safe_load(text)


def test_schema_is_valid_draft7():
    jsonschema.Draft7Validator.check_schema(SCHEMA)


def test_committed_schema_is_up_to_date():
    committed = json.loads((ROOT / "schemas" / "databricks-metric-view.json").read_text())
    assert committed == SCHEMA, (
        "run: metricview-lint --print-schema > schemas/databricks-metric-view.json"
    )


@pytest.mark.parametrize("path", sorted((ROOT / "examples").rglob("*.yaml")), ids=lambda p: p.name)
def test_examples_match_schema(path: Path):
    errors = list(VALIDATOR.iter_errors(_load(path)))
    if path.parent.name == "valid":
        assert errors == []


@pytest.mark.parametrize(
    "doc",
    [
        {"source": "t", "measures": [{"name": "n", "expr": "COUNT(1)"}]},  # no version
        {"version": 1.1, "source": "t"},  # no fields/measures
        {"version": 1.1, "source": "t", "measures": [{"name": "n"}]},  # no expr
        {
            "version": 1.1,
            "source": "t",
            "measures": [{"expr": "SUM(x)", "format": {"type": "currency"}}],
        },
        {
            "version": 1.1,
            "source": "t",
            "joins": [{"name": "c", "source": "t.c", "cardinality": "1:n"}],
            "measures": [{"expr": "COUNT(1)"}],
        },
    ],
)
def test_schema_rejects(doc):
    assert list(VALIDATOR.iter_errors(doc))
