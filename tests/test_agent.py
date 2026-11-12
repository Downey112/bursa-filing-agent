"""The agent's control flow, with fake extractors and a fake LLM: no PDFs, no network."""

import json
from types import SimpleNamespace

import pytest

from bursa_agent import agent, extract
from bursa_agent.checks import BalanceSheet
from bursa_agent.filings import Filing

FILING = Filing("x_2Q2026", "Example Berhad", "2026-06-30", "https://example.com/x.pdf")
GOOD = BalanceSheet(total_assets=100, total_liabilities=60, total_equity=40)
BAD = BalanceSheet(total_assets=100, total_liabilities=60, total_equity=45)  # breaks the identity


class FakeLLM:
    """Returns the queued JSON replies in order and records the prompts it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, messages, **kwargs):
        self.prompts.append(messages[-1]["content"])
        content = json.dumps(self.replies.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture(autouse=True)
def one_page(monkeypatch):
    monkeypatch.setattr(extract, "statement_pages", lambda path: [(3, "statement text")])


def test_rules_pass_first_time(monkeypatch):
    monkeypatch.setattr(extract, "rules_extract", lambda pages: GOOD)
    out = agent.run(FILING, llm=None, save_trace=False)
    assert out["status"] == "ok" and out["attempts"] == 1
    assert out["ratios"]["debt_to_equity"] == 1.5
    assert [t["node"] for t in out["trace"]] == ["find_pages", "extract", "validate", "compute_ratios"]


def test_bad_rules_result_without_llm_needs_review(monkeypatch):
    monkeypatch.setattr(extract, "rules_extract", lambda pages: BAD)
    out = agent.run(FILING, llm=None, save_trace=False)
    assert out["status"] == "needs_review" and out["balance_sheet"] is None


def test_llm_retry_gets_the_guardrail_complaint(monkeypatch):
    monkeypatch.setattr(extract, "rules_extract", lambda pages: BAD)
    llm = FakeLLM({"total_assets": 100, "total_liabilities": 60, "total_equity": 40, "unit": "RM million"})
    out = agent.run(FILING, llm=llm, save_trace=False)
    assert out["status"] == "ok" and out["attempts"] == 2
    assert out["balance_sheet"]["source"] == "llm"
    assert "previous answer failed this check" in llm.prompts[0] and "gap" in llm.prompts[0]


def test_stops_after_max_attempts(monkeypatch):
    monkeypatch.setattr(extract, "rules_extract", lambda pages: None)
    wrong = {"total_assets": 100, "total_liabilities": 10, "total_equity": 10}
    llm = FakeLLM(wrong, wrong, wrong, wrong)
    out = agent.run(FILING, llm=llm, save_trace=False)
    assert out["status"] == "needs_review"
    assert out["attempts"] == agent.MAX_ATTEMPTS and len(llm.prompts) == agent.MAX_ATTEMPTS - 1


def test_scanned_pdf_is_unsupported(monkeypatch):
    def scanned(path):
        raise extract.ScannedPDF("no text")

    monkeypatch.setattr(extract, "statement_pages", scanned)
    out = agent.run(FILING, llm=None, save_trace=False)
    assert out["status"] == "unsupported" and out["attempts"] == 0
