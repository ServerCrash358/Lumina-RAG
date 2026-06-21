"""
generator.py — the "G" in RAG: turn retrieved context into a grounded answer.

PROVIDER-AGNOSTIC BY DESIGN. We use the OpenAI Python client, but point it at
whatever OpenAI-compatible endpoint is in config:
  * default → Ollama at http://localhost:11434/v1 (local, free, GPU if available)
  * swap    → Groq / OpenAI / any compatible host by changing LLM_BASE_URL + key
No code change to switch — just config. That portability is the whole point.

The system prompt constrains the model to answer ONLY from the supplied context,
which is what makes RAG "grounded" and reduces hallucination.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from app.config import get_settings

_SYSTEM = (
    "You are a precise assistant. Answer the user's question using ONLY the "
    "provided context. If the context does not contain the answer, say you "
    "don't know. Be concise and cite nothing outside the context."
)


def _client() -> AsyncOpenAI:
    s = get_settings()
    # api_key is required by the client but ignored by Ollama; any string works.
    return AsyncOpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key or "not-needed")


async def generate(question: str, contexts: list[str]) -> str:
    s = get_settings()
    context_block = "\n\n---\n\n".join(contexts)
    resp = await _client().chat.completions.create(
        model=s.llm_model,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Context:\n{context_block}\n\nQuestion: {question}"},
        ],
    )
    return resp.choices[0].message.content or ""
