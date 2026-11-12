# Extraction eval

11 filings, hand-checked totals in `eval/expected.yaml`. Mode: rules only (no LLM). Run: `python eval/run_eval.py`.

**correct 8 | safe refusal 3 | missed 0 | wrong-but-reported-ok 0**

| Filing | Expected | Got | Attempts | Score | Debt/equity | Seconds |
|---|---|---|---|---|---|---|
| gamuda_4QFY2026 | ok | ok | 1 | correct | 1.84 | 9.8 |
| genting_2Q2026 | ok | ok | 1 | correct | 1.265 | 8.9 |
| gentingmy_2Q2026 | ok | ok | 1 | correct | 2.206 | 9.0 |
| ihh_2Q2026 | ok | ok | 1 | correct | 0.672 | 4.6 |
| mrdiy_2Q2026 | ok | ok | 1 | correct | 1.317 | 5.3 |
| sdproperty_2Q2026 | ok | ok | 1 | correct | 0.734 | 10.6 |
| simedarby_4QFY2026 | ok | ok | 1 | correct | 0.939 | 11.3 |
| ytlpower_4QFY2026 | ok | ok | 1 | correct | 2.45 | 11.6 |
| ytlcorp_4QFY2026 | needs_review | needs_review | 1 | safe_refusal | - | 6.8 |
| axiata_2Q2026 | needs_review | needs_review | 1 | safe_refusal | - | 6.8 |
| tenaga_2Q2026 | unsupported | unsupported | 0 | safe_refusal | - | 0.1 |
