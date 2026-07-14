import os
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from aura.audit import AuditRecorder
from aura.audio.splitter import SmartSplitterThread
from aura.settings import DEFAULT_SETTINGS
from aura.ui.messages import UI_TEXT


class SplitterTab(QWidget):
    def __init__(self, settings=DEFAULT_SETTINGS, strings=UI_TEXT, audit=None):
        super().__init__()
        self.settings = settings
        self.strings = strings
        self.audit = audit if audit is not None else AuditRecorder()
        self.file_path = None
        self.output_dir = None
        self.thread = None
        self.audit_started_perf = None
        self.initUI()

    def initUI(self):
        self.setObjectName("splitterWorkspace")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)

        header = QLabel(self.strings.splitter_header)
        header.setStyleSheet("font-size: 24px; font-weight: 700; color: #e7eef4;")
        layout.addWidget(header)

        desc = QLabel(self.strings.splitter_description)
        desc.setProperty("role", "muted")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        settings_panel = QFrame()
        settings_panel.setObjectName("splitterPanel")
        settings_layout = QHBoxLayout(settings_panel)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.addWidget(QLabel(self.strings.splitter_target_length))
        self.spin_target = QSpinBox()
        self.spin_target.setRange(5, 120)
        self.spin_target.setValue(self.settings.splitter_target_minutes)
        settings_layout.addWidget(self.spin_target)

        settings_layout.addWidget(QLabel(self.strings.splitter_tolerance))
        self.spin_tol = QSpinBox()
        self.spin_tol.setRange(1, 15)
        self.spin_tol.setValue(self.settings.splitter_tolerance_minutes)
        settings_layout.addWidget(self.spin_tol)
        settings_layout.addStretch()
        layout.addWidget(settings_panel)

        workflow_panel = QFrame()
        workflow_panel.setObjectName("splitterPanel")
        btn_layout = QHBoxLayout(workflow_panel)
        btn_layout.setContentsMargins(16, 14, 16, 14)
        btn_layout.setSpacing(10)
        self.btn_select = QPushButton(self.strings.splitter_select_source)
        self.btn_select.setFixedHeight(50)
        self.btn_select.clicked.connect(self.select_file)

        self.btn_outdir = QPushButton(self.strings.splitter_select_output)
        self.btn_outdir.setFixedHeight(50)
        self.btn_outdir.clicked.connect(self.select_outdir)

        self.btn_start = QPushButton(self.strings.splitter_start)
        self.btn_start.setFixedHeight(50)
        self.btn_start.setProperty("role", "primary")
        self.btn_start.clicked.connect(self.start_split)
        self.btn_start.setEnabled(False)

        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(self.btn_outdir)
        btn_layout.addWidget(self.btn_start)
        layout.addWidget(workflow_panel)

        self.lbl_file = QLabel(self.strings.splitter_no_file_selected)
        self.lbl_file.setProperty("role", "muted")
        self.lbl_file.setWordWrap(True)
        layout.addWidget(self.lbl_file)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_area = QTextEdit()
        self.log_area.setObjectName("runtimeLog")
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText(self.strings.splitter_log_placeholder)
        layout.addWidget(self.log_area)

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.strings.splitter_select_audio,
            "",
            self.strings.splitter_media_filter,
        )
        if path:
            self.file_path = path
            self.output_dir = os.path.dirname(path)
            self.update_status()
            self.audit.record(
                "splitter.source_selected",
                category="workflow.splitter",
                actor="user",
                workflow="splitter",
                details={"media_type": os.path.splitext(path)[1].lower() or "unknown"},
            )
        else:
            self.audit.record(
                "splitter.source_selection_cancelled",
                category="workflow.splitter",
                actor="user",
                workflow="splitter",
                outcome="cancelled",
            )

    def select_outdir(self):
        dir_path = QFileDialog.getExistingDirectory(self, self.strings.splitter_select_output_folder)
        if dir_path:
            self.output_dir = dir_path
            self.update_status()
            self.audit.record(
                "splitter.output_selected",
                category="workflow.splitter",
                actor="user",
                workflow="splitter",
            )
        else:
            self.audit.record(
                "splitter.output_selection_cancelled",
                category="workflow.splitter",
                actor="user",
                workflow="splitter",
                outcome="cancelled",
            )

    def update_status(self):
        if self.file_path and self.output_dir:
            file_name = os.path.basename(self.file_path)
            self.lbl_file.setText(self.strings.splitter_status(file_name, self.output_dir))
            self.btn_start.setEnabled(True)

    def start_split(self):
        if not self.file_path or not self.output_dir:
            self.audit.record(
                "splitter.start_rejected",
                category="workflow.splitter",
                actor="user",
                workflow="splitter",
                outcome="rejected",
                severity="warning",
                details={"reason": "source_or_output_missing"},
            )
            return
        self.btn_select.setEnabled(False)
        self.btn_outdir.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_area.clear()
        self.audit_started_perf = time.perf_counter()
        self.audit.record(
            "splitter.started",
            category="workflow.splitter",
            actor="user",
            workflow="splitter",
            details={
                "target_minutes": self.spin_target.value(),
                "tolerance_minutes": self.spin_tol.value(),
            },
        )

        self.thread = SmartSplitterThread(
            self.file_path,
            self.output_dir,
            self.spin_target.value(),
            self.spin_tol.value(),
        )
        self.thread.log_signal.connect(self.append_log)
        self.thread.progress_signal.connect(self.progress_bar.setValue)
        self.thread.error_signal.connect(self.handle_error)
        self.thread.finished_signal.connect(self.process_finished)
        self.thread.start()

    def append_log(self, text):
        self.log_area.append(text)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def handle_error(self, err_msg):
        duration_ms = (
            round((time.perf_counter() - self.audit_started_perf) * 1000, 3)
            if self.audit_started_perf is not None
            else None
        )
        self.audit.record(
            "splitter.failed",
            category="workflow.splitter",
            workflow="splitter",
            outcome="error",
            severity="error",
            details={"error_class": "splitter_error", "duration_ms": duration_ms},
        )
        self.audit_started_perf = None
        QMessageBox.critical(self, self.strings.error_title, self.strings.splitter_error(err_msg))
        self.reset_ui()

    def process_finished(self):
        duration_ms = (
            round((time.perf_counter() - self.audit_started_perf) * 1000, 3)
            if self.audit_started_perf is not None
            else None
        )
        self.audit.record(
            "splitter.completed",
            category="workflow.splitter",
            workflow="splitter",
            details={"duration_ms": duration_ms},
        )
        self.audit_started_perf = None
        self.progress_bar.setValue(100)
        QMessageBox.information(self, self.strings.splitter_completed_title, self.strings.splitter_completed)
        self.reset_ui()

    def reset_ui(self):
        self.btn_select.setEnabled(True)
        self.btn_outdir.setEnabled(True)
        self.btn_start.setEnabled(True)
