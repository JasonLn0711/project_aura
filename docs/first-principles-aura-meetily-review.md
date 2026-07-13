# Project AURA × Meetily 第一性原理架構審查

初次審查：2026-07-13

最新實作與驗證：2026-07-14
審查範圍：`project_aura` 與同層 `meetily` 的產品目標、執行路徑、依賴、資料流、音訊、ASR、摘要、UI、儲存、跨平台、測試、安全、維護成本與演進路徑。

## 決策摘要

兩個 repo 各自承擔清楚且互補的角色：

- **Project AURA 是臺灣華語會議理解的驗證工作台**：核心資產是 Breeze ASR、領域詞彙與模糊校正、逐步 artifact、可觀測性、降噪／說話者分離實驗，以及嚴格的本機結構化摘要流程。
- **Meetily 是跨平台會議產品的交付主體**：核心資產是 Tauri 桌面殼、麥克風與系統音訊、SQLite 會議庫、匯入／重轉錄、模型管理、更新與 onboarding、可編輯摘要及跨平台封裝。
- **最佳架構是「驗證與產品分工，量測勝出後單向移植」**。現階段維持兩個執行 repo，避免建立共享服務、跨語言 framework 或第三套中介層。第二個真實 consumer 出現，或模型隔離成為可量測的可靠性需求時，再啟動共用 runtime。
- **Meetily 應成為長期產品表面；AURA 應持續作為能力驗證與證據產生器**。當 Meetily 具備 AURA 等級的臺灣華語品質、artifact 與失敗可診斷性後，AURA 的 PyQt UI 才進入退場 gate。
- **ASR 的物理執行契約是 GPU-only、fail-closed**。AURA 只接受 CUDA；Meetily 依正式發布平台啟用 CUDA、Vulkan 或 Metal。GPU backend 尚未啟用、初始化失敗或執行環境不符合建置契約時，轉錄會停止並回報啟用 gate，不會以 CPU 取得一個較慢但看似成功的結果。
- **完整 audit trail**：[`2026-07-14 GPU-only ASR live benchmark audit event`](audit-events/2026-07-14-gpu-only-asr-live-benchmark/audit-event.md) 連接 source、implementation、validation、publication 與下一 evidence gate。

## 第一性原理：從物理目的而非既有程式碼出發

會議工具的根本任務不是「錄音、跑模型、產生一篇文字」，而是：

> 以最低的操作與校正成本，把真實聲音轉成可追溯、可覆核、可再次使用的決策與行動。

### 稀缺資源

依重要性排序：

1. **人的注意力**：錄音設定、等待、修字、確認講者、重新整理摘要都會消耗操作時間。
2. **可信任度**：錯誤專有名詞、錯置講者、摘要無法回到逐字稿，會快速消耗採用意願。
3. **音訊品質**：輸入訊號決定 ASR 上限；後端模型無法完整補回未被擷取的聲音。
4. **本機算力與記憶體**：模型大小、並行度、context 長度與跨平台 backend 直接競爭同一份資源。
5. **維護頻寬**：Python、Rust、TypeScript、CUDA、ONNX、FFmpeg、Tauri、Next.js 每增加一層，都增加發布與除錯成本。
6. **隱私與資料治理**：本機預設、明確啟動的 cloud provider，以及可見的 artifact boundary 是產品能力。

### 五步工程演算法

本次採用以下順序：

1. **質疑需求**：每一個 backend、狀態、依賴、測試與抽象都必須對目前真實路徑負責。
2. **刪除零產出的部分**：先刪 archive、backup、未編譯模組、假 server 狀態、重複 dependency contract。
3. **簡化真實路徑**：Meetily 收斂為 Tauri ↔ SQLite／本機模型；AURA 收斂為 `pyproject.toml` ↔ `uv.lock`。
4. **加速已證明必要的流程**：前端依賴、靜態輸出、安全版本與確定性 timeout 先行優化。
5. **自動化驗證**：讓 Node 測試、ESLint、TypeScript、Next production build、Cargo workspace tests 與 AURA unittest 成為可重跑 gate。

