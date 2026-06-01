import json
import unittest
from pathlib import Path

from aura.summary_mvp.chunking import build_time_chunks
from aura.summary_mvp.embeddings import embed_chunks
from aura.summary_mvp.graph import build_evidence_graph
from aura.summary_mvp.prompts import assemble_summary_prompt
from aura.summary_mvp.retrieval import build_evidence_packets
from aura.summary_mvp.schema import load_transcript_payload


FIXTURE = Path("tests/fixtures/asr_transcripts/synthetic_meeting_001.json")


class SummaryMvpGraphRetrievalPromptTests(unittest.TestCase):
    def setUp(self):
        transcript = load_transcript_payload(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.chunks = build_time_chunks(transcript, window_seconds=90)
        self.embeddings = embed_chunks(self.chunks)
        self.graph = build_evidence_graph(self.chunks)

    def test_graph_contains_required_node_and_edge_types(self):
        node_types = {node.node_type for node in self.graph.nodes}
        edge_types = {edge.edge_type for edge in self.graph.edges}

        self.assertIn("Chunk", node_types)
        self.assertIn("Topic", node_types)
        self.assertIn("Constraint", node_types)
        self.assertIn("MENTIONS", edge_types)
        self.assertIn("TEMPORALLY_NEAR", edge_types)

    def test_graph_rag_packets_include_neighbors(self):
        packets = build_evidence_packets(self.chunks, self.embeddings, self.graph, "graph_rag", top_k=2)

        self.assertEqual(len(packets), 6)
        self.assertTrue(any(packet.graph_neighbors for packet in packets))
        self.assertTrue(all(packet.retrieved_chunks for packet in packets))

    def test_prompt_uses_same_json_contract(self):
        packets = build_evidence_packets(self.chunks, self.embeddings, self.graph, "vector_rag", top_k=2)
        prompt = assemble_summary_prompt("meeting_001", packets, self.graph)

        self.assertIn("Do not infer speaker identity", prompt)
        self.assertIn("Use Traditional Chinese", prompt)
        self.assertIn("evidence_chunks", prompt)
        self.assertIn("meeting_001", prompt)


if __name__ == "__main__":
    unittest.main()
