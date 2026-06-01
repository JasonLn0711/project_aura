from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

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
