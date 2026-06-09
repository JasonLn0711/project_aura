from __future__ import annotations

import re
from collections import defaultdict

from aura.summary_mvp.embeddings import cosine_similarity, deterministic_embedding, tokenize
from aura.summary_mvp.schema import EvidenceGraph, GraphEdge, GraphNode, TranscriptChunk


KEYWORD_NODES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Topic", "demo", ("demo", "展示", "示範", "prototype")),
    ("Topic", "deployment", ("部署", "device", "裝置", "local", "本地")),
    ("Topic", "regulatory", ("510", "tfda", "fda", "法規", "送審")),
    ("Constraint", "no_gpu", ("沒有 gpu", "no gpu", "cpu", "算力", "記憶體")),
    ("DecisionCandidate", "tentative_decision", ("先", "決定", "共識", "暫定", "tentative")),
    ("Question", "open_issue", ("?", "？", "確認", "不確定", "要不要", "是否")),
    ("Risk", "risk_or_blocker", ("風險", "blocker", "卡", "限制", "問題")),
)

ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9_.-]{2,}\b")


def _node_id(node_type: str, label: str) -> str:
    safe_label = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_").lower()
    return f"{node_type}_{safe_label}"


def extract_rule_nodes(chunk: TranscriptChunk) -> list[GraphNode]:
    text_lower = chunk.text.lower()
    nodes: list[GraphNode] = []
    for node_type, label, keywords in KEYWORD_NODES:
        if any(keyword.lower() in text_lower for keyword in keywords):
            nodes.append(
                GraphNode(
                    node_id=_node_id(node_type, label),
                    node_type=node_type,
                    label=label,
                    chunk_ids=[chunk.chunk_id],
                )
            )
    for entity in sorted(set(ENTITY_RE.findall(chunk.text))):
        nodes.append(
            GraphNode(
                node_id=_node_id("Entity", entity),
                node_type="Entity",
                label=entity,
                chunk_ids=[chunk.chunk_id],
            )
        )
    return nodes


def build_evidence_graph(chunks: list[TranscriptChunk], related_threshold: float = 0.25) -> EvidenceGraph:
    node_map: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for chunk in chunks:
        chunk_node = GraphNode(
            node_id=f"Chunk_{chunk.chunk_id}",
            node_type="Chunk",
            label=chunk.chunk_id,
            chunk_ids=[chunk.chunk_id],
        )
        node_map[chunk_node.node_id] = chunk_node
        for rule_node in extract_rule_nodes(chunk):
            existing = node_map.get(rule_node.node_id)
            if existing:
                combined = sorted(set(existing.chunk_ids + rule_node.chunk_ids))
                node_map[rule_node.node_id] = GraphNode(
                    node_id=existing.node_id,
                    node_type=existing.node_type,
                    label=existing.label,
                    chunk_ids=combined,
                )
            else:
                node_map[rule_node.node_id] = rule_node
            edges.append(GraphEdge(source=chunk_node.node_id, target=rule_node.node_id, edge_type="MENTIONS"))

    for left, right in zip(chunks, chunks[1:]):
        edges.append(
            GraphEdge(
                source=f"Chunk_{left.chunk_id}",
                target=f"Chunk_{right.chunk_id}",
                edge_type="TEMPORALLY_NEAR",
            )
        )

    embeddings = {chunk.chunk_id: deterministic_embedding(chunk.text) for chunk in chunks}
    for left_index, left in enumerate(chunks):
        for right in chunks[left_index + 1 :]:
            similarity = cosine_similarity(embeddings[left.chunk_id], embeddings[right.chunk_id])
            shared_tokens = set(tokenize(left.text)) & set(tokenize(right.text))
            if similarity >= related_threshold or len(shared_tokens) >= 3:
                edges.append(
                    GraphEdge(
                        source=f"Chunk_{left.chunk_id}",
                        target=f"Chunk_{right.chunk_id}",
                        edge_type="RELATED_TO",
                        weight=round(max(similarity, 0.1), 4),
                    )
                )

    for node in list(node_map.values()):
        if node.node_type in {"Constraint", "DecisionCandidate", "Question", "Risk"}:
            for chunk_id in node.chunk_ids:
                edges.append(
                    GraphEdge(
                        source=node.node_id,
                        target=f"Chunk_{chunk_id}",
                        edge_type="SUPPORTS",
                    )
                )

    return EvidenceGraph(nodes=sorted(node_map.values(), key=lambda item: item.node_id), edges=edges)


def graph_neighbors_by_chunk(graph: EvidenceGraph) -> dict[str, list[str]]:
    neighbors: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        if edge.source.startswith("Chunk_c"):
            chunk_id = edge.source.replace("Chunk_", "")
            neighbors[chunk_id].add(edge.target)
        if edge.target.startswith("Chunk_c"):
            chunk_id = edge.target.replace("Chunk_", "")
            neighbors[chunk_id].add(edge.source)
    return {chunk_id: sorted(values) for chunk_id, values in neighbors.items()}
