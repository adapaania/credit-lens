# CLAUDE.md - CreditLens Build Guide

## Project

CreditLens is an agentic RAG application for commercial credit analysts. The user selects SEC filings, asks questions, and receives source-cited answers with financial figures grounded in the filing. The app should also draft a credit memo section and include an evaluation harness that proves extracted numbers match the source documents.

This is a certification-style build. Optimize for shipped, working software over elegance. Do not add extra features until the required phases work.

## Current Repository State

The repo has a completed Phase 0 walking skeleton:

- FastAPI backend in `backend/`
- Next.js frontend in `frontend/`
- `GET /health` backend route
- `POST /chat` backend route that currently echoes the request
- Responsive chat UI with a filing selector
- Frontend route handler at `frontend/app/api/chat/route.ts` that proxies to the backend
- `.env.example`
- Railway backend config
- Vercel-ready frontend config
- `scripts/smoke_test.py`

Do not rebuild Phase 0 from scratch. Continue from the existing skeleton.

## Product Direction

Use Boeing as the main demo company because its credit profile connects clearly to operational and regulatory risk:

- 737 MAX crash aftermath
- FAA scrutiny
- Production disruption
- Legal and regulatory exposure
- Reputation damage
- Liquidity pressure
- Debt and cash flow impact

Use an aerospace/defense peer set:

- Boeing 10-K
- Lockheed Martin 10-K
- RTX 10-K

If time gets tight, use Boeing plus one peer instead of all three.

## Hard Requirements

Never cut these:

1. All LLM calls go through OpenRouter, not direct OpenAI SDK calls, except embeddings may be isolated in one swappable module if OpenRouter support is unavailable.
2. LangGraph agent with a checkpointer for per-thread memory.
3. Browser app works on phone and laptop.
4. Agentic RAG: the agent chooses between filing retrieval and Tavily web search.
5. Two data sources: curated SEC filing corpus plus Tavily.
6. Evaluation harness: Ragas plus custom numeric exact-match eval.
7. Retrieval comparison: naive dense retrieval versus improved hybrid retrieval.
8. Public deployment: Railway backend and Vercel frontend.

## Required Tech Stack

Backend:

- FastAPI
- Uvicorn
- Python
- LangGraph
- OpenRouter with `openai/gpt-4.1-mini`
- Qdrant Cloud
- Tavily
- LangSmith tracing
- `pymupdf4llm` for PDF parsing
- Ragas for evals

Frontend:

- Next.js App Router
- Tailwind CSS
- Responsive browser UI

Deployment:

- Railway for backend
- Vercel for frontend

## Environment Variables

Use `.env.example` as the source of truth.

Backend variables:

- `FRONTEND_ORIGIN`
- `OPENROUTER_API_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `TAVILY_API_KEY`
- `LANGCHAIN_TRACING_V2`
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT`
- `COHERE_API_KEY`

Frontend variable:

- `NEXT_PUBLIC_API_URL`

Never commit secrets.

## Build Order

Follow this order. Do not skip ahead.

### Phase 0 - Walking Skeleton

Status: complete.

What exists:

- Backend `/health`
- Backend `/chat` echo
- Frontend chat UI
- Frontend-to-backend proxy
- Railway and Vercel config
- Smoke test

Before moving further, deploy this skeleton:

1. Deploy `backend/` to Railway.
2. Deploy `frontend/` to Vercel.
3. Set `FRONTEND_ORIGIN` in Railway to the Vercel URL.
4. Set `NEXT_PUBLIC_API_URL` in Vercel to the Railway backend URL.
5. Run `scripts/smoke_test.py` against the Railway backend.

### Phase 1 - SEC Ingestion and Naive RAG

Add these files:

- `backend/app/ingestion/parse.py`
- `backend/app/ingestion/chunk.py`
- `backend/app/ingestion/index.py`
- `backend/app/retrieval/dense.py`
- `scripts/ingest.py`

Requirements:

- Parse 10-K PDFs with `pymupdf4llm`.
- Preserve page numbers in metadata.
- Chunk by markdown sections.
- Do not split inside markdown tables.
- Store chunks in Qdrant.
- Payload must include:
  - `filing_id`
  - `company`
  - `fiscal_year`
  - `section`
  - `page`
  - `text`
- Implement naive dense retrieval with top-k 8 and `filing_id` filtering.
- Replace echo `/chat` with retrieve -> answer.
- Every financial figure must be cited with page and section.

Response shape:

```json
{
  "answer": "string",
  "citations": [
    {
      "page": 12,
      "section": "Liquidity and Capital Resources",
      "snippet": "source text"
    }
  ]
}
```

### Phase 2 - Agent, Memory, and Tavily

Add these files:

- `backend/app/agent/graph.py`
- `backend/app/agent/tools.py`
- `backend/app/agent/prompts.py`

Requirements:

