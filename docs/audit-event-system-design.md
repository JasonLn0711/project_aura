# Project AURA 稽核事件系統設計

版本：1.0
日期：2026-07-14
Canonical home：Project AURA execution repo
狀態：`source preserved`、`adopted`、`implemented`、`validated`

## 原始要求

> 並請詳細設計 audit event 的功能，記錄下來所有的稽核紀錄，這除了可以追蹤使用者的使用習慣之外，也可以利用這些功能來優化 UI 等等，以及檢視是否有使用者或系統等等的異常行為等等，也請你加入我們還沒想到、講到、討論到，但你認為很重要，必須建議我們的所有地方。

## 採納決策

AURA 採用「三層稽核、單一本機信任邊界」：

1. **產品稽核事件**：跨工作流保存去內容化的使用行為、工作流結果、延遲、錯誤類型與系統健康訊號，支援 UI 優化、可靠性分析與異常複核。
2. **工作流 evidence artifacts**：每次錄音或匯入繼續保存該次執行的 metrics、event log、runtime log 與輸出關係，支援單次案件的技術追溯。
3. **人工 closeout audit events**：`docs/audit-events/` 保存跨 repo 決策、live experiment、發布證據與重大事件的可讀稽核紀錄。

產品稽核事件以本機 JSONL 為 canonical data。AURA 不需要遙測服務、追蹤 SDK、資料庫或雲端帳號即可形成可分析的稽核鏈。資料離開裝置時，另由明確匯出、去識別化、人員覆核與授權流程啟動。

## FIRST PRINCIPLE routing

```text
scarce_resource: 使用者信任、可診斷性、人的注意力、維護頻寬、儲存空間
canonical_home: 本 repo 的本機 audit JSONL、工作流 artifacts 與 docs/audit-events
evidence_path: event schema -> append-only JSONL -> integrity check -> local report -> reviewed decision
scope_control: 去內容化、local-only、session-scoped、可停用、可保留／刪除、人工覆核異常
next_gate: 用真實使用資料校準摩擦與異常門檻，再決定 UI 實驗與產品指標
```

## 稽核目標

### 產品與 UI 決策

- 找出使用者實際採用的錄音、匯入、摘要、切割、設定與診斷路徑。
- 量測從意圖到可信任 artifact 的完成率、取消率、錯誤率與時間。
- 找出重複點擊、設定反覆開關、啟動遭拒、模型載入失敗與輸出找不到等摩擦訊號。
- 讓 UI 改版使用「完成確認時間與修正成本」做決策，而不是以點擊數或畫面新穎度代替價值。

### 系統與安全複核

- 保存模型、音訊裝置、輸出、摘要 runtime 與工作流生命週期的結果狀態。
- 標記短時間錯誤 burst、重複操作、未完成工作流、audit chain 破壞與 log parse failure。
- 將異常定義為「待複核訊號」，由人員結合 runtime report 與工作流 artifact 判斷；系統不以單一行為自動判定使用者惡意。

### stewardship

- 所有有意義的產品互動都進入已登記的事件 taxonomy。
- 每筆事件只保存完成目的所需的最小欄位。
- 每個衍生指標都能回到事件定義、公式、資料範圍與限制。
- 稽核系統失效時保護主要錄音／轉錄流程，並讓寫入失敗成為可見的系統健康問題。

## 三層架構

```text
使用者／系統／模型事件
          │
          ▼
AuditRecorder（schema、redaction、sequence、hash chain）
          │
          ├── 本機 daily JSONL ── integrity verifier ── usage/anomaly report
          │
          ├── 工作流 metrics/event_log/runtime_log（單次錄音或匯入）
          │
          └── docs/audit-events（重大決策與 release closeout）
```

### 產品稽核 JSONL

預設位置依平台使用使用者狀態目錄：

