from __future__ import annotations

import json

from aura.summary_mvp.schema import EvidenceGraph, EvidencePacket


PROMPT_CONTRACT = """You are given ASR transcript evidence chunks and a lightweight knowledge graph.

Task:
Generate a structured meeting summary.

Rules:
1. Do not infer speaker identity.
2. Do not invent decisions.
3. If a point is uncertain, put it under open_questions or low_confidence_sections.
4. Every key point, decision, risk, and next step must be grounded in the provided chunks.
5. Output valid JSON only.
6. Use Traditional Chinese.
"""


SUMMARY_SCHEMA_INSTRUCTIONS = {
    "meeting_summary": "string",
    "main_topics": [{"topic": "string", "evidence_chunks": ["c001"]}],
    "key_points": [{"point": "string", "evidence_chunks": ["c002"]}],
    "decisions_or_tentative_conclusions": [
        {"content": "string", "status": "confirmed | tentative | unclear", "evidence_chunks": ["c003"]}
    ],
    "open_questions": [{"question": "string", "evidence_chunks": ["c004"]}],
    "risks_and_constraints": [{"risk": "string", "evidence_chunks": ["c005"]}],
    "possible_next_steps": [{"step": "string", "confidence": "high | medium | low", "evidence_chunks": ["c006"]}],
    "low_confidence_sections": [
        {"reason": "ASR unclear | weak evidence | fragmented context", "evidence_chunks": ["c007"]}
    ],
}


def assemble_summary_prompt(
    meeting_id: str,
    evidence_packets: list[EvidencePacket],
    graph: EvidenceGraph,
) -> str:
    evidence_payload = [packet.to_dict() for packet in evidence_packets]
    graph_payload = graph.to_dict()
    return (
        f"{PROMPT_CONTRACT}\n"
        f"Meeting ID: {meeting_id}\n\n"
        "Required JSON schema:\n"
        f"{json.dumps(SUMMARY_SCHEMA_INSTRUCTIONS, ensure_ascii=False, indent=2)}\n\n"
        "Evidence packets:\n"
        f"{json.dumps(evidence_payload, ensure_ascii=False, indent=2)}\n\n"
        "Lightweight graph:\n"
        f"{json.dumps(graph_payload, ensure_ascii=False, indent=2)}\n"
    )
