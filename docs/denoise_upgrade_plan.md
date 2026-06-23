# Denoise Upgrade Plan

## Decision

Keep the current `noisereduce` spectral-gating path as the lightweight fallback, expose its presets clearly in the desktop UI, and evaluate model-based speech enhancement before adding heavyweight runtime dependencies.

The first-principles target is transcript quality under degraded capture, not prettier audio. Distance from the microphone reduces signal-to-noise ratio and adds room reverberation; gain and denoise can help ASR only when they preserve speech detail and domain terms. The contribution of this rollout is a stable `Meeting Distance Mode` policy layer that records the intended capture condition, applies conservative fallback preprocessing today, and creates a measured path for DeepFilterNet3, ClearVoice, and dereverberation experiments.

Current blocked handoff: `docs/denoise_blocked_handoff.md`.

The next backend candidates are:

| Backend | Primary use | Integration priority |
| --- | --- | --- |
| `noisereduce` | Lightweight fallback and quiet-room baseline | Current default fallback |
| DeepFilterNet3 | Real-time or near-real-time ASR preprocessing | First model-based candidate |
| ClearerVoice / ClearerVoice-Studio | Offline high-quality enhancement, separation, and super-resolution | First rescue-import candidate |
| NARA-WPE / WPE dereverberation | Far-field reverberation validation layer | Research candidate after baseline enhancement |
| RNNoise / WebRTC APM / SpeexDSP | Lightweight real-time gain/noise/VAD building blocks | Operational reference, not current AURA backend |

## Research Snapshot, 2026-06-23

Current public evidence supports this implementation order:

- DeepFilterNet remains the best first near-real-time candidate for AURA because it is a low-complexity full-band speech enhancement framework and includes a `deep-filter` CLI path for reproducible experiments. PyPI JSON checked on 2026-06-23 reports `deepfilternet==0.5.6` with `numpy>=1.22,<2.0`, so AURA treats it as an external CLI/backend rather than a main-environment dependency. Primary sources: <https://github.com/Rikorose/DeepFilterNet>, <https://www.isca-archive.org/interspeech_2023/schroter23b_interspeech.pdf>, <https://pypi.org/project/deepfilternet/>.
- ClearVoice is the strongest current offline rescue candidate because the 2025 package provides `pip install clearvoice`, speech enhancement models at 16 kHz and 48 kHz, automatic model fetching, single-file inference, and a NumPy-to-NumPy interface for more flexible pipelines. PyPI JSON checked on 2026-06-23 reports `clearvoice==0.1.2` with `numpy>=1.24.3,<2.0`, so AURA supports it through the `AURA_CLEARVOICE_PYTHON` external runner path instead of the main AURA environment. Primary sources: <https://pypi.org/project/clearvoice/>, <https://github.com/modelscope/ClearerVoice-Studio>, <https://arxiv.org/abs/2506.19398>.
- WPE is the correct validation layer for the reverberation part of far-field capture. NARA-WPE specifically targets background noise and signal reverberation in far-field speech recognition, with offline and online variants. Primary source: <https://github.com/fgnt/nara_wpe>.
- WebRTC APM, SpeexDSP, and RNNoise validate the engineering shape of AGC/noise/VAD blocks, but they do not replace a transcript-quality evaluation. WebRTC-style AGC uses limiter-backed capture gain control; SpeexDSP combines noise suppression, AGC, VAD, and dereverb primitives; RNNoise is a small recurrent neural noise suppressor. Primary sources: <https://docs.rs/webrtc-audio-processing-config/latest/webrtc_audio_processing_config/>, <https://www.speex.org/docs/api/speex-api-reference/speex__preprocess_8h.html>, <https://github.com/xiph/rnnoise>.

## Why Not Replace Everything Immediately

ASR preprocessing is not the same as audio mastering. A stronger denoiser can make speech sound cleaner while removing consonants, breath endings, or rare domain terms that the ASR model needs. For Project AURA, every denoise backend must be judged by transcript quality first, not only by listening quality.

The safe rollout is:

1. Preserve `off` as the default.
2. Keep `noisereduce` `light` and `medium` available for low-dependency usage.
3. Add optional model-based backends behind explicit settings.
4. Compare each backend against a fixed local evaluation set before making it the recommended mode.

## Current Implementation

The current implementation lives in `src/aura/audio/denoise.py`.

