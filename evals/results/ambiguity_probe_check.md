# Ambiguity-probe regression check

Targeted regression test for two previously-documented failure modes (README's "Known Limitations"), run directly against the live production agent (`run_agent()` — the real `/chat` code path, hybrid retrieval + query rewrite + Fix 1's system prompt), not the simplified retrieve-then-answer eval pipeline. Scored with the same [`evals/numeric_eval.py`](../numeric_eval.py) matcher used everywhere else in this project (0.5% tolerance, magnitude comparison).

## Probe 1 — consolidated vs. segment revenue (`boeing_revenue_ambiguous`)

Deliberately ambiguous phrasing, no "consolidated" qualifier — Boeing's Global Services segment revenue ($19,954M) was a previously-observed wrong answer under naive dense retrieval for exactly this kind of phrasing.

> Q: "What was Boeing total revenue?"
> A: "Boeing's total revenue for the year ended December 31, 2024, was $66,517 million (page 36, Revenues; page 82, Summary of Business Segment Data; page 161, Note 23 – Segment and Revenue Information)."

`numeric_match(answer, truth_value_millions=66517)` → **True**. Correctly returns the consolidated total, not a segment figure.

## Probe 2 — net loss vs. net loss attributable to shareholders (`boeing_net_loss_ambiguous`)

Deliberately ambiguous phrasing, no "attributable to shareholders" qualifier — the two real, differently-labeled figures are $12M apart ($11,829M consolidated "Net loss" vs. $11,817M "Net loss attributable to Boeing shareholders").

> Q: "What was Boeing net loss?"
> A: "Boeing reported a net loss of $11,829 million for the year ended December 31, 2024. The net loss attributable to Boeing shareholders was $11,817 million (page 40, Other Earnings Items; page 73, Consolidated Statements of Comprehensive Income; page 82, Summary of Business Segment Data)."

`numeric_match(answer, truth_value_millions=-11817)` → **True**. Rather than picking one figure and risking the wrong one, the agent discloses both real, distinctly-labeled numbers with their own citations — arguably the best possible answer to a genuinely ambiguous question.

## Why this wasn't run through the full naive/hybrid/hybrid-rewrite comparison harness

These two questions were added to `data/golden/questions.jsonl` (type `numeric`, reusing the existing verified `truth_id`s) so they're available for a full harness re-run. Two attempts to re-run the full `evals/run_evals.py --pipeline hybrid --rewrite` with the expanded 24-question set both hung during Ragas's internal scoring phase late in the run (network-call stall, not a code issue — confirmed via `ps` showing nearly-zero CPU and a stalled progress bar each time). Given the July 14 deadline, this direct agent-level check was run instead: it's a more representative test of what a user actually experiences (the real `/chat` path, not the eval-only retrieve-then-answer function) and is independently scored with the project's own numeric matcher rather than eyeballed. The existing 22-question naive/hybrid/hybrid-rewrite comparison table is unaffected and remains the authoritative retrieval-method comparison.
