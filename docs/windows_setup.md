# Windows Native Setup

Last updated: 2026-05-29 for Project AURA `v1.13.0`.

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

## 一般使用者流程

建議先使用 portable ZIP，不需要進入 WSL、Kali 或 Docker：

1. 安裝或更新 NVIDIA driver，確認電腦有 RTX GPU。
2. 解壓縮 `aura-windows-portable-v1.13.0.zip`。
3. 雙擊 `Check-AURA.bat`。
4. 雙擊 `Start-AURA.bat`。

`Check-AURA.bat` 和 `Start-AURA.bat` 會自動執行：

- 檢查 Python 3.11
- 建立 `.venv`
- 安裝 Project AURA dependencies
- 檢查 FFmpeg / ffprobe
- 檢查 NVIDIA driver / `nvidia-smi`
- 執行 `windows_gpu_smoke.py`
- 產生 `diagnostic_report.txt`
- 啟動 UI（`Start-AURA.bat`）

如果流程失敗，請把 `diagnostic_report.txt` 貼給開發者。

## 開發者安裝流程

在 repo root 開啟 PowerShell，仍可手動執行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e ".[punctuation]"
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

一鍵檢查 runtime：

```powershell
.\Check-AURA.ps1
```

或雙擊：

```text
Check-AURA.bat
```

一鍵啟動 AURA：

```powershell
.\Start-AURA.ps1
```

或雙擊：

```text
Start-AURA.bat
```

舊的 scripts helper 仍保留，並委派到 root-level 使用者入口：

```powershell
.\scripts\check_windows_runtime.ps1
.\scripts\run_aura_windows.ps1
```

建立 portable release：

```powershell
.\scripts\build_windows_portable.ps1
```

輸出位置：

```text
dist/aura-windows-portable/
dist/aura-windows-portable-v1.13.0.zip
```

Self-hosted RTX smoke test：

```powershell
python scripts/windows_asr_artifact_smoke.py
```

這個 smoke test 會產生一個很短的 WAV、用 CUDA/int8 跑一次 `faster-whisper`，並驗證
`raw`、`final`、`metrics` transcript artifacts 都能寫出。

## Version note

Windows one-click onboarding scripts, automatic `diagnostic_report.txt`, the First Launch Check UI, and the
versioned portable ZIP layout are part of `v1.13.0`.

## Diagnostic report

如果啟動失敗，先查看：

```text
diagnostic_report.txt
```

也可以手動執行：

```powershell
python scripts/runtime_report.py
```

將完整輸出貼給開發者。UI 的 Runtime Diagnostics 區塊也可以複製同一類報告，包含 OS、
Python、GPU、CUDA、cuBLAS、cuDNN、`ctranslate2`、`faster-whisper`、FFmpeg 與 audio
device 狀態。
