import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aura.asr.models import PARAKEET, parakeet_segments
from aura.session_core import SessionCore, options_for


class AsrModelsTests(unittest.TestCase):
    def test_model_defaults_preserve_breeze_preferences(self):
        prefs = dict(language="zh", hotwords="AURA", prompt="中文提示", punctuation=True)
        selected = options_for({"asr_model": PARAKEET}, prefs)
        self.assertEqual((selected["language"], selected["prompt"], selected["hotwords"], selected["punctuation"]),
                         ("en", "", "", False))
        self.assertEqual(options_for()["asr_model"], "breeze")
        self.assertEqual(options_for({"asr_model": "breeze"}, {**prefs, "asr_model": PARAKEET})["hotwords"], "AURA")
        for extra in ({"language": "zh"}, {"language": None}, {"hotwords": "hint"},
                      {"prompt": "hint"}, {"punctuation": True}, {"beam_size": 7}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                options_for({"asr_model": PARAKEET, **extra})
        with self.assertRaises(ValueError):
            options_for({"asr_model": "unknown"})

    def test_saved_model_and_sessions_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = SessionCore(tmp, executor=lambda *args: {})
            try:
                core.request("preferences.set", {"hotwords": "AURA"})
                core.request("preferences.set", {"asr_model": PARAKEET})
                with core.lock:
                    s = core._new({}, "recoverable")
                core.request("preferences.set", {"asr_model": "breeze"})
                self.assertEqual(s["options"]["asr_model"], PARAKEET)
            finally:
                core.close()
            core = SessionCore(tmp, executor=lambda *args: {})
            try:
                self.assertEqual(core.sessions[s["id"]]["options"]["asr_model"], PARAKEET)
                self.assertEqual(core.request("preferences.get")["hotwords"], "AURA")
            finally:
                core.close()

    def test_explicit_model_controls_are_async_and_preserve_sessions(self):
        import threading
        import time
        entered, release = threading.Event(), threading.Event()
        def load(kind, payload):
            entered.set()
            release.wait(5)
            if payload["options"]["asr_model"] == "breeze":
                raise RuntimeError("Synthetic model load failure")
            return {"model": PARAKEET, "device": "test-double"}
        with tempfile.TemporaryDirectory() as tmp:
            core = SessionCore(tmp, executor=load)
            try:
                result = core.request("model.load", {"asr_model": PARAKEET})
                self.assertEqual(result["state"], "loading")
                self.assertTrue(entered.wait(2))
                with self.assertRaises(ValueError):
                    core.request("record", {"capture_location": "client"})
                with self.assertRaises(ValueError):
                    core.request("model.unload")
                release.set()
                def wait(expected):
                    for _ in range(200):
                        result = core.request("model.status", request_id="reused-status")
                        if result["state"] == expected:
                            return result
                        time.sleep(.01)
                    self.fail(str(result))
                loaded = wait("loaded")
                self.assertTrue(loaded["kept_loaded"])
                self.assertEqual(loaded["default"], PARAKEET)
                self.assertEqual(core.request("sessions"), [])
                core.request("model.unload")
                self.assertFalse(wait("unloaded")["kept_loaded"])
                core.request("model.load", {"asr_model": "breeze"})
                failed = wait("error")
                self.assertEqual(failed["default"], PARAKEET)
                self.assertIn("Synthetic", failed["error"])
                core.request("model.unload")
                wait("unloaded")
            finally:
                release.set()
                core.close()

    def test_model_switch_is_blocked_during_existing_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = SessionCore(tmp, executor=lambda *a: {})
            try:
                with core.lock:
                    session = core._new({}, "paused")
                with self.assertRaises(ValueError):
                    core.request("model.load", {"asr_model": PARAKEET})
                self.assertEqual(session["options"]["asr_model"], "breeze")
            finally:
                core.close()

    def test_model_cli_has_visible_commands_and_old_service_guidance(self):
        from aura.cli import parser, execute, model_status_text
        args = parser().parse_args(["model", PARAKEET])
        client = MagicMock()
        client.request.side_effect = [{"model_control": True}, {"state": "loading", "asr_model": PARAKEET, "default": "breeze"}]
        with patch("builtins.print"):
            execute(client, args)
        self.assertEqual(client.request.call_args.args, ("model.load", {"asr_model": PARAKEET}))
        self.assertIn("/model load", model_status_text({"state": "unloaded", "default": "breeze"}))
        client.request.side_effect = [{}]
        with self.assertRaisesRegex(RuntimeError, "restart"):
            execute(client, args)

    def test_cli_model_reaches_shared_service(self):
        from aura.cli import parser, execute
        client = MagicMock()
        client.request.return_value = {"id": "test", "state": "starting", "title": "Meeting"}
        args = parser().parse_args(["record", "--model", PARAKEET, "--detach"])
        with patch("aura.cli.show"):
            execute(client, args)
        self.assertEqual(client.request.call_args.args[1]["options"], {"asr_model": PARAKEET})

    def test_worker_reuses_model_and_exits_before_switch(self):
        core = object.__new__(SessionCore)
        core.execute_override = None
        core.pool = None
        core.pool_model = None
        order = MagicMock()
        first, second = MagicMock(), MagicMock()
        order.attach_mock(first, "first")
        factory = MagicMock(side_effect=[first, second])
        order.attach_mock(factory, "factory")
        with patch("aura.session_core.concurrent.futures.ProcessPoolExecutor", factory):
            core._execute("file", {"options": {}})
            core._execute("file", {"options": {}})
            self.assertEqual(factory.call_count, 1)
            core._execute("file", {"options": {"asr_model": PARAKEET}})
            self.assertEqual(factory.call_count, 2)
            first.shutdown.assert_called_once()
            names = [call[0] for call in order.mock_calls]
            self.assertLess(names.index("first.shutdown"), len(names) - 1 - names[::-1].index("factory"))

    def test_timestamp_contract_and_missing_confidence(self):
        hyp = SimpleNamespace(text="Hello.", timestamp={"segment": [dict(start=.1, end=.9, segment="Hello.")]})
        segment = parakeet_segments(hyp, 1)[0]
        self.assertEqual((segment.start, segment.end, segment.text, segment.asr_logprob), (.1, .9, "Hello.", None))
        for start, end in ((-.1, .9), (.9, .1), (0, 2), (float("nan"), 1)):
            hyp.timestamp["segment"][0].update(start=start, end=end)
            with self.assertRaises(RuntimeError):
                parakeet_segments(hyp, 1)
        with self.assertRaises(RuntimeError):
            parakeet_segments(SimpleNamespace(text="Hello", timestamp={}), 1)
        self.assertEqual(parakeet_segments(SimpleNamespace(text="", timestamp={}), 1), [])

    def test_parakeet_import_preparation_decodes_stereo_48khz(self):
        import numpy as np
        import wave
        from aura.asr.file_pipeline import FileTranscriptionSettings, prepare_import_audio
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "stereo.wav", Path(tmp) / "prepared.wav"
            pcm = (np.sin(np.arange(48000) * .1) * 3000).astype("<i2")
            with wave.open(str(source), "wb") as f:
                f.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
                f.writeframes(np.column_stack([pcm, pcm]).tobytes())
            for preset in ("off", "light"):
                settings = FileTranscriptionSettings(asr_model=PARAKEET, language="en", initial_prompt="",
                                                    enable_denoise=preset != "off", denoise_preset=preset)
                prepare_import_audio(str(source), settings, target)
                with wave.open(str(target)) as f:
                    self.assertEqual((f.getnchannels(), f.getframerate(), f.getsampwidth()), (1, 16000, 2))

    def test_missing_optional_runtime_does_not_break_capabilities(self):
        from aura.asr.models import capabilities
        with patch("aura.asr.models.checkpoint", side_effect=ImportError), patch("aura.asr.models.importlib.util.find_spec", return_value=None):
            result = capabilities()
        self.assertFalse(result[PARAKEET]["dependencies_installed"])
        self.assertFalse(result[PARAKEET]["checkpoint_cached"])
        self.assertIn("breeze", result)


if __name__ == "__main__":
    unittest.main()
