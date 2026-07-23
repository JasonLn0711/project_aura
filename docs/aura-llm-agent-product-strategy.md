# Project AURA LLM Agent 必要性與產品策略完整評估

紀錄日期：2026-07-23
Canonical home：`project_aura/docs/`
紀錄狀態：`source preserved`
決策狀態：`proposed direction recorded`
實作狀態：`evidence-first implementation landed; live gates active`
發布狀態：`source commits published to remote main; release tag pending`

## 紀錄契約

本文件完整保存 2026-07-23 對 Project AURA 的下列評估：

- 現階段是否需要加入 LLM AI Agent。
- 暫時不受既有 repo 規則限制時，從第一性原理重新設計的產品方向。
- 同類產品公開評價、issue、討論與官方產品文件所反映的共同痛點。
- 更前沿且符合 2025–2026 產品趨勢的候選設計。
- Repo 現有程式、live evidence、UI 與 runtime gate 所支持的優先順序。
- 應立即推進、條件式啟動與明確延後的工作。

本文件同時保存實作前的 repo baseline 與完成後的 evidence closeout。「程式層的高價值缺口」與「UI 稽核」保留當時發現，便於追溯決策來源；本文後段的「2026-07-23 實作 closeout」是目前工作樹狀態。只有本輪重新執行過的檢查標示為 `validated`；真實硬體、live model inference 與 broader corpus 維持 activation gate 或 next validation layer。

## 原始請求

> 依照你的評估，你是否認為現在這個 repo 內，有加入 llm ai agent 的必要性？以及如果不管這個 repo 原本設定的所有規則，你會如何優化這個專案？以及這個專案有什麼更前沿、更符合趨勢性的設計呢？並且依照第一性原理，整合所有網路上的網友對類似產品的評價以及大家的痛點，給出最值得進步的完整建議。

後續保存要求：

> 請完整紀錄下來。

## 建議決策摘要

Project AURA **需要 LLM，但現階段最適合維持受控的結構化 workflow；完整通用型 AI Agent 的啟動條件尚未成立**。

最有價值的產品定位是：

> **臺灣語境、本機優先、每項結論都能回到原始音訊的會議證據工作台。**

Agent 的真正價值出現在可信任逐字稿、講者、來源引用與人員確認層完成之後。屆時由單一、有界、逐項核准的 Agent 把已確認決策轉成草稿、任務或行事曆提案。現階段加入通用 Agent 會擴大尚未校正的音訊、講者與摘要錯誤；先完成 evidence layer 會直接降低使用者的覆核成本，也會讓後續 Agent 具備可追溯的輸入。

### 能力必要性判斷

| 能力 | 現階段必要性 | 建議決策 |
|---|---:|---|
| 結構化會議摘要／欄位抽取 | 7/10 | 保留，先完成 live runtime、正確輸入與來源回證 |
| 單場會議問答＋時間戳引用 | 8/10 | evidence layer 完成後啟動 |
| 跨會議搜尋與比較 | 6/10 | 先用 SQLite FTS5 與 metadata |
| 草擬行動項目／追蹤信 | 5/10 | 以提案模式提供，經人員覆核 |
| 自動寄信、建任務、改行事曆 | 2/10 | 有重複搬運需求後，以逐項核准啟動 |
| 通用型、多 Agent 自主系統 | 0/10 | 現階段不形成產品增量 |

## Source boundary 與研究方法

### Repo source

本輪讀取並交叉檢查：

- [`README.md`](../README.md)
- [`docs/architecture_decisions.md`](architecture_decisions.md)
- [`docs/first-principles-aura-meetily-review.md`](first-principles-aura-meetily-review.md)
- [`src/aura/ui/transcription_tab.py`](../src/aura/ui/transcription_tab.py)
- [`src/aura/ui/transcript_io.py`](../src/aura/ui/transcript_io.py)
- [`src/aura/audio/capture.py`](../src/aura/audio/capture.py)
- [`src/aura/llm/summary.py`](../src/aura/llm/summary.py)
- [`src/summary/layered_summary_pipeline.py`](../src/summary/layered_summary_pipeline.py)
- [`src/summary/field_schemas.py`](../src/summary/field_schemas.py)
- 現有 LLM summary impact reports、ASR live benchmark evidence 與本機 audit 摘要。

### 公開網路 source

本次涵蓋可公開驗證的代表性樣本，不宣稱完成全網普查。來源依決策價值分層：

1. 可重現的 GitHub issue、discussion 與 release。
2. 官方產品文件、官方研究、model card 與工程指南。
3. G2、Trustpilot 等聚合評論。
4. Reddit 等使用者經驗，用作痛點線索，不作精確盛行率或品質排名。

AURA 公開 GitHub 在檢查時為 1 star、0 issues，因此直接產品回饋仍很少；市場痛點主要從 Otter、Fireflies、Notta、Granola、Descript、Meetily、MacWhisper、WhisperX、pyannote 等相鄰產品取得。

## 第一性原理

會議工具的根本任務不是「錄音、跑模型、產生摘要」；而是：

> **以最低的操作與校正成本，把真實聲音轉成可追溯、可覆核、可再次使用的決策與行動。**

### 稀缺資源

依決策影響排序：

