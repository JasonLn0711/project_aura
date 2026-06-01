# Meeting Summary Target Architecture

本文件記錄 Project AURA 的長期會議摘要目標架構。它是 target architecture / SDD，不是目前 MVP 承諾，也不是現有 local LLM summary 功能的完成狀態描述。

目前產品已經提供 ASR、transcript artifacts、optional local LLM summary、speaker diarization、punctuation restoration、runtime diagnostics、Windows onboarding。當前 summary MVP 另行記錄在 `docs/meeting_summary_mvp_sdd.md`，範圍是 Graph Knowledge + RAG + INT8 SLM summary，且刻意不納入 speaker diarization、ASR correction、完整 action item system、多人角色歸因。這份 target architecture 則記錄更完整的長期方向：把 ASR transcript 轉成 evidence-grounded structured meeting minutes，並讓每個決策、待辦、風險與不確定內容都能回指 transcript span、graph node、retrieved evidence。

## Product Target

AURA 的長期 summary layer 應該支援從 ASR transcript 產生結構化會議記錄：

```json
{
  "meeting_title": "",
  "date": "",
  "participants": [],
  "agenda": [],
  "discussion_points": [],
  "decisions": [],
  "action_items": [
    {
      "owner": "",
      "task": "",
      "deadline": "",
      "evidence_span": ""
    }
  ],
  "open_questions": [],
  "risks_or_uncertainties": [],
  "source_confidence": {}
}
```

核心原則是：SLM 不直接相信 transcript。所有 structured output 都要能回指 transcript span、evidence graph node、retrieved evidence；證據不足時標記 uncertainty，而不是把合理推測寫成 confirmed decision。

## Target Pipeline

```text
Audio
  ↓
ASR Model
  ↓
ASR Transcript + timestamp + confidence
  ↓
ASR Gate
  ↓
Cleaned / Annotated Transcript
  ↓
Chunking
  ↓
Entity / Event / Action Extraction
  ↓
Meeting Evidence Graph
  ↓
Graph-aware RAG Retrieval
  ↓
SLM Structured Inference
  ↓
Verifier / Schema Validator
  ↓
Structured Meeting Minutes
```

## Module 1: ASR Gate

ASR Gate 是 target architecture 的第一個可信度控制層。它的任務不是直接改逐字稿，而是 detect, annotate, suggest, preserve, verify。

它應該把可疑 transcript span 標記出來，分類錯誤型態，產生候選修正，標記 confidence，並保留原始 span。只有在保守 merge 條件成立時才允許自動替換；其他情況保留為 annotation，交給 downstream graph、RAG、verifier 與 human review 使用。

Target annotation format:

```json
{
  "original_text": "我們下週要跟會成智醫開會",
  "normalized_text": "我們下週要跟慧誠智醫開會",
  "error_type": "domain_term_error",
  "confidence": 0.82,
  "evidence": {
    "source": "project_lexicon",
    "matched_term": "慧誠智醫"
  },
  "action": "suggest_replace"
}
```

ASR Gate 應該優先處理五類高風險錯誤：

- Domain term error: 例如「慧誠智醫」被辨識成「會成智醫」。
- Person, organization, project name error: 例如「多寶」「冠廷」「深耕計畫」「510(k)」等關鍵名稱。
- Action item error: 例如 owner 被錯聽，導致「請冠廷確認」變成「請工程確認」。
- Negation error: 例如「不是要整合 vital sign」被誤成「是要整合 vital sign」。
- Time, number, date error: 例如「週五」「五週」「510(k)」「15 分鐘」「5 月 12 日」。

## Module 2: Four-Layer Gate

ASR Gate 不應該只靠 SLM。目標設計採四層 gate：

### Layer A: Rule / Regex Gate

處理高風險格式與可測規則：

```text
日期、時間、人名、數字、金額、510(k)、FDA、ASR、LLM、RAG、GPU、CPU
```

### Layer B: Domain Lexicon Gate

建立 project lexicon，支援 fuzzy matching 與 evidence source：

```json
{
  "organizations": ["慧誠智醫", "聯醫", "衛生局", "NYCU"],
  "people": ["吳老師", "多寶", "冠廷", "俊邑", "冠宇"],
  "projects": ["深耕計畫", "AI triage kiosk", "pre-visit workflow"],
  "technical_terms": ["ASR", "LLM", "RAG", "embedding", "510(k)", "predicate device"]
}
```

Expected examples:

```text
會成智醫 → 慧誠智醫
深根計畫 → 深耕計畫
five ten k → 510(k)
```

### Layer C: SLM Correction Candidate Gate

SLM 的角色是辨識可疑 span 與候選修正，不是全文改稿。Prompt 應該明確約束：

```text
Identify likely ASR errors in the transcript.
Do not rewrite the transcript.
Return only suspicious spans, correction candidates, confidence, and reason.
```

Candidate models for experiment planning:

- Model A: Qwen3.5 9B
- Model B: Gemma 4 E4B

這些模型名稱在進入實作前需要重新驗證當下的 official model card、license、dependency、GPU memory footprint、Windows/Linux runtime feasibility。它們是 target experiment candidates，不是 MVP dependency promise。

