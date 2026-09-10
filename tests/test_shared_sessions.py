import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from aura.session_core import SessionCore
from aura.sdk import AuraClient


def fake_inference(kind, payload):
    if kind == "load":
        return {"model": "test-double", "device": "test"}
    if kind == "chunk":
        return dict(text="測試逐字稿", start_sample=payload["start"], end_sample=payload["end"])
    if kind == "export":
        return {"path": payload["path"]}
    return {"text": "精修版本", "segments": []}


class Speech:
    def is_speech(self, *args):
        return True


def test_server(root):
    from aura.service import serve
    with patch("aura.audio.vad.SileroStreamVAD", return_value=Speech()):
        serve(root, core=SessionCore(root, executor=fake_inference))


def wait_state(client, sid, state):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        s = client.request("get", {"session_id": sid})
        if s["state"] == state:
            return s
        if s["state"] == "failed":
            raise AssertionError(s["error"])
        time.sleep(0.02)
    raise AssertionError(f"Expected {state}, got {s['state']}")


class SharedSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.core = SessionCore(self.root, executor=fake_inference)

    def tearDown(self):
        self.core.close()
        self.tmp.cleanup()

    def test_oversized_context_preserves_loaded_model_without_creating_sessions(self):
        import datetime
        from types import SimpleNamespace
        from huggingface_hub.errors import LocalEntryNotFoundError
        from aura.asr.hotwords import validate_cached_context
        from aura.config import MODEL_ID

        self.core.pool = Mock()
        self.core.keep_model = True
        self.core.model_state = dict(state="loaded", asr_model="breeze", error=None)
        before = self.core.request("model.status")
        start = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        media = self.root / "input.wav"
        media.touch()
        tokenizer = SimpleNamespace(encode=lambda text: SimpleNamespace(ids=list(text)))
        with patch("huggingface_hub.hf_hub_download", return_value="cached-tokenizer") as cached, \
                patch("tokenizers.Tokenizer.from_file", return_value=tokenizer):
            validate_cached_context(dict(prompt="", hotwords="a" * 199))  # Exactly 200 tokens.
            for command, args in (
                ("record", {}),
                ("schedule", dict(start_at=start.isoformat(), stop_at=(start + datetime.timedelta(hours=1)).isoformat())),
                ("transcribe", dict(path=str(media))),
            ):
                with self.subTest(command=command), self.assertRaisesRegex(ValueError, "201 tokens"):
                    self.core.request(command, dict(args, options=dict(asr_model="breeze", prompt="", hotwords="a" * 200)))
            cached.assert_called_with(MODEL_ID, "tokenizer.json", local_files_only=True)
            cached.reset_mock()
            validate_cached_context(dict(asr_model="parakeet-tdt-0.6b-v2"))
            cached.assert_not_called()
            cached.side_effect = LocalEntryNotFoundError("not cached")
            validate_cached_context(dict(hotwords="a" * 200))
        self.assertEqual(self.core.request("sessions"), [])
        self.assertEqual(self.core.request("model.status"), before)
        self.assertEqual(self.core.db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)
        self.core.pool.shutdown.assert_not_called()

    def test_shared_preferences_validate_and_survive_restart(self):
        self.core.request("preferences.set", {"profile": "off", "hotwords": "AURA"})
        with self.assertRaises(ValueError):
            self.core.request("preferences.set", {"beam_size": 0})
        self.core.close()
        self.core = SessionCore(self.root, executor=fake_inference)
        sid = self.record()
        self.assertEqual(self.core.request("get", {"session_id": sid})["options"]["profile"], "off")

    def test_schedule_without_confirmation_and_legacy_false_field(self):
        import datetime
        start = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        s = self.core.request("schedule", {"start_at": start.isoformat(), "stop_at": (start + datetime.timedelta(hours=1)).isoformat()})
        self.assertEqual(s["state"], "scheduled")
        s = self.core.request("record", {"consent": False, "capture_location": "client"})
        self.assertEqual(s["state"], "starting")

    def record(self):
        s = self.core.request("record", {"capture_location": "client", "options": {"audio_format": "wav"}})
        wait_state(self.core, s["id"], "recording")
        return s["id"]

    def test_cross_client_pause_resume_stop_preserves_samples_and_edits(self):
        sid = self.record()
        self.core.request("producer.open", {"session_id": sid})
        with patch("aura.audio.vad.SileroStreamVAD", return_value=Speech()):
            for seq in range(4):
                self.core.ingest(sid, seq, b"\x01\x00" * 480, ["mixed"])
            self.core.request("pause", {"session_id": sid})
            self.core.request("producer.paused", {"session_id": sid})
            with self.assertRaisesRegex(ValueError, "not accepting audio"):
                self.core.ingest(sid, 4, bytes(960), ["mixed"])
            s = self.core.request("get", {"session_id": sid})
            self.core.request("edit", dict(session_id=sid, revision=s["revision"], text="使用者的文字\n  保留空白"))
            self.core.request("resume", {"session_id": sid})
            self.core.ingest(sid, 4, bytes(960), ["mixed"])
        self.core.request("stop", {"session_id": sid})
        self.core.request("producer.stopped", {"session_id": sid})
        s = wait_state(self.core, sid, "ready")
        self.assertEqual(s["samples"], 2400)
        self.assertEqual(s["transcript"], "使用者的文字\n  保留空白")
        import wave
        with wave.open(s["artifacts"]["wav"]) as f:
            self.assertEqual(f.getnframes(), 2400)
        self.assertNotIn("refined.txt", s["artifacts"])
        self.core.request("refine", {"session_id": sid})
        s = wait_state(self.core, sid, "ready")
        self.assertEqual(s["transcript"], "使用者的文字\n  保留空白")
        self.assertEqual(Path(s["artifacts"]["refined.txt"]).read_text(encoding="utf-8"), "精修版本\n")
        self.assertEqual(self.core.request("export", {"session_id": sid, "format": "refined"})["path"], s["artifacts"]["refined.txt"])

    def test_request_replay_cannot_duplicate_recording_or_change_payload(self):
        a = self.core.request("record", {"consent": True}, request_id="same")
        b = self.core.request("record", {"consent": True}, request_id="same")
        self.assertEqual(a, b)
        with self.assertRaises(ValueError):
            self.core.request("record", {"consent": False}, request_id="same")
        self.assertEqual(len(self.core.request("sessions")), 1)

    def test_stale_editor_revision_is_rejected(self):
        sid = self.record()
        self.core.request("edit", dict(session_id=sid, revision=0, text="first"))
        with self.assertRaisesRegex(ValueError, "Transcript changed"):
            self.core.request("edit", dict(session_id=sid, revision=0, text="overwrite"))

    def test_rescue_and_frame_validation(self):
        with self.assertRaises(ValueError):
            self.core.request("record", {"options": {"profile": "rescue-offline"}})
        sid = self.record()
        with self.assertRaises(ValueError):
            self.core.ingest(sid, 0, b"broken", ["mixed"])
        with self.assertRaises(ValueError):
            self.core.ingest(sid, 1, bytes(960), ["mixed"])

    def test_failed_disk_write_does_not_claim_saved_edit(self):
        sid = self.record()
        with patch.object(self.core, "_write_text", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.core.request("edit", dict(session_id=sid, revision=0, text="important"))
        self.assertEqual(self.core.request("get", {"session_id": sid})["revision"], 0)

    def test_restart_retains_session_identity_and_recovery_status(self):
        sid = self.record()
        with patch("aura.audio.vad.SileroStreamVAD", return_value=Speech()):
            self.core.ingest(sid, 0, bytes(960), ["mixed"])
        self.core.close()
        self.core = SessionCore(self.root, executor=fake_inference)
        s = self.core.request("get", {"session_id": sid})
        self.assertEqual(s["state"], "recoverable")
        self.core.request("refine", {"session_id": sid})
        wait_state(self.core, sid, "ready")


class TransportTests(unittest.TestCase):
    def test_real_transport_two_clients_audio_and_export(self):
        with tempfile.TemporaryDirectory() as root:
            process = multiprocessing.get_context("spawn").Process(target=test_server, args=(root,))
            process.start()
            try:
                path = Path(root) / "connection.json"
                for _ in range(150):
                    if path.exists():
                        break
                    time.sleep(0.05)
                connection = json.loads(path.read_text(encoding="utf-8"))
                with AuraClient(connection) as gui, AuraClient(connection) as cli:
                    s = gui.request("record", {"capture_location": "client", "options": {"audio_format": "wav"}})
                    sid = s["id"]
                    wait_state(cli, sid, "recording")
                    gui.open_audio(sid, ["mixed"])
                    gui.send_audio(sid, 0, bytes(960))
                    cli.request("pause", {"session_id": sid})
                    gui.request("producer.paused", {"session_id": sid})
                    self.assertEqual(cli.request("get", {"session_id": sid})["state"], "paused")
                    cli.request("stop", {"session_id": sid})
                    gui.request("producer.stopped", {"session_id": sid})
                    wait_state(cli, sid, "ready")
                    target = Path(root) / "export.txt"
                    progress = []
                    cli.download(sid, "txt", target, on_progress=lambda done,total: progress.append((done,total)))
                    self.assertEqual(progress[-1], (target.stat().st_size, None))
                    media = Path(root) / "upload.wav"
                    media.write_bytes(bytes(44))
                    uploaded = []
                    remote = cli.upload(media, on_progress=lambda done,total: uploaded.append((done,total)))
                    self.assertEqual(Path(remote).read_bytes(), media.read_bytes())
                    self.assertEqual(uploaded[-1], (44,44))
                    self.assertIn("測試", target.read_text(encoding="utf-8"))
                    with self.assertRaises(ValueError):
                        cli.download(sid, "txt", target)
                # Exercise the real detached producer control loop with a synthetic device.
                import threading
                import numpy as np
                from aura.producer import capture
                class Device:
                    def read_tracks(self):
                        time.sleep(.03)
                        return {"mixed": np.ones(480, dtype=np.int16)}
                    def close(self):
                        pass
                errors = []
                with AuraClient(connection) as controller:
                    sid = controller.request("record", {"capture_location": "client", "options": {"audio_format": "wav"}})["id"]
                    wait_state(controller, sid, "recording")
                    def run_capture():
                        try:
                            capture(sid)
                        except Exception as exc:
                            errors.append(exc)
                    with patch("aura.producer.AuraClient", side_effect=lambda *a, **k: AuraClient(connection)), patch("aura.audio.inputs.open_audio_reader", return_value=Device()), patch.dict(os.environ, {"AURA_DATA_DIR": root}):
                        thread = threading.Thread(target=run_capture, daemon=True)
                        thread.start()
                        for _ in range(100):
                            if controller.request("get", {"session_id": sid})["samples"] >= 480:
                                break
                            time.sleep(.02)
                        controller.request("pause", {"session_id": sid})
                        paused = wait_state(controller, sid, "paused")
                        self.assertGreater(paused["samples"], 0)
                        time.sleep(.1)
                        self.assertEqual(controller.request("get", {"session_id": sid})["samples"], paused["samples"])
                        controller.request("resume", {"session_id": sid})
                        time.sleep(.2)
                        controller.request("stop", {"session_id": sid})
                        wait_state(controller, sid, "ready")
                        thread.join(5)
                        self.assertFalse(thread.is_alive())
                        self.assertEqual(errors, [])
                from websockets.sync.client import connect
                with self.assertRaises(Exception):
                    connect(connection["url"], additional_headers={"Authorization": "Bearer wrong"}, proxy=None)
            finally:
                process.terminate()
                process.join(10)
                if process.is_alive():
                    process.kill()
                    process.join()
                process.close()