1. **人的注意力**：設定、等待、修字、確認講者、重做摘要與搬運結果都消耗時間。
2. **可信任度**：漏錄、錯字、錯置講者、無來源摘要會迅速消耗採用意願。
3. **音訊品質**：輸入訊號決定 ASR 上限；後端模型無法完整重建未被擷取的聲音。
4. **本機算力與記憶體**：ASR、diarization、LLM 與 UI 共享 GPU、RAM 與磁碟頻寬。
5. **維護頻寬**：每個新 framework、runtime、connector 與資料庫都形成發布與除錯成本。
6. **隱私與治理**：會議內容、聲紋、逐字稿與外部動作需要清楚的保存、同意、啟動與刪除路徑。

### North-star metric

建議主要指標：

> **每小時音訊需要多少人工覆核分鐘，才能產生可信任 artifact。**

配套指標：

- `time_to_trusted_artifact`
- `review_minutes_per_audio_hour`
- `quote_retrieval_time`
- `speaker_corrections_per_session`
- `summary_claim_source_coverage`
- `unsupported_action_item_rate`
- `recording_recovery_success_rate`
- `first_launch_activation_time`

模型名稱、Agent 數、prompt 數、單純 WER 與 UI 點擊量只能作為診斷訊號，不能取代完成確認時間與人工修正成本。

## 2026-07-23 Repo 現況證據

### LLM runtime

重新執行：

```bash
.venv/bin/python -m unittest -q \
  tests.test_ollama_runtime \
  tests.test_summary \
  tests.test_layered_summary_pipeline \
  tests.test_summary_ui_runtime
```

結果：

- `Ran 44 tests`
- `OK`
- `ollama` 不在 PATH。
- `http://localhost:11434/api/tags` 無法連線。

現況分類：

| Variant | Runtime validity | Live counts |
|---|---|---:|
| local Gemma 4 E4B structured summary | `blocked_runtime` in current environment | 0 current live runs |
| LLM-focused implementation/tests | `PREFLIGHT_ONLY` | 44 passing tests |

這支持「程式路徑已存在」；目前仍需要安裝／啟動 Ollama、確認 model tag，並完成真實摘要執行後，才能升級為 live runtime evidence。

### 歷史摘要 evidence

[`reports/gemma4_e4b_summary_impact_pipeline_validity_report.md`](../reports/gemma4_e4b_summary_impact_pipeline_validity_report.md) 記錄：

- 5 組完整 artifact。
- 4 組進入 machine evaluation。
- 1 次摘要生成失敗。
- 0 筆正向 summary-impact evidence。
- Pipeline 尚未通過品質證據 gate。

[`reports/gemma4_e4b_summary_impact_current_numctx32768_review_decision.md`](../reports/gemma4_e4b_summary_impact_current_numctx32768_review_decision.md) 記錄：

- 5 個人工審查 rows。
- `ACCEPT: 1`、`REJECT: 1`、`UNSURE: 3`。
- 原始摘要偏好 2、平手 2、不安全 1。
- Corrected summary 尚未形成整體偏好。
- Decision／action item 需要 transcript/audio semantic review。

這支持保留結構化摘要為研究候選；品質提升與自動化外部動作仍由下一 evidence gate 決定。

### 2026-07-23 當前 local LLM runtime addendum

目前 active backend 維持本機 Ollama，active model tag 為
`gemma4:e4b-it-qat`。相較於既有 evidence 使用的 9.6 GB
`q4_K_M` artifact，官方 QAT tag 約 6.1 GB，能在本機 16 GB RTX 4090
Laptop GPU 與 CUDA ASR 共用的工作站上保留更充足的執行餘裕。既有
`q4_K_M` 報告與上方歷史段落持續作為 provenance，保留原始量測語境，
不回寫為新 runtime 的 live evidence。

Gemma 4 E4B 的 generation contract 固定啟用 `reasoning=true`，對應
Ollama `/api/chat` 的 `think=true`。Ollama 將 `message.thinking` 與 final
`message.content` 分開回傳；AURA 將 reasoning 視為暫態 runtime output，canonical session
只保存通過 schema 驗證的 final JSON 與 deterministic Markdown。這讓模型
保有推理能力，同時維持使用者 artifact 的可覆核性與穩定格式。

目前 command、localhost server 與 `gemma4:e4b-it-qat` model preflight
均已 ready。真實模型 runtime 已在 AURA ASR 同卡載入時完成最小 live
validation：隱私安全的繁中逐字稿由產品 client 執行九欄位 extraction，
9/9 欄位通過 schema，reasoning 已啟用且 trace 未寫入 artifact，總時間
71.186 秒；當時 ASR process 約占 2666 MiB、Ollama runner 約占 4850 MiB。
狀態因此提升為 `LIVE_MINIMUM_COMPLETED`（runtime validity）；這份結果驗證
執行契約與 16 GB 共存能力，摘要品質、人工修正時間與不同 runtime 的比較
仍由 paired corpus gate 決定。

完整 request summary、event trace、error log、GPU resident snapshots、
runtime validity、latency、failure analysis 與 final decision 收錄於
[`artifacts/llm-runtime/2026-07-23-ollama-gemma4-e4b-qat-minimum/`](../artifacts/llm-runtime/2026-07-23-ollama-gemma4-e4b-qat-minimum/)。

