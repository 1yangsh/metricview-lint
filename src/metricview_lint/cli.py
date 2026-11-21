"""Command line interface: `metricview-lint [PATH ...]`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from . import __version__
from .core import RULES, Diagnostic, Severity, lint_file, lint_text

_SUFFIXES = {".yaml", ".yml", ".sql"}


def _iter_files(paths: Iterable[str]) -> Iterable[Path]:
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            yield from sorted(f for f in p.rglob("*") if f.suffix.lower() in _SUFFIXES)
        else:
            yield p


def _format_text(d: Diagnostic) -> str:
    where = f"{d.file or '<stdin>'}:{d.line or 0}"
    loc = f" ({d.location})" if d.location else ""
    return f"{where}: {d.severity.value} {d.code} {d.message}{loc}"


def _format_github(d: Diagnostic) -> str:
    # https://docs.github.com/actions/reference/workflow-commands-for-github-actions
    level = "error" if d.severity is Severity.ERROR else "warning"
    msg = d.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::{level} file={d.file or ''},line={d.line or 1},title={d.code}::{msg}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metricview-lint",
        description="Lint Databricks Unity Catalog metric view YAML before you deploy it.",
    )
    parser.add_argument(
        "paths", nargs="*", help="files or directories (.yaml, .yml, .sql); '-' reads stdin"
    )
    parser.add_argument("--format", choices=["text", "json", "github"], default="text")
    parser.add_argument(
        "--disable", default="", help="comma-separated rule codes to skip, e.g. MV105,MV201"
    )
    parser.add_argument("--warnings-as-errors", action="store_true", help="exit 1 on warnings too")
    parser.add_argument(
        "--all-yaml",
        action="store_true",
        help="lint every YAML file; by default YAML without source/fields/measures is skipped",
    )
    parser.add_argument(
        "--print-schema",
        action="store_true",
        help="print the JSON Schema for editor autocompletion and exit",
    )
    parser.add_argument("--list-rules", action="store_true", help="print all rules and exit")
    parser.add_argument("--mcp", action="store_true", help="run as an MCP server over stdio")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.mcp:
        from .mcp_server import run

        run()
        return 0

    if args.print_schema:
        from .schema import dumps

        sys.stdout.write(dumps())
        return 0

    if args.list_rules:
        from . import rules  # noqa: F401

        for r in sorted(RULES.values(), key=lambda r: r.code):
            print(f"{r.code}  {r.severity.value:<7}  {r.summary}")
        return 0

    if not args.paths:
        _build_parser().print_usage(sys.stderr)
        return 2

    disabled = frozenset(c.strip().upper() for c in args.disable.split(",") if c.strip())
    diags: list[Diagnostic] = []
    for raw in args.paths:
        if raw == "-":
            diags += lint_text(sys.stdin.read(), disabled=disabled)
            continue
        for f in _iter_files([raw]):
            try:
                diags += lint_file(f, disabled, skip_non_metric_views=not args.all_yaml)
            except OSError as exc:
                print(f"{f}: cannot read: {exc.strerror}", file=sys.stderr)
                return 2

    if args.format == "json":
        print(json.dumps([d.to_dict() for d in diags], indent=2))
    else:
        fmt = _format_github if args.format == "github" else _format_text
        for d in diags:
            print(fmt(d))

    failing = [d for d in diags if d.severity is Severity.ERROR or args.warnings_as_errors]
    if args.format == "text" and diags:
        errors = sum(d.severity is Severity.ERROR for d in diags)
        print(f"\n{errors} error(s), {len(diags) - errors} warning(s)", file=sys.stderr)
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