- Linux：`$XDG_STATE_HOME/project_aura/audit/`，未設定時使用 `~/.local/state/project_aura/audit/`
- Windows：`%LOCALAPPDATA%/ProjectAURA/audit/`
- macOS：`~/Library/Application Support/ProjectAURA/audit/`
- 明確覆寫：`AURA_AUDIT_DIR`

每日檔案使用 `audit-YYYY-MM-DD.jsonl`。每一行是一筆完整 JSON event；寫入採 append-only、process-local lock 與單行 flush。檔案權限在平台支援時收斂為 owner-only。

### 工作流 evidence artifacts

既有 `*_processing_metrics.json`、`*_event_log.json` 與 `*_runtime.log` 保留單次執行細節。這一層可以包含該次逐字稿處理所需的來源與輸出關係，且與該次工作資料共同受控。跨工作流產品稽核不會複製這些內容。

### 人工 closeout audit events

重大 benchmark、架構決策、incident、publish closeout 與 field validation 使用 `docs/audit-events/<date>-<slug>/audit-event.md`。這一層連接 source、implementation、validation、publication 與 next gate，不取代 machine event log。

## 事件 envelope

```json
{
  "schema_version": "1.0",
  "event_id": "UUID",
  "occurred_at": "2026-07-14T18:30:00+08:00",
  "session_id": "UUID",
  "sequence": 12,
  "app_version": "1.13.0",
  "actor": "user",
  "category": "workflow.recording",
  "name": "recording.started",
  "workflow": "recording",
  "outcome": "success",
  "severity": "info",
  "details": {
    "trigger": "manual",
    "capture_source": "system_microphone",
    "summary_enabled": true
  },
  "integrity": {
    "algorithm": "sha256",
    "previous_event_hash": "GENESIS or prior hash",
    "event_hash": "sha256(canonical event without integrity)"
  }
}
```

### 欄位契約

| 欄位 | 契約 |
|---|---|
| `event_id` | 每筆唯一；只用於事件識別。 |
| `session_id` | 每次 app 啟動隨機產生；不建立跨裝置人物身分。 |
| `sequence` | 同一 session 嚴格遞增，支援排序與缺口偵測。 |
| `actor` | `user`、`system`、`model`。 |
| `category` | 穩定的領域分類，例如 `ui.navigation`、`workflow.import`、`system.runtime`。 |
| `name` | 穩定的 `domain.action` 名稱；顯示文字改版不改 event name。 |
| `workflow` | `app`、`recording`、`import`、`summary`、`splitter`、`diagnostics`、`audit`。 |
| `outcome` | `attempted`、`success`、`cancelled`、`rejected`、`error`。 |
| `severity` | `debug`、`info`、`warning`、`error`、`critical`。 |
| `details` | 事件 registry 允許的低敏感結構化欄位；字串長度受限。 |
| `integrity` | session hash chain，用於偵測缺行、改寫與重新排序。 |

Hash chain 提供 tamper-evident 證據；它不是具外部金鑰的不可否認簽章。法遵、醫療或多人管理環境需要不可否認性時，另案啟動 OS keystore 簽章、集中式 WORM 儲存與受控時間來源。

## 事件 taxonomy

### App 與導航

| Event name | 觸發 | 最小 details |
|---|---|---|
| `app.session_started` | UI 建立完成 | `audit_enabled` |
| `app.session_ending` | 使用者選擇離開 | `reason` |
| `app.session_ended` | cleanup 完成 | `reason` |
| `ui.tab_selected` | 主頁籤切換 | `tab` |
| `ui.window_hidden_to_tray` | 主視窗進入 tray | 無 |
| `ui.window_restored` | 從 tray 恢復 | 無 |
| `ui.settings_toggled` | 設定面板開合 | `visible` |
| `ui.activity_log_toggled` | 活動記錄開合 | `visible` |

### Runtime 與診斷

