from PyQt6.QtCore import QThread, pyqtSignal

from summary.field_schemas import BASE_MODEL_ID, OLLAMA_MODEL_TAG
from aura.llm.ollama_runtime import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_READY_TIMEOUT_SEC,
    check_model_tag,
    check_ollama_command,
    check_ollama_server,
    pull_model,
    start_ollama_server,
    wait_for_ollama_ready,
)
from aura.llm.summary import SummarySettings, format_summary_block, summarize_transcript


class SummaryThread(QThread):
    summary_ready = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, transcript: str, settings: SummarySettings):
        super().__init__()
        self.transcript = transcript
        self.settings = settings
        self.summary_block = ""

    def run(self):
        try:
            self.status_updated.emit(
                f"🧠 Summarizing transcript with local {OLLAMA_MODEL_TAG} ({BASE_MODEL_ID})..."
            )
            summary = summarize_transcript(self.transcript, self.settings)
            if summary.strip():
                self.summary_block = format_summary_block(summary)
                self.summary_ready.emit(self.summary_block)
                self.status_updated.emit("✅ LLM summary completed")
            else:
                self.status_updated.emit("⚠️ No transcript content available for summary")
        except Exception as exc:
            self.error_signal.emit(str(exc))
            self.status_updated.emit("❌ LLM summary failed")


class OllamaRuntimeThread(QThread):
    status_updated = pyqtSignal(str)
    ready = pyqtSignal()
    model_missing = pyqtSignal(str)
    failed = pyqtSignal(str)
    server_process_started = pyqtSignal(object)

    def __init__(
        self,
        host: str = DEFAULT_OLLAMA_HOST,
        model_tag: str = OLLAMA_MODEL_TAG,
        timeout_sec: int = DEFAULT_OLLAMA_READY_TIMEOUT_SEC,
    ):
        super().__init__()
        self.host = host
        self.model_tag = model_tag
        self.timeout_sec = timeout_sec

    def run(self):
        self.status_updated.emit("Checking local Ollama runtime...")
        if not check_ollama_server(self.host):
            self.status_updated.emit("Ollama server is not running. Starting local ollama serve...")
            if not check_ollama_command():
                self.failed.emit(
                    "Ollama command was not found. Install Ollama and restart AURA, or add ollama to PATH."
                )
                return
            process = start_ollama_server(self.host)
            if process is None:
                self.failed.emit(
                    "Ollama command was not found. Install Ollama and restart AURA, or add ollama to PATH."
                )
                return
            self.server_process_started.emit(process)
            if not wait_for_ollama_ready(host=self.host, timeout_sec=self.timeout_sec):
                self.failed.emit(
                    f"AURA started ollama serve, but localhost:11434 did not become ready within {self.timeout_sec} seconds."
                )
                return

        self.status_updated.emit(f"Checking required local model tag: {self.model_tag}")
        if not check_model_tag(model_tag=self.model_tag, host=self.host):
            self.model_missing.emit(self.model_tag)
            return

        self.status_updated.emit(f"Local Ollama runtime ready with model {self.model_tag}.")
        self.ready.emit()


class OllamaPullThread(QThread):
    status_updated = pyqtSignal(str)
    pulled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, model_tag: str = OLLAMA_MODEL_TAG):
        super().__init__()
        self.model_tag = model_tag

    def run(self):
        self.status_updated.emit(f"Pulling local Ollama model: {self.model_tag}")
        ok = pull_model(self.model_tag, progress_callback=self.status_updated.emit)
        if ok:
            self.status_updated.emit(f"Local Ollama model installed: {self.model_tag}")
            self.pulled.emit()
            return
        self.failed.emit("Model pull failed. Check network, disk space, and Ollama permissions.")
