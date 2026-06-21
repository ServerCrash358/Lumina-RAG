"""schemas.py — request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IngestDocument(BaseModel):
    content: str = Field(..., min_length=1, description="Raw document text to chunk + embed")
    metadata: dict = Field(default_factory=dict, description="Arbitrary tags: source, title, etc.")


class IngestRequest(BaseModel):
    documents: list[IngestDocument] = Field(..., min_length=1)


class IngestResponse(BaseModel):
    documents_received: int
    chunks_created: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=100, description="Defaults to TOP_K_RETRIEVE")


class SearchHit(BaseModel):
    id: str
    content: str
    metadata: dict
    score: float = Field(..., description="Cosine similarity, 1.0 = identical")


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchHit]


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)


class Source(BaseModel):
    content: str
    metadata: dict
    score: float = Field(..., description="Cross-encoder rerank score")


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[Source]
    cached: bool = False