| Event name | outcome | details |
|---|---|---|
| `model.load_requested` | attempted | `compute_type` |
| `model.load_completed` | success | `device`、`compute_type` |
| `model.load_failed` | error | `error_class` |
| `diagnostics.completed` | success/warning | GPU、CUDA、audio、output readiness booleans |
| `diagnostics.fix_guide_opened` | success | `check` |
| `diagnostics.report_copied` | success | 無 |
| `audit.folder_opened` | success/error | 無 |
| `audit.report_generated` | success/error | `event_count`、`anomaly_count` |

### Recording

| Event name | 說明 |
|---|---|
| `recording.start_rejected` | 模型或工作流 gate 尚未開啟。 |
| `recording.started` | 真實 recorder thread 已啟動。 |
| `recording.stop_requested` | 手動、排程、no-voice 或 thread-finished。 |
| `recording.artifact_saved` | transcript／summary artifact 已保存。 |
| `recording.save_skipped` | 本次沒有可保存內容。 |
| `recording.audio_export_completed` | 錄音音訊轉檔完成。 |
| `recording.audio_export_failed` | 音訊轉檔產生待複核錯誤。 |
| `recording.schedule_armed` / `recording.schedule_cancelled` | 排程生命週期。 |

### Import

| Event name | 說明 |
|---|---|
| `import.requested` | 使用者開啟匯入意圖。 |
| `import.start_rejected` | 模型、錄音或摘要 gate 尚未開啟。 |
| `import.dialog_cancelled` | 檔案選擇器關閉且未選檔。 |
| `import.batch_started` | 保存檔案數與功能設定，不保存名稱或路徑。 |
| `import.file_started` / `import.file_completed` / `import.file_failed` | 單檔處理生命週期。 |
| `import.cancel_requested` / `import.batch_cancelled` | 取消生命週期。 |
| `import.artifact_saved` / `import.batch_completed` | 輸出與 batch 完成。 |

### Summary 與 splitter

| Event name | 說明 |
|---|---|
| `summary.requested` / `summary.started` / `summary.completed` | 摘要生命週期；只保存字數級距或 duration，不保存逐字稿與摘要內容。 |
| `summary.runtime_failed` / `summary.generation_failed` | runtime 與模型錯誤。 |
| `summary.model_missing` / `summary.model_pull_selected` | 模型 activation path。 |
| `splitter.source_selected` / `splitter.output_selected` | 只保存媒體類型與選擇結果。 |
| `splitter.started` / `splitter.completed` / `splitter.failed` | 切割工作流與 duration。 |

## 資料最小化與 privacy contract

### 跨工作流 audit 明確保存

- 操作種類、順序、成功／取消／拒絕／錯誤結果。
- 非識別性設定，例如 capture source、語言代碼、denoise mode、功能開關。
- 數量、duration、錯誤類別、readiness booleans。
- app version、session ID、schema version 與 integrity fields。

### 受保護資料的處理路徑

以下資料保留在其授權工作流或 secret store，不進入跨工作流產品 audit：

- 逐字稿、摘要、prompt、檔名、完整路徑、音訊內容與 waveform sample。
- 人名、會議名稱、錄音 suffix、裝置序號、使用者帳號與穩定跨裝置識別碼。
- API token、OAuth、Hugging Face token、credential、環境變數值。
- 原始錯誤訊息、stack trace、runtime report 全文；central audit 只保存已登記 error class。
- PHI、真實病人資料、私人會議內容與專利敏感原文。

Recorder 對敏感 key 執行集中 redaction，並限制字串長度與巢狀深度。事件 caller 仍以 allowlisted details 為第一層控制；redaction 是第二層保護。

## KPI framework

現階段缺少歷史 baseline，因此先定義公式與 provisional alert，不設定容易誤導的產品目標。累積至少 20 個有效 session 或兩週使用後，再由真實分布設定 target。

### Primary KPIs

