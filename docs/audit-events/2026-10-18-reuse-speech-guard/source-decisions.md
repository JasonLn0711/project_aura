# Streaming suppression: supplied requests and adopted decisions

Recorded October 18, 2026 (Asia/Taipei). This continues the
[RE-USE redesign decisions](../2026-10-17-reuse-redesign/source-decisions.md).
The quotations below preserve the relevant user instructions. Private course
audio, transcript excerpts, session identifiers and host login details remain
in local custody; this is a selected decision record, not a full conversation
archive.

## Supplied requests

> 我們在 streaming 到一半的時候，asr 就停了，是否有什麼問題？please check all the things and fix the issues.

> 請停止且背景工作結束。

> 出現「原音有語音、增強後接近靜音」的原因是什麼呢？

> 如何避免 real-time RE-USE 過度抑制，但又能保有效果呢？請規劃並執行。

> Implement the plan.

During the later recording, the user answered the scheduling question with:

> 稍後會停止

That later answer governed the active recording: preserve it and wait for
recording completion before GPU validation and idle service activation. The
earlier Stop instruction did not authorize interrupting this new recording.

> 現在的 real time RE-USE and RE-USE 怎麼處理的呢？跟修改優化之前，有什麼差別？

## Adopted implementation scope

- Preserve the fixed NVIDIA models and enhanced-only ASR route. Source speech
  detection supplies protection evidence; source audio never bypasses RE-USE
  into ASR and is never mixed into enhanced output.
- Keep streaming state across ASR boundaries. New continuous intervals reset
  both model and transform; a suppression reset preserves the source clock.
- New sessions use `speech-guard-v1`; historical sessions retain their frozen
  policy, with `reference-v1` as the legacy default.
- Protect surviving model output in source-speech windows; retain the reference
  gate for other windows. Monitor continued suppression, reset once per episode
  and attempt bounded live repair for unsubmitted ranges.
- Keep normal captions moving without a new global three-second buffer.
  Preserve submitted results and human edits; flag overlapping ranges for review.
- Stop drains committed work and exports the full original through offline
  RE-USE. It does not initiate a second recording-wide ASR pass. Explicit stopped
  recovery remains an operator action.
- Preserve original audio for unresolved gaps. Completion of capture and export
  is independent of authorization to delete the retained producer spool.
- Validate signal and functional availability first. Human listening,
  transcription accuracy and latency retain separate evaluation gates.

## Documentation and publication request

> Using FIRST PRINCIPLE, and please take notes on my day note in the `planning-everything-track` repo, and update the relevant docs, files, and contents for it.
> Please update all the commits separately on git, and push this branch to the remote main branch of the github repo. (If there were conflict among commits, i would like to keep both local commits and remote commits.)
> And build strong connection with all other relevant files, docs, and contents.

Accepted scope: AURA owns implementation, selected source decisions, architecture
and sanitized validation. Planning owns the day/project/week/integration
locators, capacity boundary, publication receipt and next gate. Publish separate
logical commits to each repository's remote `main`, preserving both histories.
No new GPU experiment, release tag, historical bulk recovery or learning block
is activated by this documentation and publication request.

Continue to the [incident analysis and evidence](audit-event.md).