Live check 同時找出兩個只在真實推論可見的契約問題：`/api/generate` 即使
送出 `think=true`，server renderer 在此 structured JSON request 仍顯示
thinking disabled；`/api/chat` 則穩定分離 reasoning 與 final content。原本
`768` token 上限也會讓 decisions／action-items 的 reasoning 用完額度而
沒有 final JSON。Active client 因此使用 `/api/chat`、驗證
`done=true` 與非空 final content，並採用實測通過且固定的
`num_predict=1536`。每個 request 都固定送出 `think=true`；
`message.thinking` 在模型選擇回傳時可作為暫態觀測值，不作為成功與否的
硬性條件。

vLLM 保留為量測後 activation gate。當 repeated same-corpus measurement
證明持續併發需求已形成，或 Ollama 未達成事先同意的 latency、queue-time、
throughput target，才啟動 vLLM implementation 與 paired benchmark。現階段
維持單一 Ollama backend，可集中驗證摘要品質、修正成本與共享 GPU 資源。
Localhost boundary 由標準 URL parser 驗證 exact loopback host、HTTP 與
明確 port，並拒絕 credentials、path、query、fragment；AURA 啟動 server
時會強制 loopback、`OLLAMA_NO_CLOUD=1`、`OLLAMA_NUM_PARALLEL=1`、
Flash Attention 與 q8 KV cache。

參考：

