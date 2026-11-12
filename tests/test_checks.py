import pytest
from pydantic import ValidationError

from bursa_agent.checks import BalanceSheet, check_identity, ratios


def sheet(**kw):
    base = dict(total_assets=100.0, total_liabilities=60.0, total_equity=40.0)
    return BalanceSheet(**{**base, **kw})


def test_balanced_sheet_passes():
    assert check_identity(sheet()) == []


def test_rounding_within_half_a_percent_passes():
    assert check_identity(sheet(total_assets=100.4)) == []


def test_comparative_column_mixup_is_caught():
    # equity read from last year's column: the identity breaks
    problems = check_identity(sheet(total_equity=45.0))
    assert len(problems) == 1 and "gap" in problems[0]


def test_current_items_larger_than_totals_are_caught():
    assert check_identity(sheet(current_assets=150.0))
    assert check_identity(sheet(current_liabilities=70.0))


def test_schema_rejects_non_positive_assets():
    with pytest.raises(ValidationError):
        sheet(total_assets=0)


def test_ratios():
    r = ratios(sheet(current_assets=30.0, current_liabilities=20.0))
    assert r == {"debt_to_equity": 1.5, "equity_ratio": 0.4, "current_ratio": 1.5}
    assert ratios(sheet())["current_ratio"] is None
    assert ratios(sheet(total_equity=0.0, total_liabilities=100.0))["debt_to_equity"] is None
