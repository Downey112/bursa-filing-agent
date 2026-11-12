"""MCP server: lets Claude Desktop, Claude Code or any MCP client use the agent's tools.

Register with Claude Code:
    claude mcp add bursa -- python -m bursa_agent.server

Tools are read-only: they download public reports and compute numbers; nothing is written
anywhere except the local PDF cache and traces.
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from bursa_agent import agent
from bursa_agent.checks import BalanceSheet, check_identity, ratios
from bursa_agent.filings import download, load_registry

mcp = MCPServer("bursa-filing-agent")


@mcp.tool()
def list_filings() -> list[dict]:
    """List the quarterly reports this server knows about (id, company, period end)."""
    return [{"id": f.id, "company": f.company, "period_end": f.period_end} for f in load_registry().values()]


@mcp.tool()
def analyse_filing(filing_id: str) -> dict:
    """Extract the balance sheet of one filing, check it, and compute ratios.

    status is "ok" (numbers passed the assets = liabilities + equity check), "needs_review"
    (could not get numbers that pass) or "unsupported" (scanned PDF). Only trust figures when
    status is "ok".
    """
    registry = load_registry()
    if filing_id not in registry:
        raise ToolError(f"unknown filing {filing_id!r}; call list_filings for valid ids")
    download(registry[filing_id])
    result = agent.run(registry[filing_id])
    result.pop("trace")
    return result


@mcp.tool()
def compute_ratios(total_assets: float, total_liabilities: float, total_equity: float,
                   current_assets: float | None = None, current_liabilities: float | None = None) -> dict:
    """Check a balance sheet you already have and compute its ratios.

    Returns the ratios plus any problems found by the accounting-identity check; if problems is
    not empty, the inputs are inconsistent and the ratios should not be used.
    """
    try:
        sheet = BalanceSheet(total_assets=total_assets, total_liabilities=total_liabilities,
                             total_equity=total_equity, current_assets=current_assets,
                             current_liabilities=current_liabilities)
    except ValueError as exc:
        raise ToolError(f"invalid balance sheet: {exc}") from exc
    return {"problems": check_identity(sheet), "ratios": ratios(sheet)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
