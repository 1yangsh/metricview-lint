from __future__ import annotations

import sys

import anyio
import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402


async def _call(tool: str, args: dict):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "metricview_lint.cli", "--mcp"]
    )
    async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
        await session.initialize()
        names = {t.name for t in (await session.list_tools()).tools}
        return names, await session.call_tool(tool, args)


def test_mcp_lint_tool():
    sql = "CREATE VIEW v WITH METRICS LANGUAGE YAML AS $$\nversion: 1.1\nsource: t\nmeasures:\n  - {name: n, expr: price}\n$$"
    names, res = anyio.run(_call, "lint_metric_view", {"definition": sql})
    assert names == {"lint_metric_view", "lint_metric_view_file", "list_rules"}
    [diag] = res.structured_content["result"]
    assert (diag["code"], diag["line"]) == ("MV302", 5)
