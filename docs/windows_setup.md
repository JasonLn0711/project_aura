# Windows Native Setup

## 目標

這份文件讓 Windows 使用者用 native Python/PyQt6 執行 Project AURA，不需要先進入 WSL、
Kali 或 Docker。AURA 的 ASR 路徑維持 RTX/CUDA-only；CPU fallback 持續停用，讓轉錄
不會悄悄離開預期的 GPU 工作站路徑。

## 前置需求

- Windows 10/11 64-bit
- NVIDIA RTX GPU
- 最新 NVIDIA driver，且 `nvidia-smi` 可在 PowerShell 執行
- Python 3.11
- FFmpeg 已加入 `PATH`
- 可用的 microphone 或 audio input device

## 建議安裝流程

在 repo root 開啟 PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e ".[summary,punctuation]"
python scripts/runtime_report.py
python scripts/windows_gpu_smoke.py
python -m aura
```

`windows_gpu_smoke.py` 會先檢查 `nvidia-smi`、Python imports、CUDA runtime DLL、cuBLAS、
cuDNN 與 `ctranslate2`，再實際建立：

```python
WhisperModel(MODEL_ID, device="cuda", compute_type="int8")
```

## Windows-specific dependency notes

- NVIDIA driver: `nvidia-smi` 需要能看到 RTX GPU 與 driver version。
- `faster-whisper` / `ctranslate2`: AURA 透過 `faster-whisper` 載入 CUDA ASR model。
- CUDA 12 runtime: Windows native 需要 CUDA DLL 能被 Python process 找到。
- cuDNN / cuBLAS: `ctranslate2` CUDA backend 需要對應 DLL 可見。
- PyAudio / sound device handling: Windows audio device 必須能被 PyAudio 列出。
- FFmpeg path: media import/export 依賴 `ffmpeg` 與 `ffprobe`。

## Helper scripts

檢查 runtime：

```powershell
.\scripts\check_windows_runtime.ps1
```

啟動 AURA：

```powershell
.\scripts\run_aura_windows.ps1
```

建立 portable developer release：

```powershell
.\scripts\build_windows_portable.ps1
```

輸出位置：

```text
dist/aura-windows-portable/
```

Self-hosted RTX smoke test：

```powershell
python scripts/windows_asr_artifact_smoke.py
```

這個 smoke test 會產生一個很短的 WAV、用 CUDA/int8 跑一次 `faster-whisper`，並驗證
`raw`、`final`、`metrics` transcript artifacts 都能寫出。

## Diagnostic report

如果啟動失敗，先執行：

```powershell
python scripts/runtime_report.py
```

將完整輸出貼給開發者。UI 的 Runtime Diagnostics 區塊也可以複製同一類報告，包含 OS、
Python、GPU、CUDA、cuBLAS、cuDNN、`ctranslate2`、`faster-whisper`、FFmpeg 與 audio
device 狀態。
