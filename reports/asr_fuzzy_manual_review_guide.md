# ASR Fuzzy Correction Manual Review Guide

## Purpose

This package supports manual review before committing the ASR fuzzy correction feature. The review queue contains only correction spans and source transcript filenames. It does not include raw transcript context, raw Gmail content, or raw PDF content.

## Queue Files

- `reports/asr_fuzzy_manual_review_queue.csv` is the reviewer work queue.
- `reports/asr_fuzzy_manual_review_summary.json` records queue counts and blank-label status.
- Source audit: `reports/asr_fuzzy_correction_audit_report.json`.

## Review Labels

- `ACCEPT`: 明顯 ASR 錯字，且 corrected 是正確專有名詞。
- `REJECT`: 可能改變語意，或 original 本身可成立。
- `UNSURE`: 需要回聽音檔或看上下文。

Leave `review_label` blank until a human reviewer makes the call. Legal values are `ACCEPT`, `REJECT`, and `UNSURE`.

## Review Scope

- Score 85-94.99 accepted corrections.
- All `people` accepted corrections.
- All `medical_terms` accepted corrections.
- All alias corrections.
- Watch cases for Gamma/Gemma/Qwen/iMVS/IRB/510(k).

## Decision Rule

- If every reviewed row is `ACCEPT`, proceed to commit.
- If any row is `REJECT`, add the case to a denylist or raise the relevant category threshold, then rerun tests and the audit.
- If any row is `UNSURE`, do not auto-correct that pattern; route it to `manual_review_required` behavior.

## Current Queue Summary

- Total queue rows: 67
- Review labels blank: True
- Contains raw context: False
