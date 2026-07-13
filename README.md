# CreditLens

CreditLens is an agentic RAG application for commercial credit analysts. Users select SEC filings, ask credit questions, and receive source-cited answers with financial figures grounded in the filing. The finished version will also draft a credit memo section and include an evaluation harness that checks numeric accuracy.

This repository has a deployed Phase 0 walking skeleton (FastAPI backend on Railway, Next.js frontend on Vercel), Phase 1 SEC filing ingestion into Qdrant with naive dense-retrieval RAG, Phase 2's LangGraph agent with thread memory that chooses between filing retrieval and Tavily web search, Phase 3's `/memo` endpoint that drafts a cited Financial Summary & Risk Factors section, Phase 4's eval harness (numeric exact-match + Ragas) comparing naive dense retrieval against a hybrid dense+BM25+rerank pipeline, and Phase 5's query-rewrite improvement (with production promoted onto hybrid + rewrite). Every financial figure anywhere in the app is tied to a page and section citation.

For the certification-challenge write-up (problem/audience, architecture diagrams, data handling, and the full retrieval-improvement narrative), see [`CERTIFICATION_CHALLENGE.md`](CERTIFICATION_CHALLENGE.md). This document stays focused on technical/developer reference.

## Build Status

- **Phase 0 - Walking Skeleton**: complete and deployed.
- **Phase 1 - SEC Ingestion and Naive RAG**: complete.
- **Phase 2 - Agent, Memory, Tavily**: complete. `/chat` runs a LangGraph agent with a `MemorySaver` checkpointer, choosing between `retrieve_filing` and `tavily_search`.
- **Phase 3 - Memo Section**: complete. `/memo` extracts six key figures with citations, computes ratios, and drafts a cited narrative.
- **Phase 4 - Evals and Hybrid Retrieval**: complete. Golden question set, numeric exact-match eval, Ragas metrics, hybrid retrieval, real comparison table below.
- **Phase 5 - Submission Polish**: complete. Query-rewrite retrieval improvement (with hard eval evidence), production promoted from naive to hybrid+rewrite retrieval, architecture diagrams and full write-up in `CERTIFICATION_CHALLENGE.md`.

## Repository Structure

```text
creditlens/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app and CORS setup
│   │   ├── api.py                 # /health, /chat, /memo routes
│   │   ├── config.py              # environment variables
│   │   ├── memo.py                # figure extraction, ratios, memo narrative
│   │   ├── agent/
│   │   │   ├── graph.py           # LangGraph agent: state, nodes, MemorySaver
│   │   │   ├── tools.py           # retrieve_filing, tavily_search
│   │   │   └── prompts.py         # centralized prompt text
│   │   ├── ingestion/
│   │   │   ├── parse.py           # pymupdf4llm PDF -> per-page markdown
│   │   │   ├── chunk.py           # section-aware, table-safe chunking
│   │   │   ├── embeddings.py      # Cohere embeddings (isolated, swappable)
│   │   │   └── index.py           # Qdrant collection + upsert
│   │   └── retrieval/
│   │       ├── dense.py           # naive dense retrieval, top-k 8 (eval baseline only)
│   │       ├── hybrid.py          # dense + BM25, RRF fusion, Cohere rerank to top-6 (production)
│   │       └── query_rewrite.py   # LLM query rewrite before retrieval (production)
│   ├── requirements.txt
│   ├── Procfile                   # Railway process command
│   └── railway.toml               # Railway deployment config
├── frontend/
│   ├── app/
│   │   ├── page.tsx               # Chat UI + Draft memo section button
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   ├── api/chat/route.ts      # Frontend proxy to backend /chat
│   │   └── api/memo/route.ts      # Frontend proxy to backend /memo
│   ├── package.json
│   └── tailwind.config.ts
├── data/
│   ├── filings/                   # Boeing, Lockheed, RTX FY2024 10-K PDFs
│   └── golden/
│       ├── questions.jsonl        # 27 golden questions (20 numeric, 4 qualitative, 3 refusal)
│       └── numeric_truth.jsonl    # hand-verified figures, cross-checked against source text
├── evals/
│   ├── pipeline.py                # shared retrieve -> answer flow (not the agent)
│   ├── numeric_eval.py            # unit/scale normalization, 0.5% tolerance matching
│   ├── refusal_eval.py            # heuristic: does an answer decline + redirect, with no leaked figure
│   ├── cohere_langchain_embeddings.py  # LangChain Embeddings shim around our Cohere client
│   ├── run_evals.py               # orchestrator: python evals/run_evals.py --pipeline naive|hybrid [--rewrite]
│   ├── run_refusal_check.py       # runs refusal-type questions through the live agent, not the eval pipeline
│   └── results/                   # naive/hybrid/hybrid-rewrite_results.{json,md}, refusal_check*, ambiguity_probe_check.md
├── scripts/
│   ├── ingest.py                  # parse -> chunk -> index each filing
│   └── smoke_test.py              # Checks /health and /chat
└── .env.example
```

