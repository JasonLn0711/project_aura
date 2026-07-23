# Ollama Gemma 4 E4B QAT Failure Analysis

## Reasoning visibility

The first live structured-output call used `/api/generate` with `think=true`.
The request completed, while the live server renderer reported thinking
disabled for that request. `/api/chat` returned reasoning in
`message.thinking` and final JSON in `message.content`. The product and
benchmark clients now use that contract, always request `think=true`, and
accept a result when `done=true` and final content is non-empty. A model may
return an empty thinking field for a simple request, so trace presence is an
observation rather than a success gate.

## Generation budget

At `num_predict=768`, the decisions and action-items extractors produced
reasoning while leaving no final JSON. Both fields completed successfully at
`1536`, followed by a 9/9 valid full product run. The fixed product and
benchmark configuration now records that measured budget.

## GPU coexistence

A post-run resident snapshot observed AURA ASR at 2666 MiB and Ollama at
4850 MiB. A post-restart snapshot observed 2062 MiB and 4834 MiB,
respectively. These are resident snapshots rather than continuous peak
telemetry; a long-form paired corpus should sample peak VRAM over time.
