# CreditLens

CreditLens is an agentic RAG application for commercial credit analysts. Users select SEC filings, ask credit questions, and receive source-cited answers with financial figures grounded in the filing. The finished version will also draft a credit memo section and include an evaluation harness that checks numeric accuracy.

This repository has a deployed Phase 0 walking skeleton (FastAPI backend on Railway, Next.js frontend on Vercel), Phase 1 SEC filing ingestion into Qdrant with naive dense-retrieval RAG, Phase 2's LangGraph agent with thread memory that chooses between filing retrieval and Tavily web search, Phase 3's `/memo` endpoint that drafts a cited Financial Summary & Risk Factors section, and Phase 4's eval harness (numeric exact-match + Ragas) comparing naive dense retrieval against a hybrid dense+BM25+rerank pipeline. Every financial figure anywhere in the app is tied to a page and section citation.

## Build Status

- **Phase 0 - Walking Skeleton**: complete and deployed.
- **Phase 1 - SEC Ingestion and Naive RAG**: complete.
- **Phase 2 - Agent, Memory, Tavily**: complete. `/chat` runs a LangGraph agent with a `MemorySaver` checkpointer, choosing between `retrieve_filing` and `tavily_search`.
- **Phase 3 - Memo Section**: complete. `/memo` extracts six key figures with citations, computes ratios, and drafts a cited narrative.
- **Phase 4 - Evals and Hybrid Retrieval**: complete. Golden question set, numeric exact-match eval, Ragas metrics, hybrid retrieval, real comparison table below.

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
│   │       ├── dense.py           # naive dense retrieval, top-k 8
│   │       └── hybrid.py          # dense + BM25, RRF fusion, Cohere rerank to top-6
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
│       ├── questions.jsonl        # 22 golden questions (18 numeric, 4 qualitative)
│       └── numeric_truth.jsonl    # hand-verified figures, cross-checked against source text
├── evals/
│   ├── pipeline.py                # shared retrieve -> answer flow (not the agent)
│   ├── numeric_eval.py            # unit/scale normalization, 0.5% tolerance matching
│   ├── cohere_langchain_embeddings.py  # LangChain Embeddings shim around our Cohere client
│   ├── run_evals.py               # orchestrator: python evals/run_evals.py --pipeline naive|hybrid
│   └── results/                   # naive_results.{json,md}, hybrid_results.{json,md}
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

`backend/app/retrieval/dense.py` embeds the question (Cohere, `input_type="search_query"`) and does a top-8 similarity search in Qdrant filtered by `filing_id`. This is the "naive dense retrieval" baseline.

