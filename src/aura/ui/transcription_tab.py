"""Desktop presentation of the shared AURA session service."""
import datetime
import json
import os
from pathlib import Path
import queue
import re
import tempfile
import time

from PyQt6.QtCore import QThread, QTimer, QSettings, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QSplitter,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
    QPlainTextEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QGroupBox,
    QDateTimeEdit)
from PyQt6.QtCore import Qt, QDateTime
from aura.metadata import __version__
from aura.sdk import AuraClient
from aura.ui.messages import UI_TEXT
from aura.ui.transcript_io import prepare_transcript

def safe_recording_suffix(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", str(value).strip(), flags=re.UNICODE)
    return cleaned.strip("._")[:80] or "record"


def ensure_output_directory_writable(folder: str | Path) -> Path:
    directory = Path(folder).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, probe_name = tempfile.mkstemp(prefix=".aura-write-probe-", dir=directory)
    os.close(descriptor)
    Path(probe_name).unlink()
    return directory


class ServiceWorker(QThread):
    result = pyqtSignal(str, object, object)
    failed = pyqtSignal(str)

    def __init__(self, ssh=None):
        super().__init__()
        self.ssh = ssh
        self.commands = queue.Queue(maxsize=32)
        self.running = True
        self.client = None

    def submit(self, command, args=None):
        self.commands.put_nowait((command, args or {}))

    def stop(self):
        self.running = False
        if self.client:
            self.client.close()
        self.wait()

    def run(self):
        try:
            with AuraClient(ssh=self.ssh) as client:
                self.client = client
                while self.running:
                    try:
                        command, args = self.commands.get(timeout=0.5)
                    except queue.Empty:
                        command, args = "sessions", {}
                    try:
                        if command == "upload":
                            path = client.upload(args["path"])
                            result = client.request("transcribe", {**args, "path": path})
                        elif command == "download":
                            result = str(client.download(args["session_id"], args["format"], args["destination"]))
                        else:
                            if command == "recover" and not client.request("capabilities").get("recover"):
                                raise RuntimeError("服務尚未支援補轉錄；完成活動工作後請重啟服務與應用程式。")
                            result = client.request(command, args)
                        self.result.emit(command, result, args)
                    except Exception as exc:
                        self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


class TranscriptionTab(QWidget):
    def __init__(self, settings=None, strings=UI_TEXT, audit=None):
        super().__init__()
        self.strings, self.audit = strings, audit
        self.current = None
        self.snapshots = {}
        self.editor_edited = False
        self.updating_transcript = False
        self.saved_settings = QSettings("ProjectAURA", "AURA")
        self.worker = None
        self.setObjectName("transcriptionWorkspace")
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.version_banner = QLabel(f"AURA v{__version__}")
        self.version_banner.setObjectName("workspaceStatus")
        header.addWidget(self.version_banner)
        self.host = QLineEdit()
        self.host.setPlaceholderText("本機服務；輸入 SSH 主機別名可連線至遠端")
        connect = QPushButton("連線")
        connect.clicked.connect(self.connect_service)
        self.status_label = QLabel("正在連線至 AURA 服務…")
        header.addWidget(self.status_label, 1)
        header.addWidget(self.host, 1)
        header.addWidget(connect)
        layout.addLayout(header)
        split = QSplitter()
        self.session_list = QListWidget()
        self.session_list.setAccessibleName("錄音工作階段")
        self.session_list.currentItemChanged.connect(self.select_session)
        split.addWidget(self.session_list)
        workspace = QWidget()
        main = QVBoxLayout(workspace)
        controls = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("會議名稱")
        self.combo_source = QComboBox()
        for label, value in (("麥克風", "microphone"), ("系統音訊", "system"), ("系統＋麥克風", "system_microphone")):
            self.combo_source.addItem(label, value)
        self.combo_source.setCurrentIndex(2)
        self.combo_location = QComboBox()
        self.combo_location.addItem("服務主機收音", "server")
        self.combo_location.addItem("這台電腦收音", "client")
        controls.addWidget(self.name_input, 1)
        controls.addWidget(self.combo_location)
        controls.addWidget(self.combo_source)
        main.addLayout(controls)
        actions = QHBoxLayout()
        self.btn_record = QPushButton("開始錄音")
        self.btn_record.setProperty("role", "primary")
        self.btn_record.clicked.connect(self.start_recording_session)
        self.btn_pause = QPushButton("暫停")
        self.btn_pause.clicked.connect(self.pause_resume)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setProperty("role", "danger")
        self.btn_stop.clicked.connect(lambda: self.command("stop"))
        self.btn_import = QPushButton("匯入媒體")
        self.btn_import.clicked.connect(self.import_file)
        self.btn_refine = QPushButton("重新精修")
        self.btn_refine.clicked.connect(lambda: self.command("refine"))
        self.btn_recover = QPushButton("補轉錄缺段")
        self.btn_recover.clicked.connect(lambda: self.command("recover"))
        self.btn_save = QPushButton("儲存編輯")
        self.btn_save.clicked.connect(self.save_editor_transcript)
        self.btn_export = QPushButton("匯出")
        self.btn_export.clicked.connect(self.export)
        for button in (self.btn_record, self.btn_pause, self.btn_stop, self.btn_import, self.btn_refine, self.btn_recover, self.btn_save, self.btn_export):
            actions.addWidget(button)
        main.addLayout(actions)
        self.session_status = QLabel("選取工作階段，或開始新錄音。暫停會同時停止收音與新的辨識工作。")
        self.session_status.setWordWrap(True)
        main.addWidget(self.session_status)
        self.text_area = QPlainTextEdit()
        self.text_area.setAccessibleName("可編輯逐字稿")
        self.text_area.setPlaceholderText("逐字稿會顯示於此；精修結果另存，保留您的編輯。")
        self.text_area.textChanged.connect(self.on_transcript_changed)
        main.addWidget(self.text_area, 1)
        self.runtime_log = QPlainTextEdit()
        self.runtime_log.setReadOnly(True)
        self.runtime_log.setMaximumHeight(120)
        self.runtime_log.setObjectName("runtimeLog")
        main.addWidget(self.runtime_log)
        split.addWidget(workspace)
        split.setSizes([240, 1000])
        layout.addWidget(split, 1)
        advanced = QGroupBox("進階設定")
        form = QFormLayout(advanced)
        self.profile = QComboBox()
        for label, value in (("輕度降噪（預設）", "light"), ("降噪關閉", "off"), ("中度降噪", "medium"),
                             ("遠距說話者：中度降噪與音量支援", "far-speaker"), ("離線救援（匯入專用）", "rescue-offline")):
            self.profile.addItem(label, value)
        form.addRow("音訊設定", self.profile)
        self.asr_model = QComboBox()
        self.asr_model.addItem("Breeze（預設，中文／英文）", "breeze")
        self.asr_model.addItem("Parakeet v2（英文，Linux GPU 服務）", "parakeet-tdt-0.6b-v2")
        self.asr_model.setAccessibleName("ASR 模型")
        form.addRow("ASR 模型", self.asr_model)
        self.language = QComboBox()
        for label, value in (("中文", "zh"), ("英文", "en"), ("自動偵測", None)):
            self.language.addItem(label, value)
        form.addRow("語言", self.language)
        self.hotwords = QPlainTextEdit(str(self.saved_settings.value("hotwords", "")))
        self.hotwords.setMaximumHeight(65)
        form.addRow("專有詞（每行一個）", self.hotwords)
        hotword_import = QPushButton("匯入 UTF-8 專有詞")
        hotword_import.clicked.connect(self.import_hotwords)
        form.addRow(hotword_import)
        self.prompt_input = QLineEdit()
        form.addRow("辨識提示", self.prompt_input)
        self.beam = QSpinBox()
        self.beam.setRange(1, 10)
        self.beam.setValue(5)
        form.addRow("Beam size", self.beam)
        self.punctuation = QCheckBox("還原中文標點")
        self.punctuation.setChecked(True)
        form.addRow(self.punctuation)
        self.breeze_language_index = self.language.currentIndex()
        self.asr_model.currentIndexChanged.connect(self.update_model_controls)
        self.diarization = QCheckBox("匯入／精修時區分說話者")
        form.addRow(self.diarization)
        preferences = QPushButton("儲存為 GUI／CLI 共用預設")
        preferences.clicked.connect(lambda: self.submit("preferences.set", self.options()))
        form.addRow(preferences)
        diagnostics = QPushButton("服務功能檢查")
        diagnostics.clicked.connect(lambda: self.submit("capabilities"))
        form.addRow(diagnostics)
        self.schedule_start = QDateTimeEdit(QDateTime.currentDateTime().addSecs(60))
        self.schedule_start.setCalendarPopup(True)
        form.addRow("排程開始", self.schedule_start)
        self.schedule_end = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3660))
        form.addRow("排程停止", self.schedule_end)
        schedule = QPushButton("建立錄音排程")
        schedule.clicked.connect(self.schedule_recording)
        form.addRow(schedule)
        self.btn_toggle_settings = QPushButton("顯示進階設定")
        self.btn_toggle_settings.setCheckable(True)
        self.btn_toggle_settings.toggled.connect(advanced.setVisible)
        advanced.hide()
        layout.addWidget(self.btn_toggle_settings)
        layout.addWidget(advanced)
        self.connect_service()

    def connect_service(self):
        if self.worker:
            self.worker.stop()
        self.worker = ServiceWorker(self.host.text().strip() or None)
        self.worker.result.connect(self.receive)
        self.worker.failed.connect(self.show_error)
        self.worker.start()
        self.submit("preferences.get")

    def submit(self, command, args=None):
        try:
            self.worker.submit(command, args)
        except queue.Full:
            self.show_error("操作佇列已滿，請等待目前操作完成。")

    def update_model_controls(self):
        parakeet = self.asr_model.currentData() == "parakeet-tdt-0.6b-v2"
        if parakeet:
            if self.language.isEnabled():
                self.breeze_language_index = self.language.currentIndex()
            self.language.setCurrentIndex(self.language.findData("en"))
        else:
            self.language.setCurrentIndex(self.breeze_language_index)
        for widget in (self.language, self.hotwords, self.prompt_input, self.beam, self.punctuation):
            widget.setEnabled(not parakeet)
            widget.setToolTip("Parakeet 使用英文及模型內建標點；提示詞與中文標點設定供 Breeze 使用。" if parakeet else "")

    def options(self):
        words = "\n".join(dict.fromkeys(w.strip() for w in self.hotwords.toPlainText().splitlines() if w.strip()))
        self.saved_settings.setValue("hotwords", words)
        if self.asr_model.currentData() == "parakeet-tdt-0.6b-v2":
            return dict(asr_model=self.asr_model.currentData(), profile=self.profile.currentData(),
                        diarization=self.diarization.isChecked())
        return dict(asr_model="breeze", profile=self.profile.currentData(), language=self.language.currentData(),
                    beam_size=self.beam.value(), prompt=self.prompt_input.text(), hotwords=" ".join(words.splitlines()),
                    punctuation=self.punctuation.isChecked(), diarization=self.diarization.isChecked())

    def start_recording_session(self, *_):
        if self.editor_edited:
            self.show_error("請先儲存逐字稿編輯。")
            return
        self.submit("record", dict(title=self.name_input.text() or "Meeting", source=self.combo_source.currentData(),
            capture_location=self.combo_location.currentData(), options=self.options()))

    def schedule_recording(self):
        self.submit("schedule", dict(title=self.name_input.text() or "Meeting", source=self.combo_source.currentData(),
            capture_location="server", options=self.options(),
            start_at=self.schedule_start.dateTime().toPyDateTime().astimezone().isoformat(),
            stop_at=self.schedule_end.dateTime().toPyDateTime().astimezone().isoformat()))

    def command(self, command):
        if command == "recover" and self.editor_edited:
            self.show_error("請先儲存逐字稿編輯，再補轉錄缺段。")
            return
        if self.current:
            self.submit(command, {"session_id": self.current["id"]})

    def pause_resume(self):
        if self.current:
            self.command("resume" if self.current["state"] == "paused" else "pause")

    def import_file(self):
        if self.editor_edited:
            self.show_error("請先儲存逐字稿編輯。")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "匯入媒體", "", "Audio/video (*)")
        for path in paths:
            self.submit("upload", {"path": path, "title": Path(path).stem, "options": self.options()})

    def import_hotwords(self):
        path, _ = QFileDialog.getOpenFileName(self, "匯入專有詞", "", "Text (*.txt)")
        if path:
            try:
                self.hotwords.setPlainText(Path(path).read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError) as exc:
                self.show_error(str(exc))

    def export(self):
        if not self.current:
            return
        path, selected = QFileDialog.getSaveFileName(self, "匯出", "transcript.txt", "Text (*.txt);;Refined text (*.txt);;Recovered text (*.txt);;JSON (*.json);;WAV (*.wav);;M4A (*.m4a)")
        if path:
            self.submit("download", dict(session_id=self.current["id"], format="refined" if selected.startswith("Refined") else "recovered" if selected.startswith("Recovered") else (Path(path).suffix.lstrip(".") or "txt"), destination=path))

    def on_transcript_changed(self):
        if not self.updating_transcript:
            self.editor_edited = True
            self.btn_save.setText("儲存編輯＊")

    def save_editor_transcript(self):
        if self.current:
            self.submit("edit", dict(session_id=self.current["id"], revision=self.current["revision"], text=self.text_area.toPlainText()))

    def select_session(self, item, previous=None):
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if self.current and sid != self.current["id"] and self.editor_edited:
            self.show_error("請先儲存目前逐字稿的編輯，再切換工作階段。")
            return
        self.current = self.snapshots[sid]
        self.render(self.current)

    def render(self, s):
        state = s["state"]
        self.session_status.setText(f'{s["title"]} · {s["id"]}\n{state} · {s["capture_location"]} / {s["source"]} · {s["options"]["profile"]} · {s["options"].get("asr_model", "breeze")}')
        self.btn_pause.setText("繼續" if state == "paused" else "暫停")
        self.btn_pause.setEnabled(state in ("recording", "paused"))
        self.btn_stop.setEnabled(state in ("starting", "recording", "pausing", "paused", "scheduled"))
        self.btn_recover.setEnabled(state in ("ready", "recoverable", "failed"))
        self.btn_refine.setEnabled(state in ("ready", "recoverable", "failed"))
        if not self.editor_edited and self.text_area.toPlainText() != s["transcript"]:
            self.updating_transcript = True
            self.text_area.setPlainText(s["transcript"])
            self.updating_transcript = False
        gaps = sum(i["status"] == "pending" for i in s.get("asr_issues", []))
        if gaps:
            self.status_label.setText(f"{gaps} 段待補轉錄；音訊持續保存，停止後可補轉錄缺段。")
        if s.get("error"):
            self.status_label.setText(s["error"])

    def receive(self, command, result, args):
        self.status_label.setText("已連線 · 關閉視窗後可由 CLI 接續操作")
        if command == "preferences.get":
            for widget, key in ((self.profile, "profile"), (self.language, "language")):
                if key in result:
                    widget.setCurrentIndex(widget.findData(result[key]))
            if "hotwords" in result:
                self.hotwords.setPlainText(result["hotwords"])
            if "prompt" in result:
                self.prompt_input.setText(result["prompt"])
            if "beam_size" in result:
                self.beam.setValue(result["beam_size"])
            for widget, key in ((self.punctuation, "punctuation"), (self.diarization, "diarization")):
                if key in result:
                    widget.setChecked(result[key])
            self.breeze_language_index = self.language.currentIndex()
            self.asr_model.setCurrentIndex(self.asr_model.findData(result.get("asr_model", "breeze")))
            self.update_model_controls()
        elif command == "capabilities":
            self.runtime_log.appendPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        elif command == "sessions":
            self.snapshots = {s["id"]: s for s in result}
            sid = self.current["id"] if self.current else None
            self.session_list.blockSignals(True)
            self.session_list.clear()
            for s in result:
                item = QListWidgetItem(f'{s["title"]}\n{s["state"]} · {s["id"][:8]}')
                item.setData(Qt.ItemDataRole.UserRole, s["id"])
                self.session_list.addItem(item)
                if sid == s["id"]:
                    self.session_list.setCurrentItem(item)
                    # Keep the editor's base revision while local edits are outstanding.
                    if not self.editor_edited:
                        self.current = s
                    self.render(s)
        elif command in ("record", "schedule", "upload"):
            if not self.editor_edited:
                self.current = result
                self.render(result)
            if command == "record" and result["capture_location"] == "client":
                from aura.cli import start_client_capture
                start_client_capture(result["id"], self.host.text().strip() or None)
        elif command == "edit":
            if self.current and self.current["id"] == result["id"]:
                self.current = result
                if self.text_area.toPlainText() == args["text"]:
                    self.editor_edited = False
                    self.btn_save.setText("儲存編輯")
        elif command == "download":
            self.runtime_log.appendPlainText(f"已匯出：{result}")
        else:
            self.runtime_log.appendPlainText(command)
        self.session_list.blockSignals(False)

    def show_error(self, error):
        self.status_label.setText(error)
        self.runtime_log.appendPlainText(error)

    def stop_threads(self):
        if self.editor_edited and self.current:
            # Preserve an unsent editor draft independently of connection health.
            from aura.sdk import connection_file
            path = connection_file().parent / "drafts" / (self.current["id"] + ".txt")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_text(self.text_area.toPlainText(), encoding="utf-8")
        self.worker.stop()

    def prepare_transcript_input(self, text):
        return prepare_transcript(text, enable_punctuation=False, enable_glossary_correction=False)
