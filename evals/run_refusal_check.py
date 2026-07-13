"""Run the golden "refusal"-type questions through the live production agent
(not the retrieve-then-answer eval pipeline - this specifically tests the
agent's cross-company filing-scope behavior, which depends on the system
prompt, not on retrieval quality).

Usage:
    cd backend && source .venv/bin/activate
    python ../evals/run_refusal_check.py --label after
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(EVALS_DIR))

from app.agent.graph import run_agent  # noqa: E402
from refusal_eval import refusal_ok  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "golden"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CreditLens cross-company refusal check.")
    parser.add_argument("--label", required=True, help="e.g. 'before' or 'after' - used in the output filename")
    args = parser.parse_args()

    questions = [q for q in load_jsonl(DATA_DIR / "questions.jsonl") if q["type"] == "refusal"]

    results = []
    for i, question in enumerate(questions):
        result = run_agent(question["question"], filing_id=question["filing_id"], thread_id=f"refusal-check-{args.label}-{i}")
        answer = result["answer"]
        results.append(
            {
                "id": question["id"],
                "filing_id": question["filing_id"],
                "question": question["question"],
                "asked_company": question["asked_company"],
                "answer": answer,
                "refusal_ok": refusal_ok(answer),
            }
        )
        print(f"  {question['id']}: {'OK' if results[-1]['refusal_ok'] else 'LEAKED'}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / f"refusal_check_{args.label}.json"
    json_path.write_text(json.dumps(results, indent=2))

    passed = sum(1 for r in results if r["refusal_ok"])
    print(f"Saved {json_path}")
    print(f"Refusal-correct: {passed}/{len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