## 系統比較

| 面向 | Project AURA | Meetily | 第一性原理判斷 |
|---|---|---|---|
| 產品形態 | Python／PyQt6 驗證型桌面工具 | Rust／Tauri 2 + Next App Router 桌面產品 | 長期產品 UI 由 Meetily 擁有；AURA 保留研究與驗證速度 |
| 主要使用情境 | 臺灣華語錄音、轉錄、校正、實驗與 artifact 檢查 | 跨平台錄音、會議庫、匯入、搜尋、重轉錄、摘要與模型管理 | 角色互補，產品層合併的效益低於風險 |
| 音訊來源 | 以麥克風／檔案與 Python 音訊處理為主 | 麥克風 + 系統音訊、裝置偵測、混音、VAD、FFmpeg 與播放 | Meetily 的 capture 層更接近產品需求 |
| ASR | `faster-whisper` + CTranslate2，Breeze ASR 25，固定 CUDA／int8，臺灣詞彙與模糊校正 | `whisper-rs` GGML + CUDA／Vulkan／Metal，以及 Parakeet ONNX + CUDA | 同名 Breeze 不代表可直接交換權重；同一份繁中語料已建立 live paired benchmark，產品選擇繼續由真實修正成本決定 |
| 臺灣語境 | 領域詞彙、繁體中文、校正與實驗資產較成熟 | 模型選擇已涵蓋 Breeze，語境後處理證據較少 | AURA 是演算法與字詞品質的 canonical home |
| 說話者分離 | 有 pyannote optional path 與相關實驗文件 | 產品資料結構與 UI 可承接，但目前能力較薄 | 在 AURA 驗證 DER／人工修正成本，再移植結果 |
| 降噪 | 有 noisereduce、WebRTC VAD 與降噪評估／handoff | 有 RNNoise、EBU R128、VAD、混音與訊號管線 | 用真實 noisy corpus 決定組合，避免串接所有處理器造成失真與延遲 |
| 摘要 | Ollama 欄位批次、結構化 schema、artifact 與 failure evidence | 本機 llama sidecar、Ollama／cloud providers、template、翻譯與可編輯 BlockNote | Meetily 擁有產品摘要；AURA 提供 schema／evidence 驗證方法 |
| 儲存與檢索 | 檔案與 artifact 導向 | SQLite repository、會議清單、分頁逐字稿、搜尋與 metadata | 產品 canonical data 由 Meetily SQLite 擁有 |
| 可觀測性 | 每次執行輸出 artifact、runtime 與錯誤證據較完整 | 具 log、analytics、狀態與測試，使用者可回溯 artifact 仍可加強 | Meetily 下一個高價值移植項是 artifact contract，不是另一套 UI |
| 跨平台 | Python／CUDA 與 Windows 路線明確，封裝面較重 | Tauri 對 macOS／Windows／Linux，以 Metal／Vulkan／CUDA 提供 GPU ASR；CPU／OpenBLAS ASR feature 已退役 | Meetily 是發布主體；每個 release workflow 必須明確啟用該平台的 GPU backend |
| UI 狀態 | 大型 PyQt tab，迭代快但單檔責任較集中 | React context、hooks、modal、onboarding 完整，但累積未使用狀態與 Hook 警告 | 先刪死狀態，再依真實 render／profiling 拆分 |
| 安全模型 | 本機模型與 artifacts，Python supply chain | Tauri CSP、本機與 cloud provider、Node + Cargo supply chain | 明確 endpoint 與依賴稽核是 release gate |
| 測試 | stdlib unittest，supported gate 為 `make check`，另有真實 CUDA benchmark | Rust workspace、Node stdlib、TypeScript、ESLint、Next production build，以及 release-mode CUDA adapter | 兩邊都具可自動化基礎；共同繁中語料已形成最小 live gate，下一層擴充長音訊與遠距雜訊 |

## 審查時的基準證據

### Project AURA

