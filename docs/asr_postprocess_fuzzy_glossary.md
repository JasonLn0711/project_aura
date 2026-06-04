# ASR Post-Processing: Fuzzy Glossary Correction

## Contribution And Scope

Project AURA now has a controlled ASR post-processing layer for Breeze-ASR-25 transcript artifacts. The first supported capability is conservative fuzzy matching against a domain glossary. The goal is to improve high-confidence domain terms while preserving the original ASR transcript and avoiding silent natural-language rewriting.

The first implementation intentionally does not use LLM verification. The validation path is to run the corrector on 10-20 existing transcripts, inspect `correction_log.json`, then decide whether a later gray-zone LLM verifier is justified.

## Pipeline

```text
Breeze-ASR audio transcription
↓
raw_transcript.txt
↓
domain glossary fuzzy correction
↓
corrected_transcript.txt
↓
correction_log.json
↓
summary
```

Artifact naming uses the existing transcript artifact base:

```text
{base}_raw.txt
{base}_corrected.txt
{base}_correction_log.json
{base}_final.txt
{base}_summary.txt
{base}_processing_metrics.json
```

`raw.txt` remains the original ASR output. `corrected.txt` is the glossary-corrected transcript. `final.txt` uses the corrected transcript plus the optional summary. The correction log records each accepted correction for audit and research use.

## Glossary

The glossary is stored outside the code:

```text
config/domain_glossary.yaml
```

The initial glossary is seeded from the current repository documents, transcript fixtures, the project terms provided for this implementation pass, a local scan of 55 transcript `.txt` files under the workspace, and repo-safe term extraction from `Gmail - meeting in this week.pdf` plus `Gmail - Fwd_ 主旨：邀請交流 AI 與細胞精準醫療合作之可能性.pdf`. Raw email text and contact evidence stay outside git. The glossary contains organizations, medical terms, technical terms, people, thresholds, `llm_verification: false`, and explicit aliases for common ASR variants such as:

```text
志德灣 -> 智德萬
會成智醫 -> 慧誠智醫
iMBS -> iMVS
Gamma -> Gemma
```

Aliases are used for high-confidence homophone or product-name corrections where raw character similarity is not reliable enough for Chinese ASR output.

## Conservative Policy

The corrector only evaluates glossary-sized spans and ASCII technical tokens. It does not rewrite sentences, paraphrase content, infer speaker intent, or modify free-form natural language.

Default thresholds:

```text
organizations: >= 85
technical_terms: >= 90
medical_terms: >= 92
people: >= 90
```

Medical terms and people use higher thresholds because wrong corrections create higher review risk.

## Correction Log

Every accepted correction is recorded with:

```json
{
  "span": "志德灣",
  "original": "志德灣",
  "corrected": "智德萬",
  "score": 100.0,
  "category": "organizations",
  "method": "rapidfuzz",
  "accepted": true,
  "start": 2,
  "end": 5
}
```

When no term is corrected, `{base}_correction_log.json` is still written as an empty array. This distinguishes "the corrector ran and accepted no changes" from "the corrector did not run."

## LLM Verification Plan

The first version keeps `llm_verification: false`. The next validation layer can add LLM review only for gray-zone matches:

```text
score >= 95: automatic correction
85 <= score < 95: optional LLM verification
score < 85: no correction
```

This keeps the first release auditable and rollback-friendly while preserving a clear path for later verification.
