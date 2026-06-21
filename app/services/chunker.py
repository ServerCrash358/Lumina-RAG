"""
chunker.py — split long documents into overlapping chunks for embedding.

Why chunk at all: an embedding compresses a whole passage into one vector, so a
huge document becomes one blurry point that matches everything weakly. Splitting
into ~paragraph-sized pieces keeps each vector semantically focused, and overlap
prevents a relevant sentence from being orphaned at a chunk boundary.

This is a simple sliding-window splitter that prefers to break at sentence/word
boundaries. The roadmap lists fancier strategies (recursive, semantic, late
chunking) — easy to swap in later behind this same interface.
"""

from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    text = " ".join(text.split())  # collapse whitespace/newlines
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # prefer a sentence boundary in the back half of the window,
            # else fall back to the last space, to avoid cutting mid-word.
            dot = text.rfind(". ", start + chunk_size // 2, end)
            brk = dot + 1 if dot != -1 else text.rfind(" ", start, end)
            if brk > start:
                end = brk
        chunks.append(text[start:end].strip())
        start = max(end - overlap, start + 1)  # step forward, keeping overlap
    return [c for c in chunks if c]
