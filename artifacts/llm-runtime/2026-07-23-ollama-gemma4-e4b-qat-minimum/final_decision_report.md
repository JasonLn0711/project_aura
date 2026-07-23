# Project AURA Local LLM Runtime Decision

## Decision

- Production default: Ollama `0.32.1` with `gemma4:e4b-it-qat`.
- Generation contract: `/api/chat`, `think=true`, `format=json`,
  `num_ctx=32768`, `num_predict=1536`, `temperature=0`, and one local
  server-side parallel sequence.
- Operational fallback: none. AURA surfaces a clear runtime error rather than
  substituting a cloud or fallback model.
- Research candidate: vLLM with the official Gemma 4 reasoning parser and a
  compatible quantized checkpoint.
- Next optimization candidate: a same-corpus queue-time, peak-VRAM, schema-pass,
  summary-quality, and human-correction-time benchmark.

## First-principles basis

AURA is a single-user desktop assistant whose scarce resource is shared GPU
memory beside CUDA ASR. The validated Ollama QAT runtime uses the existing
local preflight and model-pull workflow, fits comfortably in the current
resident-memory snapshots, and completes the full product schema. vLLM adds
deployment and GPU-allocation complexity whose primary return is concurrent
serving throughput. That work activates when measured demand establishes the
throughput gap.
