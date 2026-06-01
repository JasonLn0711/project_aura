from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass

from aura.summary_mvp.schema import TranscriptChunk


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def deterministic_embedding(text: str, dimensions: int = 64) -> list[float]:
    if dimensions <= 0:
        raise ValueError("dimensions must be positive.")
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def embed_chunks(chunks: Iterable[TranscriptChunk], dimensions: int = 64) -> dict[str, list[float]]:
    return {chunk.chunk_id: deterministic_embedding(chunk.text, dimensions) for chunk in chunks}


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Vectors must have the same length.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


@dataclass(frozen=True)
class EmbeddingBackendConfig:
    model_id: str = ""
    dimensions: int = 64


class LocalEmbeddingBackend:
    """Optional local sentence-transformers backend with deterministic fallback."""

    def __init__(self, config: EmbeddingBackendConfig):
        self.config = config
        self._model = None
        if config.model_id:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError("sentence-transformers is not installed for local embeddings.") from exc
            self._model = SentenceTransformer(config.model_id)

    @property
    def is_local_model(self) -> bool:
        return self._model is not None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            return [deterministic_embedding(text, self.config.dimensions) for text in texts]
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]


def build_embedding_backend(model_id: str | None = None, dimensions: int = 64) -> LocalEmbeddingBackend:
    configured_model = model_id or os.environ.get("AURA_SUMMARY_MVP_EMBEDDING_MODEL", "")
    try:
        return LocalEmbeddingBackend(EmbeddingBackendConfig(model_id=configured_model, dimensions=dimensions))
    except RuntimeError:
        return LocalEmbeddingBackend(EmbeddingBackendConfig(model_id="", dimensions=dimensions))


def embed_chunks_with_backend(
    chunks: Iterable[TranscriptChunk],
    backend: LocalEmbeddingBackend | None = None,
) -> dict[str, list[float]]:
    chunk_list = list(chunks)
    embedding_backend = backend or build_embedding_backend()
    vectors = embedding_backend.embed_texts([chunk.text for chunk in chunk_list])
    return {chunk.chunk_id: vector for chunk, vector in zip(chunk_list, vectors)}
