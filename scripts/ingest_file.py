"""
ingest_file.py — load any text/markdown file into Lumina.

Splits a markdown file on its `## ` section headers (so each section becomes a
cleanly-tagged document); for a plain .txt it ingests the whole file and lets
the chunker split it. This is the everyday "add a document" tool.

Usage:
    uv run --with httpx python scripts/ingest_file.py <file> [base_url]
    uv run --with httpx python scripts/ingest_file.py sample_docs/solar_system.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx


def to_documents(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    source = path.stem
    # Split on H2 headers if present; else treat the whole file as one document.
    sections = re.split(r"(?m)^##\s+", text)
    docs: list[dict] = []
    for sec in sections:
        sec = sec.strip()
        if not sec or sec.startswith("#"):  # skip the top H1/title block
            continue
        title = sec.splitlines()[0].strip()
        docs.append({"content": sec, "metadata": {"source": source, "title": title}})
    if not docs:  # no H2 sections → whole file as one doc
        docs = [{"content": text.strip(), "metadata": {"source": source}}]
    return docs


def main() -> None:
    path = Path(sys.argv[1])
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8090"
    docs = to_documents(path)
    resp = httpx.post(f"{base_url}/ingest", json={"documents": docs}, timeout=180)
    resp.raise_for_status()
    print(f"ingested {path.name}: {resp.json()}")


if __name__ == "__main__":
    main()