| KPI | 定義 | 決策用途 | Guardrail |
|---|---|---|---|
| 可信任 artifact 完成率 | `artifact_saved 工作流數 / started 工作流數` | 找出錄音、匯入、摘要與切割的主要掉落點。 | 不以降低驗證層或隱藏錯誤換取完成率。 |
| Time to trusted artifact | `started -> artifact_saved/completed` 的 p50/p95 | 排序 UI 與 runtime 優化候選。 | 同時觀察 artifact 品質、人工覆核與錯誤率。 |
| 可恢復摩擦率 | `(rejected + cancelled + repeated-action signals) / user attempts` | 找出 gate 文案、控制位置與工作流狀態問題。 | 使用者主動取消是有效選擇，與系統錯誤分開。 |

### Driver metrics

- 功能採用：各 workflow 的 distinct sessions 與成功工作流數。
- 設定發現：`ui.settings_toggled` session ratio，以及開啟後是否完成工作流。
- 診斷自助：fix guide／report copy 後，同 session 的 retry success。
- 摘要 activation：有逐字稿的 session 中，summary requested 與 completed 比例。
- Output discovery：artifact saved 後，open output folder 的使用比例。

### Reliability 與 stewardship guardrails

- Audit integrity pass rate：要求 `100%`；任何 chain failure 直接進入複核。
- Sensitive-field exposure：要求 `0`；測試與抽樣覆核共同保護。
- Audit parse failure：要求 `0`；任何 malformed line 保留位置與錯誤類別。
- Audit write failure：要求 `0`；不阻斷錄音，但必須進入可見系統健康狀態。
- Error rate 與 crash proxy：UI 改版不得以減少可見錯誤的方式隱藏 runtime failure。

## 異常與摩擦判讀

### Provisional rules

| Signal | 初始門檻 | 解讀與下一步 |
|---|---:|---|
| Error burst | 同 session 10 分鐘內 3 個 `error/critical` | 連回 runtime report 與工作流 artifact 進行系統複核。 |
| Repeated action | 同 event 2 分鐘內 5 次 | 檢查按鈕 feedback、loading state、double-submit guard 與裝置延遲。 |
| Incomplete workflow | session 結束時有 started、沒有 terminal event | 檢查 crash、強制終止、thread ownership 與關閉流程。 |
| Integrity violation | hash、previous hash、sequence 任一不符 | 保全檔案，停止以該段資料做 KPI，啟動來源複核。 |
| Parse failure | 任一 JSONL line 無法解析 | 保存檔名與行號，檢查磁碟、並行寫入與不完整 shutdown。 |
| Rejection concentration | 同 gate 在多個 session 持續出現 | 把 activation path 與修正動作提前到 UI。 |

門檻是 review trigger，不是惡意判定。使用者行為分析聚焦產品摩擦與工作流健康，不建立心理、醫療、勞動或人格推論。

## Retention、存取與匯出

- 預設產品 audit retention：90 天；`AURA_AUDIT_RETENTION_DAYS=0` 可保留全部，正整數設定 rolling retention。
- `AURA_AUDIT_ENABLED=false` 可停用新的產品 audit 寫入；工作流必要 evidence 仍依各工作流契約保存。
- 使用者可從 AURA 設定面板開啟 audit folder、產生本機 Markdown report，並以檔案層級完成備份或刪除。
- 對外匯出先產生去識別摘要；原始 JSONL 需要明確授權、目的、接收者、保留期限與安全傳輸路徑。
- 多人共用工作站需要 OS account boundary；AURA 不以單一 session ID 推定實際人物。

## UI optimization operating loop

```text
事件契約 -> 兩週 baseline -> 摩擦／異常報告 -> 人員覆核
        -> 單一 UI 假設 -> 可回復改版 -> 前後指標比較
        -> 品質與 privacy guardrail -> 採納或復原
```

每次 UI 改版保存 experiment ID、版本、啟動範圍與主要 KPI。A/B test 只有在同意、樣本與決策能力足夠時啟動；單一使用者工作站優先採 paired before/after 與可用性觀察，避免假精確統計。

## 重要補充建議

