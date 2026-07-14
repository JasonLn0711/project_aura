import gc

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMenu,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
)

from aura.audit import AuditRecorder
from aura.system.runtime_paths import remove_transcript_backup
from aura.ui.messages import UI_TEXT
from aura.ui.splitter_tab import SplitterTab
from aura.ui.transcription_tab import TranscriptionTab


class MainWindow(QMainWindow):
    def __init__(self, strings=UI_TEXT, audit=None):
        super().__init__()
        self.strings = strings
        self.audit = audit if audit is not None else AuditRecorder()
        self.cleanup_completed = False
        self.initUI()
        self.initSystemTray()
        self.audit.record(
            "app.session_started",
            category="app.lifecycle",
            workflow="app",
            details={"audit_enabled": self.audit.enabled},
        )

    def initUI(self):
        self.setWindowTitle(self.strings.window_title)
        self.resize(1280, 820)
        self.setMinimumSize(960, 680)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        self.tab_transcription = TranscriptionTab(audit=self.audit)
        self.tab_splitter = SplitterTab(audit=self.audit)

        self.tabs.addTab(self.tab_transcription, self.strings.tab_transcribing)
        self.tabs.addTab(self.tab_splitter, self.strings.tab_splitting)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.sys_status = QLabel(self.strings.status_idle_gpu)
        self.sys_status.setStyleSheet("padding: 5px; color: #71c9be; font-weight: 600; font-size: 11px;")
        self.statusBar().addWidget(self.sys_status, 1)

        if self.audit.enabled:
            audit_status_text = self.strings.audit_status_local
        elif self.audit.last_error:
            audit_status_text = self.strings.audit_status_unavailable
        else:
            audit_status_text = self.strings.audit_status_off
        self.audit_status = QLabel(audit_status_text)
        self.audit_status.setStyleSheet("padding: 5px; color: #8fa4b5; font-size: 11px;")
        self.statusBar().addPermanentWidget(self.audit_status)

        footer = QLabel(self.strings.footer())
        footer.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        footer.setStyleSheet("padding: 5px; color: #71808e; font-size: 11px;")
        self.statusBar().addPermanentWidget(footer)

    def initSystemTray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
        self.tray_icon.setIcon(icon)

        tray_menu = QMenu()

        show_action = QAction(self.strings.tray_show_main_window, self)
        show_action.triggered.connect(self.show_window)

        quit_action = QAction(self.strings.tray_exit_program, self)
        quit_action.triggered.connect(self.quit_app)

        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)

        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def show_window(self):
        self.show()
        self.activateWindow()
        self.audit.record(
            "ui.window_restored",
            category="ui.navigation",
            actor="user",
            workflow="app",
        )

    def on_tab_changed(self, index):
        tab = "transcription" if index == 0 else "splitter"
        self.audit.record(
            "ui.tab_selected",
            category="ui.navigation",
            actor="user",
            workflow="app",
            details={"tab": tab},
        )

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
                self.audit.record(
                    "ui.window_hidden_to_tray",
                    category="ui.navigation",
                    actor="user",
                    workflow="app",
                )
            else:
                self.show_window()

    def quit_app(self):
        self.perform_cleanup("tray_exit")
        QApplication.quit()

    def perform_cleanup(self, reason="cleanup"):
        if self.cleanup_completed:
            return
        self.audit.record(
            "app.session_ending",
            category="app.lifecycle",
            actor="user",
            workflow="app",
            details={"reason": reason},
        )
        self.tab_transcription.stop_threads()

        t_thread = self.tab_transcription.transcriber_thread
        if hasattr(t_thread, "model") and t_thread.model is not None:
            del t_thread.model
            t_thread.model = None

        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        remove_transcript_backup()
        self.audit.record(
            "app.session_ended",
            category="app.lifecycle",
            workflow="app",
            details={"reason": reason},
        )
        self.cleanup_completed = True

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide()
            self.audit.record(
                "ui.window_hidden_to_tray",
                category="ui.navigation",
                actor="user",
                workflow="app",
            )
            self.tray_icon.showMessage(
                self.strings.tray_message_title,
                self.strings.tray_message_body,
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            event.ignore()
        else:
            self.perform_cleanup("window_close")
            super().closeEvent(event)
