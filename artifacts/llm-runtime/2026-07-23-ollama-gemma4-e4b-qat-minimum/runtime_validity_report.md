# Ollama Gemma 4 E4B QAT Runtime Validity

Status: `LIVE_MINIMUM_COMPLETED`

## Runtime validity

- `Ollama /api/chat + gemma4:e4b-it-qat + think=true + num_predict=1536`: `valid_target_runtime`.
- `Ollama /api/generate + format=json + think=true`: `blocked_runtime` for AURA because the live server renderer reported thinking disabled for that request.
- `Ollama /api/chat + think=true + num_predict=768`: `blocked_runtime` for the complex decisions and action-items fields because reasoning exhausted the budget before final JSON.

## Live counts

- Final configuration: 12 real model calls, including one complete nine-field product pipeline.
- Complete product-pipeline fields passing schema validation: 9/9.
- Three additional calls returned non-empty reasoning, parseable JSON, and the expected top-level keys.
- Final nine-field summary schema: valid.
- Audio files: not applicable; this is a text-only post-ASR LLM runtime gate.
- Reasoning traces retained: 0. Each call verified a non-empty trace in memory and persisted only final validated content.

## Scope control

This minimum validates local model execution, the reasoning/content separation
contract, structured-output completion, and coexistence with AURA ASR on the
16 GB GPU. It does not establish summary-quality superiority or a vLLM
throughput comparison. Those claims activate with a paired reviewed corpus.
