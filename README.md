# metricview-lint

<!-- mcp-name: io.github.1yangsh/metricview-lint -->

Catch mistakes in **Databricks Unity Catalog metric view** definitions before you deploy them, in your editor, in CI, or while a coding agent like Claude Code writes them.

```text
$ metricview-lint examples/invalid
examples/invalid/common-mistakes.yaml:8: error MV406 join 'customer' 'on' compares customer_id = customer_id; unqualified columns resolve to the joined table, so this is always true. Write source.customer_id = customer.customer_id or use 'using: [customer_id]'
examples/invalid/common-mistakes.yaml:20: error MV302 measure 'margin' has no aggregate function (SUM, COUNT, AVG, MEASURE, ...); a non-aggregated expression belongs in 'fields'.
examples/invalid/common-mistakes.yaml:22: error MV305 MEASURE(orders) references a measure defined later; move 'orders' above 'aov'
examples/invalid/common-mistakes.yaml:31: error MV502 measure 'revenue_7d': invalid range 'last 7 days'; expected current, cumulative, all, or 'trailing|leading <n> [day|month|year] [inclusive|exclusive]'
...
```

Metric views are defined in YAML inside `CREATE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$`. Today the only way to find a mistake is to run the statement against a warehouse and read the error. Some mistakes don't error at all: an unqualified `on: id = id` join condition is always true. metricview-lint checks the definition **offline, in milliseconds, with no Databricks connection or credentials**.

## Install

```bash
uvx metricview-lint path/to/metric_views     # run without installing
pip install metricview-lint                   # or install it
```

It reads `.yaml` / `.yml` metric view bodies and `.sql` files containing `CREATE VIEW ... WITH METRICS` or `ALTER VIEW ... AS $$`. Line numbers always point into the original file. YAML files without a top-level `source`, `fields` or `measures` key are skipped, so you can point it at a whole repo.

```text
metricview-lint [PATH ...] [--format text|json|github] [--disable MV201,MV303]
                [--warnings-as-errors] [--all-yaml] [--list-rules] [--mcp]
```

It exits with 1 if there are errors (or warnings, with `--warnings-as-errors`), and 0 otherwise.

## Use it from Claude Code (MCP)

metricview-lint ships an MCP server. With it, an agent validates every metric view it writes and fixes the errors before showing you the result.

```bash
claude mcp add metricview-lint -- uvx --from 'metricview-lint[mcp]' metricview-lint --mcp
```

Tools exposed:

- `lint_metric_view(definition)` takes YAML or a full `CREATE VIEW ... WITH METRICS` statement and returns the diagnostics.
- `lint_metric_view_file(path)` lints a file on disk.
- `list_rules()` returns every rule with its code, severity and summary.

The same command works in any MCP client (Claude Desktop, Cursor, ...).

## Editor autocompletion (JSON Schema)

