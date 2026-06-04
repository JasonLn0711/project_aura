from PyQt6.QtCore import QThread, pyqtSignal

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
                f"🧠 Summarizing transcript with local {self.settings.model_id} {self.settings.quantization}..."
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
