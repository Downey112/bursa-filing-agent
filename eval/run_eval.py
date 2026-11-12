"""Run the agent on every registry filing and compare with eval/expected.yaml.

    python eval/run_eval.py            # rules-only (no key needed); writes EVAL.md
    GROQ_API_KEY=... python eval/run_eval.py --llm    # also lets the LLM fallback try

Scoring per filing:
  correct      status ok and all three totals equal the hand-checked values (within 0.01%)
  safe_refusal status needs_review / unsupported where that is expected
  WRONG_OK     status ok but numbers differ from the hand-checked ones (the failure that matters)
  missed       expected ok but the agent did not get there
"""

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bursa_agent import agent, extract  # noqa: E402
from bursa_agent.filings import download, load_registry  # noqa: E402

FIELDS = ("total_assets", "total_liabilities", "total_equity")


def fixture_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Stand-in for extract.statement_pages that reads the saved text (see eval/snapshot.py)."""
    data = json.loads((ROOT / "eval" / "fixtures" / f"{Path(pdf_path).stem}.json").read_text(encoding="utf-8"))
    if data["scanned"]:
        raise extract.ScannedPDF(f"{Path(pdf_path).name} has no text layer")
    return [tuple(p) for p in data["pages"]]


def score(result: dict, expected: dict) -> str:
    if result["status"] == "ok":
        sheet = result["balance_sheet"]
        if all(f in expected for f in FIELDS) and all(
                abs(sheet[f] - expected[f]) <= 1e-4 * abs(expected[f]) for f in FIELDS):
            return "correct"
        return "WRONG_OK"
    return "safe_refusal" if expected["status"] != "ok" else "missed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="allow the LLM fallback (needs GROQ_API_KEY)")
    parser.add_argument("--offline", action="store_true",
                        help="read statement pages from eval/fixtures instead of the PDFs (used in CI)")
    args = parser.parse_args()

    if args.offline:
        extract.statement_pages = fixture_pages
    expected = yaml.safe_load((ROOT / "eval" / "expected.yaml").read_text(encoding="utf-8"))
    registry = load_registry()
    rows = []
    for filing_id, exp in expected.items():
        if not args.offline:
            download(registry[filing_id])
        started = time.perf_counter()
        result = agent.run(registry[filing_id], llm="default" if args.llm else None)
        rows.append((filing_id, exp["status"], result, score(result, exp), time.perf_counter() - started))

    counts = {k: sum(r[3] == k for r in rows) for k in ("correct", "safe_refusal", "missed", "WRONG_OK")}
    lines = [
        "# Extraction eval",
        "",
        f"{len(rows)} filings, hand-checked totals in `eval/expected.yaml`. Mode: "
        f"{'rules + LLM fallback' if args.llm else 'rules only (no LLM)'}. Run: `python eval/run_eval.py`.",
        "",
        f"**correct {counts['correct']} | safe refusal {counts['safe_refusal']} | missed {counts['missed']} | "
        f"wrong-but-reported-ok {counts['WRONG_OK']}**",
        "",
        "| Filing | Expected | Got | Attempts | Score | Debt/equity | Seconds |",
        "|---|---|---|---|---|---|---|",
    ]
    for filing_id, exp_status, result, verdict, secs in rows:
        de = (result["ratios"] or {}).get("debt_to_equity")
        lines.append(f"| {filing_id} | {exp_status} | {result['status']} | {result['attempts']} | {verdict} | "
                     f"{de if de is not None else '-'} | {secs:.1f} |")
    report = "\n".join(lines) + "\n"
    (ROOT / "EVAL.md").write_text(report, encoding="utf-8")
    print(report)
    if counts["WRONG_OK"]:
        sys.exit("FAIL: the agent reported wrong numbers as ok")


if __name__ == "__main__":
    main()
