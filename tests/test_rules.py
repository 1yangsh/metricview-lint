from __future__ import annotations

import textwrap

import pytest

from metricview_lint import lint_text
from metricview_lint.core import RULES

VALID = """\
version: 1.1
comment: Daily shop KPIs
source: main.shop.orders
filter: source.status != 'test'
parameters:
  - name: window_days
    data_type: INT
    default: 7
joins:
  - name: customer
    source: main.shop.customers
    'on': source.customer_id = customer.id
    rely:
      at_most_one_match: true
    joins:
      - name: region
        source: main.shop.regions
        on: customer.region_id = region.id
  - name: refunds
    source: main.shop.refunds
    using: [order_id]
    cardinality: one_to_many
fields:
  - name: order_date
    expr: CAST(source.ordered_at AS DATE)
    display_name: Order date
    format:
      type: date
      date_format: year_month_day
  - name: Region
    expr: region.name
    synonyms: [area, territory]
  - expr: source.*
measures:
  - name: revenue
    expr: SUM(source.amount)
    format:
      type: currency
      currency_code: USD
      decimal_places: {type: exact, places: 2}
      abbreviation: compact
  - name: orders
    expr: COUNT(DISTINCT source.order_id) FILTER (WHERE source.status = 'paid')
  - name: aov
    expr: MEASURE(revenue) / MEASURE(orders)
  - name: refund_total
    expr: SUM(refunds.amount)
  - name: trailing_revenue
    expr: MEASURE(revenue)
    window:
      - order: order_date
        range: trailing window_days day
        semiadditive: last
  - name: revenue_last_year
    expr: MEASURE(revenue)
    window:
      - order: order_date
        range: current
        offset: -1 year
"""


def codes(text: str) -> list[str]:
    return [d.code for d in lint_text(textwrap.dedent(text))]


def test_valid_definition_is_clean():
    assert lint_text(VALID) == []


def test_every_rule_has_a_unique_code_and_summary():
    assert len(RULES) >= 40
    assert all(r.summary for r in RULES.values())


