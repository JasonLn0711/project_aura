# Project AURA Linux Native Runtime Readiness Snapshot

- Evidence ID: `AURA-RUNTIME-PREFLIGHT-20260826-001`
- Source timestamp: `2026-08-26T09:22:52+08:00`
- AURA version: `1.15.0`
- Execution status: `PREFLIGHT_ONLY`
- Environment: Linux native

## Readiness result

| Capability | Current evidence | Readiness |
| --- | --- | --- |
| NVIDIA GPU and CUDA libraries | RTX 4090 Laptop GPU, driver `580.173.02`, CUDA 12 runtime, cuBLAS, cuBLASLt, and cuDNN visible | ready |
| ASR model load | `faster-whisper` loaded the configured model with `cuda/int8` | ready for the model-load gate |
| Audio and output storage | FFmpeg, PyAudio, input/output devices, writable output folder, and required free space reported ready | ready for capture setup |
| Traditional Chinese punctuation | Rule fallback, torch, and transformers dependencies reported ready | ready for the dependency gate |
| Speaker diarization | pyannote.audio, CUDA-capable torch, and Hugging Face token presence reported ready | ready for the dependency gate |
| Ollama command | Ollama client `0.32.1` is available | ready |
| Ollama local server | `localhost:11434` refused the connection; process discovery was empty and both service scopes were inactive | activation required |
| `gemma4:e4b-it-qat` inventory | The tags endpoint was unavailable | `not_evaluated` |

The CUDA driver and user-space stack now agree on `580.173.02`, and the ASR
model-load gate completes on `cuda/int8`. The optional local summary path
opens after the Ollama service is active and the exact model tag is confirmed.

The source report renders `Model tag: missing` when the tags endpoint cannot
be reached. This snapshot therefore classifies the model inventory as
`not_evaluated`; tag confirmation begins after the local server responds. The existing
[Ollama Gemma 4 live minimum](../llm-runtime/2026-07-23-ollama-gemma4-e4b-qat-minimum/runtime_validity_report.md)
remains the canonical historical runtime-validity packet.

## Source custody and public redaction

The owner-held source is stored at the ignored repository-relative path
`.record/runtime-readiness/2026-08-26-092252-linux-native.txt` using UTF-8,
LF line endings, and one terminal newline.

- Source SHA-256: `f496fc3853f1c88ea765893289c79a39295b1e6f3cd583303d8cc3cdc3fb3854`
- Executable-path replacement: `${AURA_REPO}/.venv/bin/python3`
- Output-folder replacement: `<operator-selected-output-folder>`

All other source wording, measurements, identifiers, model tags, device names,
and error text remain unchanged in the public copy below.

## De-identified source report

```text
Project AURA Runtime Diagnostic Report
Generated: 2026-08-26T09:22:52+08:00
AURA version: 1.15.0

Platform
- Environment: Linux native
- OS: Linux 7.0.0-30-generic
- Machine: x86_64
- Python: 3.12.3
- Executable: ${AURA_REPO}/.venv/bin/python3

GPU / CUDA
- nvidia-smi: available
- GPU detected: yes
- nvidia-smi output: NVIDIA GeForce RTX 4090 Laptop GPU, 580.173.02, 16376 MiB
- CUDA runtime status: ready
- CUDA runtime detail: system
- faster-whisper import: ok
- faster-whisper version: 1.2.1
- ctranslate2 import: ok
- ctranslate2 version: 4.7.1
- CUDA runtime: visible (libcudart.so.12)
- cuBLAS: visible (libcublas.so.12)
- cuBLASLt: visible (libcublasLt.so.12)
- cuDNN: visible (libcudnn.so.9)
- ASR model load status: loaded (cuda/int8)
- Selected output folder: <operator-selected-output-folder>
- Selected output folder writable: yes
- Output folder free bytes: 1128074457088
- Output disk space status: ready
- CUDA runtime preload: complete

Audio / FFmpeg
- FFmpeg: /usr/bin/ffmpeg
- PyAudio import: ok
- Audio input devices: 4
- Audio output devices: 12
- Audio detail: FFmpeg ready; 4 input device(s); 12 output device(s)
- Input device names: HDA Intel PCH: ALC285 Analog (hw:1,0); pipewire; pulse; default
- Output device names: HDA NVidia: B247Y (hw:0,3); HDA NVidia: HDMI 1 (hw:0,7); HDA NVidia: HDMI 2 (hw:0,8); HDA NVidia: HDMI 3 (hw:0,9); HDA Intel PCH: HDMI 0 (hw:1,3); HDA Intel PCH: HDMI 1 (hw:1,7); HDA Intel PCH: HDMI 2 (hw:1,8); HDA Intel PCH: HDMI 3 (hw:1,9)

Local LLM / Ollama
- Host: http://localhost:11434
- Command: available
- Server: unavailable
- Required model tag: gemma4:e4b-it-qat
- Reasoning: enabled (think=true)
- Model tag: missing
- Detail: <urlopen error [Errno 111] Connection refused>

Traditional Chinese Punctuation
- Rule fallback: ready
- torch import: ok
- transformers import: ok
- Local model status: local model dependencies ready

Optional Speaker Diarization
- Model: pyannote/speaker-diarization-community-1
- pyannote.audio import: ok
- torch import: ok
- torch CUDA: available
- Hugging Face token: configured
- Diarization status: ready with CUDA-capable torch

First Launch Check
- GPU Ready: ready (NVIDIA GeForce RTX 4090 Laptop GPU, 580.173.02, 16376 MiB)
- CUDA Ready: ready (system)
- FFmpeg Ready: ready (/usr/bin/ffmpeg)
- Microphone Ready: ready (FFmpeg ready; 4 input device(s); 12 output device(s))
- Output Folder: ready (Selected output folder is writable: <operator-selected-output-folder>)
- Output Disk Space: ready (1128074457088 bytes available; 1073741824 bytes required.)
- ASR Model Load: ready (loaded (cuda/int8))
- Ollama Command: ready (Ollama command is available on PATH.)
- Ollama Local Server: needs attention (http://localhost:11434: <urlopen error [Errno 111] Connection refused>)
- Ollama Summary Model: needs attention (<urlopen error [Errno 111] Connection refused>)
```

## Read-only host cross-check

Checked at `2026-08-26T09:39:43+08:00` with read-only commands; service and
model activation remained at the next gate:

```text
gpu=NVIDIA GeForce RTX 4090 Laptop GPU, 580.173.02, 16376 MiB
ollama_version=Warning: could not connect to a running Ollama instance
Warning: client version is 0.32.1
api_tags=curl: (7) Failed to connect to 127.0.0.1 port 11434 after 0 ms: Couldn't connect to server
ollama_processes=no matching process
system_service=inactive
user_service=inactive
```

This record covers environment inspection and ASR model loading. Transcription,
diarization execution, punctuation-model inference, Ollama model inventory,
and summary generation remain separate validation layers.

## Next activation gate

When local summary activation is authorized:

1. Start `ollama serve`.
2. Query `http://127.0.0.1:11434/api/tags`.
3. Run `ollama pull gemma4:e4b-it-qat` only when the exact tag is absent.
4. Refresh Runtime Diagnostics and preserve the new timestamped result.
5. Run a real AURA summary separately when current live-runtime evidence is required.
