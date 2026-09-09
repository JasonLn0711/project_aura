# ASR inference and CLI decision — 2026-09-09

Status: implemented Parakeet and CLI controls; framework/precision alternatives
are researched candidates with deferred activation. Owner: Jason.

## Source questions

The following user statements are preserved verbatim from the conversation:

> I would like to add another asr model "parakeet-tdt-0.6b-v2". Please optimize our asr project

> But, when we get into the cli mode, the asr model wasn't loaded. And we can't find the command to switch asr model in the cli mode.

> And please add the function that when we are in the cli mode, we can use the `tab` key to type the command and the remaining characters behind.

> Please further explain each item in this command `uv run --no-sync aura`

> parakeet-tdt-0.6b-v2 不是只有 0.6 b 嗎？為什麼我們 load model 之後，會出現 vram 5 gb 呢？

> Is it necessary to use PyTorch? Are there any better choices or frameworks for parakeet inferring? Is it better for parakeet to use fp32 instead of fp16 or nvfp16?

The request to record and publish this discussion authorizes documentation and
source publication. It does not select a replacement backend or activate a
precision/performance comparison. `nvfp16` remains an ambiguous user term;
BF16 and NVFP4 were explained as possible intended formats, not silently adopted.

## FIRST PRINCIPLE

- Scarce resources: GPU memory shared with other applications, operator attention,
  maintenance effort and trustworthy evidence.
- Product need: select an English ASR model, observe its real load state, preserve
  transcripts/timestamps and release resources deliberately.
- Canonical home: this Python AURA repo owns adapters, session lifecycle,
  operator documentation, tests and local execution receipts.
