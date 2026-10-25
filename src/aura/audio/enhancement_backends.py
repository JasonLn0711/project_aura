"""Fixed offline NVIDIA RE-USE import path; failures retain the source."""
from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class EnhancementResult:
    backend: str
    status: str
    output_path: Path | None
    note: str

    @property
    def succeeded(self):
        return self.status == 'ok' and self.output_path is not None


def enhance_import_audio_if_available(input_path, output_path, meeting_distance_mode=None):
    from aura.audio.reuse import ReuseWorker
    source, target = Path(input_path), Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    decoded = target.with_name(target.stem + '.original.wav')
    if source.resolve() in (target.resolve(), decoded.resolve()):
        raise ValueError('Enhancement output must not overwrite imported media')
    try:
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source),
                        '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(decoded)],
                       check=True, capture_output=True)
        with ReuseWorker('offline', log_path=target.with_suffix('.log')) as worker:
            worker.enhance_file(decoded, target)
        return EnhancementResult('nvidia/RE-USE', 'ok', target, 'Pinned offline RE-USE; no fallback')
    finally:
        # Imported original is user-owned and is never deleted.
        decoded.unlink(missing_ok=True)
