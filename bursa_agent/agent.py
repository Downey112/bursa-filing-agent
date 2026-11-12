"""The agent: a small LangGraph state machine around the extractors and the guardrail.

    find_pages -> extract -> validate --ok--> compute_ratios -> END
                    ^           |
                    +--retry----+  (LLM, with the guardrail's complaint, at most MAX_ATTEMPTS)
                                |
                                +--give up--> needs_review -> END

Attempt 1 uses the rules extractor. Later attempts use the LLM, and only if one is configured.
Every node is timed into `trace`, which is written to traces/<filing>.jsonl.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from bursa_agent import extract
from bursa_agent.checks import BalanceSheet, check_identity, ratios
from bursa_agent.filings import ROOT, Filing

MAX_ATTEMPTS = 3
TRACE_DIR = ROOT / "traces"


class State(TypedDict, total=False):
    filing: Filing
    llm: Any  # an LLM client, or None to run rules-only
    pages: list[tuple[int, str]]
    attempts: int
    sheet: BalanceSheet | None
    problems: list[str]
    ratios: dict
    status: Literal["ok", "needs_review", "unsupported"]
    trace: list[dict]


def traced(name):
    """Record how long a node took and a one-line note about what it did."""

    def wrap(fn):
        def node(state: State) -> State:
            started = time.perf_counter()
            update = fn(state)
            note = update.pop("_note", "")
            entry = {"node": name, "ms": round(1000 * (time.perf_counter() - started), 1), "note": note}
            return {**update, "trace": state.get("trace", []) + [entry]}

        return node

    return wrap


@traced("find_pages")
def find_pages(state: State) -> State:
    try:
        pages = extract.statement_pages(state["filing"].path)
    except extract.ScannedPDF:
        return {"pages": [], "status": "unsupported", "problems": ["scanned PDF: no text layer"],
                "_note": "scanned"}
    return {"pages": pages, "attempts": 0, "_note": f"pages {[n for n, _ in pages]}"}


@traced("extract")
def extract_node(state: State) -> State:
    attempt = state.get("attempts", 0) + 1
    if attempt == 1:
        sheet = extract.rules_extract(state["pages"])
        return {"sheet": sheet, "attempts": attempt, "_note": "rules " + ("ok" if sheet else "found nothing")}
    feedback = "; ".join(state.get("problems", [])) or None
    sheet = extract.llm_extract(state["pages"], feedback=feedback, client=state["llm"])
    return {"sheet": sheet, "attempts": attempt, "_note": "llm " + ("ok" if sheet else "invalid JSON")}


@traced("validate")
def validate(state: State) -> State:
    sheet = state.get("sheet")
    problems = ["no balance sheet extracted"] if sheet is None else check_identity(sheet)
    return {"problems": problems, "_note": "pass" if not problems else problems[0][:80]}


@traced("compute_ratios")
def compute_ratios(state: State) -> State:
    return {"ratios": ratios(state["sheet"]), "status": "ok"}


@traced("needs_review")
def needs_review(state: State) -> State:
    return {"status": "needs_review", "_note": f"gave up after {state.get('attempts', 0)} attempt(s)"}


def after_find(state: State) -> str:
    return END if state.get("status") == "unsupported" or not state["pages"] else "extract"


def after_validate(state: State) -> str:
    if not state["problems"]:
        return "compute_ratios"
    if state.get("llm") is not None and state["attempts"] < MAX_ATTEMPTS:
        return "extract"
    return "needs_review"


def build_graph():
    graph = StateGraph(State)
    graph.add_node("find_pages", find_pages)
    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate)
    graph.add_node("compute_ratios", compute_ratios)
    graph.add_node("needs_review", needs_review)
    graph.add_edge(START, "find_pages")
    graph.add_conditional_edges("find_pages", after_find, ["extract", END])
    graph.add_edge("extract", "validate")
    graph.add_conditional_edges("validate", after_validate, ["compute_ratios", "extract", "needs_review"])
    graph.add_edge("compute_ratios", END)
    graph.add_edge("needs_review", END)
    return graph.compile()


def default_llm():
    """A Groq client if GROQ_API_KEY is set, else None (rules-only mode)."""
    if not os.environ.get("GROQ_API_KEY"):
        return None
    from groq import Groq

    return Groq()


def run(filing: Filing, llm: Any = "default", save_trace: bool = True) -> dict:
    """Run the agent on one filing and return a JSON-ready result."""
    llm = default_llm() if llm == "default" else llm
    final = build_graph().invoke({"filing": filing, "llm": llm, "trace": []})
    if not final.get("pages") and final.get("status") != "unsupported":
        final["status"], final["problems"] = "needs_review", ["balance sheet page not found"]
    sheet = final.get("sheet")
    result = {
        "filing": filing.id,
        "company": filing.company,
        "period_end": filing.period_end,
        "status": final.get("status", "needs_review"),
        "balance_sheet": sheet.model_dump() if sheet and final.get("status") == "ok" else None,
        "ratios": final.get("ratios"),
        "problems": final.get("problems", []),
        "attempts": final.get("attempts", 0),
        "trace": final["trace"],
    }
    if save_trace:
        TRACE_DIR.mkdir(exist_ok=True)
        Path(TRACE_DIR / f"{filing.id}.jsonl").write_text(
            "\n".join(json.dumps(t) for t in final["trace"]) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    import sys

    from bursa_agent.filings import download, load_registry

    registry = load_registry()
    for filing_id in sys.argv[1:] or registry:
        download(registry[filing_id])
        out = run(registry[filing_id])
        print(json.dumps({k: v for k, v in out.items() if k != "trace"}, indent=2))
