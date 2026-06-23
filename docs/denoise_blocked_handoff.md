# Denoise Blocked Handoff

Date: 2026-06-23

## Status

The Meeting Distance Mode implementation and evaluation tooling are in place. The remaining blocker is evidence, not application code: AURA still needs a fixed private evaluation set with clip-level trusted references before DeepFilterNet3, ClearVoice, WPE, or any stronger default can be promoted.

Do not change the default denoise or meeting-distance behavior until the fixed evaluation set passes readiness, produces an ASR comparison report, and passes the promotion gate.

## Completed Work

- `Meeting Distance Mode` exists with `off`, `normal`, `far-speaker`, and `rescue-offline`.
- `normal` applies the current light denoise floor plus normalization behavior.
- `far-speaker` applies stronger live support through a lower energy gate, longer VAD bridge, bounded segment AGC, and imported-file DeepFilterNet3 candidate routing.
- `rescue-offline` routes difficult imports through a ClearVoice/ClearerVoice-style offline candidate when available.
- Heavy model backends stay outside the main AURA dependency graph because current DeepFilterNet and ClearVoice packages still require `numpy<2.0`.
- Private evaluation workspace scaffolding exists at `/home/jnln3799/record_jn/aura_eval_audio`.
- Local candidate discovery output exists at `local_outputs/denoise_eval_candidates/candidates.md` and `.json`; this path is ignored by git.
- The candidate manifest deliberately treats transcript sidecars as review sources only. It does not pass them as `--reference-file` unless explicitly requested.
- The workspace checker rejects implausibly long references for short clips to catch accidental full-recording transcript copies.

## Blocked Items

1. Fixed evaluation cases are not ready.

   Current evidence: `python scripts/check_denoise_eval_workspace.py --input-dir ~/record_jn/aura_eval_audio --min-cases 10 --max-reference-chars-per-second 45` reports `Ready cases: 0/10`.

   Each ready case needs:

   - `input.wav`: a 30-90 second representative clip.
   - `reference.txt`: a clip-level trusted transcript aligned to that exact clip.
   - `rare_terms.txt`: expected domain terms for rare-term preservation checks.
   - `notes.md`: room, microphone, distance, language, and why the clip matters.

2. Transcript-quality comparison has not been run.

   Reason: there are no ready reference-backed cases yet. Running the evaluation harness before this would only produce process diagnostics, not evidence for changing defaults.

3. Default-promotion gate has not been run successfully.

   Reason: there is no reference-backed evaluation JSON report yet. The promotion gate requires enough comparable baseline/candidate cases and checks WER, CER, and rare-term hit-rate deltas.

4. DeepFilterNet3 and ClearVoice have not been validated on the fixed set.

   Reason: the fixed set is not ready. Backend boundaries are implemented, but quality claims must wait for evaluation evidence.

5. WPE dereverberation remains a later validation layer.

   Reason: the first comparison should establish baseline, noisereduce, DeepFilterNet3, and ClearVoice behavior. WPE should be added only if far-field clips show reverberation as a distinct remaining failure mode.

## Resume Steps

1. Open the local candidate manifest:

   ```bash
   less local_outputs/denoise_eval_candidates/candidates.md
   ```

2. Select at least 10 clips across normal meeting, far speaker, reverberation, overlap, rare terms, and rescue-offline categories.

3. For each selected clip, prepare an evaluation case. Use the manifest command as a starting point, then add a clip-level trusted reference after human review:

   ```bash
   python scripts/prepare_denoise_eval_case.py \
     --source /path/to/source_recording.wav \
     --case-dir ~/record_jn/aura_eval_audio/far_speaker_reverb \
     --start 120 \
     --duration 60 \
     --reference-file /path/to/clip_level_trusted_reference.txt \
     --rare-term DeepFilterNet \
     --rare-term MossFormer
   ```

4. Check readiness:

   ```bash
   python scripts/check_denoise_eval_workspace.py \
     --input-dir ~/record_jn/aura_eval_audio \
     --min-cases 10 \
     --max-reference-chars-per-second 45
   ```

5. Run the backend comparison:

   ```bash
   python scripts/evaluate_denoise_backends.py \
     --input-dir ~/record_jn/aura_eval_audio \
     --backends off,noisereduce-light,noisereduce-medium,deepfilternet3,clearvoice,wpe \
     --model SoybeanMilk/faster-whisper-Breeze-ASR-25 \
     --output reports/denoise_eval_YYYYMMDD.md
   ```

6. Gate any default-promotion decision:

   ```bash
   python scripts/gate_denoise_default_promotion.py \
     --report-json reports/denoise_eval_YYYYMMDD.json \
     --baseline off \
     --candidate deepfilternet3 \
     --min-cases 10
   ```

## Completion Criteria

The blocked state is resolved only when:

- At least 10 private evaluation cases pass the workspace readiness checker.
- The evaluation harness produces Markdown and JSON reports with reference-backed ASR metrics.
- The promotion gate has been run for the candidate backend under consideration.
- Any recommendation to change defaults is supported by WER/CER and rare-term evidence, not by listening quality alone.
- The default remains conservative unless the evidence supports promotion.

## Privacy Notes

- Keep raw audio and private candidate manifests outside git.
- Do not paste full private transcripts into tracked docs.
- Tracked docs should contain paths, commands, decisions, and evidence summaries only.
