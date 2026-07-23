# Windows Native RTX Roadmap

## Current Status: Implemented In v1.13.0

As of `2026-05-29`, the Windows native foundation is implemented as a validation and onboarding path:

- `scripts/windows_gpu_smoke.py` checks `nvidia-smi`, Python imports, CUDA runtime visibility, cuBLAS/cuDNN, and `WhisperModel(..., device="cuda", compute_type="int8")`.
- `scripts/runtime_report.py` produces a developer-facing report for OS, Python, GPU, CUDA, cuBLAS, cuDNN, `ctranslate2`, `faster-whisper`, FFmpeg, audio I/O, and output-folder writability.
- `src/aura/system/platform.py`, `gpu_diagnostics.py`, `audio_diagnostics.py`, and `runtime_report.py` centralize platform/runtime facts.
- The PyQt6 transcription tab now exposes Runtime Diagnostics, First Launch Check gates, top GPU/model/device status, a workstation layout, copyable diagnostic reports, and a runtime log.
- `.github/workflows/windows.yml` runs hosted Windows unit/import/PyQt/package/runtime checks. A gated self-hosted RTX job runs `windows_gpu_smoke.py` and `windows_asr_artifact_smoke.py`.
- `Start-AURA.bat` / `Start-AURA.ps1` prepare `.venv`, install dependencies, check FFmpeg/NVIDIA, run the GPU smoke test, write `diagnostic_report.txt`, and launch the UI.
- `Check-AURA.bat` / `Check-AURA.ps1` run the same setup and validation flow without launching the UI.
- `scripts/build_windows_portable.ps1` prepares `dist/aura-windows-portable/` and `dist/aura-windows-portable-v1.13.0.zip` with root launch/check scripts, `app/`, `scripts/`, `docs/`, `sample_audio/`, and `diagnostic_report.txt`.

The next validation layer is real Windows RTX hardware exercise with the self-hosted runner enabled.

## 目標

Project AURA 的下一個平台能力，是把目前已經成立的 Ubuntu RTX/CUDA
轉錄工作站，延伸成 Windows native 也能穩定啟動、診斷、執行與封裝的本機工具。

核心判準很直接：Windows 使用者不需要先理解 WSL、Kali 或 Docker，就能完成 RTX
GPU 啟用檢查、載入 `faster-whisper` CUDA 模型、匯入音檔、產生 transcript artifacts，
並在失敗時複製一份足夠開發者判讀的 runtime diagnostic report。

## 目標架構

```text
Project AURA
├── core engine
│   ├── faster-whisper ASR
│   ├── audio import / normalization
│   ├── transcript artifacts
│   └── summary / punctuation / diarization
├── desktop UI
│   ├── Ubuntu 24 PyQt6
│   └── Windows PyQt6 native
├── diagnostics
│   ├── CUDA runtime check
│   ├── GPU smoke test
│   ├── audio device check
│   └── dependency report
├── packaging
│   ├── Windows installer / portable build
│   ├── Ubuntu source/dev install
│   └── optional Docker headless image
└── CI / release tests
    ├── Ubuntu tests
    ├── Windows CPU/import/package tests
    └── Windows self-hosted GPU test
```

## 決策原則

- Ubuntu 保持主要開發路徑；Windows 成為第一級驗證路徑。
- ASR 維持 RTX/CUDA-only。CPU fallback 持續停用，讓產品行為不會悄悄離開預期的 GPU 路徑。
- 平台差異集中在 `src/aura/system/` 與 diagnostics scripts，不散落在 UI 與 ASR code 裡。
- Windows support 先以 runtime proof 成立，再進入 installer 工作。第一個 packaging 目標是 portable ZIP release。
- Runtime failure 需要說清楚目前缺少哪一層 activation：NVIDIA driver、CUDA DLLs、cuBLAS/cuDNN、`ctranslate2`、FFmpeg 或 audio devices。

