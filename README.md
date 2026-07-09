# CreditLens

CreditLens is an agentic RAG application for commercial credit analysts. Users select SEC filings, ask credit questions, and receive source-cited answers with financial figures grounded in the filing. The finished version will also draft a credit memo section and include an evaluation harness that checks numeric accuracy.

This repository has a deployed Phase 0 walking skeleton (FastAPI backend on Railway, Next.js frontend on Vercel) and a working Phase 1: SEC filing ingestion into Qdrant plus naive dense-retrieval RAG, with every financial figure in an answer tied to a page and section citation.

## Build Status

- **Phase 0 - Walking Skeleton**: complete and deployed.
- **Phase 1 - SEC Ingestion and Naive RAG**: complete. `/chat` retrieves from Qdrant and answers via OpenRouter with citations.
- **Phase 2 - Agent, Memory, Tavily**: not started.
- **Phase 3 - Memo Section**: not started.
- **Phase 4 - Evals and Hybrid Retrieval**: not started.

## Repository Structure

```text
creditlens/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app and CORS setup
│   │   ├── api.py                 # /health and /chat routes
│   │   ├── config.py              # environment variables
│   │   ├── qa.py                  # retrieve -> OpenRouter answer flow
│   │   ├── agent/
│   │   │   └── prompts.py         # centralized prompt text
│   │   ├── ingestion/
│   │   │   ├── parse.py           # pymupdf4llm PDF -> per-page markdown
│   │   │   ├── chunk.py           # section-aware, table-safe chunking
│   │   │   ├── embeddings.py      # Cohere embeddings (isolated, swappable)
│   │   │   └── index.py           # Qdrant collection + upsert
│   │   └── retrieval/
│   │       └── dense.py           # naive dense retrieval, top-k 8
│   ├── requirements.txt
│   ├── Procfile                   # Railway process command
│   └── railway.toml               # Railway deployment config
├── frontend/
│   ├── app/
│   │   ├── page.tsx               # Chat UI
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   └── api/chat/route.ts      # Frontend proxy to backend
│   ├── package.json
│   └── tailwind.config.ts
├── data/
│   ├── filings/                   # Boeing, Lockheed, RTX FY2024 10-K PDFs
│   └── golden/                    # Evaluation questions will go here (Phase 4)
├── evals/results/                 # Saved eval outputs will go here (Phase 4)
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

## Retrieval and Answering

`backend/app/retrieval/dense.py` embeds the question (Cohere, `input_type="search_query"`) and does a top-8 similarity search in Qdrant filtered by `filing_id`. This is the "naive dense retrieval" baseline Phase 4 will compare against hybrid retrieval.

`backend/app/qa.py` takes those chunks, builds a prompt (`backend/app/agent/prompts.py`) that requires every financial figure to carry a `(page N, section)` citation and forbids estimating uncited figures, and calls OpenRouter (`openai/gpt-4.1-mini`) for the answer. This is a plain function, not a LangGraph agent yet — that, along with Tavily tool choice and thread memory, is Phase 2.

## Known Limitation: Citation Precision

Manual testing surfaced a real but subtle failure mode: the model sometimes states a figure that is genuinely present in the retrieved context, but cites a page that shows a *related, similarly-labeled* figure rather than the one actually stated. For example, asking for Boeing's net loss returned `$11,829M` (the correct consolidated "Net loss" line) but cited a page that visibly shows `$11,817M` ("Net loss attributable to Boeing shareholders" — a real, differently-labeled figure $12M lower due to noncontrolling interest). The number itself was not invented; the page attribution was imprecise.

This is expected of single-pass LLM citation over naive retrieval, not a bug to silently patch — it's exactly what Phase 4's numeric exact-match eval harness is designed to catch and quantify systematically, and part of the motivation for the memo feature (Phase 3) extracting figures into a structured, more constrained format.

## Backend

The backend is a FastAPI service.

`GET /health` returns service status. Deployment platforms use this to confirm the backend is alive.

`POST /chat` retrieves from Qdrant for the given `filing_id` and returns a cited answer.

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
  "answer": "Boeing's total revenue for 2024 was $66,517 million (page 72, section: Index to the Consolidated Financial Statements)...",
  "citations": [
    {"page": 72, "section": "Index to the Consolidated Financial Statements", "snippet": "..."}
  ]
}
```

## Frontend

The frontend is a Next.js App Router application with Tailwind. Unchanged from Phase 0 — no frontend code changes were needed for Phase 1, since the response shape (`answer` + `citations`) was already anticipated.

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
3. Add environment variables from `.env.example`, including `OPENROUTER_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, and `COHERE_API_KEY` — `/chat` will error without these.
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

1. **Phase 2**: LangGraph agent with `MemorySaver` checkpointer, `retrieve_filing` and `tavily_search` tools, thread-based memory using the frontend's `thread_id`.
2. **Phase 3**: `/memo` endpoint — extract key figures into a Pydantic model, compute ratios, generate a cited Financial Summary & Risk Factors section.
3. **Phase 4**: golden question set, numeric exact-match eval with tolerance, Ragas metrics, hybrid retrieval (dense + BM25 + rerank), naive-vs-hybrid comparison table.
4. **Phase 5**: submission polish — architecture diagrams, eval tables in README, phone browser test.
