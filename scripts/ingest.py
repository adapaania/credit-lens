"""Ingest SEC 10-K PDFs from data/filings/ into Qdrant.

Usage:
    cd backend && source .venv/bin/activate
    python ../scripts/ingest.py
    python ../scripts/ingest.py --filing-id boeing-2024-10k
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ingestion.chunk import chunk_pages  # noqa: E402
from app.ingestion.index import delete_filing, index_chunks  # noqa: E402
from app.ingestion.parse import parse_filing_pdf  # noqa: E402

FILINGS = {
    "boeing-2024-10k": {"company": "Boeing", "fiscal_year": 2024},
    "lockheed-2024-10k": {"company": "Lockheed Martin", "fiscal_year": 2024},
    "rtx-2024-10k": {"company": "RTX", "fiscal_year": 2024},
}


def ingest_one(pdf_path: Path, filing_id: str, company: str, fiscal_year: int) -> None:
    print(f"Parsing {pdf_path.name} ...")
    pages = parse_filing_pdf(pdf_path)
    print(f"  {len(pages)} pages parsed")

    chunks = chunk_pages(pages)
    print(f"  {len(chunks)} chunks created")

    delete_filing(filing_id)
    count = index_chunks(chunks, filing_id=filing_id, company=company, fiscal_year=fiscal_year)
    print(f"  {count} points indexed into Qdrant for filing_id={filing_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest SEC 10-K PDFs into Qdrant.")
    parser.add_argument("--filings-dir", default=str(Path(__file__).resolve().parent.parent / "data" / "filings"))
    parser.add_argument("--filing-id", default=None, help="Only ingest this filing_id")
    args = parser.parse_args()

    filings_dir = Path(args.filings_dir)
    targets = [args.filing_id] if args.filing_id else list(FILINGS.keys())

    for filing_id in targets:
        if filing_id not in FILINGS:
            print(f"Unknown filing_id: {filing_id}", file=sys.stderr)
            return 1
        pdf_path = filings_dir / f"{filing_id}.pdf"
        if not pdf_path.exists():
            print(f"Missing PDF: {pdf_path}", file=sys.stderr)
            return 1
        meta = FILINGS[filing_id]
        ingest_one(pdf_path, filing_id, meta["company"], meta["fiscal_year"])

    print("Ingestion complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