MINIMAL = "version: 1.1\nsource: a.b.c\n"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("- just\n- a list\n", "MV100"),
        ("source: a.b.c\nmeasures:\n  - {name: n, expr: COUNT(1)}\n", "MV101"),
        ("version: 2.0\nsource: t\nmeasures:\n  - {name: n, expr: COUNT(1)}\n", "MV102"),
        ("version: 1.1\nmeasures:\n  - {name: n, expr: COUNT(1)}\n", "MV103"),
        (MINIMAL, "MV104"),
        (
            MINIMAL + "fields:\n  - {name: a, expr: a}\ndimensions:\n  - {name: b, expr: b}\n",
            "MV105",
        ),
        (MINIMAL + "measure:\n  - {name: n, expr: COUNT(1)}\n", "MV106"),
        (MINIMAL + "measures:\n  - {name: n, expr: COUNT(1), dispaly_name: N}\n", "MV106"),
        (MINIMAL + "measures:\n  - {name: 12, expr: COUNT(1)}\n", "MV107"),
        (MINIMAL + "measures: {name: n}\n", "MV107"),
        (
            "version: 0.1\nsource: t\nmeasures:\n  - {name: n, expr: COUNT(1), synonyms: [x]}\n",
            "MV108",
        ),
        (
            MINIMAL
            + "fields:\n  - name: d\n    expr: d\n    window: [{order: d, range: current}]\n",
            "MV109",
        ),
        (MINIMAL + "measures:\n  - expr: COUNT(1)\n", "MV201"),
        (MINIMAL + "measures:\n  - {name: '', expr: COUNT(1)}\n", "MV202"),
        (
            MINIMAL
            + "fields:\n  - {name: Total, expr: a}\nmeasures:\n  - {name: total, expr: SUM(a)}\n",
            "MV203",
        ),
        (MINIMAL + "fields:\n  - {name: everything, expr: source.*}\n", "MV204"),
        (
            MINIMAL
            + "fields:\n  - name: a\n    expr: a\n    synonyms: ["
            + ",".join(f"s{i}" for i in range(11))
            + "]\n",
            "MV205",
        ),
        (MINIMAL + "measures:\n  - name: n\n", "MV301"),
        (MINIMAL + "measures:\n  - {name: n, expr: price * 2}\n", "MV302"),
        (MINIMAL + "fields:\n  - {name: n, expr: SUM(price)}\n", "MV303"),
        (MINIMAL + "measures:\n  - {name: n, expr: SUM(x) OVER (PARTITION BY y)}\n", "MV304"),
        (
            MINIMAL
            + "measures:\n  - {name: a, expr: MEASURE(b) * 2}\n  - {name: b, expr: SUM(x)}\n",
            "MV305",
        ),
        (MINIMAL + "measures:\n  - {name: a, expr: MEASURE(a) + 1}\n", "MV305"),
        (
            MINIMAL
            + "fields:\n  - {name: f, expr: MEASURE(m)}\nmeasures:\n  - {name: m, expr: SUM(x)}\n",
            "MV305",
        ),
        (
            MINIMAL
            + "measures:\n  - {name: Total revenue, expr: SUM(x)}\n  - {name: t2, expr: 'SUM(`Total revenue`)'}\n",
            "MV306",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - {name: b, expr: SUM(x)}\n"
            + "  - name: w1\n    expr: MEASURE(b)\n    window: [{order: d, range: cumulative}]\n"
            + "  - name: w2\n    expr: MEASURE(w1)\n    window: [{order: d, range: current}]\n",
            "MV307",
        ),
        (
            MINIMAL
            + "joins:\n  - {name: items, source: t.items, using: [id], cardinality: one_to_many}\n"
            + "fields:\n  - {name: sku, expr: items.sku}\n",
            "MV308",
        ),
        (
            MINIMAL
            + "joins:\n  - {source: t.c, using: [id]}\nmeasures:\n  - {name: n, expr: COUNT(1)}\n",
            "MV401",
        ),
        (
            MINIMAL
            + "joins:\n  - {name: c, source: t.c}\nmeasures:\n  - {name: n, expr: COUNT(1)}\n",
            "MV402",
        ),
        (
            MINIMAL
            + "joins:\n  - {name: c, source: t.c, using: [id], 'on': a = b}\nmeasures:\n  - {name: n, expr: COUNT(1)}\n",
            "MV402",
        ),
        (
            MINIMAL
            + "joins:\n  - {name: c, source: t.c, using: [id]}\n  - {name: C, source: t.d, using: [id]}\nmeasures:\n  - {name: n, expr: COUNT(1)}\n",
            "MV403",
        ),
        (
            MINIMAL
            + "joins:\n  - {name: c, source: t.c, using: [id], cardinality: many_to_many}\nmeasures:\n  - {name: n, expr: COUNT(1)}\n",
            "MV404",
        ),
        (
            MINIMAL
            + "joins:\n  - name: o\n    source: t.o\n    using: [id]\n    cardinality: one_to_many\n"
            + "    joins:\n      - {name: x, source: t.x, using: [id]}\nmeasures:\n  - {name: n, expr: COUNT(1)}\n",
            "MV405",
        ),
        (
            MINIMAL
            + "joins:\n  - {name: c, source: t.c, on: customer_id = customer_id}\nmeasures:\n  - {name: n, expr: COUNT(1)}\n",
            "MV406",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - name: n\n    expr: SUM(x)\n    window: [{order: d}]\n",
            "MV501",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - name: n\n    expr: SUM(x)\n    window: [{order: d, range: last 7 days}]\n",
            "MV502",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - name: n\n    expr: SUM(x)\n    window: [{order: day, range: current}]\n",
            "MV503",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: current_timestamp()}\nmeasures:\n  - name: n\n    expr: SUM(x)\n    window: [{order: d, range: current}]\n",
            "MV503",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - name: n\n    expr: SUM(x)\n    window: [{order: d, range: current, semiadditive: middle}]\n",
            "MV504",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - name: n\n    expr: SUM(x)\n    window: [{order: d, range: current, offset: 1 year ago}]\n",
            "MV505",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - name: n\n    expr: SUM(x)\n    window: [{order: d, range: trailing n_days day}]\n",
            "MV506",
        ),
        (
            MINIMAL + "measures:\n  - name: n\n    expr: SUM(x)\n    format: {type: currency}\n",
            "MV601",
        ),
        (
            MINIMAL
            + "measures:\n  - name: n\n    expr: SUM(x)\n    format: {type: percentage, abbreviation: compact}\n",
            "MV601",
        ),
        (
            MINIMAL
            + "measures:\n  - name: n\n    expr: SUM(x)\n    format: {type: number, decimal_places: {type: exact}}\n",
            "MV601",
        ),
        (
            MINIMAL
            + "fields:\n  - name: t\n    expr: t\n    format: {type: date_time, date_format: no_date, time_format: no_time}\n",
            "MV601",
        ),
        (
            MINIMAL
            + "measures:\n  - {name: n, expr: SUM(x)}\nmaterialization:\n  mode: strict\n  materialized_views:\n    - {name: b, type: unaggregated}\n",
            "MV701",
        ),
        (
            MINIMAL
            + "measures:\n  - {name: n, expr: SUM(x)}\nmaterialization:\n  mode: relaxed\n  materialized_views:\n    - {name: b, type: unaggregated}\n    - {name: c, type: unaggregated}\n",
            "MV702",
        ),
        (
            MINIMAL
            + "measures:\n  - {name: n, expr: SUM(x)}\nmaterialization:\n  mode: relaxed\n  materialized_views:\n    - {name: b, type: aggregated, fields: [x], measures: [n]}\n",
            "MV702",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - {name: n, expr: SUM(x)}\nmaterialization:\n  mode: relaxed\n  materialized_views:\n    - {name: b, type: aggregated, dimensions: [region], measures: [n]}\n",
            "MV703",
        ),
        (
            MINIMAL
            + "fields:\n  - {name: d, expr: d}\nmeasures:\n  - {name: n, expr: SUM(x)}\nmaterialization:\n  mode: relaxed\n  materialized_views:\n    - {name: b, type: aggregated, dimensions: ['*', d]}\n",
            "MV703",
        ),
        (
            MINIMAL
            + "filter: owner = current_user()\nmeasures:\n  - {name: n, expr: SUM(x)}\nmaterialization:\n  mode: relaxed\n  materialized_views:\n    - {name: b, type: unaggregated}\n",
            "MV704",
        ),
        (
            MINIMAL
            + "parameters:\n  - {name: a, data_type: INT, default: 1}\n  - {name: b, data_type: INT}\nmeasures:\n  - {name: n, expr: SUM(x)}\n",
            "MV801",
        ),
    ],
)
def test_rule_fires(text: str, code: str):
    assert code in codes(text), lint_text(text)