## Phase 1: Windows 可行性驗證

目標是確認 Windows native 能穩定載入 RTX GPU，並產生可貼給開發者看的診斷資料。

交付物：

- 新增 `scripts/windows_gpu_smoke.py`. Done in `v1.12.0`.
  - 檢查 `nvidia-smi` 是否存在並回報 GPU。
  - 檢查 Python 能否 import `faster_whisper`。
  - 檢查 CUDA runtime DLL / cuBLAS / cuDNN 可見性。
  - 實際建立 `WhisperModel(MODEL_ID, device="cuda", compute_type="int8")`。
- 新增 `scripts/runtime_report.py`. Done in `v1.12.0`.
  - 輸出 OS、Python、GPU、CUDA、cuBLAS、cuDNN、`ctranslate2`、`faster-whisper` 版本。
  - 產生 single diagnostic report，方便 issue、Slack、email 或 release smoke log 直接貼上。
- README now includes the Windows GPU quick check:

```powershell
nvidia-smi
python scripts/windows_gpu_smoke.py
```

驗收：

- Windows RTX machine 可以用 `device="cuda"` 與 `compute_type="int8"` 載入預設 ASR model。
- 失敗機器會回傳可操作的 diagnostic report，而不只是說 CUDA missing。
- Ubuntu behavior 維持不變。

## Phase 2: 跨平台邊界整理

目標是讓 Ubuntu、WSL、Windows native、Docker container 的差異集中管理。

交付物：

- 新增 platform/runtime modules. Done in `v1.12.0`:
  - `src/aura/system/platform.py`
  - `src/aura/system/gpu_diagnostics.py`
  - `src/aura/system/audio_diagnostics.py`
- 擴充 `src/aura/system/cuda.py`，讓 runtime messages 能區分。Done in `v1.12.0`:
  - Linux native
  - WSL
  - Windows native
  - Docker container
- 將 GPU errors 轉成產品化操作建議：
  - Windows: check NVIDIA driver, CUDA DLLs, cuBLAS/cuDNN, and `ctranslate2`.
  - WSL: check `/dev/dxg` and `/usr/lib/wsl/lib/nvidia-smi`.
  - Linux: check cuBLAS/cuDNN runtime libraries.
  - Docker: check `--gpus all` and container-visible NVIDIA runtime.

驗收：

- UI、ASR 與 scripts 都呼叫同一個 shared diagnostics layer。
- CPU fallback 維持停用，但訊息改成：這台機器目前尚未完成 AURA 需要的 RTX/CUDA activation。

## Phase 3: Windows Native 執行路徑

目標是讓 Windows 使用者可以用原生 Python/PyQt6 執行 AURA。

交付物：

