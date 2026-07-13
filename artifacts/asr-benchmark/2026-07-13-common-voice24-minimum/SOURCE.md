# Benchmark source

- Dataset: [OKHand/Clean_Common_Voice_Speech_24.0-TW](https://huggingface.co/datasets/OKHand/Clean_Common_Voice_Speech_24.0-TW)
- License declared by the dataset card: CC0 1.0
- Fixed revision: `96d8e4fcc3b0d0db304fec018d4b813360160e2b`
- Source shard: `data/train-00000-of-00009.parquet`
- Selected source rows: `0`, `6`, `20`, `61`, `96`
- Materialization script: `scripts/prepare_common_voice24_benchmark.py`

The five retained WAV files and their reference sentences form a small, reproducible Taiwan Mandarin clean-speech activation set. `source_manifest.jsonl` records each source row, fixed revision, reference, MOS field, and audio SHA-256. This set validates real GPU runtime activation and paired artifact generation. Product-quality selection advances through the next long-form, far-field, overlapping, and noisy-speech validation layer.

Connection map: [complete audit event](../../../docs/audit-events/2026-07-14-gpu-only-asr-live-benchmark/audit-event.md) · [first-principles review](../../../docs/first-principles-aura-meetily-review.md) · [minimum decision](final_decision_report.md)
