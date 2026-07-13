# Runtime validity

- Status: `LIVE_MINIMUM_COMPLETED`
- `aura_faster_whisper`: `valid_target_runtime` (Breeze ASR 25, CUDA/int8)
- `meetily_whisper_rs`: `valid_target_runtime` (Breeze ASR 26, CUDA release runtime)
- `meetily_parakeet`: `blocked_runtime` for zh-TW by the enforced model capability contract
- Live source audio: 5 public Common Voice 24 zh-TW files with reference text
- GPU telemetry: AURA max utilization 98%; Meetily max utilization 89%