## SEC Filing Corpus

`data/filings/` contains the FY2024 10-Ks for Boeing, Lockheed Martin, and RTX, matching the `filing_id` values in the frontend's filing selector (`boeing-2024-10k`, `lockheed-2024-10k`, `rtx-2024-10k`).

Each PDF is sourced directly from the official SEC EDGAR filing (verifiable by accession number), not a third-party mirror:

| Company | Accession Number | Filed |
|---|---|---|
| Boeing | 0000012927-25-000015 | 2025-02-03 |
| Lockheed Martin | 0000936468-25-000009 | 2025-01-28 |
| RTX | 0000101829-25-000005 | 2025-02-03 |

SEC EDGAR only provides these as inline-XBRL HTML, not PDF, for modern filings. Each `.htm` was converted to a paginated PDF with headless Chrome (`--print-to-pdf`) so `pymupdf4llm` has real page numbers to cite — the content is untouched, only the container format changed.

## Ingestion Pipeline (Phase 1)

`python scripts/ingest.py` runs, for each filing:

1. **Parse** (`backend/app/ingestion/parse.py`) — `pymupdf4llm` extracts markdown text per page, preserving page numbers. Page-break and footer artifacts are stripped.
2. **Chunk** (`backend/app/ingestion/chunk.py`) — text is split by detected section headers (SEC "Item" headers, bold subsection titles) and never split inside a markdown table, even if that makes a chunk large.
3. **Embed + index** (`backend/app/ingestion/embeddings.py`, `index.py`) — chunks are embedded with Cohere (`embed-english-v3.0`) and upserted into a single Qdrant collection (`creditlens_filings`), with a payload index on `filing_id` for filtering. Re-running ingestion for a filing deletes and replaces its existing points.

Run it with:

```bash
cd backend && source .venv/bin/activate
python ../scripts/ingest.py                          # all three filings
python ../scripts/ingest.py --filing-id boeing-2024-10k   # just one
```

Requires `OPENROUTER_API_KEY` is not needed for ingestion itself, but `QDRANT_URL`, `QDRANT_API_KEY`, and `COHERE_API_KEY` in `backend/.env` are.

## Retrieval

`backend/app/retrieval/dense.py` embeds the question (Cohere, `input_type="search_query"`) and does a top-8 similarity search in Qdrant filtered by `filing_id`. This is the "naive dense retrieval" baseline, kept as-is for the eval comparison below and no longer used by production.

