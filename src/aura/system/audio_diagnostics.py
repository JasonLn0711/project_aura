import shutil
from dataclasses import dataclass

from aura.system.native_audio import no_alsa_err, suppress_native_stderr


@dataclass(frozen=True)
class AudioDiagnostics:
    ffmpeg_path: str | None
    pyaudio_available: bool
    input_devices: tuple[str, ...]
    output_devices: tuple[str, ...]
    error: str | None = None

    @property
    def input_ready(self) -> bool:
        return self.pyaudio_available and bool(self.input_devices)

    @property
    def output_ready(self) -> bool:
        return bool(self.output_devices)

    @property
    def status_line(self) -> str:
        if self.error:
            return f"Audio check failed: {self.error}"
        input_status = f"{len(self.input_devices)} input device(s)" if self.input_devices else "no input device"
        output_status = f"{len(self.output_devices)} output device(s)" if self.output_devices else "no output device"
        ffmpeg_status = "FFmpeg ready" if self.ffmpeg_path else "FFmpeg missing"
        return f"{ffmpeg_status}; {input_status}; {output_status}"


def collect_audio_diagnostics() -> AudioDiagnostics:
    ffmpeg_path = shutil.which("ffmpeg")
    try:
        import pyaudio
    except Exception as exc:
        return AudioDiagnostics(
            ffmpeg_path=ffmpeg_path,
            pyaudio_available=False,
            input_devices=(),
            output_devices=(),
            error=f"PyAudio import failed: {exc}",
        )

    input_devices = []
    output_devices = []
    try:
        with no_alsa_err(), suppress_native_stderr():
            pa = pyaudio.PyAudio()
            try:
                for index in range(pa.get_device_count()):
                    info = pa.get_device_info_by_index(index)
                    name = str(info.get("name", f"device-{index}"))
                    if int(info.get("maxInputChannels", 0) or 0) > 0:
                        input_devices.append(name)
                    if int(info.get("maxOutputChannels", 0) or 0) > 0:
                        output_devices.append(name)
            finally:
                pa.terminate()
    except Exception as exc:
        return AudioDiagnostics(
            ffmpeg_path=ffmpeg_path,
            pyaudio_available=True,
            input_devices=tuple(input_devices),
            output_devices=tuple(output_devices),
            error=str(exc),
        )

    return AudioDiagnostics(
        ffmpeg_path=ffmpeg_path,
        pyaudio_available=True,
        input_devices=tuple(input_devices),
        output_devices=tuple(output_devices),
    )