- `off` returns the original audio unchanged.
- `light` uses non-stationary `noisereduce` with `prop_decrease=0.35`.
- `medium` uses non-stationary `noisereduce` with `prop_decrease=0.55`.
- Very short and near-silent buffers are bypassed to avoid unstable STFT settings.
- The desktop UI exposes these as a `Denoise Mode` combo box.
- `src/aura/audio/meeting_distance.py` now owns `Meeting Distance Mode` policy, while `src/aura/audio/enhancement_backends.py` owns optional model backend loading:

| Mode | Current fallback | Backend direction | Scope |
| --- | --- | --- | --- |
| `off` | No distance-mode floor; default denoise remains off | None | Controlled close capture |
| `normal` | `light` denoise plus existing normalization | `noisereduce-light` baseline | Normal meeting-room audio |
| `far-speaker` | `medium` denoise, longer VAD bridge, lower live energy gate, bounded live segment AGC | Attempts DeepFilterNet3 on imported files; falls back to `medium` noisereduce | Weak distant talkers where live ASR needs support |
| `rescue-offline` | Import-capable fallback with `medium` denoise and mode metadata | Attempts ClearVoice MossFormer on imported files; falls back to `medium` noisereduce | Difficult imported recordings; not promoted as a live backend |

The mode is written into processing metrics so evaluation reports can compare transcript quality by capture condition and backend candidate. When a model backend succeeds on import, AURA skips the fallback `noisereduce` pass to avoid double enhancement.

## Evaluation Set

Create a small private evaluation folder outside git because it may contain meeting audio. AURA provides a template initializer and a readiness checker:

```bash
python scripts/init_denoise_eval_workspace.py --input-dir ~/record_jn/aura_eval_audio
python scripts/discover_denoise_eval_candidates.py \
  --root ~/record_jn/record_audio_ubuntu \
  --output local_outputs/denoise_eval_candidates/candidates.md
python scripts/prepare_denoise_eval_case.py \
  --source /path/to/source_recording.wav \
  --case-dir ~/record_jn/aura_eval_audio/far_speaker_reverb \
  --start 120 \
  --duration 60 \
  --reference-file /path/to/trusted_reference.txt \
  --rare-term DeepFilterNet \
  --rare-term MossFormer
python scripts/check_denoise_eval_workspace.py \
  --input-dir ~/record_jn/aura_eval_audio \
  --min-cases 10 \
  --max-reference-chars-per-second 45
```

The discovery manifest is a private local aid. It records candidate paths, durations, transcript-file candidates, and ready-to-edit preparation commands; it intentionally does not include transcript contents. A transcript candidate is a review source, not automatically a clip-level reference. It becomes a trusted `reference.txt` only after human review and alignment to the selected 30-90 second clip. The workspace checker also rejects references that are implausibly long for the clip duration, which helps catch accidental full-recording transcript copies.

The expected folder shape is:

```text
~/record_jn/aura_eval_audio/
├── quiet_room/
├── fan_or_ac_noise/
├── cafe_or_background_speech/
├── lecture_or_meeting/
├── far_speaker_reverb/
├── far_speaker_low_volume/
├── far_speaker_table_end/
├── far_speaker_overlap/
├── rescue_offline_reverb/
├── rescue_offline_noise/
├── rescue_offline/
└── rare_terms/
```

For each folder, keep:

- `input.wav`
- `reference.txt` when a trusted transcript exists
- `rare_terms.txt` with one expected domain term per line
- `notes.md` with room, microphone, language, and expected hard terms

The minimum useful set is 10-20 short clips of 30-90 seconds each.

## Metrics

Use two classes of checks:

| Check | Purpose |
| --- | --- |
| WER / CER | Measures transcript accuracy against `reference.txt` |
| Rare-term hit rate | Measures whether domain vocabulary survives enhancement |
| ASR runtime | Ensures enhancement does not make the workflow too slow |
| Listening spot check | Catches artifacts that metrics miss |

For Project AURA, the recommended ranking rule is:

1. Prefer lower CER/WER.
2. If CER/WER is tied, prefer higher rare-term hit rate.
3. If transcript quality is tied, prefer lower latency and fewer dependencies.
4. Do not promote a backend if it sounds cleaner but harms ASR output.

## CLI Harness

AURA now includes a local evaluation harness:

