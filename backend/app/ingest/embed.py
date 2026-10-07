"""
Local embeddings for opinion chunks.

Uses a 768-dimension model so it matches opinion_chunks.embedding.
Does not call Groq — that budget is for Alex's agent runs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List

# 384-d bge-small: fast enough to embed the full corpus on CPU
MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=MODEL_NAME)


def embed_passages(texts: Iterable[str]) -> List[List[float]]:
    vectors = []
    for vec in _model().embed(list(texts), batch_size=64):
        vectors.append([float(x) for x in vec])
    return vectors


def embed_query(text: str) -> List[float]:
    prefixed = QUERY_PREFIX + text
    return embed_passages([prefixed])[0]


def vector_literal(values: List[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in values) + "]"
