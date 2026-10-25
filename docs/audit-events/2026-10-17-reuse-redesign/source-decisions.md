# RE-USE redesign: supplied decisions

These are the relevant user instructions visible in this task. They are source
excerpts, not a full conversation export. No private audio or transcript is copied.

> Please take full notes on all the audit logs and all the fix you have done.

> 請把所有跟 ClearVoice 有關的程式都處理掉，並重新設計，我們直接挑選 NVIDIA Real-time RE-USE 作為 live streaming 的處理，而我們要將 /stop 過後的完整原始音檔存檔時，也要先使用 NVIDIA RE-USE （這就不是 real-time RE-USE 了，是 RE-USE 喔）來處理過後，再存檔為 m4a audio file。請設計新版的 C4 model 之後，重構並優化程式碼。

> 補充一下，停止後，離線 RE-USE 處理完成的音訊再做一次完整 ASR

The following correction supersedes the preceding post-stop ASR instruction:

> 停止後，離線 RE-USE 處理完成的音訊是否要再做一次完整 ASR？
> answer: 只處理音檔 (Recommended)

> Implement the plan.

> 已在 Brave 播放英文對話，可以驗證

The last response authorizes the actual Brave capture check. Its private voice
and text remain in the owner-local diagnostics directory.

Adopted interpretation: live RE-USE precedes VAD and live ASR. Stop drains those
existing ASR jobs, runs offline RE-USE on the entire original recording, and
creates M4A without another full ASR pass. The agreed format remains 16 kHz mono.
Successful delivery retains enhanced M4A; enhancement failure retains the
original for repair and recovery. No model substitution is authorized.
The agreed model use is noncommercial personal research. GPU inference belongs
to the NVIDIA host; CPU clients retain capture, transport and control.

## Publication and Planning request — 2026-10-18

> Using FIRST PRINCIPLE, and please take notes on my day note in the `planning-everything-track` repo, and update the relevant docs, files, and contents for it.
> Please update all the commits separately on git, and push this branch to the remote main branch of the github repo. (If there were conflict among commits, i would like to keep both local commits and remote commits.)
> And build strong connection with all other relevant files, docs, and contents.

Accepted scope: preserve the implementation and evidence in AURA; mirror the
result, capacity, publication and next gate in Planning. Publish separate logical
commits to each repository's remote main, preserving both histories. This does
not activate another audio experiment, a release tag or a new learning block.