- [Ollama Gemma 4 E4B QAT model tag](https://ollama.com/library/gemma4:e4b-it-qat)
- [Ollama thinking contract](https://docs.ollama.com/capabilities/thinking)
- [vLLM Gemma 4 model recipe](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html)

### ASR live evidence

既有 5 段 Common Voice 24 臺灣華語 clean-speech 最小 live benchmark 已證明 AURA 與 Meetily 的 CUDA runtime 路徑可真實執行。它是 activation baseline，不是產品品質冠軍。

下一層需要具授權的：

- 長音訊
- 遠距收音
- 背景雜訊
- 重疊語音
- 中英 code-switching
- 臺灣專有名詞
- 取消、恢復與 crash recovery

主要比較欄位應包含人工修正時間、TER／WER、DER、peak VRAM、失敗率、取消延遲與 time-to-trusted-artifact。

### 本機 audit snapshot

執行：

```bash
python3 scripts/summarize_audit_events.py --format json
```

2026-07-23 snapshot：

- 119 events。
- 5 sessions。
- 6/6 recording workflows complete。
- 5/5 import workflows complete。
- 1 次 summary request，結果為 `summary.runtime_failed`。
- Track Splitter started／completed 均為 0。
- 3 個 uncontrolled termination candidates。
- Settings toggled 12 次。
- Output folder opened 1 次。

這是小型產品線索，不作市場採用或因果結論。它支持：

- 摘要 runtime activation 是目前可見的摩擦。
- Settings 的操作成本值得進一步觀察。
- Track Splitter 尚未取得優先擴充證據。
- Session lifecycle 與 crash recovery 應進入可靠性 gate。

## 程式層的高價值缺口

### P0-1：摘要目前取得校正前逐字稿

匯入流程在 [`src/aura/ui/transcription_tab.py`](../src/aura/ui/transcription_tab.py) 中先把 `thread.result_lines` 組成 `transcript`，再呼叫 LLM summary。後續 `finish_import_artifacts()` 才呼叫 `write_transcript_artifacts()`。

錄音流程同樣先把 `transcript_without_summary()` 送入 LLM，之後才進入 `write_transcript_artifacts()`。

Glossary correction 實際在 [`src/aura/ui/transcript_io.py`](../src/aura/ui/transcript_io.py) 的 `write_transcript_artifacts()` 中執行。

因此目前資料流是：

```text
raw transcript
  → LLM summary
  → glossary correction
  → final transcript + existing summary
```

文件與 prompt contract 宣稱 downstream summary 使用 corrected transcript；目前實作順序未遵守該 contract。根本修正是把可測試的 transcript preparation 移到摘要與 artifact 儲存共同使用的 shared path，讓兩個 caller 都取得同一份 corrected transcript。

### P0-2：完整錄音在結束前只存在記憶體

[`src/aura/audio/capture.py`](../src/aura/audio/capture.py) 會把完整 frame 與 voice flags 追加到記憶體，錄音迴圈結束後才一次寫入 WAV。

風險：

- 程式崩潰或斷電可能遺失整場錄音。
- 長音訊增加 RAM 與最後一次大規模 join/write 的壓力。
- Live ASR 成功不代表原始完整音訊已形成 durable artifact。

建議最小設計：

- Append-safe raw WAV 或固定長度 segment journal。
- 原子更新 session manifest。
- Capture 與 live ASR queue 解耦。
- 啟動時發現未完成 session 並提供 recovery。
- 最終正規化、trailing-silence trim 與格式轉換在 durable raw source 存在後執行。

### P0-3：摘要設定與 runtime 行為未對齊

UI 會建立 `SummarySettings`，包含 model、quantization、max tokens 與 temperature；[`src/aura/llm/summary.py`](../src/aura/llm/summary.py) 的 `summarize_transcript()` 目前直接呼叫固定 `generate_layered_summary(transcript)`，未把這些設定傳入實際 client。

實作前 baseline 的 UI tooltip 同時描述 FP8；本輪已統一為實際使用的
`gemma4:e4b-it-q4_K_M`。

建議：

- 產品 UI 只保留真實生效的控制項。
- 固定模型 contract 的值顯示為 runtime facts，不偽裝成可選設定。
- 實驗參數留在 Advanced／Lab mode 並完整寫入 artifact metadata。

### P0-4：摘要 evidence 檔會被固定檔名覆蓋

[`src/summary/layered_summary_pipeline.py`](../src/summary/layered_summary_pipeline.py) 固定寫入：

- `field_outputs.json`
- `final_summary.json`
- `final_summary.md`
- `validation_log.json`

建議每個 session 使用獨立 artifact 目錄，至少保存：

- session ID
- transcript hash
- source transcript path
- model tag／runner
- generation settings
- prompt／schema version
- start／end timestamps
- failure／repair log
- summary claim ↔ source span
- human review result

### P1-1：摘要 schema 有結構，尚未有可驗證來源座標

[`src/summary/field_schemas.py`](../src/summary/field_schemas.py) 的 decision 包含 `evidence_style: explicit`，但沒有 transcript segment ID、timestamp、支持狀態或 review 狀態。

建議最小 contract：

```json
{
  "decision": "string",
  "source_segment_ids": ["seg_0012", "seg_0013"],
  "support_status": "supported | partial | unsupported",
  "review_status": "pending | confirmed | edited | rejected"
}
```

Action item 同樣需要來源、owner confidence、deadline confidence 與 review status。

### P1-2：逐字稿 UI 是唯讀，缺少最關鍵的覆核迴路

目前 `QTextEdit` 使用 `setReadOnly(True)`。這讓逐字稿可以被觀看，卻無法在同一主流程完成：

- Inline correction
- Speaker rename
- 點擊文字跳到音訊
- Unknown／overlap marker review
- 修改後重新摘要
- Confirm／reject summary claims

最值得推進的是 session-centric review console，而不是更多生成按鈕。

## 同類產品的共同痛點與 AURA 對應

| 痛點 | 代表性公開 source | AURA 最值得提供的能力 |
|---|---|---|
| 錄音靜默失敗、會後才發現沒有完整資料 | [MacWhisper reliability discussion](https://www.reddit.com/r/MacWhisper/comments/1stvuxm/macwhisper_is_the_best_tool_i_cant_fully_rely_on/)、[Granola failure discussion](https://www.reddit.com/r/ArtificialInteligence/comments/1r05e7g/granola_ai_is_still_the_best_regarding_meeting/)、[Meetily releases](https://github.com/Zackriya-Solutions/meetily/releases) | Append-safe capture、session journal、crash recovery、可見的錄音健康度 |
| 多人、重疊、雜訊造成講者錯置 | [Notta reviews](https://www.g2.com/products/notta/reviews?qs=pros-and-cons)、[Fireflies reviews](https://www.g2.com/products/fireflies-ai/reviews?source=search)、[pyannote overlap discussion](https://github.com/pyannote/pyannote-audio/discussions/1157)、[speaker-count issue](https://github.com/pyannote/pyannote-audio/issues/1781) | 保存分離音軌、global speaker rename、overlap／unknown marker、人員覆核 |
| 專有名詞、口音、中英混用錯誤 | [Meetily transcript quality issue](https://github.com/Zackriya-Solutions/meetily/issues/171)、[Whisper Traditional Chinese discussion](https://github.com/openai/whisper/discussions/277)、[WhisperX issue](https://github.com/m-bain/whisperX/issues/1208) | 議程、出席者、專案名、投影片文字形成 session context pack |
| 找不到原話、無法修改後重做摘要 | [Meetily inline editing request](https://github.com/Zackriya-Solutions/meetily/issues/377)、[saved audio/search/playback request](https://github.com/Zackriya-Solutions/meetily/issues/108) | 點文字播放音訊、inline editing、修正後重跑、claim citation |
| 摘要錯置講者或形成沒有來源的決策 | [Otter Trustpilot](https://www.trustpilot.com/review/otter.ai)、[Fireflies reviews](https://www.g2.com/products/fireflies-ai/reviews?source=search) | 每個 decision／action 回指 transcript span；沒有支持來源時進入「待確認」 |
| Bot 加入會議造成隱私、同意與操作干擾 | [Otter unwanted bot discussion](https://www.reddit.com/r/projectmanagement/comments/1j0cfei/do_not_join_otterai_unless_you_want_your_whole/)、[Fireflies bot-free desktop](https://guide.fireflies.ai/articles/6666374717-how-to-record-meetings-without-a-bot-on-the-fireflies-desktop-app) | 本機、bot-free、清楚的錄音同意、保存與刪除路徑 |
| 安裝模型、GPU 與音訊裝置設定摩擦 | [Meetily model readiness issue](https://github.com/Zackriya-Solutions/meetily/issues/318)、[GPU recognition issue](https://github.com/Zackriya-Solutions/meetily/issues/100)、[Windows setup issue](https://github.com/Zackriya-Solutions/meetily/issues/111) | First Launch Check 納入 Ollama、model tag、GPU、磁碟與音訊裝置，提供可執行修復 |
| 訂閱、分鐘限制與取消帳務摩擦 | [Otter pricing](https://otter.ai/pricing)、[pricing discussion](https://www.reddit.com/r/Journalism/comments/1fy51gb/cant_afford_otterai_anymore_any_alternative/)、[Otter Trustpilot](https://www.trustpilot.com/review/otter.ai) | 本機處理、成本可預測、無分鐘綁定 |
| 摘要留在單一 app，難以進入既有工作流 | [Fireflies overview](https://guide.fireflies.ai/articles/1193528158-what-is-fireflies-ai)、[Granola sharing](https://docs.granola.ai/help-center/sharing/sharing-notes) | Markdown／JSON／SRT／VTT export、local API、條件式 connector |

### 市場結論

同類產品的核心競爭已從「能否產生逐字稿」移到：

1. 是否完整錄到。
2. 是否能快速修正。
3. 是否知道誰說了什麼。
4. 是否能回到確切音訊。
5. 摘要與行動是否有來源支持。
6. 是否尊重同意、隱私與資料保存。
7. 是否能進入使用者現有工作流。

因此 AURA 最值得建立的是 **trust UX**，而不是把 Agent 作為第一個產品標籤。

## UI 稽核

### 錄音與轉錄工作區

![AURA 錄音與轉錄工作區](../img/transcription-workspace-v1.14.0.png)

現有能力：

- 錄音、匯入、波形、逐字稿與摘要入口已形成完整 workstation 基礎。
- Runtime status、輸出位置與 activity log 提供可觀測性。

下一層：

- 顯示「原始音訊已持續保存」與 capture health。
- Transcript 由唯讀改為可覆核。
- 點擊 segment 播放對應音訊。
- Speaker rename 與 overlap review。
- Claim citation 與 confirm／edit／reject。

### Advanced Settings

![AURA Advanced Settings](../img/advanced-settings-v1.14.0.png)

現有畫面同時承載產品選項與實驗參數，部分 label／選項容易截斷。建議產品層只保留：

- 快速逐字稿
- 會議高準確度
- 臺灣語境＋講者辨識

Model、quantization、context、temperature、VAD 與 backend candidate 進入 Advanced／Lab mode。每個顯示控制都需要對應真實 runtime 行為。

### Track Splitter

![AURA Track Splitter](../img/track-splitter-v1.14.0.png)

三步驟流程清楚，但目前 audit 無使用紀錄。建議移入 Tools／研究工具層並維持現況；真實 demand 或 downstream consumer 出現後再擴充。

## 不受既有規則限制時的最佳產品設計

即使完全重新計算，也不建議先重寫技術棧。現有 Python、PyQt、音訊與 artifact contract 已可承接最重要的驗證。最小而完整的產品路徑是：

```text
原始音訊持續保存
  → provisional ASR
  → final timestamped segments
  → diarization + speaker alias
  → 人工修字／改講者
  → source-linked summary claims
  → 人員確認決策與行動
  → 可交付 artifact
  → 明確核准後的外部動作
  → execution receipt + audit event
```

### 產品角色

從純產品投資角度，AURA 最清楚的角色是：

- 臺灣華語、code-switching、遠距與噪音條件的 capability validation bench。
- Evidence contract、artifact、failure diagnostics 與 paired benchmark 的 canonical home。
- Session review UX 的可測試參考實作。

長期跨平台產品表面可以由 Meetily 承接勝出 capability。這個結論不是因為既有文件要求，而是因為重建一套跨平台資料庫、系統音訊、更新、onboarding 與 release pipeline 不會改善 AURA 的核心證據產出。

## 優化路線圖

### P0：資料完整性與 contract 正確性

1. Append-safe audio capture、session manifest 與 crash recovery。
2. Corrected transcript 在 summary 前形成並被兩個 caller 共用。
3. 刪除或接通未生效的 LLM UI 設定，修正 model tooltip。
4. First Launch Check 加入 Ollama command、server、model tag、磁碟與 output path。
5. 每場會議使用獨立 summary artifact package。
6. Capture、ASR、summary、save 各自保留清楚 failure state。

驗收：

- 強制終止後可恢復已錄音訊。
- Summary input hash 對應 corrected transcript。
- 不再覆蓋上一場 summary evidence。
- Runtime UI 與實際 readiness 一致。

### P1：Evidence-first review console

1. Inline transcript editing。
2. Segment ↔ audio seek。
3. Speaker rename 套用本場會議。
4. Unknown／overlap／low-confidence review queue。
5. Summary claim ↔ source spans。
6. Confirm／edit／reject 與重新摘要。
7. Transcript evidence、model inference、user note 三層分離。

驗收：

- `summary_claim_source_coverage` 可計算。
- 使用者能在 30 秒內回到指定原話。
- 同一 corpus 的 review minutes 顯著下降。
- Unsupported action item 不會進入 confirmed artifact。

### P2：簡單且可攜的會議資料層

1. 檔案維持 canonical source。
2. 以 Python stdlib SQLite＋FTS5 建立 session、segment、speaker、claim index。
3. 單場與跨會議搜尋必須回傳來源 span。
4. Markdown、JSON、SRT、VTT 一鍵匯出。
5. 真實 consumer 出現後再加入 folder watcher、CLI 或 local API。

驗收：

- Exact quote retrieval time。
- Search precision／source support。
- Artifact 可由外部工具讀取，不需要複製私有原文到 planning。

### P3：有界 Agent

最小工具面：

```text
read-only:
- search_meetings
- search_segments
- open_audio_span
- get_confirmed_actions

proposal-only:
- draft_followup
- draft_task
- draft_calendar_event
```

外部寫入流程：

```text
confirmed action
  → tool proposal
  → 顯示完整參數
  → user approve／edit／reject
  → execute
  → receipt
  → audit event
```

第一版使用普通 Python 函式、JSON schema 與狀態機即可。Agent framework、MCP 或多 Agent 只在新的 interoperability evidence 出現後啟動。

## Agent 啟動 gate

有界 Agent 進入實作前，至少需要：

1. LLM summary 完成真實 repeated live run，不再是 `PREFLIGHT_ONLY`。
2. 每個 decision／action item 可回到 transcript/audio source。
3. 人員可在主流程 confirm、edit 或 reject。
4. 真實使用紀錄顯示使用者重複把已確認 action 搬到同一外部系統。
5. Connector 有最小權限、完整 preview、逐項核准、receipt 與 undo／recovery path。
6. Audit 不保存 token、敏感逐字稿或不必要的個人資料。

Agent 成功指標：

- Draft acceptance rate。
- Edit distance before approval。
- Time saved per confirmed action。
- Wrong-target／wrong-owner／wrong-date rate。
- External write rollback／recovery success。

工程選型依據：

- [OpenAI — A practical guide to building AI agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)：Agent 適合動態、例外多、需要工具判斷的工作；固定可預測流程維持簡單 workflow。
- [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)：優先使用最簡單且足以完成任務的組合，只有在真實任務需要模型自主控制流程時才增加 agentic complexity。
- [OpenAI Agents SDK — Human in the loop](https://openai.github.io/openai-agents-python/human_in_the_loop/)：敏感工具呼叫由 interruption、approval 與 resume path 管理。
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)：工具採最小權限、保護 token 與敏感 log，外部操作保留明確授權。

## 前沿方向與採用判斷

### 1. On-device／local-first inference

Apple Foundation Models 已把 on-device guided generation 與 tool calling 變成平台能力。AURA 的本機預設方向正確；下一步是降低模型安裝與啟動摩擦。

Source：

- [Apple Foundation Models framework](https://developer.apple.com/documentation/FoundationModels?language=objc)
- [Apple Foundation Models technical report 2025](https://machinelearning.apple.com/research/apple-foundation-models-tech-report-2025)

### 2. Bot-free capture

桌面端直接擷取本機會議聲音可以減少會議 bot 的隱私、同意與參與者干擾。AURA 應把 bot-free 與 local capture 表達為可信任能力，同時清楚顯示錄音狀態與同意路徑。

### 3. Two-pass streaming

產品應清楚分離：

- `provisional transcript`
- `final model segment`
- `human-confirmed text`

真正 streaming 需要生成過程中的非 final chunk 與事件 trace；把完成 WAV 分段傳送或把文字 segmentation 重新命名為 streaming，不能作為 target runtime。

### 4. Context-aware ASR

最小 context pack：

- 出席者姓名
- 議程
- 專案與產品名
- 投影片文字
- 本場會議語言與預期 code-switching

先重用現有 `initial_prompt` 做 paired A/B；word boost／prompt 過強可能增加 false positive，因此由人工修正時間與錯誤專有名詞率決定。

Source：

- [NVIDIA Riva ASR customization](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/public/asr/asr-basics-customization-riva.html)
- [Do Slides Help? EMNLP 2025](https://aclanthology.org/2025.emnlp-main.814/)

### 5. 臺灣語境與方言模型路由

候選：

- 現有 Breeze ASR path。
- [Breeze-ASR-26](https://huggingface.co/MediaTek-Research/Breeze-ASR-26)：以臺語／閩南語轉中文為主要能力，適合特定 corpus，不應視為一般臺灣華語的直接替代。
- [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR/blob/main/README.md)：支援 streaming、batch、timestamps、多語與方言，適合作為 research candidate。
- [GPT-4o Transcribe Diarize](https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize)：只在明確 cloud opt-in 與資料治理成立時作 benchmark candidate。

產品預設只由同一份具授權 corpus 的人工修正成本、可靠性、VRAM 與失敗 evidence 決定。

### 6. Evidence-linked notes

產品趨勢已從單純 summary 移向可編輯、可回證、可接受的 notes：

- [Granola AI-enhanced notes](https://docs.granola.ai/help-center/taking-notes/ai-enhanced-notes)
- [Descript playback and navigation](https://help.descript.com/hc/en-us/articles/10164534109837-Playback-and-navigation)
- [Microsoft Teams recap](https://support.microsoft.com/en-US/teams/meetings/recap-in-microsoft-teams)
- [Zoom timestamp citations](https://library.zoom.com/zoom-workplace/artificial-intelligence/artificial-intelligence-bluepaper/ai-companion/ai-companion-features/zoom-meetings)

這是 AURA 最值得優先吸收的趨勢。

### 7. Cross-meeting memory 與 MCP

Otter、Fireflies、Granola 已提供 MCP：

- [Otter MCP](https://help.otter.ai/hc/en-us/articles/35287607569687-Otter-MCP-Server)
- [Fireflies MCP](https://guide.fireflies.ai/articles/3039542843-learn-about-fireflies-mcp-server-connect-your-ai-tool)
- [Granola MCP](https://docs.granola.ai/help-center/sharing/integrations/mcp)

MCP 是已有可信會議資料後的互通層，不是轉錄品質或摘要可靠性的替代品。第二個真實 connector、跨 agent host portability 或外部 consumer 出現時再啟動。

### 8. Multimodal context

音訊、視覺與文字線索可改善遠距與重疊會議辨識；最小版本先使用投影片／議程文字，不先引入攝影機、臉部資料、VLM 與新 runtime。

Source：

- [MISP-Meeting, ACL 2025](https://aclanthology.org/2025.acl-long.753/)
- [Do Slides Help? EMNLP 2025](https://aclanthology.org/2025.emnlp-main.814/)

## 明確延後清單

下列候選維持在 activation path，不進入近期產品預設：

- Multi-agent swarm。
- 通用自主 Agent。
- 會中全雙工語音助理。
- Graph RAG。
- 向量資料庫。
- 為單一實作新增 Agent framework。
- 為本機 JSONL 加 Differential Privacy。
- Consumer RTX 上的 Confidential Compute。
- 預設建立跨會議持久 speaker embeddings／voiceprints。
- 沒有真實 consumer 的 MCP server。
- 同時保留多個 ASR／LLM backend 作產品預設。
- 全面重寫 PyQt UI 或建立第三套產品 surface。

啟動條件：

- SQLite FTS5 在實際 retrieval benchmark 中明確不足後，再評估向量／Graph retrieval。
- 重複會議的 speaker correction 成本可量測且使用者明確同意後，再評估可刪除的本機 voice profile。
- 真實外部動作需求形成後，再實作單一 connector。
- 第二個 connector 或跨 host portability 形成後，再評估 MCP。
- Audio／text context 仍無法解決目標錯誤後，再評估攝影機與 VLM。

## 最值得投資的一件事

如果現階段只能選一個投資組合：

> **先完成 append-safe 錄音與 session recovery，再建立可編輯、可點回音訊、摘要可引用來源的覆核工作台。**

它直接處理市場最強的資料遺失、修正成本、講者錯置與摘要信任痛點，也為未來 Agent 建立可追溯輸入。Agent 在 evidence layer 通過後，以單一、有界、逐項核准的形式啟動。

## 2026-07-23 實作 closeout

本輪依照上述優先順序完成 evidence-first foundation，並維持「受控 LLM
workflow、暫不建立通用 Agent」的產品決策。

### 已形成的能力

| 路線 | 目前能力 | Evidence |
|---|---|---|
| Capture durability | 每場錄音建立 UUID `meeting_id`、原子 `session.json`、mixed 與實際可用來源的 PCM journal、1 秒 flush／5 秒 fsync、final／partial WAV 重建與明確 recovery；中斷後復原的音訊維持 `partial` outcome、原始狀態與 failure provenance，由 session manifest 判定可用範圍 | 強制終止子行程後可 discovery／recovery，且不會被標成 complete；capture／session／shutdown focused tests 通過 |
| Corrected-summary contract | 匯入、錄音與手動摘要共用 `punctuation → glossary correction → SHA-256` preparation；prepared transcript 與 hash 綁定 canonical session | raw／corrected fixture、session identity 與兩個 caller tests 通過 |
| Two-pass transcript | Live rows 標示 provisional；durable mixed WAV 執行 final timestamped ASR；人員確認形成第三層狀態 | final-pass UI test 與 structured-segment tests 通過 |
| Review console | Inline correction、全場 speaker rename、待覆核導覽、unknown／overlap／low-confidence flags、鍵盤可聚焦的 segment→audio playback、JSON／Markdown／SRT／VTT export；segment edit 先使既有摘要失效，再原子保存 segments／events，後段寫入失敗仍維持 fail-closed evidence state | PyQt offscreen review、autosave、manifest-first invalidation 與 write-failure tests 通過 |
| Evidence-linked summary | Decision／action claims 帶 transcript／segment revision 綁定的 stable claim ID、source segment IDs、support／review status 與 source coverage；confirm／edit／reject 以原子更新保存 append-only event history；寫入失敗時主張與 UI 維持原狀；逐字稿修正會使舊摘要失效 | schema、pipeline、claim review、disk-full、source playback 與 stale-confirmation tests 通過 |
| Confirmation guard | `unsupported` 或沒有來源片段的主張不能進入 confirmed action | claim-review 與 evidence-search regression tests 通過 |
| Session-scoped evidence | Audio、prepared transcript、segments、review events 與 summary evidence 共用 session identity；summary 不再以全域固定檔名覆蓋不同會議 | per-session output 與 manifest binding tests 通過 |
| First Launch Check | 顯示 output writability／free space、Ollama command／server／model tag、GPU／CUDA／ASR／audio readiness 與可執行 guidance | runtime diagnostics tests 與本輪 preflight |
| Local meeting data | stdlib SQLite FTS5 衍生 index 可原子重建；只有 meeting identity 與 transcript hash 相符的有效摘要可進入 meeting search／confirmed actions；confirmed action 的來源 ID 必須存在於 canonical segments；同名 action 仍各自保留 owner／deadline；canonical artifacts 維持唯讀來源 | `aura-evidence` CLI、stale-summary、missing-source、duplicate-action、target validation 與 read-only API tests 通過 |
| Packaging integrity | prompts、glossary 與 ClearVoice runner 隨 wheel 發布，runtime 由 package resources 讀取，Python 3.10 可載入核心路徑 | source-only isolated wheel build／zip import 與 resource byte-sync tests 通過 |
| Trust UX | 每場錄音需完成告知與同意確認；開始後顯示 durable source 持續保存位置；檔名輸入經安全化 | UI state 與 capture status tests 通過 |

### 刻意維持的產品邊界

- 本輪沒有加入 Agent framework、multi-agent、vector database、Graph RAG 或
  autonomous connector。
- `aura-evidence rebuild` 只更新衍生 SQLite；query command 使用唯讀連線，
  canonical JSON、JSONL、WAV 與文字 artifacts 保持 source of truth。
- 外部 action 仍由 Gate E 啟動。Confirmed action 可以被查詢，尚不會自動寄信、
  建任務或修改行事曆。
- Track Splitter 維持現有工具範圍；新的 evidence 尚未支持擴充投資。

### 本輪驗證結果

- `.venv/bin/python -m unittest discover -s tests -q`：`392 tests passed`。
- 獨立 wheel 稽核建立 `project_aura_refactor-1.15.0-py3-none-any.whl`，
  確認 `aura`／`project-aura`／`aura-evidence` entry points、10 份 summary
  prompts、domain glossary 與 packaged ClearVoice runner 均在 repo 外可讀取。
- 強制終止 recovery test 使用真實子行程、真實檔案 flush／fsync 與
  `os._exit(23)`；輸入 PCM 為合成測試資料，因此它是 durability engineering
  evidence，硬體麥克風／系統音訊與真實斷電仍由 Gate A field check 確認。
- Output path 可寫且空間充足；本機 `ollama` command、localhost server 與
  `gemma4:e4b-it-q4_K_M` 目前未就緒。LLM summary 的程式與 contract 已通過
  preflight tests，live inference 狀態維持 `BLOCKED_UNRESOLVED`。
- 本輪沒有執行長音訊、遠距、雜訊、重疊、code-switching 的 paired live
  corpus，因此沒有形成摘要品質、人工節省時間、TER／DER 或產品採用結論。

## 下一個可驗收決策

### Gate A：Capture durability

- 強制終止錄音 process。
- 驗證已持續寫入的原音可被恢復。
- 產生 session manifest、event log 與 failure record。

### Gate B：Corrected-summary contract

- 建立同一份 raw／corrected transcript fixture。
- 證明 summary input hash 對應 corrected transcript。
- 兩個 caller 共用同一 preparation path。

### Gate C：Evidence-linked summary

- 至少讓 decision 與 action item 帶 source segment IDs。
- 使用者可以點擊回到 transcript/audio。
- 計算 source coverage 與人工確認時間。

### Gate D：Broader live corpus

- 長音訊、遠距、雜訊、重疊、中英 code-switching 與臺灣專有名詞。
- Repeated／paired live inference。
- 人工修正時間、TER、DER、VRAM、取消、恢復、錯誤與 artifact 齊全。

### Gate E：Bounded action proposal

只有在 audit 顯示使用者反覆搬運 confirmed action 後，建立一個 proposal-only connector。第二個 connector 出現後再重新評估 MCP。

## Status closeout

- `source preserved`：本次完整評估、來源邊界、公開 evidence、repo findings、建議方向與 next gates 已保存於本文件。
- `proposed direction recorded`：LLM 保留為受控摘要 workflow；Agent 在 evidence layer 與真實外部動作需求成立後啟動。
- `implementation landed`：capture durability、corrected-summary ordering、session identity、evidence schema、review UI、runtime diagnostics、packaged resources 與 SQLite FTS5 read-only layer 已落在目前工作樹。
- `validated`：392 個 tests、Python 3.10 compile／version checks、isolated wheel、強制終止後的 partial recovery、output readiness、Ollama command／server／model absence 與 touched-scope checks 已於 2026-07-23 重新檢查。
- `release provenance`：`v1.15.0` source candidate 已由 commits `de0e851`、
  `c6978b0`、`f6d0faf`、`56ab98b` 發布至 remote `main`；最新已發布 tag
  維持 `v1.14.0`，annotated `v1.15.0` tag 由獨立 release gate 啟動。
- `live activation gates`：真實錄音硬體 recovery、local Gemma live inference、broader paired corpus 與人工覆核時間量測仍依 Gate A／C／D 推進。
- `published`：`git push origin HEAD:main` 成功；重新 fetch 後
  `HEAD...origin/main` divergence 為 `0 0`。

## Connection map

- [`README.md`](../README.md)：操作者入口、`v1.15.0` capability summary、
  validation 與 release provenance。
- [`docs/architecture_decisions.md`](architecture_decisions.md)：session、
  recovery、review、evidence index 與 bounded-Agent ownership contract。
- [`docs/versioning.md`](versioning.md)：runtime candidate、published tag 與
  annotated release 的版本邊界。
- `planning-everything-track/data/projects/2026-05-project-aura-refactor.md`：
  planning locator、容量影響、remote-main evidence 與下一個 activation gate。
- `planning-everything-track/weeks/2026-W30/days/2026-07-23.md`：本次
  FIRST PRINCIPLE day-note mirror；implementation、tests 與 runtime artifacts
  持續由本 repo 保存。
