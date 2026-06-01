# MVP-v0.1: Graph-Aware RAG Summary Module

本文件記錄 Project AURA 目前要先做的 LLM summary module MVP。這份 SDD 是實驗導向的 MVP 規格，範圍比 `docs/meeting_summary_target_architecture.md` 小，目標也更清楚：先驗證 Graph Knowledge + RAG + INT8 SLM summary 在 noisy ASR transcript 上是否能產生更穩定、可追溯、結構化的會議摘要。

## MVP Definition

MVP-v0.1 定義如下：

```text
Input: ASR transcript
Output: structured meeting summary
Method: Graph Knowledge + RAG + INT8 SLM summary
Models: Qwen 3.5 9B INT8, Gemma 4 E4B INT8
Not included: speaker diarization, ASR correction, full action item system, multi-speaker role attribution
```

這個 MVP 不是要證明 SLM 可以摘要。SLM summary 已經是常見任務。真正要測的是：

```text
在沒有 speaker diarization、ASR transcript 有雜訊、模型小於 10B 且 INT8 量化的條件下，
Graph Knowledge + RAG 是否能讓 SLM 產生更穩定、可追溯、結構化的會議摘要。
```

核心實驗問題：

```text
Compared with direct summarization, does Graph Knowledge + RAG improve:
1. summary completeness
2. factual grounding
3. topic coverage
4. decision / issue capture
5. unsupported claim reduction
6. output structure stability
```

本 MVP 也刻意記錄一個研究選擇：SLM summary 可以有很多做法，包括 direct prompting、hierarchical summarization、map-reduce summarization、fine-tuned summarization model。這個 MVP 先嘗試 Graph Knowledge + RAG，原因是 ASR transcript 常常有雜訊、片段化、缺 speaker diarization；直接 summary 容易漏掉分散證據、合併不相關內容，或產生 transcript 沒有支持的結論。

## Implementation Goal Prompt

完整實作 prompt 存在 `docs/meeting_summary_mvp_goal_prompt.md`。下一次要從 SDD 進入實作時，先讀本文件確認 MVP 邊界，再把 goal prompt 交給 coding agent 執行。該 prompt 要求先完成 offline experiment harness、dry-run mode、schema/evidence checks、direct / vector RAG / graph RAG 六組設定與 validation，再考慮 PyQt UI integration。

## Input

MVP input 是 ASR transcript，不需要 speaker label。

```json
{
  "meeting_id": "meeting_001",
  "asr_transcript": [
    {
      "start": "00:00:01",
      "end": "00:00:12",
      "text": "今天我們主要討論英文版 demo 還有部署在 all in one device 上面的問題"
    }
  ]
}
```

因為 MVP 不做 speaker diarization，所以 summary 不輸出 speaker attribution：

```text
Jason said...
Prof. Wu said...
多寶 suggested...
```

MVP 使用中性會議描述：

```text
會議中討論了……
與會者提到……
目前共識是……
尚未確認的是……
```

## Output

MVP output 是 structured meeting summary：

```json
{
  "meeting_summary": "",
  "main_topics": [],
  "key_points": [],
  "decisions_or_tentative_conclusions": [],
  "open_questions": [],
  "risks_and_constraints": [],
  "possible_next_steps": [],
  "evidence_coverage": {
    "used_chunks": [],
    "low_confidence_sections": []
  }
}
```

`possible_next_steps` 不是正式 action item。因為沒有 speaker diarization，owner 很可能不準，所以 MVP 不做 owner-specific action item extraction。

## MVP Architecture

```text
ASR Transcript
  ↓
Transcript Chunking
  ↓
Chunk Embedding
  ↓
Lightweight Knowledge Graph Construction
  ↓
Graph-aware RAG Retrieval
  ↓
Summary Prompt Assembly
  ↓
INT8 SLM Summary
  ↓
Schema / Evidence Check
  ↓
Structured Meeting Summary
```

## Module A: Transcript Chunking

沒有 speaker diarization 時，chunking 是 summary 品質的關鍵控制點。

### A1. Time-Based Chunk

