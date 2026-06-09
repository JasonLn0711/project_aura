# Meeting Summary

## Topic

英文版 demo、本地部署與摘要實驗規劃

## Participants

- 未提及

## Executive Summary

會議聚焦英文版 demo、本地部署限制、法規素材整理，以及 direct/vector/graph RAG 摘要比較的下一步。

## Key Points

- 英文版 demo 需要能穩定呈現，並考慮 all in one device 的本地部署。
- INT8 小模型與 evidence chunk 可追溯性是目前實驗重點。
- 法規素材需要整理 510k summary 與 TFDA 文件。

## Decisions

- 暫定先做離線實驗，schema validation 和 evidence support 比較完成後再看 PyQt 整合。

## Action Items

- 未提及

## Open Questions

- Friday meeting 前是否能產出 graph RAG、vector RAG 和 direct summary 的比較表仍不確定。

## Risks

- 沒有 GPU 時，完整 LLM 本地執行可能不實際。

## Next Steps

- 整理 510k summary、TFDA 文件，確認哪些內容可用於展示。
