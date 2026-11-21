# Changelog

## 0.1.1 (2026-11-22)

- JSON Schema for editor autocompletion (`schemas/databricks-metric-view.json`, `--print-schema`), submitted to SchemaStore for `*.metric_view.yaml`.
- MCP Registry metadata (`server.json`).

## 0.1.0 (2026-11-22)

- First release: 43 rules covering structure, names, expressions, joins, window measures, `format` metadata, materialization and parameters.
- `.sql` support for `CREATE VIEW ... WITH METRICS` and `ALTER VIEW ... AS $$`.
- Output formats: `text`, `json`, `github` (PR annotations).
- MCP server (`--mcp`) for Claude Code and other MCP clients.
- pre-commit hook and GitHub Action.