```bash
python scripts/evaluate_denoise_backends.py \
  --input-dir ~/record_jn/aura_eval_audio \
  --backends off,noisereduce-light,noisereduce-medium,deepfilternet3,clearvoice,wpe \
  --model SoybeanMilk/faster-whisper-Breeze-ASR-25 \
  --output reports/denoise_eval_YYYYMMDD.md
```

Omit `--model` to process candidate audio without ASR. Heavy optional backends are loaded only when selected; unavailable backends are recorded as `skipped` in the report. DeepFilterNet is called through the external `deep-filter` CLI. ClearVoice can run in an isolated environment by setting `AURA_CLEARVOICE_PYTHON=/path/to/clearvoice/python`, which invokes `scripts/run_clearvoice_enhancement.py`.

The report should include:

- backend name
- processed audio path
- transcript path
- CER/WER when reference exists
- rare-term hits and misses
- runtime
- recommendation per audio category
- meeting distance mode

The harness now appends a `Recommendation by Category` table. A category receives a recommended backend only when at least one candidate has reference-backed ASR metrics. Process-only runs and clips without `reference.txt` still produce useful processed audio and diagnostics, but they do not justify changing defaults.

Before promoting any backend into a recommended default, run the promotion gate against the JSON report:

```bash
python scripts/gate_denoise_default_promotion.py \
  --report-json reports/denoise_eval_YYYYMMDD.json \
  --baseline off \
  --candidate deepfilternet3 \
  --min-cases 10
```

The gate passes only when the baseline and candidate both have reference-backed ASR metrics on enough cases, average WER and CER do not regress, and rare-term hit rate does not regress. This makes the first-principles rule explicit: cleaner audio is not enough; transcript quality and domain terms must survive.

## Backend Integration Shape

The future code should keep one public entrypoint:

```python
enhance_audio(input_audio, mode="off", backend="noisereduce")
```

Recommended internal layout:

```text
src/aura/audio/
├── denoise.py                  # current noisereduce fallback
├── meeting_distance.py         # mode policy, fallback tuning, metrics contract
├── enhancement_backends.py     # optional DeepFilterNet/ClearVoice import backend boundary
├── deepfilternet_backend.py    # optional dependency boundary
├── clearvoice_backend.py       # optional dependency boundary
└── dereverb_backend.py         # optional WPE validation boundary
```

Optional dependencies should be loaded inside backend modules, not at app startup. If DeepFilterNet3 or ClearerVoice is not installed, the UI should show the mode as unavailable instead of crashing.

## Recommended Rollout

### Phase 1: UI and Baseline

- Expose `Meeting Distance Mode` as `off`, `normal`, `far-speaker`, and `rescue-offline`.
- Keep `Denoise Mode` as an expert strength input, with the meeting-distance mode providing the minimum safe denoise floor.
- Keep `off` as the default.
- Verify live recording and imported-file paths both record mode metadata and pass the effective preset.
- Wire imported-file `far-speaker` to attempt DeepFilterNet3 and `rescue-offline` to attempt ClearVoice, with safe fallback when dependencies are absent.

### Phase 2: Evaluation Harness

- Add the private evaluation folder contract.
- Add a local benchmark script.
- Save generated reports under `reports/`, while keeping raw audio outside git.

### Phase 3: DeepFilterNet3

- Add an optional DeepFilterNet3 backend. Initial imported-file attempt is available through `enhancement_backends.py`.
- Only enable live processing after measuring latency and stream stability.
- Promote it for `far-speaker` only if CER/WER and rare-term hit rate improve on distant-speaker clips.

### Phase 4: ClearVoice / ClearerVoice-Studio

- Add ClearVoice as an offline import-only backend. Initial imported-file attempt is available through `enhancement_backends.py`.
- Use it for difficult audio, speaker overlap, and enhancement experiments.
- Do not use it as the default live recording path.

### Phase 4b: Dereverberation Validation

- Add WPE/NARA-WPE as an offline experiment for clips where distance mainly creates room tail rather than stationary noise.
- Compare WPE alone, DeepFilterNet alone, ClearVoice alone, and ordered combinations.
- Promote a dereverb step only when ASR metrics improve and speech detail remains stable.

### Phase 5: Promote Defaults

Promote a new default only after the evaluation report shows that it improves ASR output across normal meeting audio and does not reduce rare-term recognition.