def test_unquoted_on_key_is_read_as_on():
    text = (
        MINIMAL
        + "joins:\n  - name: c\n    source: t.c\n    on: source.id = c.id\nmeasures:\n  - {name: n, expr: COUNT(1)}\n"
    )
    assert codes(text) == []


def test_did_you_mean():
    [d] = lint_text(MINIMAL + "measures:\n  - {name: n, expr: COUNT(1), synonym: [x]}\n")
    assert "did you mean 'synonyms'" in d.message


def test_strings_and_comments_dont_trigger_rules():
    text = (
        MINIMAL
        + "measures:\n  - name: n\n    expr: |\n      COUNT(1) -- not SUM(x) OVER (y)\n  - {name: m, expr: \"MAX(x) || ' OVER (z)'\"}\n"
    )
    assert codes(text) == []


def test_line_numbers_point_at_the_problem():
    text = MINIMAL + "measures:\n  - name: ok\n    expr: COUNT(1)\n  - name: bad\n    expr: price\n"
    [d] = lint_text(text)
    assert (d.code, d.line, d.location) == ("MV302", 7, "measures[1].expr")


def test_parse_error_hint_for_backtick():
    [d] = lint_text(MINIMAL + "measures:\n  - name: n\n    expr: `a b` + 1\n")
    assert d.code == "MV000" and "double quotes" in d.message and d.line == 5


def test_disable():
    assert (
        lint_text(MINIMAL + "measures:\n  - expr: COUNT(1)\n", disabled=frozenset({"MV201"})) == []
    )


def test_examples_report_exactly_the_annotated_mistakes():
    from pathlib import Path

    from metricview_lint import lint_file

    root = Path(__file__).parent.parent / "examples"
    for f in (root / "valid").iterdir():
        assert lint_file(f) == [], f
    bad = root / "invalid" / "common-mistakes.yaml"
    expected = sorted(
        code
        for line in bad.read_text().splitlines()
        for code in __import__("re").findall(r"MV\d{3}", line.split("#", 1)[-1])
        if "#" in line
    )
    assert sorted(d.code for d in lint_file(bad)) == expected
