# ASR Correction Summary-Impact Evaluation Report

## Scope

- Mode: audit-only existing artifacts.
- External model/API calls: false.
- Raw email/PDF content read: false.
- Raw transcript context emitted: false.
- This is an internal quality gate, not a final empirical claim.

## Aggregate Metrics

- Complete artifact sets discovered: 8
- Evaluated files: 8
- Files with both summaries: 8
- Raw summary domain terms: 52
- Corrected summary domain terms: 55
- Domain term delta: 3
- Raw ASR error spans found in summaries: 42
- Corrected canonical terms found in summaries: 42
- Rejected/denied term leaks: 0
- Manual-review term leaks: 0

## Per-File Comparison

| file_id | raw_terms | corrected_terms | delta | raw_error_spans | canonical_terms | denied_leaks | manual_review_leaks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| reports/asr_summary_impact_sample/artifacts/sample_001_260518_0902_lab_sync/sample_001_260518_0902_lab_sync | 6 | 7 | 1 | 6 | 6 | 0 | 0 |
| reports/asr_summary_impact_sample/artifacts/sample_002_transcript_260518_0902_lab_sync/sample_002_transcript_260518_0902_lab_sync | 10 | 12 | 2 | 9 | 9 | 0 | 0 |
| reports/asr_summary_impact_sample/artifacts/sample_003_transcript_260525_0858_lab_sync_final/sample_003_transcript_260525_0858_lab_sync_final | 8 | 8 | 0 | 6 | 6 | 0 | 0 |
| reports/asr_summary_impact_sample/artifacts/sample_004_transcript_260525_0858_lab_sync_raw/sample_004_transcript_260525_0858_lab_sync_raw | 8 | 8 | 0 | 6 | 6 | 0 | 0 |
| reports/asr_summary_impact_sample/artifacts/sample_005_260525_0858_lab_sync_final/sample_005_260525_0858_lab_sync_final | 6 | 6 | 0 | 4 | 4 | 0 | 0 |
| reports/asr_summary_impact_sample/artifacts/sample_006_260525_0858_lab_sync_raw/sample_006_260525_0858_lab_sync_raw | 6 | 6 | 0 | 4 | 4 | 0 | 0 |
| reports/asr_summary_impact_sample/artifacts/sample_007_260422_1415_114-2_AI_W9_1150422/sample_007_260422_1415_114-2_AI_W9_1150422 | 3 | 3 | 0 | 3 | 3 | 0 | 0 |
| reports/asr_summary_impact_sample/artifacts/sample_008_260416_2157__with_Prof_Wu_Tomi/sample_008_260416_2157__with_Prof_Wu_Tomi | 5 | 5 | 0 | 4 | 4 | 0 | 0 |