每 60 到 120 秒切一段：

```json
{
  "chunk_id": "c001",
  "start": "00:00:00",
  "end": "00:01:30",
  "text": "..."
}
```

### A2. Semantic Chunk

用 embedding 或簡單 topic shift 偵測，把同一主題放在一起。例如：

```text
English demo
All-in-One device
No GPU deployment
510(k) summary
Friday meeting
```

### A3. Sliding Window Chunk

Sliding window 避免關鍵句被切斷：

```text
chunk size: 800-1200 tokens
overlap: 150-250 tokens
```

MVP-v0.1 建議先做：

```text
time-based chunking + sliding window chunking
```

Semantic chunking 放到 v0.2。

## Module B: Lightweight Knowledge Graph

MVP 不做完整 knowledge graph。只做 summary 用的 lightweight evidence graph。

Node types:

```text
Chunk
Topic
Entity
Constraint
DecisionCandidate
Question
Risk
```

Edge types:

```text
MENTIONS
RELATED_TO
SUPPORTS
CONTRADICTS
TEMPORALLY_NEAR
```

Example:

```text
Chunk_003 -> MENTIONS -> Topic_English_Demo
Chunk_004 -> MENTIONS -> Constraint_No_GPU
Chunk_004 -> RELATED_TO -> Topic_Deployment
Constraint_No_GPU -> RELATED_TO -> Topic_Local_LLM
```

MVP 可以先用 rule + embedding 建 graph，不需要訓練模型。

## Module C: Graph-Aware RAG

一般 RAG 只找相似 chunk。Graph-aware RAG 多做一步：找相關節點附近的 evidence。

Flow:

```text
1. 根據 summary schema 產生 retrieval queries
2. 每個 query 做 vector retrieval
3. 找回 chunk 對應的 graph node
4. 擴展一階鄰居
5. 合併 evidence packet
```

Retrieval queries:

```text
main topics discussed in the meeting
important decisions or tentative conclusions
risks constraints and blockers
open questions and unresolved issues
possible next steps
```

Evidence packet:

```json
{
  "summary_field": "risks_and_constraints",
  "retrieved_chunks": [
    {
      "chunk_id": "c004",
      "time": "00:05:10-00:06:30",
      "text": "如果沒有 GPU 的話，本地部署完整 LLM 可能不實際..."
    }
  ],
  "graph_neighbors": [
    "Constraint_No_GPU",
    "Topic_Local_Deployment",
    "Topic_Embedding_Model"
  ]
}
```

## Module D: SLM Summary Prompt

同一個 prompt 跑兩個 INT8 quantized models：

```text
Qwen 3.5 9B INT8
Gemma 4 E4B INT8
```

Prompt contract:

```text
You are given ASR transcript evidence chunks and a lightweight knowledge graph.

Task:
Generate a structured meeting summary.

Rules:
1. Do not infer speaker identity.
2. Do not invent decisions.
3. If a point is uncertain, put it under open_questions or low_confidence_sections.
4. Every key point, decision, risk, and next step must be grounded in the provided chunks.
5. Output valid JSON only.
6. Use Traditional Chinese.
```

Output schema:

```json
{
  "meeting_summary": "string",
  "main_topics": [
    {
      "topic": "string",
      "evidence_chunks": ["c001"]
    }
  ],
  "key_points": [
    {
      "point": "string",
      "evidence_chunks": ["c002"]
    }
  ],
  "decisions_or_tentative_conclusions": [
    {
      "content": "string",
      "status": "confirmed | tentative | unclear",
      "evidence_chunks": ["c003"]
    }
  ],
  "open_questions": [
    {
      "question": "string",
      "evidence_chunks": ["c004"]
    }
  ],
  "risks_and_constraints": [
    {
      "risk": "string",
      "evidence_chunks": ["c005"]
    }
  ],
  "possible_next_steps": [
    {
      "step": "string",
      "confidence": "high | medium | low",
      "evidence_chunks": ["c006"]
    }
  ],
  "low_confidence_sections": [
    {
      "reason": "ASR unclear | weak evidence | fragmented context",
      "evidence_chunks": ["c007"]
    }
  ]
}
```