1. **Audit health 應成為產品狀態**：寫入失敗、磁碟空間不足、權限錯誤與 integrity failure 需要清楚顯示，避免「以為有記錄」。
2. **Crash detection 使用 session gap**：下次啟動時，前一個 session 若缺少 `app.session_ended`，標記為 uncontrolled termination candidate，再與 OS log／core dump 複核。
3. **事件 schema 有版本與 migration policy**：event name 穩定、details 可新增、刪改欄位需升 schema major；報表同時列出未知版本。
4. **Clock 與 ordering 分離**：`occurred_at` 用於人員閱讀，`sequence` 用於 session order；不能單靠 wall clock 判斷事件先後。
5. **錯誤分類取代錯誤原文**：建立有限 error taxonomy；需要原文時回到受控 runtime report，降低路徑、帳號與內容外洩。
6. **指標不成為績效監控**：產品 audit 用於功能、可靠性與支援，不直接用於個人績效、醫療推論或懲罰性判斷。
7. **異常需要人工覆核與解釋權**：保留 false-positive 標記、reviewer、處置與 resolution，避免規則長期製造同一誤報。
8. **Support bundle 使用明確內容表**：匯出前預覽檔案、敏感級別與 redaction 結果；由使用者確認後產生。
9. **UI 事件只記錄有決策價值的互動**：不記錄滑鼠軌跡、每次按鍵或逐字稿游標，減少噪音並保護使用者。
10. **真實使用資料先建立 baseline**：沒有 baseline 前只使用 provisional alert；達到資料量後檢查分布、版本差異與 workflow mix，再設定 target。
11. **高保證環境另案啟動外部信任錨**：需要法遵不可否認性時使用 keystore-backed signing、可信時間與 WORM 儲存，不把 session SHA-256 chain 誤稱為數位簽章。
12. **分析結果本身也是受控 artifact**：report 保存產生時間、來源檔案數、event count、schema coverage、integrity result 與規則版本。

## Implementation contract

本輪 v1 交付範圍：

- stdlib `AuditRecorder`：local path、daily JSONL、redaction、retention、sequence 與 SHA-256 session chain。
- `read_audit_events`、integrity verifier、KPI／摩擦／異常摘要與 Markdown renderer。
- AURA 主視窗、轉錄／匯入／錄音／摘要／診斷、splitter 與 audit report UI hooks。
- CLI report generator、單元測試、完整 repo gate 與 local smoke artifacts。

本輪 validation evidence：

- `make check PYTHON=.venv/bin/python` 通過 compile 與 287 項測試。
- 真實 PyQt 控制項 smoke 產生 8 筆有序事件，sequence `1..8`，包含 app lifecycle、UI navigation、settings、activity log 與 report generation。
- CLI 由該次完整 session 產生摘要：Integrity `PASS`，本輪規則標記 0 個待複核訊號。
- `2026-07-14T19:18:02+08:00` live activation snapshot：更新後的桌面 process 已保存 23 筆去內容化事件、1 個 active session，涵蓋 runtime、UI、navigation、import 與 summary；active-session-aware analysis 為 Integrity `PASS`、0 個待複核訊號，daily JSONL 權限為 `600`。這項證據確認正式本機寫入路徑，field threshold calibration 仍由後續 session baseline 決定。
- 回歸測試涵蓋 sensitive detail redaction、session hash chain、竄改偵測、malformed line、retention、report output，以及 active session 誤報防護。

下一 validation layer：

- 累積至少 20 個有效 session 或兩週資料後校準門檻。
- 用經授權的真實操作 session 檢查事件 coverage、漏記、重複記錄與 UI 負擔。
- 將現有 status-bar 狀態升級為動態 audit-health（持續檢查寫入、磁碟與權限），並加入受控刪除與 support-bundle preview。
- 發布版 onboarding 若啟用跨裝置或對外 analytics，先完成明確同意、資料處理告知與撤回路徑。
