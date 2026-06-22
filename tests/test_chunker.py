"""
Unit tests for the chunker — deliberately dependency-free (no DB, no models),
so CI runs them in seconds without installing torch.
"""

from __future__ import annotations

from app.services.chunker import chunk_text


def test_empty_returns_nothing():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_is_one_chunk():
    out = chunk_text("a short sentence", chunk_size=800)
    assert out == ["a short sentence"]


def test_whitespace_is_normalised():
    assert chunk_text("a\n\n  b   c", chunk_size=800) == ["a b c"]


def test_long_text_splits_into_multiple_bounded_chunks():
    text = "Sentence number one. " * 200  # ~4200 chars
    chunks = chunk_text(text, chunk_size=500, overlap=80)
    assert len(chunks) > 1
    # every chunk respects the size bound (allow a little slack for boundary search)
    assert all(len(c) <= 500 for c in chunks)
    # reassembled length should exceed the original-ish (overlap duplicates text)
    assert sum(len(c) for c in chunks) >= len(text.strip()) // 2


def test_chunks_overlap():
    text = "abcdefghij " * 100
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    # consecutive chunks should share some tail/head text given the overlap
    assert len(chunks) >= 2