Name your files `*.metric_view.yaml` (or `*.metric-view.yaml`). VS Code (with the Red Hat YAML extension), JetBrains IDEs and Neovim then pick up the schema from [SchemaStore](https://www.schemastore.org) and give you key completion, hover docs and type checks while you type. For any other file name, add this first line:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/1yangsh/metricview-lint/main/schemas/databricks-metric-view.json
```

The schema is lenient on purpose: it helps you write the file, and `metricview-lint` checks it. `metricview-lint --print-schema` prints it.

## pre-commit

```yaml
repos:
  - repo: https://github.com/1yangsh/metricview-lint
    rev: v0.1.0
    hooks:
      - id: metricview-lint
```

## GitHub Actions

This annotates the pull request diff at the offending lines.

```yaml
- uses: actions/checkout@v4
- uses: 1yangsh/metricview-lint@v0.1.0
  with:
    paths: metric_views/
    args: --warnings-as-errors
```

## Rules

Errors are things Databricks rejects, or that silently compute the wrong number. Warnings are likely mistakes that are valid in some setups. Run `metricview-lint --list-rules` for the live list, and disable any rule with `--disable`.

| Code | Severity | Checks |
|---|---|---|
| `MV000` | error | the YAML parses (with hints for backticks, `: ` in expressions, unquoted `*`) |
| `MV001` | error | no duplicate keys (YAML silently keeps the last one) |
| `MV100` | error | the document must be a YAML mapping |
| `MV101` | error | `version` is required |
| `MV102` | error | `version` must be a supported spec version |
| `MV103` | error | `source` is required |
| `MV104` | error | at least one of `fields` or `measures` is required |
| `MV105` | error | `fields` and `dimensions` are synonyms; use only one |
| `MV106` | warning | unknown key (likely a typo) |
| `MV107` | error | value has the wrong type |
| `MV108` | error | feature requires spec version 1.1 |
| `MV109` | error | `window` is only allowed on measures |
| `MV201` | warning | field/measure has no `name` (derived names need DBR 19+) |
| `MV202` | error | `name` must not be empty |
| `MV203` | error | names must be unique across fields and measures (case-insensitive) |
| `MV204` | error | wildcard expressions can't have a name or metadata |
| `MV205` | error | `display_name`/`synonyms` length limits |
| `MV301` | error | fields and measures need an `expr` |
| `MV302` | error | measure `expr` must use an aggregate function |
| `MV303` | warning | field `expr` should not aggregate |
| `MV304` | error | window functions (OVER) are not allowed; use a `window` measure |
| `MV305` | error | MEASURE() must reference an earlier measure |
| `MV306` | warning | aggregating a measure by name; use MEASURE(name) |
| `MV307` | error | a window measure can't reference another window measure |
| `MV308` | error | fields can't reference columns of a one_to_many join |
| `MV401` | error | joins need `name` and `source` |
| `MV402` | error | joins need exactly one of `on` or `using` |
| `MV403` | error | join names must be unique among siblings |
| `MV404` | error | `cardinality` must be many_to_one or one_to_many |
| `MV405` | error | a join subtree can't mix cardinalities |
| `MV406` | error | `on` compares an unqualified column with itself |
| `MV501` | error | `window` must be a list of specs with `order` and `range` |
| `MV502` | error | window `range` syntax |
| `MV503` | error | window `order` must name a field defined in this view |
| `MV504` | error | window `semiadditive` must be first or last |
| `MV505` | error | window `offset` syntax |
| `MV506` | error | window size parameters must be declared and integral |
| `MV601` | error | `format` spec is invalid |
| `MV701` | error | materialization `mode` and `materialized_views` are required |
| `MV702` | error | materialized view entries need a valid name and type |
| `MV703` | error | materialized views must reference existing fields and measures |
| `MV704` | error | materialization is incompatible with this definition |
| `MV801` | error | parameters need `name` and `data_type`; defaults come last |

The rules follow the [metric view YAML reference](https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference) for spec versions `0.1` and `1.1`, including joins (`many_to_one` / `one_to_many`, snowflake nesting), window measures, semantic metadata (`display_name`, `format`, `synonyms`), parameters and materialization. Every example in the Databricks docs lints clean, apart from intentional fragments.

## What it can't check

metricview-lint works offline, so it can't check anything that needs the catalog:

- whether tables and columns exist
- column types (e.g. that a window `order` is a date)
- row-level security that blocks materialization

Treat it as a fast first gate, and keep `CREATE VIEW` on a dev warehouse as the final check.

## Development

```bash
uv sync --all-extras
uv run pytest && uv run ruff check . && uv run pyright
```

New rules live in `src/metricview_lint/rules/`. Each rule is a generator registered with `@rule(code, severity, summary)` that yields `(message, path)`. Add a failing case to `tests/test_rules.py` first.

## License

Apache-2.0. This is an independent project, not affiliated with or endorsed by Databricks.
