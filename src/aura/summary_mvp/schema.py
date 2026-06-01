from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ChunkingMode = Literal["time", "sliding"]
SummaryMode = Literal["direct", "vector_rag", "graph_rag"]
DecisionStatus = Literal["confirmed", "tentative", "unclear"]
NextStepConfidence = Literal["high", "medium", "low"]
LowConfidenceReason = Literal["ASR unclear", "weak evidence", "fragmented context"]


@dataclass(frozen=True)
class TranscriptSegment:
    start: str
    end: str
    text: str


@dataclass(frozen=True)
class Transcript:
    meeting_id: str
    asr_transcript: list[TranscriptSegment]


@dataclass(frozen=True)
class TranscriptChunk:
    chunk_id: str
    start: str
    end: str
    text: str
    source_segment_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    label: str
    chunk_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    edge_type: str
    weight: float = 1.0


@dataclass(frozen=True)
class EvidenceGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }


@dataclass(frozen=True)
class EvidencePacket:
    summary_field: str
    query: str
    retrieved_chunks: list[TranscriptChunk]
    graph_neighbors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_field": self.summary_field,
            "query": self.query,
            "retrieved_chunks": [chunk.to_dict() for chunk in self.retrieved_chunks],
            "graph_neighbors": self.graph_neighbors,
        }


def load_transcript_payload(payload: dict[str, Any]) -> Transcript:
    meeting_id = str(payload.get("meeting_id", "")).strip()
    if not meeting_id:
        raise ValueError("Transcript JSON must include a non-empty meeting_id.")
    raw_segments = payload.get("asr_transcript")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("Transcript JSON must include a non-empty asr_transcript list.")

    segments: list[TranscriptSegment] = []
    for index, raw in enumerate(raw_segments, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Transcript segment {index} must be an object.")
        start = str(raw.get("start", "")).strip()
        end = str(raw.get("end", "")).strip()
        text = str(raw.get("text", "")).strip()
        if not start or not end or not text:
            raise ValueError(f"Transcript segment {index} must include start, end, and text.")
        segments.append(TranscriptSegment(start=start, end=end, text=text))
    return Transcript(meeting_id=meeting_id, asr_transcript=segments)
