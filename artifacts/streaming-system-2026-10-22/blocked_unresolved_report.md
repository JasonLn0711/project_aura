# BF16 candidate warmup failure

Scope: `candidate-layer8-bf16-r01`, a research-only diagnostic attempt within
`EXP-20261022-01-streaming-system`. The adopted layer-8 FP32 system executed
successfully; this blocked status applies only to the BF16 candidate.

- Execution status: `BLOCKED_UNRESOLVED`.
- Runtime validity: `blocked_runtime`.
- Gate outcome: `fail`.
- Completed streaming runs: 0; generated output audio files: 0.
- Production default: unchanged, `legacy-v1`.

The pinned streaming model rejected warmup with this error:

```text
Expected conv_state.scalar_type() == input_type to be true, but got false.  (Could this error message be improved?  If so, please report an enhancement request to PyTorch.)
```

The diagnostic adapter uses BF16 autocast while retaining FP32 model weights.
The failed attempt does not establish support for all recurrent-state/kernel
dtype combinations. Revisit only through a bounded candidate change that aligns
state and input types, verifies reset/continuity and output validity, then
undergoes the separately required quality review. No upstream model files,
kernel packages or production defaults were changed to bypass this error.

The [results receipt](results.json) contains the failed attempt's source/code
identity and private receipt hash. Full worker logs remain in the private
diagnostics directory named by the [main report](README.md).
