# Transcription front-end update — September 7, 2026

AURA now centers its desktop workflow on durable recording, editable Mandarin
transcription, and exact text export. The existing Breeze-ASR-25 CUDA/int8
recognizer remains the baseline. The changes below improve audio continuity,
punctuation coverage, and operator control.

## Implemented behavior

- **Live VAD:** faster-whisper's bundled Silero v6 ONNX model runs on CPU with
  independent recurrent state per recording. A 512-sample model buffer bridges
  480-sample capture frames. Thresholds are 0.5 for speech onset and 0.35 while
  active. Initialization or inference failure switches visibly to WebRTC.
- **Chunking:** about 320 ms pre-roll, 800 ms endpoint silence, and 12-second
  maximum chunks retain all internal audio samples. Forced splits remain
  contiguous. Source sample positions provide timestamps even across long gaps.
  Capture journals continue to own original audio. Enhancement and gain run in
  the ASR worker. Processing and queue age appear in the runtime log.
- **Punctuation:** the existing zh-wiki BERT model is repaired rather than
  replaced without evidence. Partial punctuation no longer bypasses inference.
  Token windows overlap by 64 tokens, and offset predictions select the window
  with the most context. CPU loading avoids ASR VRAM contention; reload retries
  failed loading. Identifiers, URLs, decimals and lexical content are protected.
- **Editor:** a native plain text editor replaces row verification and claim
  review. Stop saves `_live.txt` before full-recording refinement. Changes made
  before or while refinement runs stay in the editor; `_refined.txt` holds the alternative.
  Storage failures retain text and retry before finalization.
- **Hotwords:** one-per-line local Qt settings, UTF-8/BOM import, duplicate
  removal, and shared faster-whisper hints for live, file and final ASR. The
  combined prompt and hotwords must fit 200 tokenizer tokens; overflow is
  rejected visibly, with no silent truncation. A recording freezes its hints.
- **Export:** displayed words and whitespace are retained, with a final newline
  when needed. Automatic fuzzy glossary replacement is disabled. The explicit
  research helper and historical artifact readers remain available.
- **Summary retirement:** LLM runtime, automatic/manual summary controls, prompts,
  dedicated dependencies, scripts and tests are removed. Historical audio,
  summaries and evidence packets remain in their existing custody.

## Model recommendations and activation order

| Component | Recommendation | Evidence and next validation |
| --- | --- | --- |
| Live VAD | Use the integrated bundled Silero v6 baseline first | Small CPU integration reuses the installed runtime. Compare missed speech, false activations and clipped onsets on Taiwanese meetings before changing weights. |
| VAD upgrade | Compare upstream Silero 6.2.1 next | Upstream lists newer releases; AURA's bundled v6 wrapper is a distinct interface. A model-file swap requires an adapter and the same state/continuity tests. [Silero releases](https://github.com/snakers4/silero-vad/releases) |
| VAD challenger | FireRed Stream-VAD | Evaluate its streaming checkpoint on noisy Mandarin and code-switching. Vendor dataset scores establish a candidate, not AURA quality. [FireRedVAD](https://github.com/FireRedTeam/FireRedVAD) |
| Punctuation challenger | FireRedPunc after the repaired baseline | Its Chinese/English punctuation support merits a controlled comparison. Require unchanged lexical content, numbers, identifiers, newlines, and measured punctuation F1. [FireRedASR2S](https://github.com/FireRedTeam/FireRedASR2S) |
| First enhancement candidate | FastEnhancer-B DNS 16 kHz wav2wav ONNX | The new optional adapter uses CPU inference, local utterance state, and compensates the documented output delay. Vendor timing uses a different spec2spec path, so local wav2wav timing is recorded separately. [Official ONNX documentation](https://aask1357.github.io/fastenhancer/onnx/) |
| Second enhancement candidate | DPDFNet2, conservative 12 dB attenuation | Added to the evaluation dispatcher; install its package in an isolated evaluation environment. Validate actual Mandarin recognition before enabling a product route. [DPDFNet](https://github.com/ceva-ip/DPDFNet) |
| Existing alternatives | DeepFilterNet3 and ClearVoice | Keep the current isolated adapters as comparison arms. Denoise remains `off` until a reference-backed comparison passes. |

Larger generative enhancement models can improve listening quality while changing
recognition. A recent SAM Audio study reports this mismatch for its tested English
and Bengali conditions; Mandarin remains a separate validation target.
[Study](https://arxiv.org/abs/2603.04710)

## Reproducible enhancement evaluation

The optional adapter expects the **DNS 16 kHz** B checkpoint, not its 48 kHz or
spectrogram variant. Download the official asset to local model custody:

```bash
mkdir -p ~/.cache/project-aura/fastenhancer-b-dns
curl -fL https://github.com/aask1357/fastenhancer/releases/download/onnx-dns-v1.0.0/fastenhancer_b.onnx \
  -o ~/.cache/project-aura/fastenhancer-b-dns/fastenhancer_b.onnx
export AURA_FASTENHANCER_MODEL="$HOME/.cache/project-aura/fastenhancer-b-dns/fastenhancer_b.onnx"
```

Use a private corpus with `CASE/input.wav`, `reference.txt`, and `rare_terms.txt`.
The existing harness now adds enhancement time, real-time factor, and mixed
error rate (Mandarin characters plus English words; punctuation excluded), while
preserving historical CER/WER columns. It reuses one ASR model across arms.

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_denoise_backends.py \
  --input-dir /private/reviewed-corpus \
  --backends off,noisereduce-light,fastenhancer-b \
  --activate-preprocessing-effect \
  --model SoybeanMilk/faster-whisper-Breeze-ASR-25 \
  --work-dir local_outputs/frontend-eval \
  --output local_outputs/frontend-eval/results.md
```

For a DPDFNet2 comparison, run the same command using a separate Python 3.11+
environment with AURA and `dpdfnet` installed, adding `dpdfnet2` to `--backends`.
Its dependency and model activation do not change the normal app installation.

Promotion requires at least ten paired, acoustically reviewed cases, no worsening
of CER/MER or domain-term recall, checks of numbers and English terms, and live
queue growth that stays bounded on the target host. Include clean controls,
quiet/far speakers, interruptions, noise-only intervals, and overlapping speech.
The existing promotion script's legacy CER/WER gate is one validation layer;
MER, acoustic review and live backlog require explicit inspection as well.

## Validation receipt and remaining evidence

[Runtime smoke receipt](../artifacts/asr-front-end/2026-09-07/runtime-smoke.json)
records actual CPU Silero execution and FastEnhancer/DPDFNet2 inference on
synthetic signals. DPDFNet2 0.6.0 ran in an isolated Python environment. It supports interface, sample-count and runtime feasibility claims.
The punctuation baseline was also exercised locally on partially punctuated,
code-switched and 675-character text without lexical truncation.

The documented `DATA-AURA-PREPROCESS-v2` custody path is absent on this host.
The September 4 dataset record remains historical evidence; this update performs
no private-corpus quality ranking or default promotion. FireRed and DPDFNet2
quality comparisons, human acoustic review, and a real microphone acceptance
session remain the next validation layer.

The most useful next optimization is a paired error audit: inspect missed speech
and proper-name/number errors before choosing another model. Tune endpointing
against that evidence, retain source tracks for overlap-heavy meetings, and
measure whether 12-second chunks plus decode time meet the desired live cadence.
A maximum chunk duration does not guarantee an end-to-end 12-second update.
