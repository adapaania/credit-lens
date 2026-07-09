import argparse
import sys
from urllib import request
import json


def get_json(url: str) -> dict:
    with request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the CreditLens backend.")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    args = parser.parse_args()

    base_url = args.backend_url.rstrip("/")
    health = get_json(f"{base_url}/health")
    if health.get("status") != "ok":
        print(f"Health check failed: {health}")
        return 1

    chat = post_json(
        f"{base_url}/chat",
        {
            "message": "What is CreditLens?",
            "filing_id": "boeing-2024-10k",
            "thread_id": "smoke-test",
        },
    )
    if "Echo" not in chat.get("answer", ""):
        print(f"Chat check failed: {chat}")
        return 1

    print("Smoke test passed.")
    print(f"Health: {health}")
    print(f"Chat: {chat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
