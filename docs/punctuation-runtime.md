# Punctuation runtime verification

The punctuation extra keeps Torch 2.11 and torchvision 0.26 on the same CUDA
12.8 wheel index as the existing ASR stack. Transformers imports torchvision
when it is installed, even for BERT text classification. An incompatible
installation can therefore disable punctuation restoration. The supported
version pairs are listed in the [torchvision compatibility table](https://github.com/pytorch/vision#installation).

On 2026-09-14, the local environment contained Torch 2.11.0+cu128 and
torchvision 0.27.0 (which requires Torch 2.12). Real punctuation inference fell
back to rules with `operator torchvision::nms does not exist`. Replacing only
torchvision with 0.26.0+cu128 restored the cached
`p208p2002/zh-wiki-punctuation-restore` model on CPU. Torch, Transformers,
Breeze weights, hotwords, and session architecture were retained.

Verify installed dependencies and actual cached-model execution:

```sh
uv pip check
HF_HUB_OFFLINE=1 uv run --no-sync python scripts/check_punctuation_runtime.py
```

The runtime check requires the punctuation extra and cached model weights. It
fails if rules replace model inference, transcript words change, or no
punctuation is produced. It covers Chinese, mixed technical text, existing
punctuation, and overlapping long-text windows. It checks execution and content
preservation; sentence-boundary quality still needs listening/text review.

The repair passed all four real-inference cases and the 345-test regression
suite. Native torchvision NMS, Silero VAD, Light denoise, and labSync hotword
validation were also checked. Parakeet/NeMo and torchaudio were not installed in
this local environment, so their live inference was not tested; the combined
extras still resolve in `uv.lock`.

A running worker may cache the earlier loading failure. Finish and drain active
recordings before unloading and loading the model with `aura model unload` and
`aura model load`. Closing the GUI alone does not restart the shared worker.

## FIRST PRINCIPLE and ownership

Protect original audio, operator attention, and trustworthy runtime evidence.
Repair the dependency pair at its shared installation boundary; preserve model
choices and worker ownership. Unit tests with fake restorers cannot establish
model availability, so the cached-model check supplies that separate proof.

The [aggregate receipt](../artifacts/asr-front-end/2026-09-14/validation.json)
and [local vocabulary workflow](labsync-hotwords.md) connect runtime and operator
evidence. [Planning](https://github.com/JasonLn0711/planning-everything-track/blob/main/weeks/2026-W38/days/2026-09-14.md#aura-hotwords-and-punctuation--first-principle)
owns capacity, status and the next human acceptance gate. Source publication
does not establish that an existing worker has reloaded the repaired dependency.
