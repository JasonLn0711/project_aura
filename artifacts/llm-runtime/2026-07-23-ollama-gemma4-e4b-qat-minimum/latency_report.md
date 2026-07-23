# Ollama Gemma 4 E4B QAT Latency

The final product configuration uses one Ollama server-side sequence and lets
the existing nine application tasks queue at the local runner.

| Measurement | Real calls | Elapsed |
| --- | ---: | ---: |
| Decisions field at `num_predict=1536` | 1 | 14.237 s |
| Action-items field at `num_predict=1536` | 1 | 15.954 s |
| Complete nine-field product pipeline | 9 | 71.186 s |
| Post-restart meeting-topic smoke | 1 | 7.798 s |

The nine-field latency is acceptable as an optional post-ASR desktop workflow
for this minimum. Repeated same-corpus queue-time and correction-time targets
form the activation gate for a vLLM benchmark.
