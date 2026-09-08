#!/usr/bin/env python3
"""Explicitly activated functional check; reads audio only, never reference transcripts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

from aura.sdk import AuraClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audio-format", choices=("wav", "m4a"), default="wav")
    parser.add_argument("--activate-availability", action="store_true")
    args = parser.parse_args()
    if not args.activate_availability:
        parser.error("Use --activate-availability for real CUDA inference")
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = dict(validation_mode="availability_validation", status="PREFLIGHT_ONLY", accuracy="not_evaluated",
        latency="not_evaluated", ground_truth_read=False, input_sha256=hashlib.sha256(args.audio.read_bytes()).hexdigest())
    env = {**os.environ, "AURA_DATA_DIR": str(root / "service")}
    log = (root / "service.log").open("wb")
    process = subprocess.Popen([sys.executable, "-m", "aura.cli", "serve"], env=env, stdout=log, stderr=log)
    def wait(client, sid, state):
        deadline = time.monotonic() + 300  # Operating watchdog; never a performance endpoint.
        while time.monotonic() < deadline:
            s = client.request("get", {"session_id": sid})
            if s["state"] == state:
                return s
            if s["state"] in ("failed", "recoverable"):
                raise RuntimeError(s.get("error") or s["state"])
            time.sleep(0.1)
        raise RuntimeError("Availability watchdog stopped waiting")
    try:
        decoded = root / "input.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(args.audio), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(decoded)], check=True)
        receipt["decoded_sha256"] = hashlib.sha256(decoded.read_bytes()).hexdigest()
        connection_file = root / "service/connection.json"
        for _ in range(200):
            if connection_file.exists():
                break
            if process.poll() is not None:
                raise RuntimeError("Service failed to start")
            time.sleep(0.1)
        connection = json.loads(connection_file.read_text())
        with AuraClient(connection) as gui, AuraClient(connection) as cli:
            receipt["health"] = cli.request("capabilities")
            s = gui.request("record", dict(title="Controlled availability audio", capture_location="client",
                source="microphone", options={"audio_format": args.audio_format, "punctuation": False}))
            sid = s["id"]
            s = wait(cli, sid, "recording")
            receipt["runtime"] = s["runtime"]
            gui.open_audio(sid, ["mixed"])
            with wave.open(str(decoded)) as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                    raise ValueError("Availability input must be mono PCM16 WAV at 16 kHz")
                receipt["source_samples"] = audio.getnframes()
                seq = 0
                while frame := audio.readframes(480):
                    gui.send_audio(sid, seq, frame.ljust(960, b"\0"))
                    seq += 1
                    if seq == 10:
                        cli.request("pause", {"session_id": sid})
                        gui.request("producer.paused", {"session_id": sid})
                        wait(cli, sid, "paused")
                        cli.request("resume", {"session_id": sid})
            cli.request("stop", {"session_id": sid})
            gui.request("producer.stopped", {"session_id": sid})
            s = wait(cli, sid, "ready")
            if not s["transcript"].strip():
                raise RuntimeError("Real ASR produced no transcript")
            cli.download(sid, "txt", root / "transcript.txt")
            cli.download(sid, "wav", root / "recording.wav")
            if args.audio_format != "wav":
                cli.download(sid, args.audio_format, root / ("recording." + args.audio_format))
            receipt["delivery_format"] = args.audio_format
            receipt.update(status="LIVE_MINIMUM_COMPLETED", functional_result="available_and_working",
                runtime_validity="valid_target_runtime", sessions=1, audio_files=1,
                transcript_nonempty=True, shared_control=True, pause_resume=True, exports=True,
                session_id=sid, physical_microphone_acceptance="not_evaluated", ssh_second_host="not_evaluated")
    except Exception as exc:
        receipt.update(status="BLOCKED_UNRESOLVED", functional_result="blocked", error=str(exc))
    finally:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            receipt["shutdown"] = "forced"
        log.close()
        (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "LIVE_MINIMUM_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