- 新增 `docs/windows_setup.md`. Done in `v1.12.0`.
- 記錄建議安裝路徑：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e ".[punctuation]"
python scripts/windows_gpu_smoke.py
python -m aura
```

- 補上 Windows-specific dependency notes:
  - NVIDIA driver
  - `faster-whisper` / `ctranslate2`
  - CUDA 12 runtime
  - cuDNN / cuBLAS
  - PyAudio / sound device handling
  - FFmpeg on `PATH`
- 新增 helper scripts. Done in `v1.12.0`:
  - `scripts/run_aura_windows.ps1`
  - `scripts/check_windows_runtime.ps1`

驗收：

- 乾淨的 Windows machine 可以照著單一文件，從 venv setup 走到第一次 UI launch。
- Helper scripts 不隱藏失敗；它們負責執行 checks 並保留 diagnostic output。

## Phase 4: Windows UI 調整

目標是讓 AURA 在 Windows 上像本機工作站工具，而不是 Linux UI 的直接搬移。

交付物：

- 保留 PyQt6 作為主要 UI framework。
- 新增 Runtime Diagnostics 區塊：
  - GPU detected
  - CUDA runtime status
  - ASR model load status
  - audio input/output status
  - copy diagnostic report button
- 新增首次啟動檢查：
  - GPU ready
  - CUDA ready
  - FFmpeg ready
  - microphone ready
  - output folder writable
- 改善 Windows audio source wording：
  - Microphone
  - System audio
  - System + microphone
  - If system audio is unavailable, show setup guidance.

驗收：

- Error dialogs 可以直接複製完整 diagnostic report。
- Windows users 可以判斷目前 blocker 是 GPU、FFmpeg、audio、path 還是 model loading。

## Phase 5: 測試策略

目標是保留 Ubuntu 開發速度，同時讓 Windows regressions 能被持續看見。

交付物：

- 新增 `.github/workflows/windows.yml`. Done in `v1.12.0`.
- Windows hosted runner 覆蓋：
  - unit tests
  - import smoke
  - PyQt import smoke
  - packaging smoke
  - non-GPU runtime report
- Self-hosted Windows RTX runner 覆蓋：
  - `windows_gpu_smoke.py`
  - `windows_asr_artifact_smoke.py` small-audio ASR artifact smoke test
  - `device="cuda"` model load
  - transcript artifact output validation
- Ubuntu CI 持續保留：
  - unit tests
  - compile/import smoke
  - Linux runtime checks

驗收：

- Hosted CI 可以驗證 Windows source compatibility，但不假裝擁有 GPU。
- Self-hosted CI 是 Windows CUDA claims 的驗證 gate。

## Phase 6: Packaging

目標是先交付可檢查、可啟動的 Windows portable build，再評估 installer。

交付物：

- 建立第一個 portable dev release. Builder added in `v1.12.0`, ZIP layout strengthened in `v1.13.0`:

```text
dist/aura-windows-portable/
dist/aura-windows-portable-v1.13.0.zip
```

- 評估 packaging engines：
  - PyInstaller: mature and fast, with careful CUDA DLL and Qt plugin collection.
  - Nuitka: potentially stronger runtime packaging, with slower builds.
- Installer 工作延後到 portable release 完成驗證之後。
- Release artifact 包含：
  - `Start-AURA.bat`
  - `Check-AURA.bat`
  - app
  - setup guide
  - runtime checker
  - sample audio
  - known issues
  - `diagnostic_report.txt`

驗收：

- Windows user 可以解壓縮 portable build、執行 runtime checker、啟動 AURA，並在回報前先檢查 known issues。
- Packaging 不作為 Windows support 的第一個證據；runtime validation 才是第一層證據。

## Phase 7: Windows User Onboarding

目標是把 Windows 使用者流程從開發者命令串，收斂成「解壓縮、檢查、啟動」。

交付物：

- 新增 root-level 一鍵入口. Done in `v1.13.0`:
  - `Start-AURA.ps1`
  - `Start-AURA.bat`
  - `Check-AURA.ps1`
  - `Check-AURA.bat`
- `Start-AURA.ps1` 自動處理：
  - Python 3.11 檢查
  - `.venv` 建立
  - dependency install
  - FFmpeg / ffprobe 檢查
  - NVIDIA driver / `nvidia-smi` 檢查
  - `windows_gpu_smoke.py`
  - `diagnostic_report.txt`
  - 成功後啟動 UI
- UI First Launch Check. Done in `v1.13.0`:
  - GPU Ready
  - CUDA Ready
  - FFmpeg Ready
  - Microphone Ready
  - Output Folder
  - ASR Model Load
  - failed gates expose Fix Guide, Copy Diagnostic Report, Open Setup Folder, and Retry Check.

驗收：

- 使用者可以用 `Check-AURA.bat` 先驗證工作站 readiness。
- 使用者可以用 `Start-AURA.bat` 啟動；失敗時 root 會留下 `diagnostic_report.txt`。
- UI 可以顯示目前卡在 GPU、CUDA、FFmpeg、microphone、output folder 或 ASR model load 哪一層。
