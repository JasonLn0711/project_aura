import unittest

from aura.summary_mvp.embeddings import build_embedding_backend, embed_chunks_with_backend
from aura.summary_mvp.schema import TranscriptChunk


class SummaryMvpEmbeddingTests(unittest.TestCase):
    def test_embedding_backend_falls_back_to_deterministic_vectors(self):
        backend = build_embedding_backend(model_id="")
        chunks = [
            TranscriptChunk(chunk_id="c001", start="00:00:01", end="00:00:02", text="demo deployment"),
            TranscriptChunk(chunk_id="c002", start="00:00:03", end="00:00:04", text="regulatory evidence"),
        ]

        embeddings = embed_chunks_with_backend(chunks, backend)

        self.assertFalse(backend.is_local_model)
        self.assertEqual(set(embeddings), {"c001", "c002"})
        self.assertEqual(len(embeddings["c001"]), 64)


if __name__ == "__main__":
    unittest.main()
