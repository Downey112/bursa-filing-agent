"""The balance-sheet record, the guardrail that decides whether to trust it, and the ratios.

Ratios are computed here in plain Python, never by the LLM: models are unreliable at arithmetic,
and a ratio is only as good as the numbers it divides.
"""

from typing import Literal

from pydantic import BaseModel, Field

TOLERANCE = 0.005  # 0.5% of total assets: allows for rounding in "RM million" statements


class BalanceSheet(BaseModel):
    """Headline figures from a statement of financial position, in the statement's own unit."""

    unit: Literal["RM", "RM thousand", "RM million", "unknown"] = "unknown"
    total_assets: float = Field(gt=0)
    total_liabilities: float = Field(ge=0)
    total_equity: float  # can be negative for a company in deficit
    current_assets: float | None = None
    current_liabilities: float | None = None
    source: Literal["rules", "llm"] = "rules"
    liabilities_derived: bool = False  # true when computed as (equity + liabilities) - equity
    pages: list[int] = Field(default_factory=list)


def check_identity(bs: BalanceSheet, tolerance: float = TOLERANCE) -> list[str]:
    """Problems that make the extraction untrustworthy. An empty list means it passed.

    Total assets must equal total liabilities + total equity (to within rounding). A model that
    misreads a column, picks last year's figure or drops a digit almost always breaks this.
    """
    problems = []
    gap = bs.total_assets - (bs.total_liabilities + bs.total_equity)
    if abs(gap) > tolerance * bs.total_assets:
        problems.append(
            f"assets {bs.total_assets:,.1f} != liabilities {bs.total_liabilities:,.1f} + equity "
            f"{bs.total_equity:,.1f} (gap {gap:,.1f}, {abs(gap) / bs.total_assets:.2%} of assets)"
        )
    if bs.current_assets is not None and bs.current_assets > bs.total_assets:
        problems.append("current assets are larger than total assets")
    if bs.current_liabilities is not None and bs.current_liabilities > bs.total_liabilities:
        problems.append("current liabilities are larger than total liabilities")
    return problems


def ratios(bs: BalanceSheet) -> dict[str, float | None]:
    """Standard balance-sheet ratios, rounded for display."""

    def safe(num, den):
        return round(num / den, 3) if num is not None and den not in (None, 0) else None

    return {
        "debt_to_equity": safe(bs.total_liabilities, bs.total_equity),
        "equity_ratio": safe(bs.total_equity, bs.total_assets),
        "current_ratio": safe(bs.current_assets, bs.current_liabilities),
    }
