"""Find the balance sheet in a quarterly report and read its totals.

Two extractors with the same output:
- `rules_extract`: regular expressions over the page text. Free, fast, exact when it works.
- `llm_extract`: asks an LLM to fill a JSON schema. Used only when the rules fail or the
  guardrail rejects the rules' result.
Neither is trusted until `checks.check_identity` passes.
"""

import json
import os
import re
from pathlib import Path

import pdfplumber
from pydantic import ValidationError

from bursa_agent.checks import BalanceSheet

MAX_PAGES = 15  # the balance sheet is always near the front of a quarterly report
LABELS = {
    "total_assets": ["total assets"],
    "total_liabilities": ["total liabilities"],
    "total_equity": ["total equity"],
    "equity_and_liabilities": ["total equity and liabilities", "total liabilities and equity"],
    "current_assets": ["total current assets"],
    "current_liabilities": ["total current liabilities"],
}
# an amount: 1,234,567  |  105,257.9  |  (1,234)  -- with digit groups that pdfplumber sometimes splits
AMOUNT = r"\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\(?\d+\.\d+\)?|\(?\d{3,}\)?"
NOTE = r"(?:[A-Z]{1,2}\d{1,2}|\d{1,2})"  # note references like "A7" or "12" sitting before the amount


class ScannedPDF(Exception):
    """The PDF has no text layer (a scan), so text extraction cannot work."""


def statement_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """The first page titled 'financial position' that mentions total assets, plus the next page
    (most reports carry equity and liabilities over to the following page)."""
    with pdfplumber.open(pdf_path) as pdf:
        texts = [(i, p.extract_text() or "") for i, p in enumerate(pdf.pages[:MAX_PAGES], start=1)]
    if not any(t.strip() for _, t in texts):
        raise ScannedPDF(f"{pdf_path.name} has no text layer")
    best, best_score = None, 0
    for idx, (_, text) in enumerate(texts):
        score = page_score(text)
        if score > best_score:
            best, best_score = idx, score
    return [] if best is None else texts[best: best + 2]


def page_score(text: str) -> int:
    """How likely a page is to be the statement itself (not the contents page or a note)."""
    score = 0
    for line in text.splitlines():
        # a title line, but not a table-of-contents entry like "... Financial Position 3 - 4"
        if (re.search(r"statements?\s+of\s+financial\s+position", line, re.I)
                and not re.search(r"\s\d{1,3}(\s*-\s*\d{1,3})?\s*$", line)):
            score = max(score, 1)
    if score and find_line_amount(text, LABELS["total_assets"]) is not None:
        score += 2
    return score


def parse_amount(token: str) -> float:
    """'(1,234.5)' -> -1234.5"""
    negative = token.startswith("(")
    value = float(token.strip("()").replace(",", ""))
    return -value if negative else value


def detect_unit(text: str) -> str:
    if re.search(r"RM\W{0,2}000|RM\s*thousand|in thousands", text, re.I):
        return "RM thousand"
    if re.search(r"RM\W{0,2}mil|RM\s*million|in millions", text, re.I):
        return "RM million"
    return "unknown"


def find_line_amount(text: str, labels: list[str]) -> float | None:
    """The current-period amount on the first line that starts with one of `labels`.

    The label must be followed directly by an amount (optionally after a note reference), so
    'Total equity' does not match 'Total equity attributable to owners'.
    """
    for label in labels:
        pattern = rf"^\s*{label}\s+(?:{NOTE}\s+)?({AMOUNT})"
        match = re.search(pattern, text, re.I | re.M)
        if match:
            return parse_amount(match.group(1))
    return None


def rules_extract(pages: list[tuple[int, str]]) -> BalanceSheet | None:
    """Read the totals with regular expressions. None if the essential lines are missing."""
    text = "\n".join(t for _, t in pages)
    found = {field: find_line_amount(text, labels) for field, labels in LABELS.items()}
    if found["total_assets"] is None or found["total_equity"] is None:
        return None
    derived = False
    if found["total_liabilities"] is None:
        if found["equity_and_liabilities"] is None:
            return None
        found["total_liabilities"] = found["equity_and_liabilities"] - found["total_equity"]
        derived = True
    try:
        return BalanceSheet(
            unit=detect_unit(text),
            total_assets=found["total_assets"],
            total_liabilities=found["total_liabilities"],
            total_equity=found["total_equity"],
            current_assets=found["current_assets"],
            current_liabilities=found["current_liabilities"],
            source="rules",
            liabilities_derived=derived,
            pages=[n for n, _ in pages],
        )
    except ValidationError:
        return None


LLM_PROMPT = """You read Malaysian quarterly financial reports. From the statement of financial \
position below, return JSON with these keys for the CURRENT period (the first number column, \
not the comparative year-end column):
unit ("RM", "RM thousand" or "RM million"), total_assets, total_liabilities, total_equity, \
current_assets, current_liabilities.
Copy numbers exactly as printed, without commas; use null for a figure that is not shown. \
If total liabilities is not printed, add up the liability lines. Return only the JSON object."""


def llm_extract(pages: list[tuple[int, str]], feedback: str | None = None, client=None,
                model: str = "openai/gpt-oss-120b") -> BalanceSheet | None:
    """Ask the LLM to fill the schema. `feedback` carries the guardrail's complaint on a retry."""
    if client is None:
        from groq import Groq

        client = Groq(api_key=os.environ["GROQ_API_KEY"])
    text = "\n\n".join(f"--- page {n} ---\n{t}" for n, t in pages)
    user = f"{text}\n\n"
    if feedback:
        user += f"Your previous answer failed this check: {feedback}\nRead the statement again.\n"
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": LLM_PROMPT}, {"role": "user", "content": user}],
    )
    try:
        data = json.loads(response.choices[0].message.content or "{}")
        return BalanceSheet(**{k: v for k, v in data.items() if k in BalanceSheet.model_fields},
                            source="llm", pages=[n for n, _ in pages])
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None