- Planning role: the [day note](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W37/days/2026-09-09.md#aura-parakeet-and-cli-closeout)
  and [project locator](https://github.com/JasonLn0711/planning-everything-track/blob/main/data/projects/2026-05-project-aura-refactor.md)
  own dated status, capacity, publication and the next decision.
- Evidence: [availability summary](../artifacts/asr-parakeet-availability/README.md)
  keeps two real functional attempts separate from synthetic frontend tests.
- Decision rule: start from the observed bottleneck and required output contract;
  choose the smallest validated change that addresses it. Parameter count alone
  does not select a runtime or precision.

## Implemented operator contract

The optional Linux CUDA NeMo adapter loads the pinned Parakeet v2 checkpoint.
Breeze remains the application default. New sessions snapshot model settings;
queued chunks and refinement retain that snapshot. One worker owns inference,
with the prior process closed before loading a different model.

`/model` reports actual state; `/model parakeet-tdt-0.6b-v2` and `/model breeze`
select and preload; `/model load` preloads the saved default; `/model unload`
releases the worker. Successful explicit preloads remain resident across idle
periods and client disconnects. Ordinary automatic loads retain idle cleanup.
Active work blocks switching; load failure preserves the default. Entering the
CLI alone leaves ASR unloaded. Old services need a safe restart after work ends.

Tab completion uses the installed prompt_toolkit and existing argparse choices:
`/mo` → `/model`, `/model para` → the full model name, `/record --mo` → `--model`.
It also completes supported option values and local paths, handles quoted paths,
and preserves following arguments. Path completion currently operates at token
end. Repeated Tab cycles choices; Enter executes. Reopen the CLI to load updates.

In `uv run --no-sync aura`, `uv` manages the Python project environment, `run`
executes within it, `--no-sync` skips dependency synchronization, and `aura`
is the application entrypoint. The flag does not freeze source code. Source-only
CLI updates take effect on reopening; new dependencies require installation,
and changed service code requires restarting the service after active work ends.

See [operator commands and architecture](shared-sessions-2026-09-08.md#optional-parakeet-v2-integration-unreleased).

## Memory and precision interpretation

Confirmed from [the adapter](../src/aura/asr/models.py): `.float().eval()` stores
model floating-point parameters in FP32. Rough weight-only arithmetic for 600
million parameters is 2.4 GB at FP32 and 1.2 GB at FP16/BF16, in decimal units.
This excludes buffers, activations, runtime workspaces and allocator reservations.
`eval()` is inference behavior, not a precision reduction; inference already uses
`torch.inference_mode()`.

The reported 5 GB is a user observation, not a reproduced allocation breakdown.
A later host check showed 64 MiB total use and no compute process, so the original
state was unavailable for attribution. PyTorch can retain freed allocations;
`memory_allocated()` measures tensor allocations and `memory_reserved()` includes
the allocator pool. Neither alone covers all CUDA memory shown by nvidia-smi.
See [PyTorch memory management](https://docs.pytorch.org/docs/main/notes/cuda.html#cuda-memory-management).
No leak diagnosis or measured memory saving follows from this discussion.

FP32 is a reference implementation choice, not a demonstrated recognition-quality
winner. FP16 has a narrower numeric range; BF16 retains FP32-like range with fewer
significand bits. Sensitive operations may need FP32. Mixed-precision execution
can keep FP32 weights, so enabling autocast alone does not guarantee halved weight
storage or total VRAM. See [NVIDIA accuracy considerations](https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/accuracy-considerations.html).

[NVFP4](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/)
is a separate 4-bit Blackwell format, not a 16-bit mode. The inspected host has an
RTX 4090 Laptop GPU; NVFP4 is not the current deployment candidate.

## Framework options checked on 2026-09-09

| Candidate | Supported evidence | Remaining AURA integration question |
| --- | --- | --- |
| NeMo/PyTorch | [Official v2 model](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2); current adapter and functional receipts | Mixed precision compatibility and actual resource benefit |
| ONNX Runtime with onnx-asr | [Project](https://github.com/istupakov/onnx-asr) documents v2, CUDA/TensorRT and token timestamps without PyTorch | Validate preprocessing, TDT decoding, segment mapping, chunking and exports |
| sherpa-onnx | [Exact v2 conversion](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html) offers FP16 and INT8 variants | Provider support, timestamp contract and deployment fit |
| TensorRT through ONNX Runtime | onnx-asr documents this execution provider | Engine build, shapes, operator coverage and hardware-specific validation |

ONNX is a model representation; ONNX Runtime is an execution engine. ASR still
needs audio preprocessing and TDT decoding, which the named wrappers provide.
Published framework capabilities do not prove lower AURA VRAM, higher throughput,
or equivalent transcripts. In particular, converted models' input-length limits
and chunking may differ from the NeMo path.

## Decision and next gate

Confirmed: preserve the working FP32 path, model lifecycle controls and explicit
English selection. Proposed engineering order: investigate allocation ownership
first; consider NeMo mixed precision for a small change, or ONNX Runtime when
reducing deployment dependencies is the main requirement. No backend winner has
been selected.

Jason owns the next activation decision after reviewing capacity and choosing
one objective: functional alternative availability, memory reduction, or quality
comparison. Any future run records its fixed model revision, runtime, input
custody and output contract before execution. Availability validation establishes
functional output/persistence only; resource or quality comparisons require a
separately authorized protocol, with reviewed ground truth for accuracy claims.

Deferred: new downloads/conversions, FP16/BF16/INT8/NVFP4 runs, TensorRT engine
builds, performance or model ranking, production-default changes, native streaming,
physical-device/second-host acceptance and unrelated AURA sibling migrations.
This closeout adds no scheduled experiment or learning block. Actual work time
remains unreported; Planning preserves existing weekly capacity commitments.

## Follow-up: short-tail failure and recovery

The operator subsequently reported `Session is not accepting audio` after roughly
9.5 minutes and authorized a fix, continued recording through recoverable chunk
errors, and recovery of that recording. Event history identified an earlier
`Parakeet returned invalid segment timestamps` on a 120-ms interval. This is a
functional failure, not evidence for a memory/precision change.

The implemented correction uses capture-timed live text, preserves original
errors, records retryable gaps, and adds explicit saved-recording recovery. It
also addresses the PCM cleanup/queued-job dependency found during recovery.
[The incident receipt](../artifacts/asr-recovery-2026-09-09/README.md) preserves
both the failed first attempt and the successful two-job recovery. Framework,
precision and quality/performance comparisons remain deferred.
