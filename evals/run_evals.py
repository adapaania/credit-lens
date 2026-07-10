"""Run naive-dense vs hybrid retrieval evals: numeric exact-match + Ragas.

Usage:
    cd backend && source .venv/bin/activate
    python ../evals/run_evals.py --pipeline naive
    python ../evals/run_evals.py --pipeline hybrid

Saves evals/results/{pipeline}_results.json and .md.
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(EVALS_DIR))

from app.config import get_settings  # noqa: E402
from app.retrieval.dense import retrieve as dense_retrieve  # noqa: E402
from app.retrieval.hybrid import retrieve as hybrid_retrieve  # noqa: E402
from cohere_langchain_embeddings import CohereLangchainEmbeddings  # noqa: E402
from numeric_eval import numeric_match  # noqa: E402
from pipeline import answer_with_retrieval  # noqa: E402

RETRIEVE_FNS = {"naive": dense_retrieve, "hybrid": hybrid_retrieve}

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "golden"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def run_pipeline(pipeline_name: str) -> list[dict]:
    retrieve_fn = RETRIEVE_FNS[pipeline_name]
    questions = load_jsonl(DATA_DIR / "questions.jsonl")
    truths = {t["truth_id"]: t for t in load_jsonl(DATA_DIR / "numeric_truth.jsonl")}

    per_question = []
    for question in questions:
        print(f"  [{pipeline_name}] {question['id']} ...", flush=True)
        result = answer_with_retrieval(
            question["question"], filing_id=question["filing_id"], retrieve_fn=retrieve_fn
        )
        entry = {
            "id": question["id"],
            "question": question["question"],
            "filing_id": question["filing_id"],
            "type": question["type"],
            "answer": result["answer"],
            "contexts": result["contexts"],
            "citations": result["citations"],
            "reference": question.get("reference", ""),
        }
        if question["type"] == "numeric":
            truth = truths[question["truth_id"]]
            entry["truth_value_millions"] = truth["value_millions"]
            entry["numeric_correct"] = numeric_match(result["answer"], truth["value_millions"])
        per_question.append(entry)
    return per_question


def run_ragas(per_question: list[dict]) -> dict:
    from langchain_openai import ChatOpenAI
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, context_precision, faithfulness

    settings = get_settings()
    llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=0,
        )
    )
    embeddings = LangchainEmbeddingsWrapper(CohereLangchainEmbeddings())

    samples = [
        SingleTurnSample(
            user_input=entry["question"],
            response=entry["answer"],
            retrieved_contexts=entry["contexts"] or [""],
            reference=entry.get("reference") or "",
        )
        for entry in per_question
    ]
    dataset = EvaluationDataset(samples=samples)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=llm,
        embeddings=embeddings,
        raise_exceptions=False,
    )
    df = result.to_pandas()

    # Attach per-question Ragas scores back onto the entries for the report.
    for i, entry in enumerate(per_question):
        entry["ragas"] = {
            "faithfulness": _safe_float(df.loc[i, "faithfulness"]),
            "answer_relevancy": _safe_float(df.loc[i, "answer_relevancy"]),
            "context_precision": _safe_float(df.loc[i, "context_precision"]),
        }

    return {
        "faithfulness": _safe_float(df["faithfulness"].mean(skipna=True)),
        "answer_relevancy": _safe_float(df["answer_relevancy"].mean(skipna=True)),
        "context_precision": _safe_float(df["context_precision"].mean(skipna=True)),
    }


def _safe_float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None  # filter NaN


def summarize(pipeline_name: str, per_question: list[dict], ragas_scores: dict) -> dict:
    numeric_entries = [e for e in per_question if e["type"] == "numeric"]
    numeric_correct = sum(1 for e in numeric_entries if e["numeric_correct"])
    return {
        "pipeline": pipeline_name,
        "num_questions": len(per_question),
        "num_numeric": len(numeric_entries),
        "numeric_correct": numeric_correct,
        "numeric_accuracy": (numeric_correct / len(numeric_entries)) if numeric_entries else None,
        "ragas": ragas_scores,
        "questions": per_question,
    }


def write_markdown(summary: dict, path: Path) -> None:
    ragas = summary["ragas"]
    lines = [
        f"# Eval results: {summary['pipeline']}",
        "",
        f"- Numeric accuracy: {summary['numeric_accuracy']:.1%} "
        f"({summary['numeric_correct']}/{summary['num_numeric']})",
        f"- Faithfulness: {ragas['faithfulness']:.3f}" if ragas["faithfulness"] is not None else "- Faithfulness: n/a",
        f"- Answer relevancy: {ragas['answer_relevancy']:.3f}"
        if ragas["answer_relevancy"] is not None
        else "- Answer relevancy: n/a",
        f"- Context precision: {ragas['context_precision']:.3f}"
        if ragas["context_precision"] is not None
        else "- Context precision: n/a",
        "",
        "## Per-question detail",
        "",
        "| id | type | numeric correct | faithfulness | answer relevancy | context precision |",
        "|---|---|---|---|---|---|",
    ]
    for entry in summary["questions"]:
        numeric_flag = ""
        if entry["type"] == "numeric":
            numeric_flag = "yes" if entry["numeric_correct"] else "no"
        r = entry.get("ragas", {})
        fmt = lambda v: f"{v:.2f}" if v is not None else "n/a"  # noqa: E731
        lines.append(
            f"| {entry['id']} | {entry['type']} | {numeric_flag} | "
            f"{fmt(r.get('faithfulness'))} | {fmt(r.get('answer_relevancy'))} | {fmt(r.get('context_precision'))} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CreditLens retrieval evals.")
    parser.add_argument("--pipeline", choices=["naive", "hybrid"], required=True)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Running {args.pipeline} pipeline over golden questions...")
    per_question = run_pipeline(args.pipeline)

    print("Scoring with Ragas (faithfulness, answer_relevancy, context_precision)...")
    ragas_scores = run_ragas(per_question)

    summary = summarize(args.pipeline, per_question, ragas_scores)

    json_path = RESULTS_DIR / f"{args.pipeline}_results.json"
    md_path = RESULTS_DIR / f"{args.pipeline}_results.md"
    json_path.write_text(json.dumps(summary, indent=2))
    write_markdown(summary, md_path)

    print(f"Saved {json_path} and {md_path}")
    print(f"Numeric accuracy: {summary['numeric_accuracy']:.1%}")
    print(f"Ragas: {ragas_scores}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
