# Design decisions (be ready to explain these)

## 1. Why rules first and the LLM only as a fallback

8 of 11 real statements print "Total assets / Total liabilities / Total equity" on their own lines.
A regular expression reads those exactly, for free, in milliseconds, and the same way every time.
An LLM is slower, costs quota, and can misread a column. So the LLM is only called when the rules
find nothing (Axiata prints no "Total assets" line) or the guardrail rejects what they found.

## 2. Why the accounting identity is the guardrail

Assets = liabilities + equity holds for every balance sheet. The usual extraction mistakes
(taking last year's column, dropping a digit, reading a subtotal) almost always break it, so it
catches errors without needing the right answer in advance. Tolerance is 0.5% of assets because
statements in RM million are rounded line by line.

**What it cannot catch:** two errors that cancel out, or a correct-looking total from the wrong
company or period. The eval compares against hand-checked values for that reason.

## 3. Why ratios are computed in Python

The LLM's job is reading, not arithmetic. Division in Python is exact and testable; a model can
round, transpose or invent. The tool `compute_ratios` also runs the identity check, so a client
that passes inconsistent numbers is told so.

## 4. Why the agent loop is bounded

The graph allows at most 3 extraction attempts (rules + 2 LLM retries), then ends in
`needs_review`. Without a limit, a model that keeps failing the check would loop and burn quota.
Each retry includes the exact complaint ("assets 100 != liabilities 60 + equity 45 ..."), which
gives the model something specific to fix.

## 5. Hard cases found in real filings

| Filing | Problem | How it is handled |
|---|---|---|
| Gamuda | comparative column prints as `3 0,269,060` | regex takes the first (current) amount only |
| Sime Darby Property | note reference `A7` before the amount | optional note token in the pattern |
| IHH, YTL Power, SD Property | equity and liabilities continue on the next page | read the statement page and the one after |
| YTL Corp | contents page also says "Statement of Financial Position 3 - 4"; real statement extracts as vertically stacked letters | page scoring skips contents lines; garbled page goes to needs_review |
| MR DIY | title says "Statements" (plural) | `statements?` in the title pattern |
| Tenaga | scanned, no text layer | detected and reported as unsupported |

## 6. Why the MCP server

MCP lets any client (Claude Desktop, Claude Code, other agents) discover and call the tools with
typed arguments, without custom glue code. The tools are read-only: they download public reports
and compute numbers.

## 7. What I would add next

OCR (Tesseract) for scanned filings; more line items (cash, borrowings) for liquidity ratios;
quarter-on-quarter comparisons; run the LLM fallback eval with a key and record its accuracy.
