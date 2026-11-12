import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from bursa_agent import server


def test_tools_are_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {"list_filings", "analyse_filing", "compute_ratios"}


def test_list_filings_reads_registry():
    filings = server.list_filings()
    assert len(filings) >= 10 and {"id", "company", "period_end"} <= set(filings[0])


def test_compute_ratios_flags_inconsistent_input():
    good = server.compute_ratios(100, 60, 40)
    assert good["problems"] == [] and good["ratios"]["equity_ratio"] == 0.4
    assert server.compute_ratios(100, 60, 10)["problems"]


def test_unknown_filing_is_a_tool_error():
    with pytest.raises(ToolError):
        server.analyse_filing("nope")