### Layer D: Conservative Merge Gate

只有在高可信條件成立時才自動替換：

```text
lexicon match confidence > 0.85
or
SLM confidence > 0.90 + domain lexicon support
```

其他候選修正保留為 annotation。這個設計讓 ASR 錯誤不會被 SLM 幻覺放大，也讓 reviewer 能看到原始文字、候選修正、confidence 與 evidence。

## Module 3: Evidence Graph

每場會議建立一個小型 meeting evidence graph。Graph 是 meeting minutes 的證據骨架，不是替代 transcript 的摘要結果。

Node types:

```text
Person
Organization
Project
Topic
Decision
ActionItem
Risk
Question
EvidenceSpan
Time
Document
```

Edge types:

```text
SPOKE_ABOUT
DECIDED
ASSIGNED_TO
DEPENDS_ON
MENTIONED_IN
SUPPORTED_BY
CONTRADICTS
HAS_DEADLINE
HAS_UNCERTAINTY
```

Example graph assertions:

```text
[吳老師] --DECIDED--> [先做 English demo]
[English demo] --SUPPORTED_BY--> [Transcript span 00:12:30-00:13:10]
[AI triage kiosk] --HAS_RISK--> [No GPU deployment constraint]
[No GPU deployment constraint] --AFFECTS--> [LLM local deployment]
```

## Module 4: Graph-Aware RAG

會議紀錄不能只靠 vector RAG。目標 retrieval layer 應該是 hybrid retrieval：

```text
BM25 keyword retrieval
+ vector retrieval
+ graph neighborhood retrieval
+ timestamp-window retrieval
```

Query example:

```text
Find all action items related to English demo deployment.
```

Expected retrieval package:

```json
{
  "query": "English demo deployment action items",
  "retrieved_nodes": ["ActionItem_03", "Project_EnglishDemo", "Person_Jason"],
  "evidence_spans": [
    "00:14:20-00:15:02",
    "00:21:10-00:22:00"
  ],
  "neighbor_nodes": ["NoGPUConstraint", "AllInOneDevice"]
}
```

## Module 5: SLM Structured Inference

SLM layer 的任務分三類：

- Summary task: 產生會議摘要、討論重點、決議。
- Inference task: 推論下一步、風險、不確定事項與待確認問題。
- Structured extraction task: 依 schema 輸出 JSON。

Prompt contract:

```text
You are given transcript evidence spans and graph nodes.
Generate structured meeting minutes.
Every decision and action item must cite evidence_span.
If evidence is weak, mark uncertainty instead of guessing.
```

Qwen3.5 9B 可作為主要 reasoning / structured inference candidate。Gemma 4 E4B 可作為 lightweight baseline，用來評估低資源環境下 schema validity、action item extraction、evidence grounding 的穩定度。實作前必須重新驗證模型可用性與部署條件。

## Module 6: Verifier

Verifier 是 target architecture 的必要層。它檢查 structured output 是否可靠，特別是避免小模型把合理內容寫成 transcript 已支持的事實。

Verifier checks:

```text
JSON schema 是否正確
每個 action item 是否有 owner
每個 decision 是否有 evidence_span
是否出現 transcript 沒有的內容
是否把 uncertain content 寫成 confirmed decision
```

Expected verifier output:

```json
{
  "valid": false,
  "errors": [
    {
      "type": "unsupported_claim",
      "field": "decisions[2]",
      "message": "No evidence span supports this decision."
    }
  ]
}
```

## Future MVP Slice For This Target

這不是目前 MVP，但若要啟動這條 target architecture，建議第一個可實作切片是：

```text
1. ASR transcript input
2. domain lexicon
3. ASR Gate annotation
4. chunking by timestamp
5. entity/action/decision extraction
6. lightweight evidence graph
7. hybrid RAG retrieval
8. Qwen3.5 9B / Gemma 4 E4B structured output experiment
9. verifier
10. evaluation report
```

第一個切片的交付物應該是離線 pipeline 與 evaluation report，不應該先塞進現有 PyQt main workflow。這樣可以先驗證 unsupported claim rate、ASR correction precision、schema validity，再決定哪些功能適合進入桌面 UI。

## Evaluation Metrics

會議記錄評估不應該只看 ROUGE。目標指標應該以結構正確性與 evidence grounding 為主：

```text
Action item precision
Action item recall
Decision precision
Owner accuracy
Deadline accuracy
Evidence support rate
Unsupported claim rate
ASR correction precision
ASR correction recall
Schema validity rate
Human review time reduction
```

最關鍵指標是 Unsupported Claim Rate：模型輸出的會議記錄中，有多少內容其實沒有 transcript evidence 支持。

## Implementation Boundaries

- Current local LLM summary remains optional post-ASR summarization.
- This target does not replace raw transcript artifacts; it adds evidence-grounded structured minutes beside them.
- ASR Gate preserves original spans and correction evidence.
- SLM output is treated as review-support evidence, not as an authoritative record without verifier support.
- Model candidates are experiment inputs and must be refreshed against current official model cards before implementation.
- UI integration should come after offline pipeline metrics demonstrate stable schema validity and low unsupported claim rate.