- 280 個 tracked files，tracked size 約 2.54 MB。
- `src` 約 8,679 行、`scripts` 約 4,442 行、`tests` 約 4,657 行。
- 43 個 `unittest.TestCase` 類別，supported check 實際執行 282 個測試。
- 最大 UI 熱點是 `src/aura/ui/transcription_tab.py`，約 1,811 行。它是結構風險，但目前缺少 render latency、錯誤集中度或變更衝突證據；保留為有條件重構項。

### Meetily

- 基準為 528 個 tracked files、約 46.7 MB。
- TypeScript 約 30,632 行、Rust 約 44,189 行、舊 Python backend 約 2,255 行。
- 基準 repo 同時保留 Tauri runtime、標示為 unsupported 的 FastAPI archive、數套未編譯或 backup 音訊實作，以及 4.46 MB Visual Studio installer。
- 基準 package 直接 dependencies + devDependencies 共 69 項，並同時宣告 BlockNote、Remirror 與 Tiptap React editor surface；實際產品路徑使用 BlockNote。
- 基準 `pnpm audit --prod`：18 個已知漏洞（6 high、10 moderate、2 low）。
- 基準 TypeScript test 引用未宣告的 `bun:test`；Cargo 可編譯，但有 ignored workspace config 與 10 項 compiler warning。

## 本輪已落地的改變

### Project AURA：單一依賴契約

- 以 `pyproject.toml` 作為直接依賴與 optional capability 的唯一宣告。
- 以 `uv.lock` 作為可重現解析結果。
- 移除重複且已凍結 transitive dependencies 的 `requirements.txt`。
- 移除 runtime 中的 `setuptools` 與未被測試程式使用的 pytest optional group；build-system 仍正式擁有 setuptools。
- README 對齊實際安裝與摘要路徑：日常 Ollama UI 使用核心安裝，Transformers 實驗才啟動 `summary` extra。

結果：4 個檔案變更，淨減少 118 行；`uv.lock` 同步移除 pytest、iniconfig 與 plug。

### Project AURA：刪除未經 live evidence 支持的摘要平行架構

- 保留目前唯一受支援的本機 Gemma field-batch 摘要路徑。
- 移除 Graph-RAG deterministic dry harness、目標架構草稿、MVP scaffold 與其測試；歷史設計仍可由 Git 取回。
- 將比較性摘要研究的啟動條件收斂為：具授權 paired corpus、真實模型執行、schema validity、來源支持率、錯誤紀錄與人工修正時間。

結果：25 個檔案變更，淨減少 3,787 行。維護頻寬回到已投入日常工作的 runtime，不再把 scaffold 誤認為完成的實驗。

### 兩個 repo：ASR GPU-only 執行契約

- AURA 的 `AppSettings`、live／file model loader 與降噪評估入口皆拒絕 CPU ASR；CUDA runtime 尚未完成啟用時提供明確診斷。
- Meetily 的 Whisper runtime 驗證編譯 backend 與執行環境；未取得相符 GPU backend 時停止載入模型。
- Meetily Parakeet session 明確使用 CUDA Execution Provider，設定 `session.disable_cpu_ep_fallback=1`，並移除 CPU Execution Provider 與 OpenBLAS build scripts。
- Linux／Windows release workflows 以 Vulkan 發布通用 GPU 路徑；CUDA release script 提供可重現的 compute capability 與 PIC 旗標；macOS 使用 Metal。

這項契約移除「CPU fallback 讓功能表面成功、實際延遲與產品假設失真」的測量污染。GPU 是 ASR 的必要資源；診斷與啟用流程承接環境差異。

### Meetily：刪除平行世界

- 移除整個 unsupported `backend/` FastAPI／Docker／whisper archive；Git history 繼續提供歷史取用。
- 移除 `audio_v2` 未編譯模組、`lib_old_complex.rs`、`core-old.rs`、`recording_saver_old.rs`、`.backup` 與其他未納入 module tree 的音訊檔案。
- 移除 4.46 MB `vs_buildtools.exe` 與舊 build backup script。
- 移除 dead sample `/notes/[id]` route；它同時包含展示資料、舊導航分支與 `dangerouslySetInnerHTML`。
- 移除舊 localhost FastAPI API helper、profile commands、backend connectivity debug commands，以及前端 5167／8178 假 server state。
- CSP `connect-src` 收斂為產品實際使用的本機 Ollama 與明確 cloud endpoint。
- Whisper model path 收斂至產品 models directory。