## Experiment Design

MVP 至少比較三組 summary methods：

### Baseline A: Direct Summary

```text
ASR transcript -> SLM -> summary
```

### Baseline B: Vector RAG Summary

```text
ASR transcript -> chunks -> vector retrieval -> SLM summary
```

### Proposed: Graph Knowledge + RAG Summary

```text
ASR transcript -> chunks -> lightweight graph -> graph-aware RAG -> SLM summary
```

每組都跑兩個 INT8 model：

```text
Qwen 3.5 9B INT8
Gemma 4 E4B INT8
```

總共 6 個 settings：

```text
1. Qwen direct
2. Qwen vector RAG
3. Qwen graph RAG
4. Gemma direct
5. Gemma vector RAG
6. Gemma graph RAG
```

## Evaluation Metrics

MVP 不以 ROUGE 作為主指標。會議摘要更需要看 evidence grounding、結構穩定、coverage 與 unsupported claims。

Metrics:

```text
Schema validity rate
Evidence support rate
Unsupported claim rate
Topic coverage
Decision capture accuracy
Risk / constraint capture accuracy
Open question capture accuracy
Human preference ranking
Human correction time
```

最重要三個指標：

```text
1. Unsupported claim rate
2. Evidence support rate
3. Topic coverage
```

這個 MVP 的研究重點是 trustworthy summary，不是語句漂亮。

## Experiment Note

```text
In this MVP, we intentionally focus only on the LLM summary module rather than a full meeting-intelligence pipeline. Although SLM-based summarization can be implemented through many approaches, including direct prompting, hierarchical summarization, map-reduce summarization, or fine-tuned summarization models, this experiment specifically evaluates a Graph Knowledge + RAG design.

The motivation is that ASR transcripts are often noisy, fragmented, and lack speaker diarization. Direct summarization may cause small language models to miss dispersed evidence, merge unrelated points, or generate unsupported conclusions. By constructing a lightweight evidence graph from transcript chunks, topics, entities, constraints, and decision candidates, the system can retrieve not only semantically similar chunks but also graph-neighboring evidence relevant to the summary schema.

Speaker diarization is excluded from this MVP to keep the task focused. Therefore, the system does not attempt speaker attribution or owner-specific action item extraction. Instead, the output uses neutral meeting-summary language and focuses on topics, key points, tentative decisions, risks, constraints, open questions, and possible next steps.

Both Qwen 3.5 9B and Gemma 4 E4B are tested in INT8 quantized form to simulate a realistic small-model deployment setting under limited compute resources. The main comparison is not whether the models can summarize, but whether Graph Knowledge + RAG improves grounding, coverage, and structural stability compared with direct summarization and vector-only RAG.
```

## Version Naming

Recommended MVP name:

```text
MVP-v0.1: Graph-aware RAG Summary Module for Noisy ASR Meeting Transcripts
```

Research-style name:

```text
Evidence-Graph Guided Summarization for Quantized Small Language Models
```

## Minimal Implementation Scope

v0.1 must include:

```text
- transcript chunking
- chunk embedding
- simple topic/entity extraction
- lightweight graph construction
- graph-aware retrieval
- fixed JSON summary prompt
- Qwen 3.5 9B INT8
- Gemma 4 E4B INT8
- direct vs vector RAG vs graph RAG comparison
- schema validation
- evidence support checking
```

v0.1 does not include:

```text
- speaker diarization
- ASR correction
- fine-tuning
- action item owner extraction
- medical/legal conclusion generation
- autonomous decision-making
```

## Relationship To The Larger Target Architecture

This MVP is the first controlled slice of the longer-term meeting-summary architecture. It intentionally starts with Graph Knowledge + RAG summary rather than the full ASR Gate + Evidence Graph + Verifier system.

The current priority is to test whether evidence graph retrieval improves summary grounding under limited-model conditions. If v0.1 shows improved unsupported claim rate, evidence support rate, and topic coverage, later versions can add semantic chunking, ASR Gate annotations, richer verifier checks, and UI integration.
