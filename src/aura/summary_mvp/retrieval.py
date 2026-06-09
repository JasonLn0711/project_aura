from __future__ import annotations

from aura.summary_mvp.embeddings import cosine_similarity, deterministic_embedding
from aura.summary_mvp.graph import graph_neighbors_by_chunk
from aura.summary_mvp.schema import EvidenceGraph, EvidencePacket, SummaryMode, TranscriptChunk


RETRIEVAL_QUERIES: dict[str, str] = {
    "main_topics": "main topics discussed in the meeting",
    "key_points": "important facts and key points",
    "decisions_or_tentative_conclusions": "important decisions or tentative conclusions",
    "open_questions": "open questions and unresolved issues",
    "risks_and_constraints": "risks constraints blockers limitations",
    "possible_next_steps": "possible next steps follow up work",
}


def retrieve_chunks(
    query: str,
    chunks: list[TranscriptChunk],
    chunk_embeddings: dict[str, list[float]],
    top_k: int = 4,
) -> list[TranscriptChunk]:
    if top_k <= 0:
        raise ValueError("top_k must be positive.")
    query_embedding = deterministic_embedding(query)
    scored = [
        (cosine_similarity(query_embedding, chunk_embeddings[chunk.chunk_id]), chunk)
        for chunk in chunks
    ]
    scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
    return [chunk for _, chunk in scored[:top_k]]


def build_evidence_packets(
    chunks: list[TranscriptChunk],
    chunk_embeddings: dict[str, list[float]],
    graph: EvidenceGraph,
    mode: SummaryMode,
    top_k: int = 4,
) -> list[EvidencePacket]:
    if mode == "direct":
        return [
            EvidencePacket(
                summary_field="meeting_summary",
                query="full transcript compact context",
                retrieved_chunks=chunks,
                graph_neighbors=[],
            )
        ]

    neighbor_index = graph_neighbors_by_chunk(graph) if mode == "graph_rag" else {}
    packets: list[EvidencePacket] = []
    for field_name, query in RETRIEVAL_QUERIES.items():
        retrieved = retrieve_chunks(query, chunks, chunk_embeddings, top_k=top_k)
        neighbors: list[str] = []
        if mode == "graph_rag":
            for chunk in retrieved:
                neighbors.extend(neighbor_index.get(chunk.chunk_id, []))
            neighbors = sorted(set(neighbors))
        packets.append(
            EvidencePacket(
                summary_field=field_name,
                query=query,
                retrieved_chunks=retrieved,
                graph_neighbors=neighbors,
            )
        )
    return packets
