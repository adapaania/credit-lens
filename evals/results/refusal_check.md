# Cross-company filing-scope check (Fix 1)

Tests whether the agent correctly declines a company-specific financial question when the question is about a *different* company than the one covered by the currently selected `filing_id` — instead of answering from general knowledge and attaching a fabricated or mismatched citation.

This is a behavioral check on the agent's system prompt, not a retrieval-quality check: `retrieve_filing` is already filtered by `filing_id` at the Qdrant level, so the leak this catches is purely on the LLM side (the model answering a cross-company question from its own training data instead of declining).

## Before Fix 1 (original `AGENT_SYSTEM_PROMPT`)

**Refusal-correct: 0/3.** Every probe leaked a real, correctly-remembered figure for the *other* company, each with page/section citations that were retrieved from the *selected* (wrong) company's filing — a citation-integrity failure, not just a plain hallucination.

| Filing selected | Asked about | Answer |
|---|---|---|
| Boeing | Lockheed Martin net sales | "Lockheed Martin's total net sales in fiscal year 2024 were $71.0 billion (page 59, Net Sales section; page 122, Overview; page 95, Years Ended December 31 section)." |
| Lockheed Martin | RTX total debt | "RTX's total long-term debt... was approximately $43.5 billion... (page 153, 172)... (page 98)." |
| RTX | Boeing net loss | "Boeing's net loss in fiscal year 2024 was $11.829 billion (page 40, Other Earnings Items; page 57, Cash Flow Summary; page 73, Consolidated Statements of Comprehensive Income)." |

## After Fix 1

**Refusal-correct: 3/3.** Every probe declined and redirected, with no dollar figure stated for the other company.

| Filing selected | Asked about | Answer |
|---|---|---|
| Boeing | Lockheed Martin net sales | "The selected filing_id is for Boeing's 2024 10-K, which does not cover Lockheed Martin's financial figures. To provide Lockheed Martin's total net sales for fiscal year 2024, you would need to switch the filing selector to lockheed-2024-10k." |
| Lockheed Martin | RTX total debt | "The selected filing_id is lockheed-2024-10k, which covers Lockheed Martin. It does not cover RTX... please switch the filing selector to rtx-2024-10k." |
| RTX | Boeing net loss | "The selected filing_id is for RTX, not Boeing... please switch the filing selector to \"boeing-2024-10k\" and ask again." |

## Regression check

Same-company questions still answer and cite correctly after the fix — verified directly against the agent, not assumed:

> Q: "What was Boeing total revenue and net loss in fiscal 2024?" (filing_id: boeing-2024-10k)
> A: "Boeing's total revenue for fiscal year 2024 was $66.517 billion. The net loss for the same period was $11.829 billion (page 82, Summary of Business Segment Data; page 40, Other Earnings Items)."

## Full per-question detail

`evals/results/refusal_check_before.json`, `evals/results/refusal_check_after.json`.

## Methodology note

`refusal_ok()` ([`evals/refusal_eval.py`](../refusal_eval.py)) is a heuristic, not an exact-match check: it looks for the absence of a `$`-prefixed dollar figure plus the presence of redirect language ("switch", "select", "does not cover", "cannot provide"). It can be fooled by phrasing that avoids both patterns while still leaking, or by declining for the wrong reason. For this specific, narrow before/after comparison (same 3 questions, same code path, only the system prompt changed) it's sufficient evidence; it isn't a general-purpose refusal classifier and shouldn't be read as one.
