import unittest
from unittest.mock import MagicMock, patch

from aura.llm.ollama_runtime import (
    DEFAULT_OLLAMA_HOST,
    OllamaRuntimeError,
    check_model_tag,
    check_ollama_command,
    check_ollama_server,
    ensure_ollama_ready,
    pull_model,
    validate_localhost_host,
)


class FakeResponse:
    def __init__(self, payload: str):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload.encode("utf-8")


class OllamaRuntimeTests(unittest.TestCase):
    def test_server_already_running_and_model_exists_is_ready(self):
        with patch("aura.llm.ollama_runtime.shutil.which", return_value="/usr/bin/ollama"):
            with patch(
                "aura.llm.ollama_runtime.urllib.request.urlopen",
                return_value=FakeResponse('{"models":[{"name":"gemma4:e4b-it-q4_K_M"}]}'),
            ):
                status = ensure_ollama_ready()

        self.assertTrue(status.server_running)
        self.assertTrue(status.model_available)
        self.assertTrue(status.ollama_command_available)
        self.assertIn("ready", status.message)

    def test_server_unavailable_and_ollama_command_missing_fails_clearly(self):
        with patch("aura.llm.ollama_runtime.shutil.which", return_value=None):
            with patch("aura.llm.ollama_runtime.urllib.request.urlopen", side_effect=OSError("not running")):
                status = ensure_ollama_ready()

        self.assertFalse(status.server_running)
        self.assertFalse(status.model_available)
        self.assertFalse(status.ollama_command_available)
        self.assertIn("Ollama command was not found", status.message)

    def test_server_unavailable_command_exists_and_server_starts_is_ready(self):
        with patch("aura.llm.ollama_runtime.check_ollama_command", return_value=True):
            with patch("aura.llm.ollama_runtime.check_ollama_server", side_effect=[False, True]):
                with patch("aura.llm.ollama_runtime.start_ollama_server") as start:
                    with patch("aura.llm.ollama_runtime.wait_for_ollama_ready", return_value=True):
                        with patch("aura.llm.ollama_runtime.check_model_tag", return_value=True):
                            status = ensure_ollama_ready()

        start.assert_called_once()
        self.assertTrue(status.server_running)
        self.assertTrue(status.model_available)

    def test_server_starts_but_times_out_fails_clearly(self):
        with patch("aura.llm.ollama_runtime.check_ollama_command", return_value=True):
            with patch("aura.llm.ollama_runtime.check_ollama_server", return_value=False):
                with patch("aura.llm.ollama_runtime.start_ollama_server"):
                    with patch("aura.llm.ollama_runtime.wait_for_ollama_ready", return_value=False):
                        status = ensure_ollama_ready(timeout_sec=20)

        self.assertFalse(status.server_running)
        self.assertFalse(status.model_available)
        self.assertIn("did not become ready within 20 seconds", status.message)

    def test_model_missing_returns_model_missing_status(self):
        with patch("aura.llm.ollama_runtime.shutil.which", return_value="/usr/bin/ollama"):
            with patch(
                "aura.llm.ollama_runtime.urllib.request.urlopen",
                return_value=FakeResponse('{"models":[{"name":"other:model"}]}'),
            ):
                status = ensure_ollama_ready()

        self.assertTrue(status.server_running)
        self.assertFalse(status.model_available)
        self.assertIn("Required local model tag not found", status.message)

    def test_pull_model_success_streams_progress(self):
        process = MagicMock()
        process.stdout = iter(["pulling manifest\n", "success\n"])
        process.wait.return_value = 0
        progress = []

        with patch("aura.llm.ollama_runtime.shutil.which", return_value="/usr/bin/ollama"):
            with patch("aura.llm.ollama_runtime.subprocess.Popen", return_value=process):
                ok = pull_model("gemma4:e4b-it-q4_K_M", progress_callback=progress.append)

        self.assertTrue(ok)
        self.assertEqual(progress, ["pulling manifest", "success"])

    def test_pull_model_failure_returns_false(self):
        process = MagicMock()
        process.stdout = iter(["error\n"])
        process.wait.return_value = 1

        with patch("aura.llm.ollama_runtime.shutil.which", return_value="/usr/bin/ollama"):
            with patch("aura.llm.ollama_runtime.subprocess.Popen", return_value=process):
                ok = pull_model("gemma4:e4b-it-q4_K_M")

        self.assertFalse(ok)

    def test_host_must_be_localhost(self):
        with self.assertRaises(OllamaRuntimeError):
            validate_localhost_host("https://api.example.com")

    def test_check_model_tag_reads_local_tags(self):
        with patch(
            "aura.llm.ollama_runtime.urllib.request.urlopen",
            return_value=FakeResponse('{"models":[{"name":"gemma4:e4b-it-q4_K_M"}]}'),
        ):
            self.assertTrue(check_model_tag("gemma4:e4b-it-q4_K_M", DEFAULT_OLLAMA_HOST))

    def test_check_ollama_command_uses_path(self):
        with patch("aura.llm.ollama_runtime.shutil.which", return_value="/usr/bin/ollama"):
            self.assertTrue(check_ollama_command())

    def test_check_ollama_server_returns_false_when_unavailable(self):
        with patch("aura.llm.ollama_runtime.urllib.request.urlopen", side_effect=OSError("down")):
            self.assertFalse(check_ollama_server())


if __name__ == "__main__":
    unittest.main()
