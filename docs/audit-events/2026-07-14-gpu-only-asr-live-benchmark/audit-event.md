# Project AURA × Meetily GPU-only ASR Live Benchmark Audit Event

## 事件識別

- Event ID：`AUDIT-2026-07-14-AURA-MEETILY-GPU-ASR-001`
- 事件時間：`2026-07-13 22:55:44` 至 `2026-07-14 00:30:48`（Asia/Taipei；以相關 commit 時間與 live artifact 為準）
- Audit record closeout：`2026-07-14 00:49 CST`（Asia/Taipei；文件、連結與目前工作樹重新驗證）
- 事件類型：跨 repo 架構收斂、GPU-only ASR policy、真實 paired benchmark 與發布 closeout
- 目前狀態：`source preserved`、`adopted decision`、`validated`、`LIVE_MINIMUM_COMPLETED`、`implementation published`
- Canonical home：Project AURA execution repo
- Product counterpart：[`JasonLn0711/meetily`](https://github.com/JasonLn0711/meetily)
- Planning mirror：`planning-everything-track` 僅保存 locator、status、capacity、publish evidence 與 next gate

## FIRST PRINCIPLE routing

```text
scarce_resource: 可相信的逐字稿、人工覆核時間、GPU 容量、維護頻寬
canonical_home: Project AURA 擁有 paired evaluation 與 evidence contract；Meetily 擁有產品 runtime
planning_role: locator、status、capacity impact、publish evidence、next gate
evidence_path: artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/
next_gate: 長音訊、遠距、重疊語音與雜訊的 reference-backed GPU benchmark
```

## 結論

本事件把 ASR 的執行假設收斂成一項可驗證契約：Project AURA 的 ASR 只在 CUDA 上執行；Meetily 的 ASR 只在已編譯且與執行環境相符的 GPU backend 上執行。GPU readiness 是 activation gate，所有未完成 GPU 啟用的請求會提供明確錯誤並停止，不會產生 CPU ASR 結果。

兩條 NVIDIA 路徑已用同一組真實臺灣華語音訊完成最小 live benchmark。AURA Breeze ASR 25 與 Meetily Breeze ASR 26 各完成 10 次 CUDA inference，總計 20 次；5 個來源 WAV、逐次 transcript、event trace、GPU telemetry、latency、failure analysis 與 decision report 均已保存，`error_log.jsonl` 為空。

這份最小 clean-speech evidence 證明 runtime activation、paired protocol 與 artifact contract 可運作。產品預設維持各 repo 現有 Breeze runtime；跨 repo capability migration 由下一輪長音訊與真實會議條件的人工修正成本決定。

## 觸發背景

### Confirmed：跨 repo 第一性原理審查

使用者要求完整比較 Project AURA 與 Meetily，允許刪除、簡化與架構變更。審查把兩個 repo 的責任定義為：

- Project AURA：臺灣華語 ASR、校正、降噪／說話者分離實驗、artifact 與 falsifiable promotion gate。
- Meetily：Tauri 產品介面、音訊擷取、SQLite、編輯、模型管理與跨平台發布。
- 共享原則：以同一語料量測勝出後單向移植；在第二個真實 consumer 或可量測 isolation requirement 出現前，不增加共享 service 或第三套中介層。

Canonical decision record：[`docs/first-principles-aura-meetily-review.md`](../../first-principles-aura-meetily-review.md)。

### Confirmed：ASR 必須使用 GPU

使用者明確指定所有相關 repo 的 ASR 不得使用 CPU inference。這個要求被實作為 central invariant，而不是 UI preference：

- AURA `AppSettings` 拒絕任何非 `cuda` 的 ASR device。
- AURA ASR-backed denoise evaluator 的 CLI 只接受 `--device cuda`，函式入口再次驗證。
- Meetily Whisper 檢查 compiled backend 與 runtime GPU 是否相符。
- Meetily Parakeet 明確註冊 CUDA Execution Provider，並停用 ONNX Runtime CPU provider fallback。

### Confirmed：live evidence 是完成條件

工程 scaffold、compile、unit test 與 benchmark adapter 只構成 preflight。完成條件要求真實模型、真實 GPU、真實音訊、真實時間戳、可稽核輸出與錯誤紀錄。本事件因此保存整組 live artifacts，而不是只報告 CUDA build 成功。

## 事件時間線

| 時間（Asia/Taipei） | Repo / commit | 事件與證據意義 |
|---|---|---|
| 2026-07-13 22:55:44 | Meetily `9434e9f` | 刪除 2,242 行未接入產品的舊音訊監控與重複 UI 路徑，縮小 native audio surface。 |
| 2026-07-13 23:07:36 | Meetily `1f4be5d` | `cpal::Stream` 移入 dedicated owner thread；四層 `unsafe impl Send` 移除。 |
| 2026-07-13 23:10:01 | AURA `784b717` | 移除 3,787 行沒有 live model evidence 的摘要平行 scaffold。 |
| 2026-07-13 23:18:02 | Meetily `528cad1` | 建立 Parakeet model-language capability contract；zh-TW 路由至 Local Whisper。 |
| 2026-07-13 23:22:38 | Meetily `0259461` | onboarding 下載與產品設定對齊 Breeze ASR 26。 |
| 2026-07-13 23:23:17 | Meetily `7a39693` | Linux CI 安裝目前 CPAL PipeWire build 所需的開發套件。 |
| 2026-07-13 23:29:12 | Meetily `bff4cb9` | 新增最小 live ASR adapter，輸出 backend、model、時間與 transcript。 |
| 2026-07-13 23:44:23 | AURA `0ffe59e` | AURA settings 與 ASR-backed evaluator 落實 CUDA-only policy。 |
| 2026-07-14 00:03:05 | Meetily `4a97604` | Whisper／Parakeet GPU-only runtime、build scripts 與文件收斂。 |
| 2026-07-14 00:03:13 | Meetily `182b551` | Linux／Windows release workflows 改為 GPU-enabled build。 |
| 2026-07-14 00:23:33 | Meetily `69e3e3c` | CUDA architecture、PIC 與 runtime detection 成為可重現 release activation。 |
| 2026-07-14 00:30:07 | AURA `32c1361` | paired CUDA benchmark scripts、CC0 WAV、logs、reports 與 dependency contract 發布。 |
| 2026-07-14 00:30:48 | AURA `cca641b` | README、架構決策、refactor plan 與跨 repo review 對齊 live evidence。 |

## AURA implementation record

### CUDA-only invariant

[`src/aura/settings.py`](../../../src/aura/settings.py) 的 `AppSettings.__post_init__` 在物件建立時拒絕 `device != "cuda"`。這是 AURA UI、live ASR、file ASR 與共用 defaults 的集中入口，因此 caller 無法以另一個設定值啟用 CPU ASR。

[`scripts/evaluate_denoise_backends.py`](../../../scripts/evaluate_denoise_backends.py) 保留不執行 ASR 的純音訊處理模式；只要提供 ASR model，就必須使用 CUDA。CLI 以單一 `cuda` choice 表達產品契約，`transcribe_audio()` 再於模型載入前驗證，讓直接函式呼叫也遵守同一界線。

Regression evidence：

- `tests/test_settings.py::test_custom_settings_reject_cpu_asr`
- `tests/test_evaluate_denoise_backends.py::test_transcription_rejects_cpu_before_loading_model`
- 原有 `tests/test_gpu_policy.py` 繼續保護 model loader 的 CUDA pin 與 missing-runtime failure path。

### Deletion-first architecture cleanup

Commit `784b717` 移除 Graph-RAG deterministic dry harness、目標架構草稿、MVP scaffold 與其測試，共淨減少 3,787 行。Git history 保留設計 provenance；active tree 只保留已投入使用的 Gemma field-batch summary runtime。新的 comparative summary architecture 由 licensed paired corpus、真實 inference、schema validity、source support、failure record 與人工修正時間啟動。

## Benchmark source layer

Canonical source note：[`SOURCE.md`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/SOURCE.md)。

| 欄位 | 保存值 |
|---|---|
| Dataset | `OKHand/Clean_Common_Voice_Speech_24.0-TW` |
| Dataset card license | CC0 1.0 |
| Fixed revision | `96d8e4fcc3b0d0db304fec018d4b813360160e2b` |
| Shard | `data/train-00000-of-00009.parquet` |
| Selected rows | `0`, `6`, `20`, `61`, `96` |
| Distinct WAV files | 5 |
| Manifest evidence | source row、reference、MOS、SHA-256、revision |
| Materialization | `scripts/prepare_common_voice24_benchmark.py` |

來源音訊與 reference 已隨 artifact 保存。這組資料的證據範圍是短句、clean speech 與臺灣華語 runtime activation；長會議、遠距、重疊、環境噪音與不同裝置條件由下一 validation layer 承接。

## Benchmark protocol

- Random seed：`20260713`
- Repetitions：每個 runtime、每個 case 2 次
- Randomized request count：每個 runtime 10 次；總計 20 次
- AURA runtime：`faster-whisper`、`SoybeanMilk/faster-whisper-Breeze-ASR-25`、CUDA、int8
- Meetily runtime：release-mode `whisper-rs`、`ggml-breeze-asr-26.bin`、CUDA compute capability 8.9
- Meetily build controls：`--features cuda`、`CMAKE_CUDA_ARCHITECTURES=89`、PIC enabled
- GPU monitor interval：0.1 秒
- Runtime acceptance：`compiled_backend == "Cuda"`、`gpu_inference_required == true`、`runtime_validity == "valid_target_runtime"`
- Failure handling：任何 build、model load、inference、result-count 或 backend-contract error 進入 `error_log.jsonl` 並停止 run

Runnable owner：[`scripts/benchmark_aura_meetily_asr.py`](../../../scripts/benchmark_aura_meetily_asr.py)。

## Live results

| Runtime | Validity | Runs | Exact | Mean CER | Mean runtime | Mean RTF | Model load | Max GPU utilization |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `aura_faster_whisper` | `valid_target_runtime` | 10 | 8 | 0.0714 | 0.290 s | 0.114 | 3.315 s | 98% |
| `meetily_whisper_rs` | `valid_target_runtime` | 10 | 8 | 0.0571 | 0.196 s | 0.076 | 0.729 s | 89% |
| `meetily_parakeet` for zh-TW | `blocked_runtime` | 0 | — | — | — | — | — | — |

完整結果：

- [`runtime_validity_report.md`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/runtime_validity_report.md)
- [`latency_report.md`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/latency_report.md)
- [`request_summary.jsonl`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/request_summary.jsonl)
- [`event_trace.jsonl`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/event_trace.jsonl)
- [`gpu_metrics.jsonl`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/gpu_metrics.jsonl)
- [`meetily_stderr.log`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/meetily_stderr.log)

## Failure analysis

所有 20 次 request 均完成，`error_log.jsonl` 為空。兩個 runtime 的非 exact 結果都集中在 `cv24-096`：

| Runtime | Reference | Transcript | CER |
|---|---|---|---:|
| AURA | 必要時可再另案召開考績會研處 | 並要時可在另案召開考機會演出 | 0.3571 |
| Meetily | 必要時可再另案召開考績會研處 | 病藥食可在另案召開考績會研處 | 0.2857 |

這筆結果把「必要時／可再／考績／研處」標記為下一語料的行政領域詞 evidence seed。最小樣本不支援一般化的跨產品品質排名；它支持兩條 CUDA runtime 都進入更廣 corpus 的研究候選層。

Canonical failure record：[`failure_analysis.md`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/failure_analysis.md)。

## Model-language capability decision

### Confirmed

Meetily Parakeet v3 的產品 capability contract 列出 25 種歐洲語言，zh-TW 不在支援集合；v2 為 English-only。zh-TW request 因此在模型載入／推論前路由至 Local Whisper。這保護 benchmark 不會以不相容語言模型產生看似完整但無效的比較。

### Deferred activation

Parakeet 的 CUDA runtime 可在其正式支援語言 corpus 上另案驗證。繁中 lane 保留 Breeze／Local Whisper，直到正式模型 capability 或已驗證權重涵蓋 zh-TW。

## Validation record

### AURA supported gate

```text
make check PYTHON=.venv/bin/python
Ran 276 tests
OK
```

### Artifact contract

- 20 個 `request_summary.jsonl` records
- 24 個 `event_trace.jsonl` records
- 5 個持久化 WAV files
- 51 個 GPU telemetry samples
- 0 個 error records
- 所有 20 個 result 均記錄 `Cuda`、`gpu_inference_required=true`、`valid_target_runtime`
- durable JSONL paths 不含 machine-specific home path

### Meetily counterpart gate

- 5 個 Whisper acceleration policy tests passed
- 1 個 Parakeet CUDA activation test passed
- 4 個 Parakeet model-language capability／routing tests passed
- release CUDA example build passed
- 10 次 Meetily real CUDA inference completed
- stderr 明確記錄 `use gpu = 1`、CUDA device、compute capability 8.9 與 CUDA model allocation

### Audit record integrity

- `2026-07-14` 重新執行 AURA `make check PYTHON=.venv/bin/python`：`276` tests passed。
- AURA 與 Meetily 本次 audit／backlink 文件共 `75` 個本機相對連結完成解析。
- AURA、Meetily、planning 三個 repo 的 `git diff --check` 均通過。
- Planning knowledge validator 通過：`157` metadata notes 與 `157` catalog entries 對齊。

## Decision register

| Decision | Evidence label | Adopted action |
|---|---|---|
| ASR GPU-only | `confirmed` | AURA 只接受 CUDA；Meetily 只接受 activated GPU backend。 |
| CPU ASR fallback | `scope change` | 從可能的低速 fallback 移出 supported runtime；activation errors 保持可見。 |
| AURA product default | `confirmed` | 保留 Breeze ASR 25 CUDA/int8。 |
| Meetily product default | `confirmed` | 保留 Breeze ASR 26 Local Whisper GPU path。 |
| Parakeet zh-TW | `deferred activation` | 由 model-language contract 阻擋；不列入繁中 quality ranking。 |
| Cross-repo winner | `pending confirmation` | 最小 clean corpus 不選 winner；由長音訊與真實會議 evidence 決定。 |
| Shared ASR service／monorepo | `deferred activation` | 第二個 consumer 或可量測 isolation/release benefit 出現後再評估。 |

## Connection map

| 入口 | 連結目的 |
|---|---|
| [`README.md`](../../../README.md) | 使用者與未來 agent 的第一個 GPU-only／live benchmark 入口。 |
| [`docs/architecture_decisions.md`](../../architecture_decisions.md) | ASR ownership、GPU execution contract 與 evidence policy。 |
| [`docs/first-principles-aura-meetily-review.md`](../../first-principles-aura-meetily-review.md) | 跨 repo 角色、刪除結果、CPAL gate、優先序與下一決策。 |
| [`docs/refactor_plan.md`](../../refactor_plan.md) | GPU-only 與 cross-repo evaluation phase 的完成／下一步狀態。 |
| [`artifacts/.../SOURCE.md`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/SOURCE.md) | Corpus revision、license、rows 與 SHA evidence 的 source layer。 |
| [`artifacts/.../final_decision_report.md`](../../../artifacts/asr-benchmark/2026-07-13-common-voice24-minimum/final_decision_report.md) | 最小 live gate 的 production／fallback／research decision。 |
| [Meetily counterpart audit](https://github.com/JasonLn0711/meetily/blob/main/docs/audit-events/2026-07-14-audio-owner-gpu-asr-hardening/audit-event.md) | 產品 repo 的 native audio ownership、model routing 與 GPU build evidence。 |
| `planning-everything-track/data/projects/2026-05-project-aura-refactor.md` | 薄式 status、capacity、publish evidence 與 next gate。 |
| `planning-everything-track/weeks/2026-W29/days/2026-07-14.md` | 當日 closeout 與 W29 capacity boundary。 |

## Unresolved question and action ledger

| ID | Question / action | Owner | Due / trigger | Evidence needed |
|---|---|---|---|---|
| `ASR-NEXT-001` | 建立長音訊、遠距、重疊與雜訊 corpus | Jason / next evaluation run | W29 primary lane 容量允許且 reference set ready | 授權、去識別化音訊與 trusted references |
| `ASR-NEXT-002` | 比較人工修正與確認成本 | Evaluation owner | broader corpus run | 原始／修正 transcript、修正字數、確認時間 |
| `ASR-NEXT-003` | 補齊 peak VRAM、cancellation、retry、recovery | Runtime owners | broader corpus run | GPU metrics、cancel trace、failure/recovery logs |
| `ASR-NEXT-004` | 選擇產品 default 或 capability migration | AURA + Meetily owners | `ASR-NEXT-001..003` 完成 | 同 corpus decision report |
| `ASR-NEXT-005` | 驗證 Parakeet CUDA runtime | Meetily owner | 有正式支援語言的 paired corpus 時 | real audio、CUDA EP proof、transcript、latency、error log |

## Publication evidence

### Project AURA

- `784b71761723c8f8633861bdc08a98edcd807bf9` — retire unvalidated summary scaffolds
- `0ffe59e104b0ae82cc09143783ab447647961d1e` — enforce CUDA-only inference
- `32c13610d936eb2b30e95ed9acca63ce246e8cb1` — add paired CUDA live benchmark
- `cca641bebe21c8dadf1e1e1b41b2810618ce3d45` — close first-principles GPU benchmark gates
- Remote：`JasonLn0711/project_aura` `main`
- Post-push divergence at closeout：`0 0`

### Meetily

- Audit implementation range：`9434e9fd025bd8f019e257241a8e5de2ed973f3a..69e3e3c7668e3f668b02e20b49a015b2502067b7`
- Remote：`JasonLn0711/meetily` `main`
- Post-push divergence at closeout：`0 0`

### Planning

- `b1f17f36` — AURA × Meetily GPU gate planning closeout
- Remote：`JasonLn0711/planning-everything-track` `main`
- Post-push divergence at closeout：`0 0`

## Scope controls

- 本 audit 記錄已實作、已量測與已發布的 event；不把 benchmark harness 等同於 live evidence。
- `LIVE_MINIMUM_COMPLETED` 適用於兩條 Breeze CUDA runtime 的 20 次實測。
- Parakeet zh-TW 保持 `blocked_runtime`；它的 CUDA session policy 已實作，繁中 real inference 不列入 completed counts。
- 五段 clean speech 建立 activation baseline；產品品質、長音訊可靠性、遠距與噪音表現由下一 validation layer 確認。
- Planning mirror 不保存 WAV、逐字稿、GPU telemetry、runtime log 或 implementation diff。