### Meetily：簡化真實音訊與 UI 流程

- 移除未使用的 `AudioCapture.recording_sender`、`AudioStream` 轉接參數與 `AudioPipeline.state`；錄音持續由實際 mixed-audio pipeline 寫入。
- Sidebar 的會議清單改為 `useMemo(meetings)` 的衍生資料，取代 mirrored state 與同步 effects。
- Sidebar 移除未渲染的 model／transcript settings 狀態、listeners、save handlers、imports 與無效 window callback。
- 所有 file item 直接導向真實 `/meeting-details?id=...`，首頁 intro item 保留 `/`。
- Bluetooth buffer timeout 改用整數奈秒運算，消除跨平台浮點 rounding 邊界。

### Meetily：完成 CPAL stream ownership migration

- `cpal::Stream` 的建立、持有、暫停與釋放集中在 dedicated owner thread。
- start／pause／stop／shutdown 透過 channel 傳遞，移除跨 thread 移動 native stream 所需的四層 `unsafe impl Send`。
- 刪除 2,242 行未接入產品路徑的舊監控、system detector、post-processor 與重複 UI surface。
- 25 次真實 microphone lifecycle 循環均完成 start／stop／drop，讓 native ownership 從設計意圖成為可重跑的 live evidence。

這個改動把資源生命週期交還給建立資源的 thread；UI 與 command handler 只傳遞意圖，不再持有平台音訊資源。

### Meetily：依賴與安全收斂

- 直接 package 宣告由 69 項降至 49 項。
- 移除實際程式無 import 的 Remirror、Tiptap React UI、React Markdown、Zod、Lodash、額外 Tauri JS plugin、等待／併行工具與其他重複 packages。
- 保留 BlockNote 真實需要的 `@tiptap/pm`，並以單一 ProseMirror resolution 維持 editor identity。
- Next.js 升至 15.5.20 安全線；加入正式 ESLint 9 gate。
- 以 pnpm workspace policy 明確固定已修補的 transitive versions，並明確拒絕產品不需要的 install scripts。
- 生產依賴稽核結果由 18 個已知漏洞降為 0。
- Node dependency install 的一次變更曾顯示移除 261 個 packages；加入 ESLint gate 後仍維持直接宣告的大幅收斂。

### Meetily：可重跑驗證

- BlockNote markdown 測試由未宣告的 Bun runtime 改為 Node 內建 `node:test`。
- `pnpm test`：9 tests passed；BlockNote markdown 與 summary-language local fallback 都使用 Node 內建 runner。
- `pnpm exec tsc --noEmit`：passed。
- `pnpm lint`：可執行、0 blocking errors；首次啟用 gate 時的 322 項 warnings 已降至 289 項，分布於 72 個檔案。Sidebar touched scope 已清至 0 warnings。
- `pnpm build`：Next 15 production static export passed；輸出路由為 `/`、`/meeting-details`、`/settings` 與框架 404。
- `pnpm audit --prod`：0 known vulnerabilities。
- `cargo test --workspace`：Meetily library 185 passed、2 ignored；llama-helper 2 passed；doc test 1 passed。
- 初次審查的 `make check PYTHON=.venv/bin/python`：AURA compile + 282 tests passed；刪除 6 個 retired summary-scaffold tests 並加入 GPU policy tests 後，2026-07-14 supported gate 為 276 tests passed。

Meetily 目前 diff 的主要量體為 101 個檔案、65 個刪除檔；文字淨減少 32,064 行，另移除 4,460,128 bytes 的 binary installer。Lockfile 與 touched Rust formatting 會產生機械性行數變動，架構價值以「刪除的 runtime／依賴／入口」衡量。

## 效率瓶頸與下一階段優先序

### P0-A：Linux native audio ownership gate（已完成）

