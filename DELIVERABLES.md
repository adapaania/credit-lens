# CreditLens Deliverables Traceability

This document maps each rubric deliverable to the exact place it is addressed in the repository. Evidence may live in the narrative write-up (`CERTIFICATION_CHALLENGE.md`), implementation code, evaluation artifacts, deployment configuration, or a combination of those.

Line numbers reference the current `main` branch.

## Task 1: Defining the Problem, Audience, and Scope

| Points | Deliverable | Evidence |
| ---: | --- | --- |
| 1 | One-sentence problem description | [`CERTIFICATION_CHALLENGE.md:13`](CERTIFICATION_CHALLENGE.md#the-problem) |
| 3 | 1-2 paragraphs on why this is a problem for the specific user | [`CERTIFICATION_CHALLENGE.md:17-19`](CERTIFICATION_CHALLENGE.md#who-this-is-for) |
| 3 | Workflow diagram: how the user solves this today | [`CERTIFICATION_CHALLENGE.md:23-36`](CERTIFICATION_CHALLENGE.md#who-this-is-for), Mermaid flowchart |
| 2 | List of questions / input-output pairs to evaluate the app | [`data/golden/questions.jsonl`](data/golden/questions.jsonl) with 27 questions, plus [`data/golden/numeric_truth.jsonl`](data/golden/numeric_truth.jsonl) with 18 hand-verified truth values. Sample table: [`CERTIFICATION_CHALLENGE.md:46-56`](CERTIFICATION_CHALLENGE.md#scope-of-this-build) |

## Task 2: Propose a Solution

| Points | Deliverable | Evidence |
| ---: | --- | --- |
| 1 | One-sentence solution | [`CERTIFICATION_CHALLENGE.md:62`](CERTIFICATION_CHALLENGE.md#the-solution) |
| 7 | Infrastructure diagram + one sentence per tooling choice | [`CERTIFICATION_CHALLENGE.md:68-104`](CERTIFICATION_CHALLENGE.md#how-the-pieces-fit-together), Mermaid diagram. Tooling-choice table: [`CERTIFICATION_CHALLENGE.md:106-118`](CERTIFICATION_CHALLENGE.md#how-the-pieces-fit-together) |
| 7 | Agent workflow diagram, end to end | [`CERTIFICATION_CHALLENGE.md:122-134`](CERTIFICATION_CHALLENGE.md#how-the-agent-decides-what-to-do), Mermaid diagram. Implementation: [`backend/app/agent/graph.py`](backend/app/agent/graph.py), including `StateGraph` at line 71, `MemorySaver` checkpointer at line 77, and `run_agent()` at line 127 |

## Task 3: Dealing with the Data

| Points | Deliverable | Evidence |
| ---: | --- | --- |
| 5 | Data sources and external APIs, and what they are used for | [`CERTIFICATION_CHALLENGE.md:151-165`](CERTIFICATION_CHALLENGE.md#where-the-data-comes-from-and-how-the-two-sources-interact), SEC filing corpus table + Tavily. Code: [`backend/app/agent/tools.py`](backend/app/agent/tools.py), `retrieve_filing` at line 24 and `tavily_search` at line 56. Env vars: [`backend/app/config.py:12-19`](backend/app/config.py) |
| 5 | Default chunking strategy, and why | [`CERTIFICATION_CHALLENGE.md:142-149`](CERTIFICATION_CHALLENGE.md#how-the-filings-are-chunked). Code: [`backend/app/ingestion/chunk.py`](backend/app/ingestion/chunk.py), including `_header_title()` at line 27, bold-vs-italic tuning note at lines 41-43, `_build_blocks()` at line 56, and `chunk_pages()` at line 91 |

## Task 4: Build End-to-End Prototype

| Points | Deliverable | Evidence |
| ---: | --- | --- |
| 15 | End-to-end prototype, deployed with a frontend on Vercel | Live app: <https://credit-lens-teal.vercel.app>. Live backend: <https://credit-lens-production-929c.up.railway.app>. Frontend deploy config: [`frontend/next.config.ts`](frontend/next.config.ts). Backend deploy config: [`backend/Procfile`](backend/Procfile), [`backend/railway.toml`](backend/railway.toml). Proxy routes: [`frontend/app/api/chat/route.ts`](frontend/app/api/chat/route.ts), [`frontend/app/api/memo/route.ts`](frontend/app/api/memo/route.ts). Smoke test: [`scripts/smoke_test.py`](scripts/smoke_test.py), `main()` at line 24. Narrative: [`CERTIFICATION_CHALLENGE.md:169-171`](CERTIFICATION_CHALLENGE.md#getting-it-live) |

## Task 5: Evals

| Points | Deliverable | Evidence |
| ---: | --- | --- |
| 2 | Test dataset | [`data/golden/questions.jsonl`](data/golden/questions.jsonl), 27 questions: 20 numeric, 4 qualitative, 3 refusal. [`data/golden/numeric_truth.jsonl`](data/golden/numeric_truth.jsonl), 18 hand-verified figures with page and section references |
| 10 | Evaluation harness relevant to the problem space | [`evals/run_evals.py`](evals/run_evals.py), including `run_pipeline()` at line 50, `run_ragas()` at line 88, and `write_markdown()` at line 162. Numeric exact-match: [`evals/numeric_eval.py`](evals/numeric_eval.py), including `numeric_match()` at line 47 and unit/scale normalization in `extract_candidate_values()` at line 21. Refusal harness: [`evals/refusal_eval.py`](evals/refusal_eval.py) and [`evals/run_refusal_check.py`](evals/run_refusal_check.py). Results: [`evals/results/`](evals/results/) |
| 3 | Conclusions on pipeline performance/effectiveness | [`CERTIFICATION_CHALLENGE.md:188-198`](CERTIFICATION_CHALLENGE.md#where-things-started-naive-dense-retrieval), naive-dense baseline table + analysis. Full detail: [`evals/results/naive_results.md`](evals/results/naive_results.md) |

## Task 6: Improving the Prototype

| Points | Deliverable | Evidence |
| ---: | --- | --- |
| 6 | Advanced retrieval technique + why it should help this use case | [`CERTIFICATION_CHALLENGE.md:203-207`](CERTIFICATION_CHALLENGE.md#fix-one-hybrid-retrieval-instead-of-naive-dense). Code: [`backend/app/retrieval/hybrid.py`](backend/app/retrieval/hybrid.py), including dense + BM25 fusion via `_reciprocal_rank_fusion()` at line 90, `RRF_K=60` at line 20, reranking via `_rerank()` at line 104, and entry point `retrieve()` at line 117 |
| 2 | Performance comparison table vs. original RAG | [`CERTIFICATION_CHALLENGE.md:209-216`](CERTIFICATION_CHALLENGE.md#fix-one-hybrid-retrieval-instead-of-naive-dense), naive vs. hybrid table. Full detail: [`evals/results/hybrid_results.md`](evals/results/hybrid_results.md) |
| 6 | At least one more improvement, with hard evaluation evidence | Two documented improvements: query rewriting and filing-scoped refusal. Query rewriting: [`CERTIFICATION_CHALLENGE.md:218-243`](CERTIFICATION_CHALLENGE.md#fix-two-rewriting-the-query-before-it-hits-the-retriever), [`backend/app/retrieval/query_rewrite.py`](backend/app/retrieval/query_rewrite.py), `rewrite_query()` at line 45, production wiring at [`backend/app/agent/tools.py:34`](backend/app/agent/tools.py), and results in [`evals/results/hybrid-rewrite_results.md`](evals/results/hybrid-rewrite_results.md). Filing-scoped refusal: [`CERTIFICATION_CHALLENGE.md:245-259`](CERTIFICATION_CHALLENGE.md#fix-three-closing-a-cross-company-citation-leak), [`backend/app/agent/prompts.py:9`](backend/app/agent/prompts.py), before/after evidence in [`evals/results/refusal_check.md`](evals/results/refusal_check.md), [`evals/results/refusal_check_before.json`](evals/results/refusal_check_before.json), and [`evals/results/refusal_check_after.json`](evals/results/refusal_check_after.json) |

## Task 7: Next Steps

| Points | Deliverable | Evidence |
| ---: | --- | --- |
| 2 | What to keep / what to change for Demo Day | [`CERTIFICATION_CHALLENGE.md:272-286`](CERTIFICATION_CHALLENGE.md#whats-next) |

## Final Submission

| Points | Deliverable | Evidence |
| ---: | --- | --- |
| 10 | Public GitHub repo | <https://github.com/adapaania/credit-lens> |
| 10 | <=10-minute Loom demo video, live demo + use case | <https://www.loom.com/share/13f3332517bb42568cab1fa0a4d6087f> |
| 10 | Written document addressing each deliverable | [`CERTIFICATION_CHALLENGE.md`](CERTIFICATION_CHALLENGE.md) - in-repo write-up, and [`CERTIFICATION_CHALLENGE.pdf`](CERTIFICATION_CHALLENGE.pdf) - the same content as a submission-ready PDF |
| 0 | All relevant code | This repository: `backend/`, `frontend/`, `evals/`, `scripts/`, and `data/` |
