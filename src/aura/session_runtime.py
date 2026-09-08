"""Inference subprocess entry point. The service and clients never own CUDA objects."""
import os
from pathlib import Path

_model = None


def execute(kind, payload):
    global _model
    if kind == "export":
        from aura.audio.export import normalize_wav_to_recording_audio
        options = payload["options"]
        path = normalize_wav_to_recording_audio(payload["path"], options["target_dbfs"], options["audio_format"], remove_source=False)
        return {"path": str(path)}
    from aura.config import MODEL_ID, SAMPLE_RATE
    from aura.asr.file_pipeline import FileTranscriptionSettings, transcribe_file, build_transcribe_kwargs
    from aura.asr.punctuation import restore_chinese_punctuation
    from aura.audio.denoise import reduce_noise_safely
    from aura.audio.meeting_distance import meeting_distance_policy_for, apply_live_segment_agc
    from aura.system.cuda import preload_cuda_runtime_libraries
    import numpy as np

    if _model is None:
        ready, detail = preload_cuda_runtime_libraries()
        if not ready:
            raise RuntimeError(f"RTX/CUDA activation required: {detail}")
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL_ID, device="cuda", compute_type="int8", local_files_only=True)
    if kind == "load":
        from aura.asr.hotwords import validate_context
        validate_context(_model.hf_tokenizer, payload.get("prompt", ""), payload.get("hotwords", ""))
        return {"model": MODEL_ID, "device": "cuda", "compute_type": "int8"}
    options = payload["options"]
    # Backups and normalization scratch are private to this session, including imports.
    scratch = Path(payload["directory"]) / ".runtime"
    scratch.mkdir(mode=0o700, exist_ok=True)
    os.environ["AURA_RUNTIME_DIR"] = str(scratch)
    if kind == "file":
        from dataclasses import asdict
        from aura.diarization.pyannote_pipeline import DiarizationSettings
        settings = FileTranscriptionSettings(
            target_dbfs=options["target_dbfs"], beam_size=options["beam_size"],
            language=options["language"], initial_prompt=options["prompt"],
            hotwords=options["hotwords"], denoise_preset=options["denoise"],
            meeting_distance_mode=options["distance"],
            chinese_punctuation_enabled=options["punctuation"],
            diarization=DiarizationSettings(enabled=options["diarization"],
                min_speakers=options["min_speakers"], max_speakers=options["max_speakers"]),
        )
        result = transcribe_file(_model, payload["path"], settings, "session")
        return {"text": "\n".join(result.lines), "segments": [asdict(s) for s in result.segments]}
    start, end = payload["start"], payload["end"]
    with open(payload["path"], "rb") as f:
        f.seek(start * 2)
        raw = f.read((end - start) * 2)
    if len(raw) != (end - start) * 2:
        raise RuntimeError("The durable audio interval is incomplete")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    samples = reduce_noise_safely(samples, SAMPLE_RATE, options["denoise"])
    samples = apply_live_segment_agc(samples, meeting_distance_policy_for(options["distance"]))
    segments, info = _model.transcribe(samples, **build_transcribe_kwargs(
        beam_size=options["beam_size"], language=options["language"],
        initial_prompt=options["prompt"], hotwords=options["hotwords"], condition_on_previous_text=False))
    text = "".join(s.text for s in segments)
    if options["punctuation"]:
        text = restore_chinese_punctuation(text, language=info.language, terminal=payload["terminal"]).text
    return {"text": text, "start_sample": start, "end_sample": end}
