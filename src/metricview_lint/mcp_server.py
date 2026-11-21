"""MCP server so coding agents (Claude Code, etc.) can validate metric views while writing them.

Run with `metricview-lint --mcp` (requires the `mcp` extra).
"""

from __future__ import annotations

from typing import Any

from . import __version__
from .core import RULES, lint_file, lint_text

INSTRUCTIONS = (
    "Validate Databricks Unity Catalog metric view YAML offline. Call lint_metric_view on any "
    "metric view YAML (or CREATE VIEW ... WITH METRICS SQL) you write or edit, fix every error, "
    "and re-run until it returns no errors before presenting it."
)


def _server():
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised manually
        raise SystemExit(
            "The MCP server needs the 'mcp' extra: pip install 'metricview-lint[mcp]'"
        ) from exc

    from . import rules  # noqa: F401

    server = MCPServer("metricview-lint", instructions=INSTRUCTIONS, version=__version__)

    @server.tool()
    def lint_metric_view(definition: str) -> list[dict[str, Any]]:
        """Lint a metric view definition.

        Args:
            definition: The metric view YAML body, or a full SQL script containing
                `CREATE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$`.

        Returns:
            A list of diagnostics (code, severity, message, line, path). Empty means clean.
        """
        from .loader import extract_from_sql

        snippets = extract_from_sql(definition)
        if not snippets:
            return [d.to_dict() for d in lint_text(definition)]
        out = []
        for s in snippets:
            out += [d.to_dict() for d in lint_text(s.text, line_offset=s.line_offset)]
        return out

    @server.tool()
    def lint_metric_view_file(path: str) -> list[dict[str, Any]]:
        """Lint a metric view file on disk (.yaml, .yml or .sql).

        Args:
            path: Path to the file.
        """
        return [d.to_dict() for d in lint_file(path)]

    @server.tool()
    def list_rules() -> list[dict[str, str]]:
        """List every rule the linter checks, with its code, severity and summary."""
        return [
            {"code": r.code, "severity": r.severity.value, "summary": r.summary}
            for r in sorted(RULES.values(), key=lambda r: r.code)
        ]

    return server


def run() -> None:
    _server().run()