- Use LangGraph.
- Use `MemorySaver` checkpointer for v1.
- Frontend-generated `thread_id` must be passed into the graph.
- Add two tools:
  - `retrieve_filing(query, filing_id)`
  - `tavily_search(query)`
- Company-specific financial figures must come from filing retrieval.
- Market, industry, and recent external context may come from Tavily.
- Never present Tavily numbers as SEC filing numbers.

### Phase 3 - Memo Section

Add:

- `backend/app/memo.py`
- `/memo` route
- frontend "Draft memo section" button

The memo endpoint should:

1. Retrieve financial statement and risk chunks.
2. Extract key figures into a Pydantic model.
3. Compute ratios where possible.
4. Generate "Financial Summary & Risk Factors."
5. Include citations.

Key figures:

- Revenue
- Net income
- Total debt
- Cash
- Current assets
- Current liabilities

If a value is not found, return `null` and say "not disclosed in reviewed filings." Never invent.

### Phase 4 - Evals and Retrieval Improvement

Add:

- `data/golden/questions.jsonl`
- `data/golden/numeric_truth.jsonl`
- `evals/numeric_eval.py`
- `evals/run_evals.py`
- `backend/app/retrieval/hybrid.py`

Requirements:

- Numeric exact-match scoring with unit and scale normalization.
- 0.5% tolerance for rounding.
- Ragas metrics:
  - faithfulness
  - context precision
  - answer relevancy
- Run evals for both:
  - naive dense
  - hybrid retrieval
- Save JSON and markdown results in `evals/results/`.
- Add comparison table to README.

Hybrid retrieval:

- Dense retrieval plus BM25.
- Fuse with reciprocal rank fusion.
- Rerank top 20 to top 6.
- Use Cohere Rerank if available, otherwise local BGE reranker if faster to implement.

### Phase 5 - Submission Polish

Only after Phases 1-4 work:

- Complete README challenge sections.
- Add architecture diagrams.
- Paste eval tables.
- Confirm no secrets committed.
- Run deployed smoke test.
- Test on phone browser.

## Prompt Rules

Answer prompt:

Every financial figure in your answer must be immediately followed by its citation in the format `(page N, section)`. If the retrieved context does not contain the figure, say so explicitly. Never estimate or infer figures.

Agent routing rules:

- SEC filing figures must come from `retrieve_filing`.
- Current market or industry context may come from `tavily_search`.
- If sources conflict, explain the source boundary.
- Do not mix external web data into filing-cited financial values.

Memo prompt:

- Use only retrieved filing context.
- Null fields become "not disclosed in reviewed filings."
- Every material number needs a citation.

## Suggested First SEC Questions

Use these for manual testing after Boeing ingestion:

- What were Boeing's total revenue, net loss, cash, and total debt?
- What liquidity risks did Boeing disclose?
- What risks did Boeing disclose related to aircraft safety and certification?
- What does Boeing say about production disruptions?
- What are the main credit risks for Boeing based on the filing?
- How does Boeing's liquidity compare with Lockheed Martin?

## Development Rules

- Prefer simple, working code.
- Keep env handling centralized in `backend/app/config.py`.
- Keep prompts centralized in `backend/app/agent/prompts.py`.
- Do not hide important logic in notebooks.
- Keep scripts runnable with `python -m` or explicit script commands.
- Pin dependencies.
- If Ragas dependency conflicts take more than one hour, create `evals/requirements.txt` and isolate evals in a separate venv.
- Keep Qdrant to one collection and filter by `filing_id`.
- Keep naive retrieval top-k at 8.
- Keep hybrid final results at top 6 after reranking.
- Do not overbuild UI polish before RAG and evals work.

## Cut List

If time is short, cut in this order:

1. Second retrieval/prompt improvement beyond hybrid retrieval.
2. Memo feature depth.
3. Third filing.
4. UI polish.

Never cut:

- Deployment
- OpenRouter gateway
- Memory
- Agent tool choice
- Eval harness
- Retrieval comparison table

## Definition of Done

- Deployed frontend works on phone and laptop.
- User can select a filing and ask a question.
- Filing question returns correct cited answer.
- Follow-up question uses thread memory.
- Industry/current-context question routes to Tavily.
- Memo section generates with citations.
- `python evals/run_evals.py --pipeline naive` saves results.
- `python evals/run_evals.py --pipeline hybrid` saves results.
- README contains real comparison table.
- `.env.example` is complete.
- No secrets are committed.
- Smoke test passes against deployed backend.

## Important Commands

Backend local dev:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Frontend local dev:

```bash
cd frontend
npm run dev
```

Backend smoke test:

```bash
python scripts/smoke_test.py --backend-url http://localhost:8000
```

Frontend build:

```bash
cd frontend
npm run build
```

## Current Next Step

Deploy the Phase 0 skeleton before adding AI code.

After deployment, start Phase 1 with Boeing 10-K ingestion.