本輪驗證期間，另一個工作階段完成並保存一份真實非預期終止事件：[`Meetily 非預期終止 Audit Event`](../../meetily/docs/audit-events/2026-07-13-uncontrolled-shutdown/audit-event.md)。原始 73,837-byte log 已逐 byte 保存，顯示 glibc 以 `corrupted double-linked list` 結束 process；第一個造成 heap 損壞的 native instruction 仍由 core dump／sanitizer 確認。

本輪先完成低風險 containment：

- Linux 裝置發現由每輪三次 native scan 收斂為 input 與 output 各一次。
- 穩定裝置的 polling interval 現在會實際切換為 5 秒；裝置遺失時才使用 2 秒。
- 新增 interval regression test，保護 stable／missing 兩個頻率契約。

owner-thread migration 已落地：`cpal::Stream` 保留在 dedicated thread，command channel 接收 start／pause／stop／shutdown，四層 `unsafe impl Send` 已移除，25 次 microphone lifecycle live 循環通過。這關閉了最直接的 native ownership 風險。

下一層驗收是長時間 microphone + system audio、hot-plug／default-device change、受控 shutdown markers 與原始非預期終止案例的壓力重播。這一層量測長時間與裝置變更可靠性，不會重新引入跨 thread stream ownership。

### P0-B：本輪完成的地基

1. 單一 runtime boundary。
2. 單一 dependency contract。
3. dead code／archive／binary 清除。
4. production dependency audit 清零。
5. 兩邊 supported tests 與 Meetily production build 通過。

### P1：共同繁中語料的最小 live gate（已完成）

第一個最小 live benchmark 使用固定 revision 的公開 Common Voice 24 臺灣華語清理資料，選取 5 段帶 reference 的真實音訊；以固定 seed 隨機排序，每個 runtime、每段音訊重複 2 次，共 20 次真實推論。每次執行保留 request summary、event trace、error log、GPU telemetry、實際音訊與決策報告。

| Runtime | 有效性 | Runs | Exact | Mean CER | Mean time | Mean RTF | Model load |
|---|---|---:|---:|---:|---:|---:|---:|
| AURA `faster-whisper`／Breeze ASR 25 | `valid_target_runtime`，CUDA/int8 | 10 | 8 | 0.0714 | 0.290 s | 0.114 | 3.315 s |
| Meetily `whisper-rs`／Breeze ASR 26 | `valid_target_runtime`，CUDA release | 10 | 8 | 0.0571 | 0.196 s | 0.076 | 0.729 s |
| Meetily Parakeet | `blocked_runtime` for zh-TW | 0 | — | — | — | — | — |

Parakeet 留在語言 capability gate：目前正式模型能力不涵蓋臺灣華語，因此不以錯誤語言模型製造無效比較。完整證據位於 [`artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/`](../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/)。

最低證據欄位：

- 臺灣專有詞／人名／醫療或技術領域詞的 error rate。
- CER／WER 與人工修正字數。
- real-time factor、首段等待時間、總處理時間。
- peak RAM／VRAM、模型載入時間。
- 長音訊失敗率、重試與 cancellation 行為。
- 說話者分離 DER 或人工講者修正次數。
- 摘要 claim 可回指 transcript 的比例，以及人工完成確認所需時間。

最小 gate 證明兩條 CUDA 路徑均能真實執行，並提供小型 clean-speech 基線；它尚未決定產品預設。下一輪將同一 evidence contract 擴充至長音訊、遠距、重疊語音與雜訊，並補齊人工修正時間、peak VRAM、cancellation、重試與 crash recovery。達成這層後，才選定要移植的 ASR、校正、降噪與 diarization 組合。

### P1：Meetily 前端體積與狀態債

production build 顯示 `/meeting-details` First Load JS 約 845 kB，是目前最清楚的前端效能候選。優化順序：

1. 以 bundle analyzer 確認 BlockNote、modal 與 model manager 的實際占比。
2. 對編輯器與低頻設定 UI 使用 route-level／component-level dynamic import。
3. 以 interaction timing 驗證首次開啟會議與首次開啟 editor 的取捨。
4. 逐檔刪除目前 289 項 lint baseline 中的 unused code；Hook dependency 警告以行為測試保護後修正。

