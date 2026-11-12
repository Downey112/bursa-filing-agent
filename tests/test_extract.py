import pytest

from bursa_agent.extract import detect_unit, find_line_amount, page_score, parse_amount, rules_extract

STATEMENT = """CONDENSED CONSOLIDATED STATEMENT OF FINANCIAL POSITION
AS AT 30 JUNE 2026
RM'000 RM'000
Total current assets 1,500,000 1,400,000
TOTAL ASSETS A7 4,243,476 3,921,208
Total equity attributable to owners of the Company 1,700,000 1,900,000
TOTAL EQUITY 1,831,215 2,016,543
Total current liabilities 900,000 800,000
TOTAL LIABILITIES 2,412,261 1,904,665
TOTAL EQUITY AND LIABILITIES 4,243,476 3,921,208
"""


def test_reads_current_period_not_comparative():
    assert find_line_amount(STATEMENT, ["total assets"]) == 4_243_476


def test_total_equity_does_not_match_attributable_line():
    assert find_line_amount(STATEMENT, ["total equity"]) == 1_831_215


def test_skips_note_reference_and_split_comparative_digits():
    assert find_line_amount("TOTAL ASSETS 12 36,901,070 3 0,269,060", ["total assets"]) == 36_901_070


@pytest.mark.parametrize("token,value", [("1,234", 1234), ("(1,234.5)", -1234.5), ("105,257.9", 105257.9)])
def test_parse_amount(token, value):
    assert parse_amount(token) == value


@pytest.mark.parametrize("text,unit", [("RM'000", "RM thousand"), ("RM’000", "RM thousand"),
                                       ("Amounts in RM million", "RM million"), ("RM'mil", "RM million"),
                                       ("nothing here", "unknown")])
def test_detect_unit(text, unit):
    assert detect_unit(text) == unit


def test_rules_extract_full_statement():
    bs = rules_extract([(3, STATEMENT)])
    assert (bs.total_assets, bs.total_liabilities, bs.total_equity) == (4_243_476, 2_412_261, 1_831_215)
    assert (bs.current_assets, bs.current_liabilities, bs.unit) == (1_500_000, 900_000, "RM thousand")
    assert bs.source == "rules" and not bs.liabilities_derived


def test_liabilities_derived_when_only_grand_total_printed():
    text = STATEMENT.replace("TOTAL LIABILITIES 2,412,261 1,904,665\n", "")
    bs = rules_extract([(3, text)])
    assert bs.total_liabilities == 2_412_261 and bs.liabilities_derived


def test_returns_none_when_totals_missing():
    assert rules_extract([(3, "STATEMENT OF FINANCIAL POSITION\nO T A L A S S E T S\n")]) is None


def test_contents_page_scores_below_the_statement():
    contents = "Condensed Consolidated Statement of Financial Position 3 - 4"
    assert page_score(contents) == 0
    assert page_score(STATEMENT) == 3
