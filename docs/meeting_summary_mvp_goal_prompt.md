# Meeting Summary MVP Goal Prompt

This prompt is the execution prompt for implementing `MVP-v0.1: Graph-aware RAG Summary Module for Noisy ASR Meeting Transcripts`. It should be used after reading `docs/meeting_summary_mvp_sdd.md`. The prompt keeps the MVP bounded to an offline experiment harness before PyQt UI integration.

```text
You are working in /home/jnclaw/every_on_git_jnclaw/project_aura.

Goal:
Implement MVP-v0.1: Graph-aware RAG Summary Module for Noisy ASR Meeting Transcripts.

FIRST PRINCIPLE:
The goal is not to prove that small language models can summarize. The goal is to test whether Graph Knowledge + RAG improves structured, evidence-grounded meeting summaries under these constraints:
- input is ASR transcript
- no speaker diarization
- no ASR correction
- no owner-specific action item extraction
- models are below 10B and run in INT8 quantized form
- output must cite transcript chunks as evidence
- unsupported claims must be measurable

Canonical docs:
- Read docs/meeting_summary_mvp_sdd.md first.
- Treat docs/meeting_summary_target_architecture.md as longer-term context only.
- Do not expand MVP-v0.1 into the full ASR Gate / verifier / action-item-owner system.

MVP scope:
Input:
A JSON ASR transcript:
{
  "meeting_id": "meeting_001",
  "asr_transcript": [
    {
      "start": "00:00:01",
      "end": "00:00:12",
      "text": "..."
    }
  ]
}

Output:
A structured meeting summary JSON:
{
  "meeting_summary": "string",
  "main_topics": [
    {
      "topic": "string",
      "evidence_chunks": ["c001"]
    }
  ],
  "key_points": [
    {
      "point": "string",
      "evidence_chunks": ["c002"]
    }
  ],
  "decisions_or_tentative_conclusions": [
    {
      "content": "string",
      "status": "confirmed | tentative | unclear",
      "evidence_chunks": ["c003"]
    }
  ],
  "open_questions": [
    {
      "question": "string",
      "evidence_chunks": ["c004"]
    }
  ],
  "risks_and_constraints": [
    {
      "risk": "string",
      "evidence_chunks": ["c005"]
    }
  ],
  "possible_next_steps": [
    {
      "step": "string",
      "confidence": "high | medium | low",
      "evidence_chunks": ["c006"]
    }
  ],
  "low_confidence_sections": [
    {
      "reason": "ASR unclear | weak evidence | fragmented context",
      "evidence_chunks": ["c007"]
    }
  ]
}

Non-goals:
- Do not implement speaker diarization.
- Do not infer speaker identity.
- Do not output "Jason said", "Prof. Wu said", or named-speaker claims.
- Do not implement ASR correction.
- Do not implement fine-tuning.
- Do not extract owner-specific action items.
- Do not generate medical/legal conclusions.
- Do not implement autonomous decision-making.
- Do not integrate into PyQt UI yet unless all offline MVP tests are complete and the repo already has a clear integration point.

Implementation target:
Build an offline experiment harness before UI integration.

Suggested module structure:
- src/aura/summary_mvp/
  - schema.py
  - chunking.py
  - embeddings.py
  - graph.py
  - retrieval.py
  - prompts.py
  - models.py
  - validation.py
  - evaluation.py
  - pipeline.py
- scripts/run_summary_mvp_experiment.py
- tests/test_summary_mvp_*.py
- docs/meeting_summary_mvp_experiment_report.md

Required pipeline:
1. Load ASR transcript JSON.
2. Build transcript chunks.
   - v0.1 must support time-based chunking.
   - v0.1 must support sliding-window chunking.
   - Semantic chunking is deferred to v0.2.
3. Embed chunks.
   - Use a local embedding backend when available.
   - Provide a deterministic fallback for tests so CI does not need model downloads.
4. Build lightweight evidence graph.
   Node types:
   - Chunk
   - Topic
   - Entity
   - Constraint
   - DecisionCandidate
   - Question
   - Risk

   Edge types:
   - MENTIONS
   - RELATED_TO
   - SUPPORTS
   - CONTRADICTS
   - TEMPORALLY_NEAR

   MVP graph can be rule + embedding based. Do not train a graph model.
5. Implement retrieval modes:
   - direct summary: full transcript or compact transcript context
   - vector RAG: vector-retrieved chunks only
   - graph RAG: vector-retrieved chunks + graph-neighbor evidence
6. Assemble summary prompt.
   The same prompt contract must be used for both models:

   You are given ASR transcript evidence chunks and a lightweight knowledge graph.

   Task:
   Generate a structured meeting summary.

   Rules:
   1. Do not infer speaker identity.
   2. Do not invent decisions.
   3. If a point is uncertain, put it under open_questions or low_confidence_sections.
   4. Every key point, decision, risk, and next step must be grounded in the provided chunks.
   5. Output valid JSON only.
   6. Use Traditional Chinese.

7. Add INT8 model runners:
   - Qwen 3.5 9B INT8
   - Gemma 4 E4B INT8

   Before downloading or hardcoding model IDs, verify the exact local/official model identifiers and license/runtime requirements. Keep model IDs configurable.
   If the models cannot run in the current environment, preserve the pipeline, tests, and dry-run mode, and report the exact blocker.

8. Run six experiment settings:
   - qwen_direct
   - qwen_vector_rag
   - qwen_graph_rag
   - gemma_direct
   - gemma_vector_rag
   - gemma_graph_rag

9. Implement schema and evidence checks.
   Required checks:
   - output is valid JSON
   - required fields exist
   - evidence_chunks refer to real chunk IDs
   - key_points / decisions / risks / possible_next_steps include evidence_chunks
   - no speaker attribution appears
   - possible_next_steps do not include owner-specific action item claims
   - unsupported claims are counted when no evidence chunk supports the statement

10. Produce evaluation report.
   Metrics:
   - Schema validity rate
   - Evidence support rate
   - Unsupported claim rate
   - Topic coverage
   - Decision capture accuracy
   - Risk / constraint capture accuracy
   - Open question capture accuracy
   - Human preference ranking placeholder
   - Human correction time placeholder

   Most important:
   - Unsupported claim rate
   - Evidence support rate
   - Topic coverage

Deliverables:
- Offline runnable MVP experiment script.
- Unit tests for chunking, schema validation, evidence checking, graph construction, retrieval packet construction, and prompt assembly.
- At least one synthetic ASR transcript fixture.
- Dry-run mode that does not require downloading Qwen/Gemma.
- Clear model-run mode that attempts INT8 quantized inference if dependencies and hardware are available.
- Experiment output directory with:
  - chunks.json
  - graph.json
  - evidence_packets.json
  - summaries/*.json
  - evaluation_report.json
  - evaluation_report.md

Validation:
Run:
- git diff --check
- make check PYTHON=.venv/bin/python
- the new summary MVP unit tests
- the experiment script in dry-run mode

Commit policy:
Make separate logical commits:
1. implementation modules
2. tests / fixtures
3. docs / experiment report updates

Do not push until validation is complete.
Do not force-push.
If remote main has advanced, fetch and reconcile while preserving both local and remote commits.

Final response must report:
- files created/changed
- commands run
- validation results
- whether Qwen/Gemma model execution actually ran or was blocked
- exact blocker if model execution was not possible
- commit hashes if committed
```