目標值：meeting detail 初始 JS 降至 600 kB 以下，或取得資料證明 845 kB 對 Tauri 本機載入未形成可感知瓶頸。

### P1：把 AURA 的證據能力移植到 Meetily

優先移植 contract，而非 Python UI：

- 每次 ASR／摘要的 runtime metadata。
- 模型、參數、輸入 hash、時間、失敗與 retry artifact。
- transcript span ↔ summary claim 的 evidence link。
- 可匯出的 failure bundle。

這讓 Meetily 在產品層具備 AURA 的可診斷性，也讓之後的演算法比較能使用同一份資料契約。

### P2：條件式大改

| 候選大改 | 可行性 | 啟動 gate | 判斷 |
|---|---:|---|---|
| AURA 校正邏輯移植到 Rust | 高 | paired corpus 證明其穩定降低人工修正量 | 優先移植規則與測試 corpus，避免嵌入 Python runtime |
| AURA 摘要 schema／verifier 移植到 Meetily | 中高 | 同一 transcript 的人員覆核時間明顯改善 | 由 Rust 或 TypeScript 實作 contract；sidecar 只在模型隔離需求成立時採用 |
| Meetily 加入完整 artifact contract | 高 | 欄位定義完成 | 直接提升可信任度與可除錯性 |
| Meetily editor 動態載入 | 高 | bundle 分析確認 editor 為主要來源 | 低架構風險，需驗證 Tauri 首次互動 |
| 退役 AURA PyQt UI | 中 | Meetily 達成臺灣 ASR、artifact、Windows RTX 與實驗操作 feature parity | 保留 AURA CLI／evaluation package，逐步收斂 UI |
| 合併為單一 monorepo | 低效益 | 共享 release cadence 與跨 repo 原子變更成為持續痛點 | 目前維持兩 repo 更節省維護頻寬 |
| 建立共享網路 ASR service | 中 | 第二個真實 consumer 或 process isolation 帶來可量測可靠性收益 | 本機產品現階段直接呼叫更簡單、隱私邊界更清楚 |
| Graph RAG／向量資料庫 | 條件式 | 實際跨會議 retrieval 任務超出 SQLite FTS／metadata 能力 | 以 retrieval benchmark 啟動，避免技術先行 |

## 明確延後清單

- AURA `transcription_tab.py` 的全面拆分：以變更衝突、錯誤密度、render latency 或測試困難度作為啟動證據。
- 兩 repo 共享 domain model package：第二個同步 consumer 出現後再抽取。
- 同時保留多套 ASR／降噪／摘要為產品預設：paired evaluation 只保留勝出者；其他 GPU ASR 能力定位為研究候選，CPU ASR 不進入 fallback 路徑。
- 自建 FastAPI server：process isolation、remote execution 或多 client 需求成立後另案啟動。
- 全量 major dependency upgrade：安全線、實際 capability 與 release test 分批推進。

## 最終架構

```text
授權且去識別化的真實會議 corpus
             │
             ├── Project AURA
             │     ├── ASR／校正／降噪／diarization 實驗
             │     ├── runtime artifacts 與 paired reports
             │     └── 勝出 capability + tests + contract
             │
             └──────────量測通過後移植──────────┐
                                                ▼
使用者 ── Meetily Tauri UI ── Rust audio/ASR/summary ── SQLite
              │                       │                  │
              └── 操作與覆核 ─────────┴── evidence artifacts
```

## 下一個可驗收決策

下一個 gate 是把已通過的 GPU-only benchmark 從 5 段 clean speech 擴充為具授權的長音訊、遠距、重疊語音與雜訊 corpus。唯一勝出條件仍是「最少人工修正、最短完成確認、可接受的 GPU 記憶體與取消恢復行為、完整可追溯證據」。模型名稱、framework 與既有投資不構成保留理由；量測結果決定產品預設、GPU fallback、研究候選與退場項目。
