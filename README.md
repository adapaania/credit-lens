# CreditLens

CreditLens is an agentic RAG application for commercial credit analysts. Users select a SEC 10-K filing, ask credit questions, and get source-cited answers — every financial figure is tied to a page and section citation. The app also drafts a cited credit memo section and includes an evaluation harness that checks numeric accuracy against hand-verified truth values.

**For the "why" behind the design** — problem/audience, architecture diagrams, data handling, and the full retrieval-improvement narrative — see [`CERTIFICATION_CHALLENGE.md`](CERTIFICATION_CHALLENGE.md). This README stays focused on technical/developer reference: how the code is laid out, how to run it, and what the APIs look like.

**For a rubric-to-code traceability map**, see [`DELIVERABLES.md`](DELIVERABLES.md).

- Live app: https://credit-lens-teal.vercel.app
- Live backend: https://credit-lens-production-929c.up.railway.app

---

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

---

## Quick Start

**Backend:**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

**Smoke test** (backend running, filings already ingested — see [Ingestion](#ingestion)):

```bash
python scripts/smoke_test.py --backend-url http://localhost:8000
```

Checks that `/health` returns `status: ok` and `/chat` returns a non-empty answer with a `citations` list.

---

## SEC Filing Corpus

`data/filings/` has the FY2024 10-Ks for Boeing, Lockheed Martin, and RTX, matching the `filing_id` values in the frontend's filing selector (`boeing-2024-10k`, `lockheed-2024-10k`, `rtx-2024-10k`).

Each PDF is sourced directly from the official SEC EDGAR filing, verifiable by accession number:

| Company | Accession Number | Filed |
|---|---|---|
| Boeing | 0000012927-25-000015 | 2025-02-03 |
| Lockheed Martin | 0000936468-25-000009 | 2025-01-28 |
| RTX | 0000101829-25-000005 | 2025-02-03 |

SEC EDGAR only serves modern 10-Ks as inline-XBRL HTML, not native PDF. Each `.htm` was converted to a paginated PDF with headless Chrome (`--print-to-pdf`) so `pymupdf4llm` has real page numbers to cite — content is untouched, only the container format changed.

---

## Ingestion

`python scripts/ingest.py` runs, per filing:

1. **Parse** (`ingestion/parse.py`) — `pymupdf4llm` extracts markdown text per page, preserving page numbers.
2. **Chunk** (`ingestion/chunk.py`) — split by detected section headers, never mid-table (splitting a table could separate a line-item label from its value).
3. **Embed + index** (`ingestion/embeddings.py`, `index.py`) — chunks embedded with Cohere (`embed-english-v3.0`), upserted into one Qdrant collection (`creditlens_filings`) with a payload index on `filing_id`. Re-ingesting a filing deletes and replaces its existing points.

```bash
cd backend && source .venv/bin/activate
python ../scripts/ingest.py                             # all three filings
python ../scripts/ingest.py --filing-id boeing-2024-10k  # just one
```

Requires `QDRANT_URL`, `QDRANT_API_KEY`, and `COHERE_API_KEY` in `backend/.env` (`OPENROUTER_API_KEY` is not needed for ingestion itself).

---

## Retrieval

Three pipelines live in `backend/app/retrieval/`:

- **`dense.py`** — naive baseline: embed the question, top-8 similarity search filtered by `filing_id`. Kept for the eval comparison; not used in production.
- **`hybrid.py`** — production pipeline: dense top-20 + BM25 top-20 (built on demand per filing from a Qdrant scroll, cached in-process), fused with reciprocal rank fusion (k=60), reranked to a final top-6 with Cohere Rerank (`rerank-v3.5`).
- **`query_rewrite.py`** — a small LLM call rewrites the incoming question into a short, targeted keyword query before retrieval, falling back to the original on any error. This exists because raw natural-language questions about balance-sheet totals (lots of filler words) consistently failed to surface the correct chunk in either naive or hybrid retrieval — see [`CERTIFICATION_CHALLENGE.md`](CERTIFICATION_CHALLENGE.md#fix-two-rewriting-the-query-before-it-hits-the-retriever) for the full diagnosis and before/after numbers.

`/chat` and `/memo` both use hybrid retrieval; `/chat`'s `retrieve_filing` tool additionally applies query rewriting.

---

## Agent

`backend/app/agent/graph.py` builds a two-node LangGraph `StateGraph`: an `agent` node (`openai/gpt-4.1-mini` via OpenRouter) bound to two tools, and a `tools` node that executes them. A `MemorySaver` checkpointer persists conversation history per `thread_id`.

Two tools (`backend/app/agent/tools.py`):

- `retrieve_filing(query, filing_id)` — rewrites the query, then runs hybrid retrieval. Any company-specific financial figure must come from here.
- `tavily_search(query)` — web search for market/industry/general context. Never used for filing-specific figures.

Routing and citation rules live in `backend/app/agent/prompts.py`: filing figures need a `(page N, section)` citation, Tavily results are described as external context, and conflicting sources get an explicit boundary explanation.

A few implementation notes worth knowing:

- **Filing-scope refusal.** The system prompt states the `filing_id`-to-company mapping explicitly and instructs the model to decline and redirect if asked about a company other than the one covered by the selected filing — even if the model already "knows" the figure. This closes a real leak where the model would answer with a correct competitor figure but cite a page/section retrieved from the wrong company's filing. Before/after evidence: `evals/results/refusal_check.md`.
- **`thread_id` vs `filing_id`.** One `thread_id` per browser session, but `filing_id` comes from the dropdown and can change per message — so it travels inline with every message (`[Selected filing_id: ...]`) rather than being baked into a one-time system prompt.
- **Citation extraction.** `run_agent()` recovers citations by matching page numbers mentioned in the final answer against every `retrieve_filing` result seen anywhere in the thread — not just the current turn's tool calls — so citations still populate on a follow-up answered from conversation memory.
- **Known limitation: in-memory checkpointer.** `MemorySaver` doesn't survive a server restart or work across multiple backend instances. A Postgres/Redis-backed checkpointer would be the production upgrade.

---

## Memo Section

`POST /memo` (`{"filing_id": "boeing-2024-10k"}`) drafts a full credit review memorandum in a fixed, risks-first structure (per `MEMO_TEMPLATE.md`): risks and mitigants lead, financials support the argument rather than heading it.

Pipeline (`backend/app/memo.py`):

1. **Targeted retrieval per figure** — six separate queries (revenue, net income, total debt, cash, current assets, current liabilities), merged and deduplicated, to avoid pulling the wrong line item (e.g. a segment total instead of the consolidated one).
2. **Structured figure extraction** — one call returns all six figures as `{value, page, section}`, `null` if not clearly stated.
3. **Ratios computed in code**, never by the LLM: current ratio, net margin, cash-to-debt, debt-to-revenue.
4. **Risk retrieval from two sources** — Item 1A "Risk Factors" and MD&A, merged and deduplicated (material risks often live in MD&A, not Item 1A boilerplate).
5. **Structured risk/mitigant extraction** — exactly 3-5 risks, each borrower-specific and paired with its disclosed mitigant, or the literal string `"No disclosed mitigant - flag for analyst"` if none is disclosed.
6. **Cash-flow retrieval** for repayment considerations.
7. **Structured narrative generation** — summary, borrower background, one interpretation sentence per ratio, repayment considerations — as separate schema fields, not free-form prose.
8. **Deterministic template assembly in code**, not by the LLM. The "Analyst-Input Sections" (loan structure, collateral, risk rating) are fixed placeholders the LLM never touches; "Sources" is a deduplicated, page-sorted citation list.

Output structure (full spec in `MEMO_TEMPLATE.md`):

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

The API response shape (`company`, `fiscal_year`, `figures`, `ratios`, `narrative`, `citations`) hasn't changed since it was first introduced — `narrative` holds the entire assembled markdown document above. The frontend's "Draft memo section" button posts to `frontend/app/api/memo/route.ts` and appends the narrative as an assistant message, with a "Download memo (.md)" button that saves it via a client-side Blob download.

A note on figure accuracy: every figure has been hand cross-checked against the source filing at least once. One real extraction miss was caught this way (Lockheed's `total_debt` briefly came back $1,287M too high, from a mislabeled debt-maturity schedule chunk) and confirmed retrieval-variance-driven, not deterministic — see [`CERTIFICATION_CHALLENGE.md`](CERTIFICATION_CHALLENGE.md#whats-next) for the follow-up fix this motivates.

---

## Evaluation Harness

### Golden dataset

`data/golden/questions.jsonl` — 27 questions across all three filings: 18 numeric (6 key figures × 3 companies), 4 qualitative, 2 deliberately-ambiguous numeric probes, and 3 refusal questions. `data/golden/numeric_truth.jsonl` holds hand-verified ground truth for the numeric ones, each cross-checked directly against the filing text.

The two ambiguous probes regression-test two documented failure modes (consolidated-vs-segment revenue, net-loss-vs-attributable-to-shareholders) directly against the live agent — see `evals/results/ambiguity_probe_check.md`. The 3 refusal questions test the cross-company citation leak described above — see `evals/results/refusal_check.md`.

### How it's measured

- **Numeric exact-match** (`evals/numeric_eval.py`) — extracts every number from the model's answer, normalizes units/scale ("million"/"billion"/"thousand"), and checks whether any falls within 0.5% relative tolerance of the truth value. Matches on magnitude, not signed value, so a "net loss of $11,817 million" correctly matches a truth value of `-11817`.
- **Ragas** — faithfulness, answer relevancy, and context precision, via `ragas.evaluate()` with `ChatOpenAI` (OpenRouter) as the judge and a small Cohere `Embeddings` shim (`evals/cohere_langchain_embeddings.py`).

### Results: naive dense vs. hybrid vs. hybrid + query rewrite

All three runs answer the same 22 questions through the same prompt and model, differing only in retrieval:

| Metric | Naive dense (top-8) | Hybrid (dense+BM25, RRF, rerank top-6) | Hybrid + query rewrite |
|---|---|---|---|
| Numeric accuracy | 33.3% (6/18) | 66.7% (12/18) | **83.3% (15/18)** |
| Faithfulness | 0.777 | 0.708 | 0.576 |
| Answer relevancy | 0.422 | 0.521 | 0.731 |
| Context precision | 0.250 | 0.514 | 0.628 |

Full per-question results: `evals/results/naive_results.md`, `hybrid_results.md`, `hybrid-rewrite_results.md` (`.json` versions have the raw contexts/citations). The full analysis — why hybrid roughly doubles accuracy, why faithfulness drops as accuracy climbs, and the specific new failure mode query rewriting introduces — is in [`CERTIFICATION_CHALLENGE.md`](CERTIFICATION_CHALLENGE.md#making-it-better).

### Running it yourself

```bash
cd backend && source .venv/bin/activate
pip install -r ../evals/requirements.txt   # ragas + a langchain-community pin; not part of the deployed app
python ../evals/run_evals.py --pipeline naive
python ../evals/run_evals.py --pipeline hybrid
python ../evals/run_evals.py --pipeline hybrid --rewrite
```

Requires `OPENROUTER_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, and `COHERE_API_KEY` in `backend/.env`. Each run takes a few minutes — 22 questions × (retrieval + answer generation), plus Ragas's own multi-step LLM evaluation per question.

`ragas` and its `langchain-community` pin live in `evals/requirements.txt`, separate from `backend/requirements.txt` — Railway never needs them, only local eval runs do.

---

## Known Limitations

- **Citation precision.** The model occasionally states a figure that's genuinely in the retrieved context but cites a page showing a related, similarly-labeled figure rather than the one actually stated (e.g. Boeing's "Net loss" vs. "Net loss attributable to Boeing shareholders," $12M apart).
- **Ambiguous-query retrieval.** A short, unqualified question ("What was Boeing's total revenue?") can surface a segment-level figure alongside the true consolidated total, especially under naive dense retrieval.
- **Wrong-similarly-labeled-total risk.** Query rewriting fixed most of the current-assets/current-liabilities retrieval gap, but introduced this same failure mode in one new place — see [`CERTIFICATION_CHALLENGE.md`](CERTIFICATION_CHALLENGE.md#fix-two-rewriting-the-query-before-it-hits-the-retriever) for the specific case.

These aren't bugs to silently prompt-engineer away — they're exactly what the eval harness exists to catch and measure as retrieval keeps improving, and part of why the memo feature extracts figures into a structured, constrained format instead of free-form chat answers.

---

## API Reference

`GET /health` — service status, used by deployment platforms to confirm the backend is alive.

`POST /chat` — runs the LangGraph agent for a given `filing_id` and `thread_id`, returns a cited answer.

```json
// Request
{
  "message": "What were Boeing's total revenue, net loss, cash, and total debt?",
  "filing_id": "boeing-2024-10k",
  "thread_id": "browser-session-id"
}
```

```json
// Response
{
  "answer": "Boeing's total revenue for 2024 was $66,517 million (page 36, Revenues)...",
  "citations": [
    {"page": 36, "section": "Revenues", "snippet": "..."}
  ]
}
```

`POST /memo` — see [Memo Section](#memo-section) above for the request/response shape.

The frontend (Next.js App Router + Tailwind) is a filing selector, message thread, chat input, per-answer citation rendering, and a persistent `thread_id` in `localStorage`. It posts to `frontend/app/api/chat/route.ts`, which forwards to the backend at `NEXT_PUBLIC_API_URL`.

---

## Deployment

**Backend on Railway:**

1. Create a Railway project from this repo, service root `backend`.
2. Add env vars from `.env.example`: `OPENROUTER_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `COHERE_API_KEY`, `TAVILY_API_KEY` (required — `/chat` errors without these). `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` are optional (LangSmith tracing).
3. Set `FRONTEND_ORIGIN` to the deployed Vercel URL.
4. Confirm `/health` is reachable.
5. Run `python scripts/ingest.py` locally, pointed at the same Qdrant Cloud instance the deployed backend uses.

**Frontend on Vercel:**

1. Create a Vercel project from this repo, project root `frontend`.
2. Set `NEXT_PUBLIC_API_URL` to the Railway backend URL.
3. Under **Settings → Deployment Protection**, allow public access to Production (the default can put a login wall in front of the URL).
4. Deploy and test the chat form.

---

## What's Next

Ideas for beyond this submission — a persistent checkpointer, a larger/more adversarial golden set, citation-page precision, a label-matching verification step for retrieved figures, multi-year filings — are tracked in [`CERTIFICATION_CHALLENGE.md`](CERTIFICATION_CHALLENGE.md#whats-next).
