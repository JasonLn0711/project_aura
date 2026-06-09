# G4E4B-SummaryImpact

Gemma 4 E4B local model-backed ASR correction summary-impact gate.

## Scope

- Fixed local summarizer: Gemma 4 E4B.
- Runner: ollama.
- Endpoint: http://127.0.0.1:11434.
- Ollama tag: gemma4:e4b-it-q4_K_M.
- External calls: false.
- Cloud calls: false.
- Transcript context emitted to reports: false.
- Claim scope: internal local model-backed gate, not final empirical claim.
- Fixed model id: google/gemma-4-E4B-it
- Precision variant: ollama_q4_K_M_local_tag
- FP8 checkpoint: false
- Download during gate: false
- Local files only: true

## Result

- Model available: true
- Reason: Ollama local model found: gemma4:e4b-it-q4_K_M; 1 artifact sets generated empty structured summaries
- Complete artifact sets: 5
- Evaluated files: 4
- Files with both summaries: 4
- Summary generation failures: 1
- Domain terms in raw summaries: 41
- Domain terms in corrected summaries: 44
- Domain term delta: 3
- Raw ASR error spans in raw summaries: 0
- Canonical terms in corrected summaries: 0
- Rejected leakage: 0
- Manual-review leakage: 0
- Decision changes: {"domain_term_only": 3, "manual_review_needed": 0, "possible_semantic_change": 1}
- Hallucinated entity watch count: 3
