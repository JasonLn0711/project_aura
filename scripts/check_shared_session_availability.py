#!/usr/bin/env python3
"""Explicitly activated functional check; reads audio only, never reference transcripts."""
import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import subprocess
import sys
import time
import wave
import datetime
import platform
import uuid

from aura.sdk import AuraClient
from aura.asr.models import MODEL_KEYS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", choices=MODEL_KEYS, default="breeze")
    parser.add_argument("--source-url", default="operator-authorized audio")
    parser.add_argument("--preload", action="store_true", help="Validate explicit model load, reuse and unload")
    parser.add_argument("--all-paths", action="store_true", help="Also validate import and explicit refinement")
    parser.add_argument("--audio-format", choices=("wav", "m4a"), default="m4a", help="Legacy wav selection also exports M4A")
    parser.add_argument("--capture-backend", choices=("rust", "python"), default="rust")
    parser.add_argument("--virtual-capture", action="store_true", help="Play public input into a dedicated PulseAudio null sink and capture its monitor")
    parser.add_argument("--language", choices=("en", "zh"), default="en")
    parser.add_argument('--max-segment-seconds', type=float, default=2,
                        help='Fixed ASR segment cap for this functional validation')
    parser.add_argument('--recover-enhancement-gaps', action='store_true',
                        help='Explicitly recover missing enhanced speech after Stop')
    parser.add_argument('--live-policy', choices=('reference-v1', 'speech-guard-v1'), default='speech-guard-v1')
    parser.add_argument('--continuous-replay', action='store_true',
                        help='Keep SDK input within one second of enhancement; finish live repair before Stop')
    parser.add_argument('--require-segment-range', action='append', default=[], metavar='START:END',
                        help='Require nonempty live ASR overlapping this source-time range in seconds')
    parser.add_argument('--watchdog-seconds', type=int, default=300,
                        help='Safety stop for stalled stages; not an ASR timing measurement')
    parser.add_argument("--activate-availability", action="store_true")
    args = parser.parse_args()
    if not args.activate_availability:
        parser.error("Use --activate-availability for real CUDA inference")
    if not 2 <= args.max_segment_seconds <= 30 or not 1 <= args.watchdog_seconds <= 86400:
        parser.error('Segment cap must be 2–30 seconds and watchdog must be 1–86400 seconds')
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    print("Availability check: preparing isolated service and authorized input audio", file=sys.stderr, flush=True)
    receipt = dict(run_id="RUN-" + root.name, run_date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        architecture=platform.machine(), capture_backend=args.capture_backend, validation_mode="availability_validation", status="PREFLIGHT_ONLY", accuracy="not_evaluated",
        latency="not_evaluated", ground_truth_read=False, model=args.model, source_url=args.source_url,
        runtime_validity="blocked_runtime", functional_result="blocked", input_sha256=hashlib.sha256(args.audio.read_bytes()).hexdigest())
    env = {**os.environ, "AURA_DATA_DIR": str(root / "service"), 'AURA_LIVE_ENHANCEMENT_POLICY':args.live_policy}
    receipt['live_policy'] = args.live_policy
    required_ranges = []
    for value in args.require_segment_range:
        try:
            left, right = map(float,value.split(':'))
            if not 0 <= left < right or not __import__('math').isfinite(right):
                raise ValueError()
            required_ranges.append((left,right))
        except ValueError:
            parser.error('Required segment ranges must be finite 0 <= START < END')
    log = (root / "service.log").open("wb")
    process = subprocess.Popen([sys.executable, "-m", "aura.cli", "serve"], env=env, stdout=log, stderr=log)
    native = None
    native_log = None
    playback = None
    pulse_module = None
    def wait(client, sid, state):
        deadline = time.monotonic() + args.watchdog_seconds  # Operating watchdog, not a performance endpoint.
        last_progress = 0
        while time.monotonic() < deadline:
            s = client.request("get", {"session_id": sid})
            if s["state"] == state:
                return s
            if s["state"] in ("failed", "recoverable"):
                raise RuntimeError(s.get("error") or s["state"])
            if time.monotonic() - last_progress >= 5:
                enhancement = s.get('enhancement', {})
                progress = enhancement.get('recovery_progress', {})
                completed = progress.get('completed_samples', 0) if enhancement.get('recovery_scanning') else enhancement.get('processed_samples', 0)
                pending = sum(g['status'] == 'pending' for g in enhancement.get('gaps', []))
                print(f"Availability check: {s['state']} · enhanced/inspected {completed}/{s.get('samples', 0)} source samples · ASR done {s.get('work', {}).get('done', 0)} · enhancement gaps {pending}", file=sys.stderr, flush=True)
                last_progress = time.monotonic()
            time.sleep(0.1)
        raise RuntimeError("Availability watchdog stopped waiting")
    def wait_model(client, state):
        deadline = time.monotonic() + args.watchdog_seconds
        while time.monotonic() < deadline:
            result = client.request("model.status")
            if result["state"] == state:
                return result
            if result["state"] == "error":
                raise RuntimeError(result["error"])
            time.sleep(.1)
        raise RuntimeError("Model-control availability watchdog stopped waiting")
    def wait_enhancement(client, sid, target, *, final=False):
        deadline = time.monotonic() + args.watchdog_seconds
        marker = None
        while True:
            s = client.request('get', {'session_id':sid})
            enhancement = s.get('enhancement', {})
            position = enhancement.get('processed_samples',0)
            repairs = enhancement.get('live_repair_work',{})
            current = (position,s.get('work',{}).get('done',0),repairs.get('queued',0),repairs.get('active',False))
            if current != marker:
                marker = current
                deadline = time.monotonic() + args.watchdog_seconds
            if s['state'] == 'failed':
                raise RuntimeError(s['error'])
            if position >= target and (not final or not (repairs.get('active') or repairs.get('queued'))):
                return
            if time.monotonic() > deadline:
                raise RuntimeError('Continuous enhancement replay stopped advancing; source retained')
            time.sleep(.05)
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
            if args.preload:
                cli.request("model.load", {"asr_model": args.model})
                receipt["preload"] = wait_model(cli, "loaded")
            options = {"asr_model": args.model, "audio_format": "m4a", "punctuation": False,
                       "language": args.language, "profile": "reuse-v1", "live_max_segment_len_sec": args.max_segment_seconds}
            receipt["options"] = options
            if args.all_paths:
                imported = cli.request("transcribe", {"path": cli.upload(args.audio), "options": options,
                                                      "title": "Public English import"})
                imported = wait(cli, imported["id"], "ready")
                if not imported["transcript"].strip() or not imported["segments"]:
                    raise RuntimeError("Import did not produce text and segments")
                cli.download(imported["id"], "txt", root / "import.txt")
                cli.download(imported["id"], "json", root / "import.json")
                receipt["import_session_id"] = imported["id"]
                receipt["import_runtime"] = imported["runtime"]
                receipt["import_available"] = True
            s = gui.request("record", dict(title="Controlled availability audio", capture_location="client",
                source="microphone", options=options))
            sid = s["id"]
            s = wait(cli, sid, "recording")
            receipt["runtime"] = s["runtime"]
            if args.capture_backend == "rust":
                from aura.native_capture import helper
                with wave.open(str(decoded)) as audio:
                    receipt["source_samples"] = audio.getnframes()
                    raw = audio.readframes(audio.getnframes())
                raw = raw.ljust(((len(raw) + 959) // 960) * 960, b"\0")
                raw_path = root / "input.pcm"
                raw_path.write_bytes(raw)
                init = dict(version=1, connection=connection, session_id=sid,
                            directory=str(root / "capture"), sources=[], input_pcm=str(raw_path))
                if args.virtual_capture:
                    sink = "aura_availability_" + uuid.uuid4().hex[:12]
                    pulse_module = subprocess.check_output(["pactl", "load-module", "module-null-sink", "sink_name=" + sink], text=True).strip()
                    init.pop("input_pcm")
                    init["sources"] = [dict(name=sink + ".monitor", track="system")]
                native_log = (root / "capture-events.jsonl").open("w")
                native = subprocess.Popen([helper()], stdin=subprocess.PIPE, stdout=native_log, stderr=log, text=True)
                native.stdin.write(json.dumps(init) + "\n"); native.stdin.flush()
                watchdog = time.monotonic() + max(300, receipt["source_samples"] / 16000 + 120)
                while not cli.request("get", {"session_id": sid})['producer_connected']:
                    if native.poll() is not None or time.monotonic() > watchdog:
                        raise RuntimeError("Native producer did not connect; see capture-events.jsonl")
                    time.sleep(.05)
                if args.virtual_capture:
                    cli.request("pause", {"session_id": sid})
                    wait(cli, sid, "paused")
                    cli.request("resume", {"session_id": sid})
                    wait(cli, sid, "recording")
                    playback = subprocess.Popen(["paplay", "--device=" + sink, str(decoded)], stdout=log, stderr=log)
                receipt["live_text_before_capture_end"] = False
                receipt["enhancement_backlog_max_samples_after_warmup"] = 0
                print("Availability check: native capture and GPU transcription active", file=sys.stderr, flush=True)
                while (playback.poll() is None if playback else native.poll() is None):
                    current = cli.request("get", {"session_id": sid})
                    enhancement = current.get('enhancement', {})
                    if enhancement.get('processed_samples', 0) >= 160000:
                        receipt['enhancement_backlog_max_samples_after_warmup'] = max(receipt['enhancement_backlog_max_samples_after_warmup'], enhancement.get('backlog_samples', 0))
                    if current['state'] == 'failed':
                        raise RuntimeError(current['error'])
                    if current['state'] == 'recording' and current['transcript'].strip():
                        receipt["live_text_before_capture_end"] = True
                    if time.monotonic() > watchdog:
                        raise RuntimeError("Native capture safety watchdog expired")
                    time.sleep(.1)
                if playback:
                    if playback.returncode:
                        raise RuntimeError("Public audio playback failed")
                    cli.request("stop", {"session_id": sid})
                receipt["capture_path"] = "virtual_pulse_monitor" if args.virtual_capture else "paced_pcm_fixture"
                receipt["pause_resume"] = bool(args.virtual_capture)
            else:
                gui.open_audio(sid, ["mixed"])
                receipt['capture_path'] = 'sdk_pcm_replay'
                receipt['live_text_before_capture_end'] = False
                with wave.open(str(decoded)) as audio:
                    if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                        raise ValueError("Availability input must be mono PCM16 WAV at 16 kHz")
                    receipt["source_samples"] = audio.getnframes()
                    seq = 0
                    last_replay_progress = 0
                    while frame := audio.readframes(480):
                        gui.send_audio(sid, seq, frame.ljust(960, b"\0"))
                        seq += 1
                        if seq == 1000:
                            deadline = time.monotonic() + args.watchdog_seconds
                            while not cli.request('get', {'session_id': sid})['transcript'].strip():
                                current = cli.request('get', {'session_id': sid})
                                if current['state'] == 'failed' or time.monotonic() > deadline:
                                    raise RuntimeError(current.get('error') or 'No live text before the remaining source was sent')
                                time.sleep(.1)
                            receipt['live_text_before_capture_end'] = True
                            print('Availability check: live text exists; sending remaining source samples', file=sys.stderr, flush=True)
                        if seq == 10:
                            cli.request("pause", {"session_id": sid})
                            gui.request("producer.paused", {"session_id": sid})
                            wait(cli, sid, "paused")
                            cli.request("resume", {"session_id": sid})
                        if args.continuous_replay and seq % 16 == 0:
                            wait_enhancement(cli,sid,max(0,seq * 480 - 8000))
                            if time.monotonic() - last_replay_progress >= 5:
                                print(f'Availability check: source replay {seq * 480}/{receipt["source_samples"]} samples', file=sys.stderr,flush=True)
                                last_replay_progress = time.monotonic()
                if args.continuous_replay:
                    wait_enhancement(cli,sid,seq * 480 - 480,final=True)
                cli.request("stop", {"session_id": sid})
                gui.request("producer.stopped", {"session_id": sid})
            s = wait(cli, sid, "ready")
            receipt['enhancement_before_recovery'] = s.get('enhancement', {})
            if args.recover_enhancement_gaps:
                print('Availability check: checking and recovering unqueued enhanced speech', file=sys.stderr, flush=True)
                cli.request('recover', {'session_id': sid, 'language': args.language})
                s = wait(cli, sid, 'ready')
                if any(g['status'] == 'pending' for g in s.get('enhancement', {}).get('gaps', [])):
                    raise RuntimeError('Enhancement recovery left unresolved speech gaps; original audio retained')
                if not s.get('delivery_committed'):
                    raise RuntimeError('Recovery did not commit validated delivery audio')
                receipt['enhancement_recovery_available'] = True
            if native and native.wait(timeout=args.watchdog_seconds):
                raise RuntimeError('Native capture failed; see capture-events.jsonl')
            receipt['enhancement_after_recovery'] = s.get('enhancement', {})
            if not s["transcript"].strip():
                raise RuntimeError("Real ASR produced no transcript")
            receipt['required_segment_ranges'] = [dict(start_seconds=left,end_seconds=right,
                pass_gate=any(x['text'].strip() and x['start_ms'] < right * 1000 and x['end_ms'] > left * 1000
                    for x in s.get('segments',[]))) for left,right in required_ranges]
            if any(not row['pass_gate'] for row in receipt['required_segment_ranges']):
                raise RuntimeError('Required source interval still has no live ASR output')
            duration_ms = s["samples"] * 1000 / 16000
            if not s["segments"] or any(
                not (0 <= segment["start_ms"] < segment["end_ms"] <= duration_ms)
                for segment in s["segments"]
            ):
                raise RuntimeError("Live segments are missing or outside retained audio")
            receipt["segment_bounds_valid"] = True
            cli.download(sid, "txt", root / "transcript.txt")
            cli.download(sid, "m4a", root / "recording.m4a")
            from aura.audio.retention import validate_m4a
            receipt["audio_validation"] = validate_m4a(root / "recording.m4a")
            if args.capture_backend == "rust":
                receipt["capture_frames"] = s["input_sequence"]
                receipt["capture_spool_removed"] = not (root / "capture/frames.pcm").exists()
                if not receipt["capture_spool_removed"] or not s.get("delivery_committed"):
                    raise RuntimeError("Enhanced delivery commit did not clean the native spool")
            cli.download(sid, "json", root / "session.json")
            if args.all_paths:
                original = s["transcript"]
                cli.request("edit", {"session_id": sid, "revision": s["revision"], "text": original + "\n[operator edit]"})
                cli.request("refine", {"session_id": sid})
                refined = wait(cli, sid, "ready")
                if refined["transcript"] != original + "\n[operator edit]":
                    raise RuntimeError("Refinement overwrote operator edits")
                cli.download(sid, "refined", root / "refined.txt")
                if not (root / "refined.txt").read_text().strip():
                    raise RuntimeError("Refinement produced empty text")
                receipt["refinement_available"] = True
                receipt["edits_preserved"] = True
            if args.preload:
                warm = cli.request("model.status")
                if not warm["kept_loaded"] or warm["state"] != "loaded":
                    raise RuntimeError("Explicitly loaded ASR was not retained")
                worker_pid = receipt["preload"]["runtime"]["worker_pid"]
                if any(runtime["worker_pid"] != worker_pid for runtime in (receipt["runtime"], warm["runtime"], receipt.get("import_runtime", warm["runtime"]))):
                    raise RuntimeError("Same-model jobs did not reuse the preloaded worker")
                receipt["preloaded_worker_reused"] = True
                cli.request("model.unload")
                receipt["unload"] = wait_model(cli, "unloaded")
                if Path(f"/proc/{worker_pid}").exists():
                    raise RuntimeError("Unloaded ASR worker still exists")
                receipt["unloaded_worker_exited"] = True
            receipt["delivery_format"] = "m4a"
            if args.capture_backend == "rust":
                receipt["enhancement_backlog_gate"] = "pass" if receipt["enhancement_backlog_max_samples_after_warmup"] <= 16000 else "fail"
            receipt.update(status="LIVE_MINIMUM_COMPLETED", functional_result="available_and_working",
                runtime_validity="valid_target_runtime", sessions=2 if args.all_paths else 1, audio_files=1,
                transcript_nonempty=True, shared_control=True, exports=True,
                session_id=sid, physical_microphone_acceptance="not_evaluated", ssh_second_host="not_evaluated")
    except Exception as exc:
        receipt.update(status="BLOCKED_UNRESOLVED", functional_result="blocked", error=str(exc))
    finally:
        if playback and playback.poll() is None:
            playback.terminate(); playback.wait(timeout=5)
        if native:
            if native.poll() is None:
                native.terminate(); native.wait(timeout=5)
            native.stdin.close()
        if native_log:
            native_log.close()
        if pulse_module:
            subprocess.run(["pactl", "unload-module", pulse_module], check=False, stdout=subprocess.DEVNULL)
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            receipt["shutdown"] = "forced"
        log.close()
        database = root / "service/sessions.sqlite3"
        if database.exists():
            with sqlite3.connect(database) as db:
                jobs = [dict(id=r[0], session=r[1], kind=r[2], state=r[3],
                             asr_model=json.loads(r[4])["options"].get("asr_model", "breeze"))
                        for r in db.execute("SELECT id,session,kind,state,payload FROM jobs ORDER BY id")]
                events = [dict(seq=r[0], **json.loads(r[1])) for r in db.execute("SELECT seq,data FROM events ORDER BY seq")]
            (root / "requests.jsonl").write_text("".join(json.dumps(j) + "\n" for j in jobs))
            (root / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
            (root / "errors.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events if
                e.get('session', {}).get('error') or any(g.get('error') for g in e.get('session', {}).get('enhancement', {}).get('gaps', []))))
            receipt["successful_inference_jobs"] = sum(j["state"] == "done" and j["kind"] in ("file", "chunk") for j in jobs)
            receipt["successful_jobs_by_kind"] = {kind: sum(j["state"] == "done" and j["kind"] == kind for j in jobs) for kind in ("file", "chunk")}
        (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Availability check: " + receipt["status"] + "; receipt: " + str(root / "receipt.json"), file=sys.stderr)
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "LIVE_MINIMUM_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