`backend/app/retrieval/hybrid.py` is the Phase 4 alternative: dense top-20 plus a BM25 top-20 (built on demand per `filing_id` from a Qdrant `scroll` over that filing's chunks, cached in-process — the largest corpus here is under 500 chunks, small enough for an unpaginated in-memory BM25 index), fused with reciprocal rank fusion (k=60), then reranked from the fused top-20 down to a final top-6 with Cohere Rerank (`rerank-v3.5`).

`/chat` and `/memo` still use naive dense retrieval in production — Phase 4's job was to build and measure the hybrid alternative, not silently swap production over. See the eval results below before deciding whether to switch.

## Agent (Phase 2)

`backend/app/agent/graph.py` builds a LangGraph `StateGraph`: an `agent` node (OpenRouter `openai/gpt-4.1-mini` via `langchain-openai`'s `ChatOpenAI`, pointed at OpenRouter's base URL) bound to two tools, and a `tools` node that executes them. A `MemorySaver` checkpointer persists conversation history per `thread_id`.

Two tools (`backend/app/agent/tools.py`):

- `retrieve_filing(query, filing_id)` — wraps naive dense retrieval. Any company-specific financial figure must come from here.
- `tavily_search(query)` — web search for market/industry/general context. Never used for filing-specific figures.

Routing and citation rules live in `backend/app/agent/prompts.py`: filing figures need a `(page N, section)` citation, Tavily results are described as external context and never presented as filing data, and conflicting sources get an explicit source-boundary explanation.

**`thread_id` vs `filing_id`**: the frontend generates one `thread_id` per browser session (`localStorage`) but `filing_id` comes from the dropdown and can change on any message. Since a conversation can span multiple filings, `filing_id` isn't baked into a one-time system prompt — it travels inline with every message as `[Selected filing_id: ...]`, while the system prompt (routing/citation rules) is added once per thread.

**Citation extraction**: the graph's chat-completion loop doesn't hand back structured citations on its own — only conversational text. `run_agent()` recovers them by matching page numbers actually mentioned in the final answer against every `retrieve_filing` tool result seen anywhere in the thread so far (keyed by `filing_id` + page). This was a deliberate fix: an earlier version only looked at the current turn's tool calls, which produced an empty `citations` array whenever the model answered a follow-up from conversation memory instead of calling `retrieve_filing` again — even though the answer text still said "(page 36, ...)". Matching against mentioned page numbers works whether or not a fresh tool call happened this turn.

**Known limitation — in-memory checkpointer**: `MemorySaver` is explicitly the "v1" choice per the build spec, and it means what it says: conversation history lives in the running process's memory only. It does not survive a server restart or work across multiple backend instances. Fine for this project's scope; a persistent checkpointer (e.g. backed by Postgres/Redis) would be the production upgrade.

## Memo Section (Phase 3)

`POST /memo` (`{"filing_id": "boeing-2024-10k"}`) drafts a credit memo section. Pipeline in `backend/app/memo.py`:

1. **Targeted retrieval per figure** — six separate `retrieve()` calls, one per key figure (revenue, net income, total debt, cash, current assets, current liabilities), each with its own tailored query. This is deliberate: a single generic query risks the same wrong-line-item problem noted in the ambiguous-query limitation above (e.g. pulling a segment's revenue instead of the consolidated total). Results are merged and deduplicated into one context.
2. **Structured extraction** — `ChatOpenAI(...).with_structured_output(FinancialFigures, method="function_calling")` extracts all six figures in one call, each as `{value, page, section}`. A figure not clearly stated in the excerpts comes back with all three fields `null` — enforced by the schema itself, not just a prompt instruction. Verified with a synthetic test (a fabricated field name with no matching context correctly returned null) and against real filings (every figure cross-checked by hand against the source PDF text for Boeing — see below).
3. **Ratios** — computed only when both required figures are non-null and the denominator isn't zero: current ratio, net margin, cash-to-debt, debt-to-revenue. Missing inputs produce `null`, not a guess.
4. **Risk factor retrieval** — one more `retrieve()` call for credit-relevant risk excerpts.
5. **Narrative generation** — a final OpenRouter call writes the "Financial Summary & Risk Factors" prose. It's given the already-extracted figures pre-formatted as either `"$X million (page N, section)"` or the literal string `"not disclosed in reviewed filings"` for nulls, and instructed not to restate or recompute anything differently than given.

Response shape:

```json
{
  "company": "Boeing",
  "fiscal_year": 2024,
  "figures": {
    "revenue": {"value": 66517, "page": 36, "section": "Revenues"},
    "cash": {"value": 13801, "page": 75, "section": "Assets"}
  },
  "ratios": {"current_ratio": 1.32, "net_margin": -0.178, "cash_to_debt": 0.26, "debt_to_revenue": 0.81},
  "narrative": "Financial Summary & Risk Factors\n\n...",
  "citations": [{"page": 36, "section": "Revenues", "snippet": "..."}]
}
```

**Figure accuracy, verified by hand**: for Boeing, every extracted figure was cross-checked against the actual balance sheet/income statement text. Total debt ($53,864M) exactly equals short-term debt ($1,278M) plus long-term debt ($52,586M) as stated on the same page. Current assets ($127,998M) and current liabilities ($97,078M) look unusually large at first glance — but that's genuinely correct for Boeing specifically: program-accounting inventory ($87,550M) and advance billings ($60,333M) are unusually large current-statement line items for an aircraft manufacturer, not an extraction bug pulling in total-balance-sheet figures instead of current ones.

The frontend's "Draft memo section" button (next to the filing selector) posts to `frontend/app/api/memo/route.ts` and appends the narrative as an assistant message in the existing chat thread, reusing the same citation-rendering UI as `/chat` — no new frontend components needed.

## Evaluation Harness (Phase 4)

### Golden dataset

`data/golden/questions.jsonl` has 22 questions across all three filings: 18 numeric (6 key figures × 3 companies) and 4 qualitative (risk-factor style). `data/golden/numeric_truth.jsonl` holds the ground truth for the numeric ones.

Every numeric truth value was hand cross-checked against the actual filing text, not just trusted from a pipeline's own output — this caught a real bug along the way: RTX's Phase 3 memo extraction had returned $41,146M for "total debt," but the filing's own explicit "Total debt" line (in its Liquidity and Financial Condition discussion) states $41,261M — the extracted figure was actually "Total principal long-term debt" from a debt-maturity note, a different, similarly-labeled line item. The golden truth uses the correct $41,261M; the eval results below reflect that, not a value that would make either pipeline look artificially better.

### Numeric eval (`evals/numeric_eval.py`)

Extracts every number from the model's answer text (handling `$`, commas, parenthesized negatives, and "million"/"billion"/"thousand" scale words, normalized to millions), and checks whether any of them matches the truth value within 0.5% relative tolerance. Matching is on magnitude, not signed value — real answers commonly phrase a loss as `"a net loss of $11,817 million"` (positive number, contextual wording) rather than `"-$11,817 million"` or `"($11,817)"`, and penalizing that would be testing prose style, not numeric accuracy.

### Ragas metrics

Faithfulness, answer relevancy, and context precision, computed via the classic `ragas.evaluate()` API (the newer `ragas.metrics.collections` API needs an `instructor`-wrapped async client and looked less mature at this ragas version; classic is deprecated for v1.0 but fully functional today). The LLM judge is `ChatOpenAI` pointed at OpenRouter — same as the rest of the app — wrapped in `LangchainLLMWrapper`; embeddings are our existing Cohere client wrapped in a two-method `Embeddings` shim (`evals/cohere_langchain_embeddings.py`) so Ragas didn't need a second embedding provider.

Getting `ragas` installed required one real fix: it pulled in `langchain-community` 0.4.2, whose `chat_models.vertexai` submodule `ragas`'s LLM base module imports unconditionally at the top of the file — but that submodule was removed from `langchain-community` in the 0.4 line. Pinning `langchain-community==0.3.31` (last release with it still in-tree) resolved it without touching any of this project's own pinned `langchain-core`/`langchain-openai`/`langgraph` versions.

### Comparison: naive dense vs hybrid

Both pipelines answer the same 22 questions through the same prompt and model (`evals/pipeline.py` — a plain retrieve-then-answer function, deliberately not the LangGraph agent, so Tavily/tool-choice behavior can't confound a retrieval-method comparison), differing only in which retriever supplies the context.

| Metric | Naive dense (top-8) | Hybrid (dense+BM25, RRF, rerank top-6) |
|---|---|---|
| Numeric accuracy | 33.3% (6/18) | 66.7% (12/18) |
| Faithfulness | 0.777 | 0.708 |
| Answer relevancy | 0.422 | 0.521 |
| Context precision | 0.250 | 0.514 |

Full per-question results: `evals/results/naive_results.md` and `evals/results/hybrid_results.md` (or the `.json` versions for the raw contexts/citations behind each answer).

**Hybrid roughly doubles numeric accuracy and context precision**, and improves answer relevancy — reranking directly optimizes for putting the actually-relevant chunk near the top, which is exactly what numeric precision and context precision both reward. Run to run:

- **Every current-assets and current-liabilities question failed in both pipelines**, for all three companies. Phase 3's `/memo` endpoint successfully extracts these same figures — but it uses short, targeted retrieval queries per figure (e.g. `"total current assets"`), while this eval embeds the full natural-language question (`"What were Boeing's total current assets at the end of fiscal year 2024?"`) as the query. That gap is itself a real, useful finding about query-formulation sensitivity in both naive and hybrid dense retrieval — not a bug in either pipeline, and not something this phase's scope asked to fix.
- **Faithfulness dropped slightly under hybrid** (0.708 vs 0.777). With a sample size of 22 this could be noise, or it could mean that once hybrid supplies more genuinely relevant context, the model attempts more specific claims that are occasionally less tightly grounded than the vaguer, safer answers naive retrieval's weaker context tends to produce. Not confirmed either way at this sample size.
- **The 0.5% tolerance can pass a technically-wrong figure that happens to be numerically close.** Hybrid's RTX total-debt answer stated $41,146M (the same wrong "long-term debt" line item flagged above) — not the correct $41,261M — but the two are within 0.28% of each other, so it passes. This is a known, accepted property of tolerance-based numeric matching, not a scoring bug; a hard exact-match would have a near-zero false-pass rate but would also fail on legitimate rounding differences.

### Running it yourself

```bash
cd backend && source .venv/bin/activate
pip install -r ../evals/requirements.txt   # ragas + a langchain-community pin; not part of the deployed app
python ../evals/run_evals.py --pipeline naive
python ../evals/run_evals.py --pipeline hybrid
```

Requires `OPENROUTER_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, and `COHERE_API_KEY` (same as the rest of the app) in `backend/.env`. Each run takes a few minutes — 22 questions × (retrieval + answer generation) plus Ragas's own multi-step LLM evaluation per question.

`ragas` and its `langchain-community` pin live in `evals/requirements.txt`, separate from `backend/requirements.txt` — Railway never needs them, only local eval runs do. `rank-bm25` (used by `hybrid.py` itself) is a real backend dependency and stays in `backend/requirements.txt`.

## Known Limitations

**Citation precision.** Manual testing surfaced a real but subtle failure mode: the model sometimes states a figure that is genuinely present in the retrieved context, but cites a page that shows a *related, similarly-labeled* figure rather than the one actually stated. For example, asking for Boeing's net loss returned `$11,829M` (the correct consolidated "Net loss" line) but cited a page that visibly shows `$11,817M` ("Net loss attributable to Boeing shareholders" — a real, differently-labeled figure $12M lower due to noncontrolling interest). The number itself was not invented; the page attribution was imprecise.

**Ambiguous-query retrieval.** Asking "What was Boeing's total revenue?" with naive dense retrieval sometimes surfaces segment-level revenue chunks (e.g. Global Services' $19,954M) alongside the true consolidated total ($66,517M), and the model has picked the wrong one. More specific phrasing ("total consolidated revenue") retrieves correctly. Naive top-8 dense search has no way to distinguish "the segment discussion that happens to also say Revenues" from "the consolidated total" — that's a retrieval precision problem, not a generation problem.

Both are expected of single-pass LLM answering over naive dense retrieval, not bugs to silently patch around with more prompt engineering — they're exactly what Phase 4's numeric exact-match eval harness and hybrid retrieval (dense + BM25 + rerank) exist to catch and fix systematically, and part of the motivation for the memo feature (Phase 3) extracting figures into a structured, more constrained format instead of free-form chat answers.

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

1. **Phase 5**: submission polish — architecture diagrams, confirm no secrets committed, deployed smoke test, phone browser test.
