# CreditLens

CreditLens is an agentic RAG application for commercial credit analysts. Users select SEC filings, ask credit questions, and receive source-cited answers with financial figures grounded in the filing. The finished version will also draft a credit memo section and include an evaluation harness that checks numeric accuracy.

This repository currently contains the Phase 0 walking skeleton: a deployable FastAPI backend and a responsive Next.js frontend. The first goal is to prove browser -> frontend -> backend works before adding AI, SEC ingestion, Qdrant, LangGraph, or evals.

## Why Start With Phase 0

The project has several moving parts: deployment, CORS, frontend state, backend routes, SEC parsing, vector search, an agent, memory, Tavily, and evals. Starting with a tiny deployed skeleton reduces risk because every later feature has a working place to plug into.

Phase 0 answers one question:

> Can a user on a phone or laptop open the app, send a message, and get a backend response?

Once that is true, the project can safely move into SEC ingestion and RAG.

## Repository Structure

```text
creditlens/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app and CORS setup
│   │   ├── api.py         # /health and /chat routes
│   │   └── config.py      # environment variables
│   ├── requirements.txt
│   ├── Procfile           # Railway process command
│   └── railway.toml       # Railway deployment config
├── frontend/
│   ├── app/
│   │   ├── page.tsx       # Chat UI
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   └── api/chat/route.ts # Frontend proxy to backend
│   ├── package.json
│   └── tailwind.config.ts
├── data/
│   ├── filings/           # SEC filings will go here
│   └── golden/            # Evaluation questions will go here
├── evals/results/         # Saved eval outputs will go here
├── scripts/smoke_test.py  # Checks /health and /chat
└── .env.example
```

## Backend

The backend is a FastAPI service.

`GET /health` returns service status. Deployment platforms use this to confirm the backend is alive.

`POST /chat` currently returns an echo response. This is intentional. In the next phases, this route will call retrieval and then the LangGraph agent.

Example request:

```json
{
  "message": "What are Boeing's major credit risks?",
  "filing_id": "boeing-2024-10k",
  "thread_id": "browser-session-id"
}
```

Example response:

```json
{
  "answer": "Echo for filing `boeing-2024-10k` on thread `browser-session-id`: What are Boeing's major credit risks?",
  "citations": []
}
```

## Frontend

The frontend is a Next.js App Router application with Tailwind.

The page includes:

- A filing selector
- A message thread
- A chat input
- Citation rendering support, even though Phase 0 returns no citations yet
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

With the backend running:

```bash
python scripts/smoke_test.py --backend-url http://localhost:8000
```

The smoke test checks:

- `/health` returns `status: ok`
- `/chat` returns an echo answer

## Deployment

Backend on Railway:

1. Create a Railway project from this repo.
2. Set the service root to `backend`.
3. Add environment variables from `.env.example`.
4. Set `FRONTEND_ORIGIN` to the deployed Vercel URL.
5. Confirm `/health` is reachable.

Frontend on Vercel:

1. Create a Vercel project from this repo.
2. Set the project root to `frontend`.
3. Set `NEXT_PUBLIC_API_URL` to the Railway backend URL.
4. Deploy and test the chat form.

## Recommended SEC Filing Set

For the first demo set, use aerospace and defense:

- Boeing 10-K
- Lockheed Martin 10-K
- RTX 10-K

Boeing gives the strongest story because credit risk connects directly to safety incidents, regulatory scrutiny, production disruptions, lawsuits, reputation damage, cash flow, and debt. Lockheed Martin and RTX provide cleaner peers for comparison.

## Next Build Phases

1. Add SEC filing ingestion with `pymupdf4llm`.
2. Chunk filings by section while preserving tables.
3. Store chunks in Qdrant with page, section, company, fiscal year, and filing id metadata.
4. Add naive dense retrieval.
5. Replace the echo `/chat` with cited RAG answers.
6. Add LangGraph agent tools for filing retrieval and Tavily search.
7. Add `MemorySaver` checkpointer using the frontend thread id.
8. Add memo generation.
9. Add numeric exact-match evals and Ragas evals.
10. Add hybrid retrieval and comparison table.
