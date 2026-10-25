"""Inference subprocess entry point. The service and clients never own CUDA objects."""
import os
from pathlib import Path

_model = None
_runtime = None


def execute(kind, payload):
    try:
        return _execute(kind, payload)
    except ModuleNotFoundError as exc:
        if exc.name not in {"pydub", "numpy", "faster_whisper", "noisereduce", "yaml",
                            "rapidfuzz", "requests", "webrtcvad"}:
            raise
        raise RuntimeError(
            f"Local inference requires the server dependencies. Import detail: {exc}. "
            "In the AURA repository on the service host, run: "
            "uv sync --locked --extra server --inexact. "
            "Then launch with: uv run --no-sync aura and retry the command."
        ) from exc


def _execute(kind, payload):
    global _model, _runtime
    if kind == "export":
        from aura.audio.retention import prepare_recording_m4a
        options = payload["options"]
        path = prepare_recording_m4a(Path(payload["directory"]) / "session.json", options["target_dbfs"])
        return {"path": str(path)}
    from aura.config import SAMPLE_RATE
    from aura.asr.file_pipeline import FileTranscriptionSettings, transcribe_file, build_transcribe_kwargs
    from aura.asr.punctuation import restore_chinese_punctuation
    import numpy as np

    from aura.asr.models import load_model, runtime_receipt, PARAKEET
    options = payload["options"]
    key = options.get("asr_model", "breeze")
    if _model is None:
        _model = load_model(key)
        _runtime = runtime_receipt(key, _model)
    runtime = _runtime
    if kind == "load":
        from aura.asr.hotwords import validate_context
        if hasattr(_model, "hf_tokenizer"):
            validate_context(_model.hf_tokenizer, options.get("prompt", ""), options.get("hotwords", ""))
        return runtime
    # Backups and normalization scratch are private to this session, including imports.
    scratch = Path(payload["directory"]) / ".runtime"
    scratch.mkdir(mode=0o700, exist_ok=True)
    os.environ["AURA_RUNTIME_DIR"] = str(scratch)
    if kind == "file":
        from dataclasses import asdict
        from aura.diarization.nemotron import DiarizationSettings
        settings = FileTranscriptionSettings(
            asr_model=key, target_dbfs=options["target_dbfs"], beam_size=options["beam_size"],
            language=options["language"], initial_prompt=options["prompt"],
            hotwords=options["hotwords"], denoise_preset=options["denoise"],
            meeting_distance_mode=options["distance"],
            chinese_punctuation_enabled=options["punctuation"],
            diarization=DiarizationSettings(enabled=options["diarization"]),
        )
        result = transcribe_file(_model, payload["path"], settings, "session")
        return {"text": "\n".join(result.lines), "segments": [asdict(s) for s in result.segments], "runtime": runtime,
                "diarization": {"state": "completed" if options["diarization"] else "disabled",
                    "model_id": settings.diarization.model_id}, "speaker_turns": [asdict(t) for t in result.speaker_turns]}
    start, end = payload["start"], payload["end"]
    if Path(payload["path"]).suffix.lower() == ".wav":
        import wave
        with wave.open(payload["path"], "rb") as f:
            if (f.getnchannels(), f.getsampwidth(), f.getframerate()) != (1, 2, SAMPLE_RATE):
                raise ValueError("Recovery audio must be mono 16-bit PCM at 16 kHz")
            f.setpos(start)
            raw = f.readframes(end - start)
    elif Path(payload["path"]).suffix.lower() == ".m4a":
        import subprocess
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", payload["path"],
            "-af", f"atrim=start_sample={start}:end_sample={end},asetpts=PTS-STARTPTS",
            "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le", "-"],
            capture_output=True, check=True).stdout
    elif Path(payload["path"]).suffix.lower() == ".pcm":
        with open(payload["path"], "rb") as f:
            f.seek(start * 2)
            raw = f.read((end - start) * 2)
    else:
        raise ValueError("Gap recovery requires retained WAV, PCM, or M4A audio")
    if len(raw) != (end - start) * 2:
        raise RuntimeError("The durable audio interval is incomplete")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    if key == PARAKEET:
        text = _model.transcribe_chunk(samples, language=options["language"])
        return {"text": text, "start_sample": start, "end_sample": end, "runtime": runtime}
    segments, info = _model.transcribe(samples, **build_transcribe_kwargs(
        beam_size=options["beam_size"], language=options["language"],
        initial_prompt=options["prompt"], hotwords=options["hotwords"], condition_on_previous_text=False))
    text = (" " if key == PARAKEET else "").join(s.text for s in segments)
    if options["punctuation"]:
        text = restore_chinese_punctuation(text, language=info.language, terminal=payload["terminal"]).text
    return {"text": text, "start_sample": start, "end_sample": end, "runtime": runtime}