`backend/app/retrieval/hybrid.py` is the Phase 4 alternative: dense top-20 plus a BM25 top-20 (built on demand per `filing_id` from a Qdrant `scroll` over that filing's chunks, cached in-process — the largest corpus here is under 500 chunks, small enough for an unpaginated in-memory BM25 index), fused with reciprocal rank fusion (k=60), then reranked from the fused top-20 down to a final top-6 with Cohere Rerank (`rerank-v3.5`).

`backend/app/retrieval/query_rewrite.py` is the Phase 5 addition: a small LLM call rewrites the incoming question into a short, targeted keyword query before it reaches the retriever, falling back to the original question on any error. This exists because of a diagnosed, 100%-consistent retrieval failure — see the comparison table below — where raw natural-language questions about balance-sheet totals never surfaced the correct (indexed, retrievable) chunk in either naive or hybrid retrieval.

**`/chat` and `/memo` now both use hybrid retrieval, with `/chat`'s `retrieve_filing` tool additionally applying query rewriting.** This was a real gap found and fixed in Phase 5: Phase 4 built and measured hybrid retrieval but never actually promoted it into the production code path — `tools.py` and `memo.py` were still importing `retrieval/dense.py` despite the eval evidence favoring hybrid. See `CERTIFICATION_CHALLENGE.md` (Task 6) for the full before/after diagnosis and numbers.

## Agent (Phase 2)

`backend/app/agent/graph.py` builds a LangGraph `StateGraph`: an `agent` node (OpenRouter `openai/gpt-4.1-mini` via `langchain-openai`'s `ChatOpenAI`, pointed at OpenRouter's base URL) bound to two tools, and a `tools` node that executes them. A `MemorySaver` checkpointer persists conversation history per `thread_id`.

Two tools (`backend/app/agent/tools.py`):

- `retrieve_filing(query, filing_id)` — rewrites the query (`retrieval/query_rewrite.py`), then runs it through hybrid retrieval. Any company-specific financial figure must come from here.
- `tavily_search(query)` — web search for market/industry/general context. Never used for filing-specific figures.

Routing and citation rules live in `backend/app/agent/prompts.py`: filing figures need a `(page N, section)` citation, Tavily results are described as external context and never presented as filing data, and conflicting sources get an explicit source-boundary explanation.

**Filing-scope refusal (Fix 1)**: the system prompt states the `filing_id`-to-company mapping explicitly and instructs the model to decline and redirect if a question is about a *different* company than the one covered by the selected filing — even if the model already knows the figure from general knowledge. This closes a real, verified leak: before the fix, asking about Company B's numbers while Company A's filing was selected returned a real, correctly-remembered figure for Company B, cited with a page/section number that was actually retrieved from Company A's filing — a citation-integrity failure, not just a hallucination, since `retrieve_filing` is already scoped to the selected `filing_id` at the Qdrant level and had no way to catch this. Before/after evidence (0/3 correct refusals → 3/3): `evals/results/refusal_check.md`.

**`thread_id` vs `filing_id`**: the frontend generates one `thread_id` per browser session (`localStorage`) but `filing_id` comes from the dropdown and can change on any message. Since a conversation can span multiple filings, `filing_id` isn't baked into a one-time system prompt — it travels inline with every message as `[Selected filing_id: ...]`, while the system prompt (routing/citation rules) is added once per thread.

**Citation extraction**: the graph's chat-completion loop doesn't hand back structured citations on its own — only conversational text. `run_agent()` recovers them by matching page numbers actually mentioned in the final answer against every `retrieve_filing` tool result seen anywhere in the thread so far (keyed by `filing_id` + page). This was a deliberate fix: an earlier version only looked at the current turn's tool calls, which produced an empty `citations` array whenever the model answered a follow-up from conversation memory instead of calling `retrieve_filing` again — even though the answer text still said "(page 36, ...)". Matching against mentioned page numbers works whether or not a fresh tool call happened this turn.

**Known limitation — in-memory checkpointer**: `MemorySaver` is explicitly the "v1" choice per the build spec, and it means what it says: conversation history lives in the running process's memory only. It does not survive a server restart or work across multiple backend instances. Fine for this project's scope; a persistent checkpointer (e.g. backed by Postgres/Redis) would be the production upgrade.

## Memo Section — risks-first credit review memorandum (Phase 3, restructured Phase 5)

`POST /memo` (`{"filing_id": "boeing-2024-10k"}`) drafts a full credit review memorandum in a fixed, risks-first structure (per `MEMO_TEMPLATE.md`'s "Nichols style": the memo's job is to surface the 3-5 pertinent risks and their mitigants first, with financials supporting that argument rather than leading it). Pipeline in `backend/app/memo.py`:

1. **Targeted retrieval per figure** — six separate `retrieve()` calls, one per key figure (revenue, net income, total debt, cash, current assets, current liabilities), each with its own tailored query. This is deliberate: a single generic query risks the same wrong-line-item problem noted in the ambiguous-query limitation above (e.g. pulling a segment's revenue instead of the consolidated total). Results are merged and deduplicated into one context.
2. **Structured figure extraction** — `with_structured_output(FinancialFigures, ...)` extracts all six figures in one call, each as `{value, page, section}`, `null` if not clearly stated (enforced by the schema).
3. **Ratios** — computed in code, never by the LLM: current ratio, net margin, cash-to-debt, debt-to-revenue. Missing inputs produce `null`.
4. **Risk retrieval from two sources** — separate `retrieve()` calls for Item 1A "Risk Factors" and for MD&A, merged and deduplicated. Material, borrower-specific risks often live in MD&A discussion, not Item 1A boilerplate, so pulling from only one source misses real risks.
5. **Structured risk/mitigant extraction** — `with_structured_output(RiskAssessment, ...)` returns exactly 3-5 risks (enforced by the schema's `min_length`/`max_length`), each specific to the borrower (not a generic "recession" or "competition" risk unless tied to something borrower-specific) and each paired with its disclosed mitigant, or the literal string `"No disclosed mitigant - flag for analyst"` if the filing discloses none — never an invented one.
6. **Cash-flow retrieval** — one more `retrieve()` call, specifically for operating cash flow context (repayment considerations).
7. **Structured narrative-sections generation** — one call returns the borrower summary, borrower background paragraph, one interpretation sentence per ratio (what the number means for repayment capacity, not a restatement of it), and the repayment-considerations paragraph — all as separate schema fields, not free-form prose, so assembly into the template is deterministic.
8. **Deterministic template assembly in code** — the final markdown document (all 6 sections) is built by string formatting in `_assemble_markdown()`, not generated by the LLM. Section 5 ("Analyst-Input Sections": loan structure, collateral, risk rating) is fixed boilerplate with bracketed placeholders — the LLM never touches it, so it can never fabricate deal-specific content that doesn't exist yet. Section 6 ("Sources") is a deduplicated, page-sorted citation list compiled from every figure, risk, and excerpt actually used.

Output structure (see `MEMO_TEMPLATE.md` for the full spec):

```
# CREDIT REVIEW MEMORANDUM — [Company] (FY[year])
*Generated by CreditLens from [filing name, accession number]. Draft for analyst review — not a credit decision.*

## 1. Summary & Key Risks       <- 2-3 sentence summary + exactly 3-5 Risk -> Mitigant pairs
## 2. Borrower Background        <- one cited paragraph
## 3. Financial Analysis         <- figures table + ratios with interpretation, not restatement
## 4. Repayment Considerations   <- operating cash flow direction and drivers, cited
## 5. Analyst-Input Sections     <- fixed placeholders, never LLM-generated
## 6. Sources                    <- deduplicated (page, section) list
```

The API response shape is unchanged from Phase 3 (`company`, `fiscal_year`, `figures`, `ratios`, `narrative`, `citations`) — `narrative` now holds the entire assembled markdown document above, so the existing frontend flow (display + "Download memo (.md)" button) needed no changes.

**Figure accuracy, verified by hand across all three companies**: Boeing's figures were cross-checked in Phase 3 (total debt exactly equals short-term + long-term debt stated on the same page; current assets/liabilities are large but genuinely correct for an aircraft manufacturer's program-accounting inventory). Retesting after the Phase 5 restructure surfaced a real, pre-existing extraction miss on Lockheed Martin specifically: `total_debt` came back as $21,557M (summed from a debt-maturity schedule table on a mislabeled "Deferred Income Taxes" chunk) instead of the correct $20,270M ("total outstanding short-term and long-term debt, net of unamortized discounts and issuance costs" stated in the Financing Activities discussion). This is the same class of bug as the previously-documented RTX total-debt line-item confusion (Phase 3/4) — both are in `extract_figures()`'s per-figure targeted retrieval, which is separate from the chat agent's hybrid+query-rewrite path (Phase 5) and wasn't in scope for this restructure to fix. Re-running the same RTX case after this restructure actually returned the correct $41,261M this time, confirming the miss is retrieval-variance-driven rather than a deterministic bug — worth a dedicated fix (e.g. a label-matching verification step, already flagged in `CERTIFICATION_CHALLENGE.md`'s Task 7) rather than a quick patch here.

The frontend's "Draft memo section" button (next to the filing selector) posts to `frontend/app/api/memo/route.ts` and appends the narrative as an assistant message in the existing chat thread, with a "Download memo (.md)" button that saves the exact assembled document via a client-side Blob download.

## Evaluation Harness (Phase 4)

### Golden dataset

`data/golden/questions.jsonl` has 27 questions across all three filings: 18 numeric (6 key figures × 3 companies), 4 qualitative (risk-factor style), 2 deliberately-ambiguous numeric probes (see below), and 3 refusal questions (a company-specific question paired with a different company's filing selected). `data/golden/numeric_truth.jsonl` holds the ground truth for the numeric ones — the two ambiguous probes reuse existing truth entries since they're testing phrasing sensitivity on figures already verified, not new figures.

The two ambiguous probes exist specifically to regression-test the two failure modes documented earlier in this file: `boeing_revenue_ambiguous` ("What was Boeing's total revenue?", no "consolidated" qualifier) and `boeing_net_loss_ambiguous` ("What was Boeing's net loss?", no "attributable to shareholders" qualifier). Run directly against the live production agent (not the eval-only pipeline) and scored with `numeric_eval.py`'s own matcher, both now resolve correctly — the revenue question returns the consolidated $66,517M rather than a segment figure, and the net-loss question distinguishes both real, differently-labeled figures rather than picking one ($11,829M "Net loss" vs. $11,817M "Net loss attributable to Boeing shareholders"). Full detail and a note on why this ran against the agent directly rather than through the full comparison harness: `evals/results/ambiguity_probe_check.md`.

The 3 refusal questions test something the retrieval-comparison harness below can't: whether the agent leaks a competitor's figures from general knowledge when the *wrong* filing is selected. See "Fix 1" in the retrieval section below and `evals/results/refusal_check.md` for the full before/after.

Every numeric truth value was hand cross-checked against the actual filing text, not just trusted from a pipeline's own output — this caught a real bug along the way: RTX's Phase 3 memo extraction had returned $41,146M for "total debt," but the filing's own explicit "Total debt" line (in its Liquidity and Financial Condition discussion) states $41,261M — the extracted figure was actually "Total principal long-term debt" from a debt-maturity note, a different, similarly-labeled line item. The golden truth uses the correct $41,261M; the eval results below reflect that, not a value that would make either pipeline look artificially better.

### Numeric eval (`evals/numeric_eval.py`)

Extracts every number from the model's answer text (handling `$`, commas, parenthesized negatives, and "million"/"billion"/"thousand" scale words, normalized to millions), and checks whether any of them matches the truth value within 0.5% relative tolerance. Matching is on magnitude, not signed value — real answers commonly phrase a loss as `"a net loss of $11,817 million"` (positive number, contextual wording) rather than `"-$11,817 million"` or `"($11,817)"`, and penalizing that would be testing prose style, not numeric accuracy.

### Ragas metrics

Faithfulness, answer relevancy, and context precision, computed via the classic `ragas.evaluate()` API (the newer `ragas.metrics.collections` API needs an `instructor`-wrapped async client and looked less mature at this ragas version; classic is deprecated for v1.0 but fully functional today). The LLM judge is `ChatOpenAI` pointed at OpenRouter — same as the rest of the app — wrapped in `LangchainLLMWrapper`; embeddings are our existing Cohere client wrapped in a two-method `Embeddings` shim (`evals/cohere_langchain_embeddings.py`) so Ragas didn't need a second embedding provider.

Getting `ragas` installed required one real fix: it pulled in `langchain-community` 0.4.2, whose `chat_models.vertexai` submodule `ragas`'s LLM base module imports unconditionally at the top of the file — but that submodule was removed from `langchain-community` in the 0.4 line. Pinning `langchain-community==0.3.31` (last release with it still in-tree) resolved it without touching any of this project's own pinned `langchain-core`/`langchain-openai`/`langgraph` versions.

### Comparison: naive dense vs hybrid vs hybrid + query rewrite

All three runs answer the same 22 questions through the same prompt and model (`evals/pipeline.py` — a plain retrieve-then-answer function, deliberately not the LangGraph agent, so Tavily/tool-choice behavior can't confound a retrieval-method comparison), differing only in retrieval.

| Metric | Naive dense (top-8) | Hybrid (dense+BM25, RRF, rerank top-6) | Hybrid + query rewrite |
|---|---|---|---|
| Numeric accuracy | 33.3% (6/18) | 66.7% (12/18) | **83.3% (15/18)** |
| Faithfulness | 0.777 | 0.708 | 0.576 |
| Answer relevancy | 0.422 | 0.521 | 0.731 |
| Context precision | 0.250 | 0.514 | 0.628 |

Full per-question results: `evals/results/naive_results.md`, `evals/results/hybrid_results.md`, `evals/results/hybrid-rewrite_results.md` (or the `.json` versions for the raw contexts/citations behind each answer).

**Hybrid roughly doubles numeric accuracy and context precision over naive**, and query rewriting adds another +16.6 points of numeric accuracy on top of that. Notable findings, including the ones that motivated query rewriting in the first place:

- **Every current-assets and current-liabilities question failed in both naive and hybrid**, for all three companies — a 100%-consistent pattern, not scattered noise. Diagnosis: raw natural-language questions ("What were Boeing's total current assets at the end of fiscal year 2024?") are mostly filler words that dilute both BM25 and dense-embedding relevance against terse balance-sheet table rows, even though the correct chunk is indexed and retrievable — a short query like `"total current assets"` finds it at rank 0 every time. This is exactly the workaround `/memo` had already stumbled into by using hand-written short queries per figure; query rewriting generalizes that fix to arbitrary questions. Full diagnosis and the three-way comparison: `CERTIFICATION_CHALLENGE.md` (Task 6).
- **Query rewriting is a net win but not a free one.** It fixed 5 of hybrid's 6 failures (including, as a side effect, the RTX total-debt line-item issue below), but caused one regression (`lockheed_cash_2024`, a tolerance-boundary miss) and one new wrong-but-confident answer (`rtx_current_liabilities_2024`, which matched an unrelated same-labeled "Total X" row in a different footnote). See `CERTIFICATION_CHALLENGE.md` for the full accounting — faithfulness dropping further under query rewriting (0.576) is partly this real new failure mode, not just "the model attempts more answers."
- **Faithfulness dropped under hybrid, and further under hybrid+rewrite** (0.777 → 0.708 → 0.576). Part of this is expected and even desirable: naive retrieval's higher score was partly a "faithful non-answer" artifact (correctly declining when given irrelevant context), and each retrieval improvement gives the model correct context to actually attempt more of the answers it used to decline. Part of it, at the rewrite stage specifically, is the new wrong-line-item failure mode above.
- **The 0.5% tolerance can pass a technically-wrong figure that happens to be numerically close.** The original hybrid run's RTX total-debt answer stated $41,146M (a different, similarly-labeled "long-term debt" line item, not the correct $41,261M "Total debt" line) — within 0.28% of the truth, so it passed by coincidence. Query rewriting happened to fix this one specifically (see above), but the underlying tolerance-matching blind spot is a general, accepted property of tolerance-based numeric matching, not something any of these three pipelines fully closes.

### Running it yourself

```bash
cd backend && source .venv/bin/activate
pip install -r ../evals/requirements.txt   # ragas + a langchain-community pin; not part of the deployed app
python ../evals/run_evals.py --pipeline naive
python ../evals/run_evals.py --pipeline hybrid
python ../evals/run_evals.py --pipeline hybrid --rewrite
```

Requires `OPENROUTER_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, and `COHERE_API_KEY` (same as the rest of the app) in `backend/.env`. Each run takes a few minutes — 22 questions × (retrieval + answer generation) plus Ragas's own multi-step LLM evaluation per question.

`ragas` and its `langchain-community` pin live in `evals/requirements.txt`, separate from `backend/requirements.txt` — Railway never needs them, only local eval runs do. `rank-bm25` (used by `hybrid.py` itself) is a real backend dependency and stays in `backend/requirements.txt`.

## Known Limitations

**Citation precision.** Manual testing surfaced a real but subtle failure mode: the model sometimes states a figure that is genuinely present in the retrieved context, but cites a page that shows a *related, similarly-labeled* figure rather than the one actually stated. For example, asking for Boeing's net loss returned `$11,829M` (the correct consolidated "Net loss" line) but cited a page that visibly shows `$11,817M` ("Net loss attributable to Boeing shareholders" — a real, differently-labeled figure $12M lower due to noncontrolling interest). The number itself was not invented; the page attribution was imprecise.

**Ambiguous-query retrieval.** Asking "What was Boeing's total revenue?" with naive dense retrieval sometimes surfaces segment-level revenue chunks (e.g. Global Services' $19,954M) alongside the true consolidated total ($66,517M), and the model has picked the wrong one. More specific phrasing ("total consolidated revenue") retrieves correctly. Naive top-8 dense search has no way to distinguish "the segment discussion that happens to also say Revenues" from "the consolidated total" — that's a retrieval precision problem, not a generation problem.

**Wrong-similarly-labeled-total risk (production, hybrid + query rewrite).** Query rewriting (Phase 5) fixed most of the current-assets/current-liabilities retrieval gap and, as a side effect, RTX's total-debt line-item confusion — but it also introduced this same failure mode in one new place: `rtx_current_liabilities_2024` now confidently cites an unrelated "Total X" row from a different footnote table instead of the balance sheet figure. A 10-K has many tables with similarly-labeled totals, and a short keyword query is more prone to matching the wrong one than a longer, specific question would be. Full detail in `CERTIFICATION_CHALLENGE.md` (Task 6). None of the numeric-tolerance check, Ragas faithfulness, or citation rendering catches "right magnitude, wrong line item" reliably — that would need an explicit label-matching verification step, noted as future work.

These are expected of single-pass LLM answering over retrieval, not bugs to silently patch around with more prompt engineering — they're exactly what the eval harness (numeric exact-match + Ragas) exists to catch and measure systematically as retrieval keeps improving, and part of the motivation for the memo feature (Phase 3) extracting figures into a structured, more constrained format instead of free-form chat answers.

## Backend

The backend is a FastAPI service.

`GET /health` returns service status. Deployment platforms use this to confirm the backend is alive.

`POST /chat` runs the LangGraph agent for the given `filing_id` and `thread_id`, returning a cited answer.

Example request:

```json
{
  "message": "What were Boeing's total revenue, net loss, cash, and total debt?",
  "filing_id": "boeing-2024-10k",
  "thread_id": "browser-session-id"
}
```

Example response shape:

```json
{
  "answer": "Boeing's total revenue for 2024 was $66,517 million (page 36, Revenues)...",
  "citations": [
    {"page": 36, "section": "Revenues", "snippet": "..."}
  ]
}
```

## Frontend

The frontend is a Next.js App Router application with Tailwind. Unchanged since Phase 0 — no frontend code changes were needed for Phase 1 or Phase 2, since the response shape (`answer` + `citations`) and the persistent `thread_id` were already anticipated in the original skeleton.

The page includes:

- A filing selector
- A message thread
- A chat input
- Citation rendering below each answer (page, section, snippet)
- A persistent thread id stored in browser `localStorage`

The browser posts to `frontend/app/api/chat/route.ts`, which forwards the request to the backend configured by `NEXT_PUBLIC_API_URL`.

## Local Development

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Smoke Test

With the backend running (and filings ingested — see below):

```bash
python scripts/smoke_test.py --backend-url http://localhost:8000
```

The smoke test checks:

- `/health` returns `status: ok`
- `/chat` returns a non-empty answer with a `citations` list

## Deployment

Backend on Railway:

1. Create a Railway project from this repo.
2. Set the service root to `backend`.
3. Add environment variables from `.env.example`, including `OPENROUTER_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `COHERE_API_KEY`, and `TAVILY_API_KEY` — `/chat` will error without these. `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` are optional (LangSmith tracing); leave `LANGCHAIN_API_KEY` blank to skip it.
4. Set `FRONTEND_ORIGIN` to the deployed Vercel URL.
5. Confirm `/health` is reachable.
6. Run `python scripts/ingest.py` locally pointed at the same Qdrant Cloud instance the deployed backend uses, so its collection is populated.

Frontend on Vercel:

1. Create a Vercel project from this repo.
2. Set the project root to `frontend`.
3. Set `NEXT_PUBLIC_API_URL` to the Railway backend URL.
4. Check **Settings → Deployment Protection** — the default can put a Vercel login wall in front of the production URL, which blocks real users on phone/laptop. Set it to allow public access to Production.
5. Deploy and test the chat form.

## Recommended SEC Filing Set

Aerospace and defense, per the product direction:

- Boeing 10-K (`boeing-2024-10k`)
- Lockheed Martin 10-K (`lockheed-2024-10k`)
- RTX 10-K (`rtx-2024-10k`)

Boeing gives the strongest story because credit risk connects directly to safety incidents, regulatory scrutiny, production disruptions, lawsuits, reputation damage, cash flow, and debt. Lockheed Martin and RTX provide cleaner peers for comparison.

## Next Build Phases

All build-spec phases (0-5) are complete. Ideas for beyond this submission are tracked in `CERTIFICATION_CHALLENGE.md`'s Task 7 (persistent checkpointer, larger/more adversarial golden set, citation-page precision, a label-matching verification step for retrieved figures, multi-year filings).
