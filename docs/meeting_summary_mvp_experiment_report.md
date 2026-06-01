# Meeting Summary MVP Experiment Report

This report records the first offline dry-run for `MVP-v0.1: Graph-aware RAG Summary Module for Noisy ASR Meeting Transcripts`.

## Contribution And Evidence

The MVP now provides an offline experiment harness for comparing direct summarization, vector RAG, and graph-aware RAG across the six required settings:

- `qwen_direct`
- `qwen_vector_rag`
- `qwen_graph_rag`
- `gemma_direct`
- `gemma_vector_rag`
- `gemma_graph_rag`

The dry-run evidence is stored under `outputs/summary_mvp/meeting_001_dry_run/`:

- `chunks.json`
- `graph.json`
- `evidence_packets.json`
- `prompts.json`
- `summaries/*.json`
- `validation_results.json`
- `evaluation_report.json`
- `evaluation_report.md`

## Current Dry-Run Result

Fixture: `tests/fixtures/asr_transcripts/synthetic_meeting_001.json`

Run command:

```bash
.venv/bin/python scripts/run_summary_mvp_experiment.py \
  --transcript tests/fixtures/asr_transcripts/synthetic_meeting_001.json \
  --output-dir outputs/summary_mvp/meeting_001_dry_run \
  --dry-run
```

Primary dry-run metrics:

- Unsupported claim rate: `2.0`
- Evidence support rate: `0.75`
- Topic coverage: `1.0`

Full dry-run metrics:

- Schema validity rate: `1.0`
- Decision capture accuracy: pending human-labelled reference set
- Risk / constraint capture accuracy: pending human-labelled reference set
- Open question capture accuracy: pending human-labelled reference set
- Human preference ranking: pending human review
- Human correction time: pending human review

## Model Identifier Check

The model IDs are configurable in the CLI and pipeline. The current defaults are:

- Qwen: `Qwen/Qwen3.5-9B`
- Gemma: `google/gemma-4-E4B-it`

Current source check:

- Hugging Face lists the official Qwen model as `Qwen/Qwen3.5-9B` and the Transformers docs page covers Qwen3.5 dense variants including `Qwen/Qwen3.5-9B`.
- Hugging Face lists the official Gemma instruction-tuned E4B model as `google/gemma-4-E4B-it`; the model card uses the Transformers `AutoModelForImageTextToText` loading path and reports Apache 2.0 licensing for the Gemma 4 E4B family.

The implementation keeps INT8 execution behind `--model-run`. Dry-run mode remains the default validation path and does not download models or allocate GPU memory.

## Model-Run Preflight

Model-run command:

```bash
.venv/bin/python scripts/run_summary_mvp_experiment.py \
  --transcript tests/fixtures/asr_transcripts/synthetic_meeting_001.json \
  --output-dir outputs/summary_mvp/meeting_001_model_run_preflight \
  --model-run
```

Current blocker:

- The active `.venv` does not include `torch`, `transformers`, `bitsandbytes`, or `accelerate`, so INT8 model execution cannot start.
- GPU status at preflight time: NVIDIA GeForce RTX 5080, `11122 MiB / 16303 MiB` memory used, `80%` GPU utilization.

The model-run preflight therefore produced blocked statuses for all six settings without downloading model weights or allocating model memory.

## Scope Control

This MVP intentionally stays within the SDD boundary:

- no speaker diarization
- no speaker identity inference
- no ASR correction
- no fine-tuning
- no owner-specific action item extraction
- no medical or legal conclusion generation
- no PyQt UI integration before offline validation

The next validation layer is to run `--model-run` when GPU memory is available, then compare the generated summaries against a human-labelled reference set for decision, risk, and open-question capture accuracy.
