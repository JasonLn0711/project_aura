# ASR Fuzzy Manual Review Decision Report

## Reviewed Gate Result

The reviewed manual gate is recorded in:

```text
reports/asr_fuzzy_manual_review_queue_reviewed.csv
reports/asr_fuzzy_manual_review_result_summary.json
reports/asr_fuzzy_manual_review_20260604_153546_reviewed.zip
```

Reviewed labels:

```text
Total rows: 67
ACCEPT: 42
REJECT: 11
UNSURE: 14
Decision: do_not_commit_as_is
```

## Policy Applied

The glossary correction policy now separates accepted ASR corrections from review-controlled cases:

- `denylist`: reviewed `REJECT` patterns are not applied to the transcript and are logged with `accepted: false`.
- `manual_review_required`: reviewed `UNSURE` patterns are not applied to the transcript and are logged with `accepted: false`.
- Valid abbreviation expansion such as `陽明交大 -> 國立陽明交通大學` is treated as normalization-only policy, not ASR correction.

The policy is stored in:

```text
config/domain_glossary.yaml
```

## Re-Audit After Policy

After rebuilding the audit-only correction logs with the reviewed policy:

```text
Total corrections/candidates: 216
Accepted corrections: 174
Rejected candidates: 42
Denylist rejections: 22
Manual review required: 20
```

The rejected count is larger than the reviewed CSV row count because the policy is pattern-based and applies to every matching occurrence across the 42 repo transcript artifacts.

## Decision State

This revision is no longer a blind text replacement pass. Risky reviewed cases are surfaced as non-applied candidates:

- `REJECT` patterns do not change transcript text.
- `UNSURE` patterns do not change transcript text.
- Audit reports now include rejected candidates and manual-review-required candidates.

No commit has been made at this decision point.
