"""Detached capture helper with disk-backed forwarding and explicit control acknowledgements."""
import os
from pathlib import Path
import threading
import time
import uuid

from aura.sdk import AuraClient


def capture(session_id, ssh=None):
    from aura.audio.inputs import open_audio_reader
    from aura.audio.recording_session import RecordingSession
    from aura.config import CHUNK_SIZE, SAMPLE_RATE
    from aura.session_core import default_root
    client = AuraClient(ssh=ssh)
    control = AuraClient(connection=client.connection)
    source_stop = threading.Event()
    session_stop = threading.Event()
    shared = {"state": "starting", "frames": 0, "error": None, "tracks": None}
    reader = None
    recorder = None
    writer = None
    sent = 0
    sequence = 0
    source_lock = threading.Lock()

    def watch():
        try:
            while not session_stop.wait(0.1):
                s = control.request("get", {"session_id": session_id})
                shared["state"] = s["state"]
                if s["state"] in ("pausing", "stopping", "failed", "ready", "recoverable"):
                    source_stop.set()
        except Exception as exc:
            shared["error"] = exc
            source_stop.set()

    def record():
        try:
            while not source_stop.is_set():
                frames = reader.read_tracks()
                if source_stop.is_set():
                    break
                with source_lock:
                    if shared["tracks"] is None:
                        shared["tracks"] = list(frames)
                    if list(frames) != shared["tracks"]:
                        raise RuntimeError("Capture track layout changed")
                    recorder.append_pcm({k: v.astype("<i2").tobytes() for k, v in frames.items()})
                    recorder._flush()
                    shared["frames"] += 1
        except Exception as exc:
            if not source_stop.is_set():
                shared["error"] = exc
            source_stop.set()

    try:
        while True:
            s = client.request("get", {"session_id": session_id})
            if s["state"] != "starting":
                break
            time.sleep(0.1)
        if s["state"] != "recording":
            raise RuntimeError(f'Capture cannot start while session is {s["state"]}')
        sequence = s["input_sequence"]
        directory = default_root() / "capture_sources" / session_id / uuid.uuid4().hex
        recorder = RecordingSession.start(directory, recording_name=session_id, capture_mode=s["source"], sample_rate=SAMPLE_RATE, sample_width=2)
        reader = open_audio_reader(s["source"])
        writer = threading.Thread(target=record, daemon=True)
        writer.start()
        threading.Thread(target=watch, daemon=True).start()
        while shared["tracks"] is None:
            if source_stop.is_set() and not shared["error"]:
                raise RuntimeError("Capture stopped before the first audio frame")
            if shared["error"]:
                raise shared["error"]
            time.sleep(0.01)
        client.open_audio(session_id, shared["tracks"])
        while True:
            if shared["error"]:
                raise shared["error"]
            while sent < shared["frames"]:
                if shared["state"] in ("failed", "ready", "recoverable"):
                    break
                parts = []
                for track in shared["tracks"]:
                    with (directory / ".capture" / f"{track}.pcm").open("rb") as f:
                        f.seek(sent * CHUNK_SIZE * 2)
                        parts.append(f.read(CHUNK_SIZE * 2))
                try:
                    response = client.send_audio(session_id, sequence, b"".join(parts))
                except RuntimeError:
                    current = control.request("get", {"session_id": session_id})
                    if current["state"] not in ("failed", "ready", "recoverable"):
                        raise
                    shared["state"] = current["state"]
                    source_stop.set()
                    break
                sequence = response["input_sequence"]
                sent += 1
            state = shared["state"]
            if state in ("pausing", "stopping"):
                source_stop.set()
                writer.join(timeout=1)
                if writer.is_alive():
                    reader.close()
                    writer.join(timeout=2)
                if writer.is_alive():
                    raise RuntimeError("Audio device did not acknowledge capture stop")
                if sent < shared["frames"]:
                    continue
                command = "producer.paused" if state == "pausing" else "producer.stopped"
                client.request(command, {"session_id": session_id})
                if state == "stopping":
                    break
                shared["state"] = "paused"
            elif state == "recording" and source_stop.is_set():
                reader.close()
                reader = open_audio_reader(s["source"])
                source_stop.clear()
                writer = threading.Thread(target=record, daemon=True)
                writer.start()
            elif state in ("failed", "ready", "recoverable"):
                break
            time.sleep(0.01)
    except Exception as exc:
        try:
            control.request("capture.failed", {"session_id": session_id, "error": str(exc)})
        except Exception:
            pass  # The disconnected service retains its last durable session state.
        raise
    finally:
        session_stop.set()
        source_stop.set()
        if reader:
            reader.close()
        if writer:
            writer.join(timeout=3)
        try:
            if recorder:
                recorder.finalize()
        finally:
            control.close()
            client.close()
