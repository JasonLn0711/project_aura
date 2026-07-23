import datetime
import gc
import json
import logging
import os
import re
import tempfile
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTime, QTimer, QUrl, pyqtSlot
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from aura.audit import AuditRecorder, write_audit_report
from aura.asr.threads import FileTranscriberThread, ModelLoaderThread, TranscriberThread
from aura.audio.denoise import DEFAULT_ACTIVE_DENOISE_PRESET, OFF_DENOISE_PRESET, normalize_denoise_preset
from aura.audio.meeting_distance import (
    MEETING_DISTANCE_FAR_SPEAKER,
    MEETING_DISTANCE_NORMAL,
    MEETING_DISTANCE_OFF,
    MEETING_DISTANCE_RESCUE_OFFLINE,
    effective_denoise_preset_for_mode,
    meeting_distance_policy_for,
)
from aura.audio.capture import AudioRecorderThread
from aura.audio.recording_session import write_session_manifest
from aura.audio.export import normalize_wav_to_recording_audio, recording_audio_format_spec
from aura.config import CHUNK_MS, LIVE_CAPTURE_MICROPHONE, LIVE_CAPTURE_SYSTEM, LIVE_CAPTURE_SYSTEM_MICROPHONE
from aura.llm.summary import SummarySettings
from aura.llm.threads import OllamaPullThread, OllamaRuntimeThread, SummaryThread
from aura.review import export_segments
from aura.scheduling import milliseconds_until, next_wall_clock_datetime, stop_datetime_after_start
from aura.settings import DEFAULT_SETTINGS
from aura.system.platform import detect_runtime_platform
from aura.system.runtime_report import (
    build_runtime_report,
    collect_runtime_diagnostics,
    first_launch_checks,
    format_runtime_report,
)
from aura.system.runtime_paths import remove_transcript_backup, transcript_backup_path
from aura.system.update_checker import UpdateCheckerThread
from aura.ui.messages import UI_TEXT
from aura.ui.transcript_io import (
    PreparedTranscript,
    collision_safe_transcript_base_path,
    ensure_transcript_session,
    prepare_transcript,
    split_transcript_sections,
    transcript_artifact_paths,
    write_json_file,
    write_event_log_file,
    write_transcript_artifacts,
    write_transcript_file,
)
from aura.ui.summary_claims_table import SummaryClaimsTable
from aura.ui.transcript_review_table import TranscriptReviewTable
from summary.field_schemas import BASE_MODEL_ID, OLLAMA_MODEL_TAG

logger = logging.getLogger(__name__)


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


class TranscriptionTab(QWidget):
    def __init__(self, settings=DEFAULT_SETTINGS, strings=UI_TEXT, audit=None):
        super().__init__()
        self.settings = settings
        self.strings = strings
        self.audit = audit if audit is not None else AuditRecorder()
        self.recorder_thread = None
        self.file_thread = None
        self.final_recording_thread = None
        self.transcriber_thread = TranscriberThread()
        self.transcriber_thread.text_updated.connect(self.update_log)
        self.transcriber_thread.status_updated.connect(self.update_status_only)
        self.transcriber_thread.telemetry_updated.connect(self.on_live_asr_telemetry)
        self.transcriber_thread.start()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.pending_files = []
        self.model_loader = None
        self.summary_thread = None
        self.ollama_runtime_thread = None
        self.ollama_pull_thread = None
        self.ollama_server_process = None
        self.ollama_server_started_by_aura = False
        self.summary_audit_actor = None
        self.summary_audit_started_perf = None
        self.summary_workflow_busy = False
        self.total_batch_count = 0
        self.update_checker = None
        self.transcript_revision = 0
        self.finalize_recording_pending = False
        self.import_cancel_requested = False
        self.import_summary_pending = False
        self.current_import_metrics = None
        self.current_recording_metrics = None
        self.recording_log_handler = None
        self.recording_log_path = None
        self.current_meeting_id = None
        self.current_summary_session_dir = None
        self.current_review_session_dir = None
        self.current_review_meeting_id = None
        self.current_review_audio_path = None
        self.review_audio_path = None
        self.review_player = None
        self.review_audio_output = None
        self.last_output_folder = None
        self.custom_output_folder = os.path.join(os.getcwd(), "outputs", "transcripts")
        self.scheduled_recording_pending = False
        self.scheduled_start_at = None
        self.scheduled_stop_at = None
        self.scheduled_start_timer = QTimer(self)
        self.scheduled_start_timer.setSingleShot(True)
        self.scheduled_start_timer.timeout.connect(self.start_scheduled_recording)
        self.scheduled_stop_timer = QTimer(self)
        self.scheduled_stop_timer.setSingleShot(True)
        self.scheduled_stop_timer.timeout.connect(self.stop_scheduled_recording)
        self.asr_model_status = "not loaded"
        self.latest_runtime_report = ""
        self.first_launch_guidance = {}

        self.current_folder = os.getcwd()
        self.current_filename = "transcript"
        self.initUI()

    def initUI(self):
        self.setObjectName("transcriptionWorkspace")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(12)

        workspace_header = QFrame()
        workspace_header.setObjectName("workspaceHeader")
        header_layout = QVBoxLayout(workspace_header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(8)

        status_layout = QHBoxLayout()
        self.status_label = QLabel(self.strings.status_waiting_gpu)
        self.status_label.setObjectName("workspaceStatus")
        self.top_gpu_label = QLabel(self.strings.top_gpu_status.format(status="checking"))
        self.top_model_label = QLabel(self.strings.top_model_status.format(status=self.asr_model_status))
        self.top_device_label = QLabel(self.strings.top_device_status.format(status="not selected"))
        for status_chip in (self.top_gpu_label, self.top_model_label, self.top_device_label):
            status_chip.setObjectName("statusChip")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(self.strings.recording_suffix_placeholder)
        self.name_input.setMinimumWidth(220)
        status_layout.addWidget(self.status_label, stretch=1)
        status_layout.addWidget(self.name_input)
        header_layout.addLayout(status_layout)

        readiness_layout = QHBoxLayout()
        readiness_layout.setSpacing(8)
        readiness_layout.addWidget(self.top_gpu_label)
        readiness_layout.addWidget(self.top_model_label)
        readiness_layout.addWidget(self.top_device_label)
        readiness_layout.addStretch()
        header_layout.addLayout(readiness_layout)
        layout.addWidget(workspace_header)

        self.btn_toggle_settings = QPushButton(self.strings.show_advanced_settings)
        self.btn_toggle_settings.setCheckable(True)
        self.btn_toggle_settings.setProperty("role", "quiet")
        self.btn_toggle_settings.clicked.connect(self.toggle_settings)

        self.settings_container = QWidget()
        settings_vbox = QVBoxLayout(self.settings_container)
        settings_vbox.setContentsMargins(0, 8, 4, 8)
        settings_vbox.setSpacing(10)

        meeting_distance_layout = QHBoxLayout()
        meeting_distance_layout.addWidget(QLabel(self.strings.meeting_distance_mode_label))
        self.combo_meeting_distance = QComboBox()
        self.combo_meeting_distance.setToolTip(self.strings.meeting_distance_tooltip)
        self.combo_meeting_distance.addItem(self.strings.meeting_distance_off, MEETING_DISTANCE_OFF)
        self.combo_meeting_distance.addItem(self.strings.meeting_distance_normal, MEETING_DISTANCE_NORMAL)
        self.combo_meeting_distance.addItem(self.strings.meeting_distance_far_speaker, MEETING_DISTANCE_FAR_SPEAKER)
        self.combo_meeting_distance.addItem(
            self.strings.meeting_distance_rescue_offline,
            MEETING_DISTANCE_RESCUE_OFFLINE,
        )
        meeting_distance_index = self.combo_meeting_distance.findData(self.settings.meeting_distance_mode)
        self.combo_meeting_distance.setCurrentIndex(meeting_distance_index if meeting_distance_index >= 0 else 0)
        meeting_distance_layout.addWidget(self.combo_meeting_distance)
        meeting_distance_layout.addStretch()
        settings_vbox.addLayout(meeting_distance_layout)

        denoise_layout = QHBoxLayout()
        denoise_layout.addWidget(QLabel(self.strings.denoise_mode_label))
        self.combo_denoise = QComboBox()
        self.combo_denoise.setToolTip(self.strings.denoise_tooltip)
        self.combo_denoise.addItem(self.strings.denoise_off, OFF_DENOISE_PRESET)
        self.combo_denoise.addItem(self.strings.denoise_light, DEFAULT_ACTIVE_DENOISE_PRESET)
        self.combo_denoise.addItem(self.strings.denoise_medium, "medium")
        denoise_preset = normalize_denoise_preset(self.settings.denoise_enabled, self.settings.denoise_preset)
        denoise_index = self.combo_denoise.findData(denoise_preset)
        self.combo_denoise.setCurrentIndex(denoise_index if denoise_index >= 0 else 0)
        denoise_layout.addWidget(self.combo_denoise)
        denoise_layout.addStretch()
        settings_vbox.addLayout(denoise_layout)

        speaker_layout = QVBoxLayout()
        self.check_speaker_diarization = QCheckBox(self.strings.speaker_diarization_label)
        self.check_speaker_diarization.setToolTip(self.strings.speaker_diarization_tooltip)
        self.check_speaker_diarization.setChecked(self.settings.speaker_diarization_enabled)
        self.check_speaker_diarization.toggled.connect(self.update_speaker_controls)
        speaker_layout.addWidget(self.check_speaker_diarization)

        speaker_range_layout = QHBoxLayout()
        speaker_range_layout.addWidget(QLabel(self.strings.speaker_min_label))
        self.spin_min_speakers = QSpinBox()
        self.spin_min_speakers.setRange(1, 20)
        self.spin_min_speakers.setValue(self.settings.speaker_min_speakers)
        speaker_range_layout.addWidget(self.spin_min_speakers)

        speaker_range_layout.addWidget(QLabel(self.strings.speaker_max_label))
        self.spin_max_speakers = QSpinBox()
        self.spin_max_speakers.setRange(1, 20)
        self.spin_max_speakers.setValue(self.settings.speaker_max_speakers)
        speaker_range_layout.addWidget(self.spin_max_speakers)
        speaker_range_layout.addStretch()
        speaker_layout.addLayout(speaker_range_layout)
        settings_vbox.addLayout(speaker_layout)
        self.update_speaker_controls(self.check_speaker_diarization.isChecked())

        capture_layout = QHBoxLayout()
        capture_layout.addWidget(QLabel(self.strings.live_capture_source_label))
        self.combo_live_capture = QComboBox()
        self.combo_live_capture.setToolTip(self.strings.live_capture_source_tooltip)
        self.combo_live_capture.addItem(self.strings.live_capture_system_microphone, LIVE_CAPTURE_SYSTEM_MICROPHONE)
        self.combo_live_capture.addItem(self.strings.live_capture_system, LIVE_CAPTURE_SYSTEM)
        self.combo_live_capture.addItem(self.strings.live_capture_microphone, LIVE_CAPTURE_MICROPHONE)
        capture_index = self.combo_live_capture.findData(self.settings.live_capture_source)
        self.combo_live_capture.setCurrentIndex(capture_index if capture_index >= 0 else 0)
        self.combo_live_capture.currentIndexChanged.connect(self.update_top_active_device)
        self.combo_live_capture.currentIndexChanged.connect(self.update_capture_guidance)
        capture_layout.addWidget(self.combo_live_capture)
        capture_layout.addStretch()
        settings_vbox.addLayout(capture_layout)
        self.capture_guidance_label = QLabel()
        self.capture_guidance_label.setWordWrap(True)
        self.capture_guidance_label.setStyleSheet("color: #d7a65b; font-size: 12px;")
        settings_vbox.addWidget(self.capture_guidance_label)
        self.update_capture_guidance()

        schedule_layout = QVBoxLayout()
        schedule_start_layout = QHBoxLayout()
        self.check_schedule_recording = QCheckBox(self.strings.schedule_recording_label)
        self.check_schedule_recording.setToolTip(self.strings.schedule_recording_tooltip)
        self.check_schedule_recording.toggled.connect(self.update_schedule_controls)
        self.check_schedule_recording.toggled.connect(self.update_record_button_label)
        schedule_start_layout.addWidget(self.check_schedule_recording)

        schedule_start_layout.addWidget(QLabel(self.strings.schedule_start_time_label))
        self.time_schedule_start = QTimeEdit()
        self.time_schedule_start.setDisplayFormat("HH:mm")
        self.time_schedule_start.setTime(QTime.currentTime().addSecs(300))
        schedule_start_layout.addWidget(self.time_schedule_start)
        schedule_start_layout.addStretch()
        schedule_layout.addLayout(schedule_start_layout)

        schedule_stop_layout = QHBoxLayout()
        self.check_schedule_auto_stop = QCheckBox(self.strings.schedule_auto_stop_label)
        self.check_schedule_auto_stop.setToolTip(self.strings.schedule_stop_tooltip)
        self.check_schedule_auto_stop.toggled.connect(self.update_schedule_controls)
        schedule_stop_layout.addWidget(self.check_schedule_auto_stop)

        self.time_schedule_end = QTimeEdit()
        self.time_schedule_end.setDisplayFormat("HH:mm")
        self.time_schedule_end.setTime(QTime.currentTime().addSecs(3600))
        schedule_stop_layout.addWidget(self.time_schedule_end)
        schedule_stop_layout.addStretch()
        schedule_layout.addLayout(schedule_stop_layout)
        settings_vbox.addLayout(schedule_layout)

        summary_layout = QHBoxLayout()
        self.check_llm_summary = QCheckBox(self.strings.llm_summary_label)
        self.check_llm_summary.setToolTip(self.strings.llm_summary_tooltip)
        self.check_llm_summary.setChecked(self.settings.llm_summary_enabled)
        summary_layout.addWidget(self.check_llm_summary)
        summary_layout.addStretch()
        settings_vbox.addLayout(summary_layout)

        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel(self.strings.output_policy_label))
        self.combo_output_policy = QComboBox()
        self.combo_output_policy.setToolTip(self.strings.output_policy_tooltip)
        self.combo_output_policy.addItem(self.strings.output_policy_same_folder, "same")
        self.combo_output_policy.addItem(self.strings.output_policy_session_folder, "session")
        self.combo_output_policy.addItem(self.strings.output_policy_custom_folder, "custom")
        self.combo_output_policy.currentIndexChanged.connect(self.update_output_folder_controls)
        output_layout.addWidget(self.combo_output_policy)
        self.btn_select_output_folder = QPushButton(self.strings.select_output_folder)
        self.btn_select_output_folder.clicked.connect(self.select_output_folder)
        output_layout.addWidget(self.btn_select_output_folder)
        self.output_folder_label = QLabel()
        self.output_folder_label.setProperty("role", "muted")
        settings_vbox.addLayout(output_layout)
        self.output_folder_label.setWordWrap(True)
        settings_vbox.addWidget(self.output_folder_label)
        self.update_output_folder_controls()

        recording_audio_layout = QHBoxLayout()
        recording_audio_layout.addWidget(QLabel(self.strings.recording_audio_format_label))
        self.combo_recording_audio_format = QComboBox()
        self.combo_recording_audio_format.setToolTip(self.strings.recording_audio_format_tooltip)
        self.combo_recording_audio_format.addItem(self.strings.recording_audio_m4a, "m4a")
        self.combo_recording_audio_format.addItem(self.strings.recording_audio_mp3, "mp3")
        recording_audio_index = self.combo_recording_audio_format.findData(self.settings.recording_audio_format)
        self.combo_recording_audio_format.setCurrentIndex(recording_audio_index if recording_audio_index >= 0 else 0)
        recording_audio_layout.addWidget(self.combo_recording_audio_format)
        recording_audio_layout.addStretch()
        settings_vbox.addLayout(recording_audio_layout)

        norm_layout = QHBoxLayout()
        norm_layout.addWidget(QLabel(self.strings.target_volume_label))
        self.spin_norm = QSpinBox()
        self.spin_norm.setRange(-40, -5)
        self.spin_norm.setValue(int(self.settings.target_dbfs))
        norm_layout.addWidget(self.spin_norm)
        norm_layout.addStretch()
        settings_vbox.addLayout(norm_layout)

        beam_layout = QHBoxLayout()
        beam_layout.addWidget(QLabel(self.strings.beam_size_label))
        self.spin_beam = QSpinBox()
        self.spin_beam.setRange(1, 15)
        self.spin_beam.setValue(self.settings.beam_size)
        beam_layout.addWidget(self.spin_beam)
        beam_layout.addStretch()
        settings_vbox.addLayout(beam_layout)

        prompt_layout = QVBoxLayout()
        prompt_layout.addWidget(QLabel(self.strings.initial_prompt_label))
        self.prompt_input = QLineEdit()
        self.prompt_input.setText(self.settings.file_initial_prompt or "")
        prompt_layout.addWidget(self.prompt_input)
        settings_vbox.addLayout(prompt_layout)

        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel(self.strings.language_label))
        self.combo_lang = QComboBox()
        self.combo_lang.addItem(self.strings.language_auto, None)
        self.combo_lang.addItem(self.strings.language_zh, "zh")
        self.combo_lang.addItem(self.strings.language_en, "en")
        self.combo_lang.addItem(self.strings.language_ja, "ja")
        lang_index = self.combo_lang.findData(self.settings.language)
        self.combo_lang.setCurrentIndex(lang_index if lang_index >= 0 else 0)
        lang_layout.addWidget(self.combo_lang)
        lang_layout.addStretch()
        settings_vbox.addLayout(lang_layout)

        model_settings_layout = QHBoxLayout()
        model_settings_layout.addWidget(QLabel(self.strings.compute_precision_label))
        self.combo_compute = QComboBox()
        self.combo_compute.addItem(self.strings.compute_float16, "float16")
        self.combo_compute.addItem(self.strings.compute_int8, "int8")
        self.combo_compute.addItem(self.strings.compute_float32, "float32")
        compute_index = self.combo_compute.findData(self.settings.compute_type)
        self.combo_compute.setCurrentIndex(compute_index if compute_index >= 0 else 0)
        model_settings_layout.addWidget(self.combo_compute)

        self.btn_reload_model = QPushButton(self.strings.reload_model)
        self.btn_reload_model.setProperty("role", "quiet")
        self.btn_reload_model.clicked.connect(self.apply_model_settings)
        model_settings_layout.addWidget(self.btn_reload_model)

        model_settings_layout.addStretch()
        settings_vbox.addLayout(model_settings_layout)

        diagnostics_layout = QVBoxLayout()
        diagnostics_layout.addWidget(QLabel(self.strings.runtime_diagnostics_title))
        self.runtime_gpu_label = QLabel(self.strings.runtime_gpu_status.format(status="checking"))
        self.runtime_cuda_label = QLabel(self.strings.runtime_cuda_status.format(status="checking"))
        self.runtime_model_label = QLabel(self.strings.runtime_model_status.format(status=self.asr_model_status))
        self.runtime_audio_label = QLabel(self.strings.runtime_audio_status.format(status="checking"))
        self.runtime_output_label = QLabel(self.strings.runtime_output_status.format(status="checking"))
        diagnostics_layout.addWidget(self.runtime_gpu_label)
        diagnostics_layout.addWidget(self.runtime_cuda_label)
        diagnostics_layout.addWidget(self.runtime_model_label)
        diagnostics_layout.addWidget(self.runtime_audio_label)
        diagnostics_layout.addWidget(self.runtime_output_label)

        first_launch_title = QLabel(self.strings.first_launch_title)
        first_launch_title.setProperty("role", "sectionTitle")
        diagnostics_layout.addWidget(first_launch_title)
        self.first_launch_check_labels = {}
        self.first_launch_fix_buttons = {}
        self.first_launch_action_buttons = {}
        for key, label in (
            ("gpu", "GPU Ready"),
            ("cuda", "CUDA Ready"),
            ("ffmpeg", "FFmpeg Ready"),
            ("microphone", "Microphone Ready"),
            ("output", "Output Folder"),
            ("disk_space", "Output Disk Space"),
            ("asr_model", "ASR Model Load"),
            ("ollama_command", "Ollama Command"),
            ("ollama_server", "Ollama Local Server"),
            ("ollama_model", "Ollama Summary Model"),
        ):
            row = QHBoxLayout()
            status_label = QLabel(self.strings.first_launch_status.format(label=label, status="checking"))
            fix_button = QPushButton(self.strings.first_launch_fix_guide)
            fix_button.setEnabled(False)
            fix_button.clicked.connect(lambda _checked=False, check_key=key: self.show_first_launch_fix(check_key))
            row.addWidget(status_label, stretch=2)
            row.addWidget(fix_button, stretch=0)
            diagnostics_layout.addLayout(row)
            self.first_launch_check_labels[key] = status_label
            self.first_launch_fix_buttons[key] = fix_button
            self.first_launch_action_buttons[key] = (fix_button,)

        diagnostics_buttons = QHBoxLayout()
        self.btn_refresh_runtime = QPushButton(self.strings.runtime_refresh)
        self.btn_refresh_runtime.clicked.connect(self.refresh_runtime_diagnostics)
        self.btn_copy_runtime_report = QPushButton(self.strings.runtime_copy_report)
        self.btn_copy_runtime_report.clicked.connect(self.copy_runtime_report)
        self.btn_open_setup_folder = QPushButton(self.strings.first_launch_open_setup)
        self.btn_open_setup_folder.clicked.connect(self.open_setup_folder)
        diagnostics_buttons.addWidget(self.btn_refresh_runtime)
        diagnostics_buttons.addWidget(self.btn_copy_runtime_report)
        diagnostics_buttons.addWidget(self.btn_open_setup_folder)
        diagnostics_buttons.addStretch()
        diagnostics_layout.addLayout(diagnostics_buttons)
        settings_vbox.addLayout(diagnostics_layout)

        audit_title = QLabel(self.strings.audit_trail_title)
        audit_title.setProperty("role", "sectionTitle")
        settings_vbox.addWidget(audit_title)
        audit_scope = QLabel(self.strings.audit_local_scope)
        audit_scope.setWordWrap(True)
        audit_scope.setProperty("role", "muted")
        settings_vbox.addWidget(audit_scope)
        audit_buttons = QHBoxLayout()
        self.btn_open_audit_folder = QPushButton(self.strings.audit_open_folder)
        self.btn_open_audit_folder.clicked.connect(self.open_audit_folder)
        self.btn_generate_audit_report = QPushButton(self.strings.audit_generate_report)
        self.btn_generate_audit_report.clicked.connect(self.generate_audit_report)
        audit_buttons.addWidget(self.btn_open_audit_folder)
        audit_buttons.addWidget(self.btn_generate_audit_report)
        audit_buttons.addStretch()
        settings_vbox.addLayout(audit_buttons)

        for combo in (
            self.combo_meeting_distance,
            self.combo_denoise,
            self.combo_live_capture,
            self.combo_output_policy,
            self.combo_recording_audio_format,
            self.combo_lang,
            self.combo_compute,
        ):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName("settingsScroll")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setWidget(self.settings_container)
        self.settings_scroll.setVisible(False)

        self.batch_progress = QProgressBar()
        self.batch_progress.setVisible(False)

        self.plot_widget = pg.PlotWidget(title=self.strings.live_waveform_title)
        self.plot_widget.setYRange(-30000, 30000)
        self.plot_widget.setMaximumHeight(155)
        self.plot_widget.setBackground("#0b1117")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.12)
        self.plot_data = np.zeros(4000)
        self.curve = self.plot_widget.plot(self.plot_data, pen=pg.mkPen("#48c7b8", width=1))

        self.text_area = TranscriptReviewTable()
        self.text_area.setObjectName("transcriptArea")
        self.text_area.setReadOnly(False)
        self.text_area.setFontPointSize(12)
        self.text_area.setPlaceholderText(self.strings.transcript_placeholder)
        self.text_area.review_changed.connect(self.on_review_changed)
        self.text_area.seek_requested.connect(self.play_review_segment)

        self.btn_record = QPushButton(self.strings.start_recording)
        self.btn_record.clicked.connect(self.toggle_record)
        self.btn_record.setFixedHeight(50)
        self.btn_record.setProperty("role", "primary")

        self.check_recording_consent = QCheckBox(self.strings.recording_consent_label)
        self.check_recording_consent.setToolTip(self.strings.recording_consent_tooltip)
        self.check_recording_consent.setAccessibleName(self.strings.recording_consent_label)
        self.update_schedule_controls()

        self.btn_import = QPushButton(self.strings.import_media)
        self.btn_import.setToolTip(self.strings.import_media_tooltip)
        self.btn_import.clicked.connect(self.import_file)
        self.btn_import.setFixedHeight(50)

        self.btn_cancel_import = QPushButton(self.strings.cancel_import)
        self.btn_cancel_import.clicked.connect(self.cancel_import)
        self.btn_cancel_import.setFixedHeight(50)
        self.btn_cancel_import.setVisible(False)
        self.btn_cancel_import.setProperty("role", "danger")

        self.btn_open_output_folder = QPushButton(self.strings.open_output_folder)
        self.btn_open_output_folder.clicked.connect(self.open_last_output_folder)
        self.btn_open_output_folder.setFixedHeight(50)
        self.btn_open_output_folder.setVisible(False)

        self.btn_summary = QPushButton(self.strings.llm_summary_button)
        self.btn_summary.clicked.connect(self.summarize_current_transcript)
        self.btn_summary.setFixedHeight(50)
        self.btn_summary.setProperty("role", "primary")

        self.btn_split_workspace = QPushButton(self.strings.open_split_workspace)
        self.btn_split_workspace.clicked.connect(self.open_split_workspace)
        self.btn_split_workspace.setFixedHeight(42)

        self.batch_hint = QLabel(self.strings.batch_hint)
        self.batch_hint.setWordWrap(True)
        self.batch_hint.setProperty("role", "muted")

        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(8)

        workflow_panel = QFrame()
        workflow_panel.setObjectName("sidePanel")
        workflow_panel.setMinimumWidth(180)
        workflow_layout = QVBoxLayout(workflow_panel)
        workflow_layout.setContentsMargins(14, 14, 14, 16)
        workflow_layout.setSpacing(10)
        workflow_title = QLabel(self.strings.workstation_workflows_title)
        workflow_title.setProperty("role", "sectionTitle")
        workflow_layout.addWidget(workflow_title)
        workflow_layout.addWidget(self.check_recording_consent)
        workflow_layout.addWidget(self.btn_record)
        workflow_layout.addWidget(self.btn_import)
        workflow_layout.addWidget(self.btn_cancel_import)
        workflow_layout.addWidget(self.btn_split_workspace)
        workflow_layout.addStretch()

        transcript_panel = QFrame()
        transcript_panel.setObjectName("mainPanel")
        transcript_panel.setMinimumWidth(420)
        transcript_layout = QVBoxLayout(transcript_panel)
        transcript_layout.setContentsMargins(14, 14, 14, 14)
        transcript_layout.setSpacing(10)
        transcript_title = QLabel(self.strings.transcript_workspace_title)
        transcript_title.setProperty("role", "sectionTitle")
        transcript_layout.addWidget(transcript_title)
        transcript_layout.addWidget(self.batch_progress)
        transcript_layout.addWidget(self.plot_widget)
        transcript_layout.addWidget(self.text_area, stretch=1)
        review_actions = QHBoxLayout()
        self.btn_play_segment = QPushButton("播放選取片段")
        self.btn_play_segment.setAccessibleName("播放選取的逐字稿來源音訊")
        self.btn_play_segment.clicked.connect(self.play_selected_segment)
        self.btn_confirm_segment = QPushButton("確認選取片段")
        self.btn_confirm_segment.clicked.connect(self.confirm_selected_segment)
        self.btn_next_review = QPushButton("下一個待覆核")
        self.btn_next_review.clicked.connect(self.select_next_pending_segment)
        self.btn_rename_speaker = QPushButton("套用本場講者名稱")
        self.btn_rename_speaker.clicked.connect(self.rename_selected_speaker)
        self.btn_export_review = QPushButton("匯出覆核結果")
        self.btn_export_review.clicked.connect(self.export_current_review)
        review_actions.addWidget(self.btn_play_segment)
        review_actions.addWidget(self.btn_confirm_segment)
        review_actions.addWidget(self.btn_next_review)
        review_actions.addWidget(self.btn_rename_speaker)
        review_actions.addWidget(self.btn_export_review)
        review_actions.addStretch()
        transcript_layout.addLayout(review_actions)
        transcript_layout.addWidget(self.batch_hint)

        artifact_panel = QFrame()
        artifact_panel.setObjectName("sidePanel")
        artifact_panel.setMinimumWidth(270)
        artifact_layout = QVBoxLayout(artifact_panel)
        artifact_layout.setContentsMargins(14, 14, 14, 16)
        artifact_layout.setSpacing(10)
        artifact_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        artifact_title = QLabel(self.strings.artifact_panel_title)
        artifact_title.setProperty("role", "sectionTitle")
        artifact_layout.addWidget(artifact_title)
        artifact_layout.addWidget(self.btn_open_output_folder)
        artifact_layout.addWidget(self.btn_summary)
        self.summary_claims = SummaryClaimsTable()
        self.summary_claims.setMinimumHeight(180)
        self.summary_claims.setVisible(False)
        self.summary_claims.source_requested.connect(self.open_claim_source)
        artifact_layout.addWidget(self.summary_claims)
        claim_actions = QHBoxLayout()
        self.btn_confirm_claim = QPushButton("確認主張")
        self.btn_confirm_claim.clicked.connect(
            lambda: self.review_selected_claim("confirmed")
        )
        self.btn_reject_claim = QPushButton("退回主張")
        self.btn_reject_claim.clicked.connect(
            lambda: self.review_selected_claim("rejected")
        )
        self.btn_edit_claim = QPushButton("編輯主張")
        self.btn_edit_claim.clicked.connect(self.edit_selected_claim)
        self.btn_confirm_claim.setVisible(False)
        self.btn_reject_claim.setVisible(False)
        self.btn_edit_claim.setVisible(False)
        claim_actions.addWidget(self.btn_confirm_claim)
        claim_actions.addWidget(self.btn_edit_claim)
        claim_actions.addWidget(self.btn_reject_claim)
        artifact_layout.addLayout(claim_actions)
        self.artifact_hint = QLabel(self.strings.artifact_empty_hint)
        self.artifact_hint.setWordWrap(True)
        self.artifact_hint.setProperty("role", "muted")
        artifact_layout.addWidget(self.artifact_hint)
        artifact_layout.addWidget(self.btn_toggle_settings)
        artifact_layout.addWidget(self.settings_scroll, stretch=1)
        artifact_layout.addStretch()

        self.body_splitter.addWidget(workflow_panel)
        self.body_splitter.addWidget(transcript_panel)
        self.body_splitter.addWidget(artifact_panel)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setStretchFactor(2, 0)
        self.body_splitter.setSizes([210, 680, 340])
        layout.addWidget(self.body_splitter, stretch=1)

        runtime_header = QHBoxLayout()
        runtime_title = QLabel(self.strings.runtime_log_title)
        runtime_title.setProperty("role", "sectionTitle")
        self.btn_toggle_runtime_log = QPushButton(self.strings.show_runtime_log)
        self.btn_toggle_runtime_log.setCheckable(True)
        self.btn_toggle_runtime_log.setProperty("role", "quiet")
        self.btn_toggle_runtime_log.clicked.connect(self.toggle_runtime_log)
        runtime_header.addWidget(runtime_title)
        runtime_header.addStretch()
        runtime_header.addWidget(self.btn_toggle_runtime_log)
        layout.addLayout(runtime_header)
        self.runtime_log = QTextEdit()
        self.runtime_log.setObjectName("runtimeLog")
        self.runtime_log.setReadOnly(True)
        self.runtime_log.setFixedHeight(110)
        self.runtime_log.setVisible(False)
        layout.addWidget(self.runtime_log)

        self.update_summary_button_state()
        self.apply_model_settings()
        self.update_top_active_device()
        QTimer.singleShot(0, self.refresh_runtime_diagnostics)
        self.check_for_updates()

    def check_for_updates(self):
        self.update_checker = UpdateCheckerThread()
        self.update_checker.found_update.connect(self.show_update_dialog)
        self.update_checker.start()

    def show_update_dialog(self, version, url):
        reply = QMessageBox.question(
            self,
            self.strings.new_version_found,
            self.strings.update_found(version),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            webbrowser.open(url)

    def toggle_settings(self):
        visible = self.btn_toggle_settings.isChecked()
        self.btn_toggle_settings.setText(
            self.strings.hide_advanced_settings if visible else self.strings.show_advanced_settings
        )
        self.settings_scroll.setVisible(visible)
        self.body_splitter.setSizes([180, 460, 590] if visible else [210, 680, 340])
        self.audit.record(
            "ui.settings_toggled",
            category="ui.interaction",
            actor="user",
            workflow="app",
            details={"visible": visible},
        )

    def toggle_runtime_log(self):
        visible = self.btn_toggle_runtime_log.isChecked()
        self.btn_toggle_runtime_log.setText(
            self.strings.hide_runtime_log if visible else self.strings.show_runtime_log
        )
        self.runtime_log.setVisible(visible)
        self.audit.record(
            "ui.activity_log_toggled",
            category="ui.interaction",
            actor="user",
            workflow="app",
            details={"visible": visible},
        )

    def open_audit_folder(self):
        try:
            self.audit.root.mkdir(parents=True, exist_ok=True)
            webbrowser.open(self.audit.root.resolve().as_uri())
        except OSError:
            self.audit.record(
                "audit.folder_opened",
                category="audit.access",
                actor="user",
                workflow="audit",
                outcome="error",
                severity="error",
                details={"error_class": "OSError"},
            )
            self.status_label.setText(self.strings.audit_report_failed)
            return
        self.audit.record(
            "audit.folder_opened",
            category="audit.access",
            actor="user",
            workflow="audit",
        )

    def generate_audit_report(self):
        try:
            path, report = write_audit_report(
                self.audit.root,
                active_session_id=self.audit.session_id,
            )
        except OSError:
            self.audit.record(
                "audit.report_generated",
                category="audit.reporting",
                actor="user",
                workflow="audit",
                outcome="error",
                severity="error",
                details={"error_class": "OSError"},
            )
            self.status_label.setText(self.strings.audit_report_failed)
            return
        self.audit.record(
            "audit.report_generated",
            category="audit.reporting",
            actor="user",
            workflow="audit",
            details={
                "event_count": report["event_count"],
                "anomaly_count": len(report["anomalies"]),
            },
        )
        self.status_label.setText(self.strings.audit_report_ready_message(str(path)))

    def timestamp_now(self) -> str:
        return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    def selected_output_policy(self) -> str:
        if not hasattr(self, "combo_output_policy"):
            return "same"
        return self.combo_output_policy.currentData() or "same"

    def selected_recording_audio_format(self) -> str:
        if not hasattr(self, "combo_recording_audio_format"):
            return self.settings.recording_audio_format
        return self.combo_recording_audio_format.currentData() or "m4a"

    def session_output_folder(self) -> str:
        return os.path.join(os.getcwd(), "outputs", "transcripts")

    def resolved_output_folder(self, default_folder: str) -> str:
        policy = self.selected_output_policy()
        if policy == "session":
            return self.session_output_folder()
        if policy == "custom":
            return self.custom_output_folder
        return default_folder

    def transcript_base_path(self, default_folder: str, base_name: str) -> str:
        return os.path.join(self.resolved_output_folder(default_folder), base_name)

    def update_output_folder_controls(self):
        policy = self.selected_output_policy()
        custom_selected = policy == "custom"
        self.btn_select_output_folder.setEnabled(custom_selected)
        if policy == "session":
            folder = self.session_output_folder()
        elif policy == "custom":
            folder = self.custom_output_folder
        else:
            folder = self.current_folder
        self.output_folder_label.setText(self.strings.output_folder_selected.format(folder=folder))

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.strings.select_output_folder, self.custom_output_folder)
        if folder:
            self.custom_output_folder = folder
            self.update_output_folder_controls()
            self.audit.record(
                "output.custom_folder_selected",
                category="ui.output",
                actor="user",
                workflow="app",
            )

    def remember_output_folder(self, folder: str | Path):
        self.last_output_folder = str(Path(folder).resolve())
        self.btn_open_output_folder.setVisible(True)
        self.btn_open_output_folder.setEnabled(True)
        self.artifact_hint.setVisible(False)

    def open_last_output_folder(self):
        if not self.last_output_folder:
            self.status_label.setText(self.strings.output_folder_unavailable)
            self.audit.record(
                "output.folder_open_rejected",
                category="ui.output",
                actor="user",
                workflow="app",
                outcome="rejected",
                severity="warning",
                details={"reason": "not_available"},
            )
            return
        folder = Path(self.last_output_folder)
        if not folder.exists():
            self.status_label.setText(self.strings.output_folder_unavailable)
            self.audit.record(
                "output.folder_open_rejected",
                category="ui.output",
                actor="user",
                workflow="app",
                outcome="rejected",
                severity="warning",
                details={"reason": "missing"},
            )
            return
        webbrowser.open(folder.as_uri())
        self.audit.record(
            "output.folder_opened",
            category="ui.output",
            actor="user",
            workflow="app",
        )

    def new_metrics(self, workflow: str, source_path: str | None, base_path: str) -> dict:
        return {
            "workflow": workflow,
            "source_path": source_path,
            "base_path": str(base_path),
            "output_policy": self.selected_output_policy(),
            "started_at": self.timestamp_now(),
            "_started_perf": time.perf_counter(),
            "stage_durations_seconds": {},
            "status_events": [],
        }

    def finish_metrics(self, metrics: dict | None):
        if not metrics:
            return None
        metrics["finished_at"] = self.timestamp_now()
        started = metrics.get("_started_perf")
        if started is not None:
            metrics["total_seconds"] = round(time.perf_counter() - started, 3)
        return metrics

    def add_stage_duration(self, metrics: dict | None, stage: str, started_perf: float | None):
        if metrics is None or started_perf is None:
            return
        metrics.setdefault("stage_durations_seconds", {})[stage] = round(time.perf_counter() - started_perf, 3)

    def recording_log_active(self) -> bool:
        return self.current_recording_metrics is not None

    def append_recording_event(self, category: str, message: str, **fields):
        if not self.recording_log_active():
            return
        metrics = self.current_recording_metrics
        event = {
            "timestamp": self.timestamp_now(),
            "category": category,
            "message": str(message),
        }
        event.update(fields)
        metrics.setdefault("status_events", []).append(event)

    def append_event_to_metrics(self, metrics: dict | None, category: str, message: str, **fields):
        if metrics is None:
            return
        event = {
            "timestamp": self.timestamp_now(),
            "category": category,
            "message": str(message),
        }
        event.update(fields)
        metrics.setdefault("status_events", []).append(event)

    def start_recording_runtime_log(self, base_path: str):
        self.close_recording_runtime_log()
        runtime_log_path = transcript_artifact_paths(base_path)["runtime_log"]
        runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(runtime_log_path, encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        logging.getLogger().addHandler(handler)
        self.recording_log_handler = handler
        self.recording_log_path = runtime_log_path
        logger.info("Recording runtime log started: %s", runtime_log_path)

    def close_recording_runtime_log(self):
        handler = self.recording_log_handler
        if handler is None:
            return
        logger.info("Recording runtime log finished: %s", self.recording_log_path)
        logging.getLogger().removeHandler(handler)
        handler.close()
        self.recording_log_handler = None
        self.recording_log_path = None

    def import_file(self):
        self.audit.record(
            "import.requested",
            category="workflow.import",
            actor="user",
            workflow="import",
            outcome="attempted",
        )
        if vars(self).get("summary_workflow_busy", False):
            self.audit.record(
                "import.start_rejected",
                category="workflow.import",
                actor="user",
                workflow="import",
                outcome="rejected",
                severity="warning",
                details={"reason": "summary_active"},
            )
            self.status_label.setText(self.strings.summary_already_running)
            return
        if self.transcriber_thread.model is None:
            self.audit.record(
                "import.start_rejected",
                category="workflow.import",
                actor="user",
                workflow="import",
                outcome="rejected",
                severity="warning",
                details={"reason": "model_not_ready"},
            )
            QMessageBox.warning(self, self.strings.please_wait_title, self.strings.model_not_ready)
            return
        if self.recorder_thread is not None:
            self.audit.record(
                "import.start_rejected",
                category="workflow.import",
                actor="user",
                workflow="import",
                outcome="rejected",
                severity="warning",
                details={"reason": "recording_active"},
            )
            QMessageBox.warning(self, self.strings.error_title, self.strings.stop_recording_before_import)
            return
        if self.summary_thread and self.summary_thread.isRunning():
            self.audit.record(
                "import.start_rejected",
                category="workflow.import",
                actor="user",
                workflow="import",
                outcome="rejected",
                severity="warning",
                details={"reason": "summary_active"},
            )
            QMessageBox.warning(self, self.strings.please_wait_title, self.strings.summary_already_running)
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            self.strings.select_media_files,
            "",
            self.strings.media_files_filter,
        )
        if files:
            self.import_cancel_requested = False
            self.pending_files.extend(files)
            self.total_batch_count = len(self.pending_files)
            self.batch_progress.setMaximum(self.total_batch_count)
            self.batch_progress.setValue(0)
            self.batch_progress.setVisible(True)

            self.set_import_controls(True)
            self.audit.record(
                "import.batch_started",
                category="workflow.import",
                actor="user",
                workflow="import",
                details={
                    "file_count": len(files),
                    "denoise_preset": self.selected_denoise_preset(),
                    "meeting_distance_mode": self.selected_meeting_distance_mode(),
                    "speaker_diarization": self.check_speaker_diarization.isChecked(),
                    "summary_enabled": self.check_llm_summary.isChecked(),
                },
            )
            if self.file_thread is None or not self.file_thread.isRunning():
                self.process_next_file()
        else:
            self.audit.record(
                "import.dialog_cancelled",
                category="workflow.import",
                actor="user",
                workflow="import",
                outcome="cancelled",
            )

    def selected_denoise_preset(self) -> str:
        selected = normalize_denoise_preset(
            enable_denoise=self.combo_denoise.currentData() != OFF_DENOISE_PRESET,
            preset=self.combo_denoise.currentData(),
        )
        return effective_denoise_preset_for_mode(self.selected_meeting_distance_mode(), selected)

    def denoise_enabled(self) -> bool:
        return self.selected_denoise_preset() != OFF_DENOISE_PRESET

    def selected_meeting_distance_mode(self) -> str:
        if not hasattr(self, "combo_meeting_distance"):
            return self.settings.meeting_distance_mode
        return self.combo_meeting_distance.currentData() or self.settings.meeting_distance_mode

    def selected_meeting_distance_policy(self):
        return meeting_distance_policy_for(self.selected_meeting_distance_mode())

    def selected_live_capture_source(self) -> str:
        return self.combo_live_capture.currentData() or LIVE_CAPTURE_SYSTEM_MICROPHONE

    def schedule_recording_enabled(self) -> bool:
        return bool(
            hasattr(self, "check_schedule_recording")
            and self.check_schedule_recording.isChecked()
        )

    def scheduled_auto_stop_enabled(self) -> bool:
        return bool(
            self.schedule_recording_enabled()
            and hasattr(self, "check_schedule_auto_stop")
            and self.check_schedule_auto_stop.isChecked()
        )

    def selected_schedule_datetime(self) -> tuple[datetime.datetime, datetime.datetime | None]:
        now = datetime.datetime.now().astimezone()
        start_time = self.time_schedule_start.time()
        start_at = next_wall_clock_datetime(now, start_time.hour(), start_time.minute())
        stop_at = None
        if self.scheduled_auto_stop_enabled():
            stop_time = self.time_schedule_end.time()
            stop_at = stop_datetime_after_start(start_at, stop_time.hour(), stop_time.minute())
        return start_at, stop_at

    def update_schedule_controls(self, *_):
        if not hasattr(self, "check_schedule_recording"):
            return

        active_workflow = (
            self.scheduled_recording_pending
            or self.recorder_thread is not None
            or self.file_import_active()
            or self.finalize_recording_pending
        )
        schedule_enabled = self.check_schedule_recording.isChecked()
        self.check_schedule_recording.setEnabled(not active_workflow)
        self.check_recording_consent.setEnabled(not active_workflow)
        self.time_schedule_start.setEnabled(schedule_enabled and not active_workflow)
        self.check_schedule_auto_stop.setEnabled(schedule_enabled and not active_workflow)
        self.time_schedule_end.setEnabled(
            schedule_enabled
            and self.check_schedule_auto_stop.isChecked()
            and not active_workflow
        )

    def update_record_button_label(self, *_):
        if not hasattr(self, "btn_record"):
            return
        if self.scheduled_recording_pending:
            text, role = self.strings.cancel_scheduled_recording, "danger"
        elif self.recorder_thread is not None:
            text, role = self.strings.stop_recording, "danger"
        elif self.schedule_recording_enabled():
            text, role = self.strings.schedule_recording_button, "scheduled"
        else:
            text, role = self.strings.start_recording, "primary"
        self.btn_record.setText(text)
        self.btn_record.setProperty("role", role)
        self.btn_record.style().unpolish(self.btn_record)
        self.btn_record.style().polish(self.btn_record)

    def update_speaker_controls(self, enabled):
        self.spin_min_speakers.setEnabled(enabled)
        self.spin_max_speakers.setEnabled(enabled)

    def update_top_active_device(self, *_):
        if hasattr(self, "top_device_label"):
            self.top_device_label.setText(
                self.strings.top_device_status.format(status=self.selected_live_capture_source())
            )

    def update_capture_guidance(self, *_):
        if not hasattr(self, "capture_guidance_label"):
            return
        platform_info = detect_runtime_platform()
        selected_source = self.selected_live_capture_source()
        needs_system_audio = selected_source in {LIVE_CAPTURE_SYSTEM, LIVE_CAPTURE_SYSTEM_MICROPHONE}
        if platform_info.is_windows and needs_system_audio:
            self.capture_guidance_label.setText(self.strings.windows_system_audio_guidance)
            self.capture_guidance_label.setVisible(True)
        else:
            self.capture_guidance_label.clear()
            self.capture_guidance_label.setVisible(False)

    def open_split_workspace(self):
        widget = self.parentWidget()
        while widget is not None:
            if hasattr(widget, "indexOf") and hasattr(widget, "setCurrentIndex"):
                current_index = widget.indexOf(self)
                if current_index >= 0 and current_index + 1 < widget.count():
                    widget.setCurrentIndex(current_index + 1)
                return
            widget = widget.parentWidget()

    def file_import_active(self) -> bool:
        return (
            bool(self.pending_files)
            or bool(self.file_thread and self.file_thread.isRunning())
            or self.import_summary_pending
        )

    def set_import_controls(self, active: bool):
        self.btn_record.setEnabled(not active)
        self.btn_import.setEnabled(not active)
        self.btn_reload_model.setEnabled(not active)
        self.btn_cancel_import.setVisible(active)
        self.btn_cancel_import.setEnabled(active)
        self.update_summary_button_state()
        self.update_schedule_controls()
        self.update_record_button_label()

    def cancel_import(self):
        if not self.file_import_active():
            return
        self.audit.record(
            "import.cancel_requested",
            category="workflow.import",
            actor="user",
            workflow="import",
            outcome="attempted",
        )
        self.import_cancel_requested = True
        self.pending_files.clear()
        self.btn_cancel_import.setEnabled(False)
        if self.file_thread and self.file_thread.isRunning():
            self.file_thread.request_cancel()
            self.status_label.setText(self.strings.import_cancel_requested)
            return
        self.status_label.setText(self.strings.import_cancel_after_current)

    def selected_speaker_range(self):
        min_speakers = self.spin_min_speakers.value()
        max_speakers = self.spin_max_speakers.value()
        if max_speakers < min_speakers:
            max_speakers = min_speakers
            self.spin_max_speakers.setValue(max_speakers)
        return min_speakers, max_speakers

    def apply_model_settings(self):
        if self.model_loader and self.model_loader.isRunning():
            return

        new_compute = self.combo_compute.currentData()
        self.audit.record(
            "model.load_requested",
            category="system.runtime",
            actor="user" if self.model_loader is not None else "system",
            workflow="diagnostics",
            outcome="attempted",
            details={"compute_type": new_compute},
        )
        self.asr_model_status = "loading"
        self.update_runtime_model_status()
        self.btn_reload_model.setEnabled(False)
        self.btn_record.setEnabled(False)
        self.btn_import.setEnabled(False)
        self.btn_reload_model.setText(self.strings.loading_model)
        self.update_schedule_controls()

        self.model_loader = ModelLoaderThread(self.settings.device, new_compute)
        self.model_loader.status_signal.connect(self.update_status_only)
        self.model_loader.error_signal.connect(self.on_model_error)
        self.model_loader.finished_signal.connect(self.on_model_loaded)
        self.model_loader.start()

    @pyqtSlot(object)
    def on_model_loaded(self, new_model):
        if self.transcriber_thread.model:
            del self.transcriber_thread.model
            gc.collect()

        self.transcriber_thread.model = new_model
        active_device = getattr(self.model_loader, "actual_device", self.settings.device)
        active_compute = getattr(self.model_loader, "actual_compute_type", self.combo_compute.currentData())
        self.transcriber_thread.device = active_device
        self.transcriber_thread.compute_type = active_compute

        combo_index = self.combo_compute.findData(active_compute)
        if combo_index >= 0 and combo_index != self.combo_compute.currentIndex():
            self.combo_compute.blockSignals(True)
            self.combo_compute.setCurrentIndex(combo_index)
            self.combo_compute.blockSignals(False)

        import_active = self.file_import_active()
        self.btn_record.setEnabled(not import_active)
        self.btn_import.setEnabled(not import_active)
        self.btn_reload_model.setEnabled(not import_active)
        self.btn_reload_model.setText(self.strings.reload_model)
        self.update_schedule_controls()
        self.update_record_button_label()
        self.status_label.setText(self.strings.model_ready(active_device, active_compute))
        self.asr_model_status = f"loaded ({active_device}/{active_compute})"
        self.update_runtime_model_status()
        self.audit.record(
            "model.load_completed",
            category="system.runtime",
            workflow="diagnostics",
            details={"device": active_device, "compute_type": active_compute},
        )

    @pyqtSlot(str)
    def on_model_error(self, err_msg):
        self.asr_model_status = f"failed: {err_msg.splitlines()[0] if err_msg else 'unknown error'}"
        self.update_runtime_model_status()
        self.show_diagnostic_error(self.strings.model_loading_failed, err_msg)
        import_active = self.file_import_active()
        self.btn_record.setEnabled(not import_active)
        self.btn_import.setEnabled(not import_active)
        self.btn_reload_model.setEnabled(not import_active)
        self.btn_reload_model.setText(self.strings.reload_model)
        self.update_schedule_controls()
        self.update_record_button_label()
        self.audit.record(
            "model.load_failed",
            category="system.runtime",
            workflow="diagnostics",
            outcome="error",
            severity="error",
            details={"error_class": "model_load_error"},
        )

    def process_next_file(self):
        if self.import_cancel_requested:
            cancelled_count = self.total_batch_count
            self.pending_files.clear()
            self.set_import_controls(False)
            self.status_label.setText(self.strings.batch_tasks_cancelled)
            self.batch_progress.setVisible(False)
            self.total_batch_count = 0
            self.import_cancel_requested = False
            self.audit.record(
                "import.batch_cancelled",
                category="workflow.import",
                actor="user",
                workflow="import",
                outcome="cancelled",
                details={"file_count": cancelled_count},
            )
            return

        if not self.pending_files:
            completed_count = self.total_batch_count
            self.set_import_controls(False)
            self.status_label.setText(self.strings.batch_tasks_completed)
            self.batch_progress.setVisible(False)
            self.total_batch_count = 0
            if completed_count:
                self.audit.record(
                    "import.batch_completed",
                    category="workflow.import",
                    workflow="import",
                    details={"file_count": completed_count},
                )
            return

        file_path = self.pending_files.pop(0)
        self.current_review_session_dir = None
        self.current_review_meeting_id = None
        self.current_review_audio_path = None
        self.review_audio_path = None
        self.reset_summary_claims()
        self.text_area.clear()
        self.transcript_revision += 1
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        self.current_filename = f"transcript_{base_name}"
        self.current_folder = os.path.dirname(file_path)
        self.set_review_audio_source(file_path)
        self.update_output_folder_controls()

        completed = self.total_batch_count - len(self.pending_files) - 1
        self.batch_progress.setValue(completed)

        total_left = len(self.pending_files) + 1
        self.status_label.setText(self.strings.batch_processing(total_left, base_name))
        min_speakers, max_speakers = self.selected_speaker_range()
        try:
            output_base_path = str(
                collision_safe_transcript_base_path(
                    self.transcript_base_path(
                        self.current_folder,
                        self.current_filename,
                    ),
                    file_path,
                )
            )
            ensure_output_directory_writable(Path(output_base_path).parent)
        except (OSError, ValueError) as exc:
            self.status_label.setText(
                f"輸出資料夾目前無法寫入；來源媒體保持不變：{exc}"
            )
            self.audit.record(
                "import.start_rejected",
                category="workflow.import",
                actor="system",
                workflow="import",
                outcome="error",
                severity="error",
                details={"reason": "output_unavailable", "error_class": type(exc).__name__},
            )
            QTimer.singleShot(0, self.process_next_file)
            return
        self.current_filename = Path(output_base_path).name
        self.current_import_metrics = self.new_metrics("import", file_path, output_base_path)
        self.current_import_metrics.update(self.selected_meeting_distance_policy().metadata())
        self.current_import_metrics["effective_denoise_preset"] = self.selected_denoise_preset()
        self.current_import_metrics["file_transcription_started_at"] = self.timestamp_now()
        self.current_import_metrics["_file_transcription_started_perf"] = time.perf_counter()
        self.audit.record(
            "import.file_started",
            category="workflow.import",
            workflow="import",
            details={
                "position": completed + 1,
                "batch_size": self.total_batch_count,
            },
        )

        self.file_thread = FileTranscriberThread(
            self.transcriber_thread.model,
            file_path,
            target_dbfs=float(self.spin_norm.value()),
            beam_size=self.spin_beam.value(),
            initial_prompt=self.prompt_input.text(),
            language=self.combo_lang.currentData(),
            meeting_distance_mode=self.selected_meeting_distance_mode(),
            enable_denoise=self.denoise_enabled(),
            denoise_preset=self.selected_denoise_preset(),
            enable_speaker_diarization=self.check_speaker_diarization.isChecked(),
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        self.file_thread.text_updated.connect(self.update_log)
        self.file_thread.status_updated.connect(self.update_status_only)
        self.file_thread.error_signal.connect(self.on_file_error)
        self.file_thread.finished_signal.connect(self.on_file_finished)
        self.file_thread.start()

    def on_file_finished(self):
        thread = self.file_thread
        metrics = self.current_import_metrics
        self.file_thread = None
        if metrics is not None:
            self.add_stage_duration(metrics, "file_transcription", metrics.get("_file_transcription_started_perf"))
            metrics["file_transcription_finished_at"] = self.timestamp_now()
            metrics["status_events"] = list(getattr(thread, "status_events", []))

        self.batch_progress.setValue(self.total_batch_count - len(self.pending_files))

        if not thread or thread.cancel_requested or not thread.result_lines:
            duration_ms = None
            if metrics and metrics.get("_file_transcription_started_perf") is not None:
                duration_ms = round(
                    (time.perf_counter() - metrics["_file_transcription_started_perf"]) * 1000,
                    3,
                )
            self.audit.record(
                "import.file_completed",
                category="workflow.import",
                workflow="import",
                outcome="cancelled" if thread and thread.cancel_requested else "rejected",
                severity="warning",
                details={
                    "reason": "cancelled" if thread and thread.cancel_requested else "empty_result",
                    "duration_ms": duration_ms,
                },
            )
            self.current_import_metrics = None
            self.process_next_file()
            return

        duration_ms = None
        if metrics and metrics.get("_file_transcription_started_perf") is not None:
            duration_ms = round(
                (time.perf_counter() - metrics["_file_transcription_started_perf"]) * 1000,
                3,
            )
        self.audit.record(
            "import.file_completed",
            category="workflow.import",
            workflow="import",
            details={"duration_ms": duration_ms},
        )

        transcript = "\n".join(thread.result_lines)
        if getattr(thread, "result_segments", None):
            self.text_area.set_segments(thread.result_segments)
            transcript = self.text_area.toPlainText()
        base_path = metrics["base_path"] if metrics else self.default_transcript_base_path()
        if self.check_llm_summary.isChecked():
            summary_holder = {"text": ""}
            summary_started = time.perf_counter()
            self.import_summary_pending = True
            if metrics is not None:
                metrics["llm_summary_started_at"] = self.timestamp_now()
            self.prepare_llm_runtime_then_summarize(
                transcript,
                finished_callback=lambda: self.finish_import_artifacts(
                    base_path,
                    transcript,
                    summary_holder["text"] or getattr(self.summary_thread, "summary_block", ""),
                    metrics,
                    summary_started,
                ),
                summary_ready_callback=lambda summary: summary_holder.update(text=summary),
            )
            return

        self.finish_import_artifacts(base_path, transcript, "", metrics, None)

    def finish_import_artifacts(self, base_path: str, transcript: str, summary: str, metrics: dict | None, summary_started):
        if metrics is not None and summary_started is not None:
            self.add_stage_duration(metrics, "llm_summary", summary_started)
            metrics["llm_summary_finished_at"] = self.timestamp_now()

        save_started = time.perf_counter()
        prepared = self.prepare_transcript_input(transcript)
        if metrics is not None:
            metrics["save_started_at"] = self.timestamp_now()
            if prepared.punctuation_backend != "skipped":
                metrics["punctuation_restoration_backend"] = prepared.punctuation_backend
        self.import_summary_pending = False
        try:
            saved = self.save_session_artifacts(
                base_path,
                prepared,
                summary,
                metrics,
                default_workflow="import",
            )
        except (OSError, ValueError) as exc:
            self.import_summary_pending = False
            self.current_import_metrics = None
            self.status_label.setText(
                f"逐字稿仍保留在畫面中；輸出寫入需要協助確認：{exc}"
            )
            self.audit.record(
                "import.artifact_save_failed",
                category="workflow.import",
                workflow="import",
                outcome="error",
                severity="error",
                details={"error_class": type(exc).__name__},
            )
            QTimer.singleShot(0, self.process_next_file)
            return
        if metrics is not None:
            self.add_stage_duration(metrics, "save_outputs", save_started)
            finished_metrics = self.finish_metrics(metrics)
            saved["event_log"] = transcript_artifact_paths(base_path)["event_log"]
            finished_metrics["outputs"] = {name: str(path) for name, path in saved.items()}
            saved["event_log"] = write_event_log_file(base_path, finished_metrics)
            finished_metrics["outputs"] = {name: str(path) for name, path in saved.items()}
            metrics_path = transcript_artifact_paths(base_path)["metrics"]
            saved["metrics"] = write_json_file(metrics_path, finished_metrics)
        else:
            finished_metrics = None

        final_path = saved.get("final") or saved.get("raw")
        if final_path:
            remove_transcript_backup()
            self.remember_output_folder(final_path.parent)
            elapsed = finished_metrics.get("total_seconds", 0.0) if finished_metrics else 0.0
            if self.import_cancel_requested:
                self.status_label.setText(
                    self.strings.transcript_artifacts_saved_cancelled_message(str(final_path), elapsed)
                )
            else:
                self.status_label.setText(self.strings.transcript_artifacts_saved_message(str(final_path), elapsed))
            self.audit.record(
                "import.artifact_saved",
                category="workflow.import",
                workflow="import",
                details={
                    "duration_ms": round(elapsed * 1000, 3),
                    "summary_included": bool(summary),
                },
            )
        self.current_import_metrics = None
        if self.import_cancel_requested:
            cancelled_count = self.total_batch_count
            self.pending_files.clear()
            self.set_import_controls(False)
            self.batch_progress.setVisible(False)
            self.total_batch_count = 0
            self.import_cancel_requested = False
            self.audit.record(
                "import.batch_cancelled",
                category="workflow.import",
                actor="user",
                workflow="import",
                outcome="cancelled",
                details={"file_count": cancelled_count},
            )
            return
        self.process_next_file()

    @pyqtSlot(str)
    def on_file_error(self, err_msg):
        self.audit.record(
            "import.file_failed",
            category="workflow.import",
            workflow="import",
            outcome="error",
            severity="error",
            details={"error_class": "file_transcription_error"},
        )
        self.show_diagnostic_error(self.strings.file_transcription_failed, err_msg)

    def toggle_record(self):
        if self.scheduled_recording_pending:
            self.cancel_scheduled_recording()
            return
        if self.recorder_thread is None and self.schedule_recording_enabled():
            self.arm_scheduled_recording()
            return
        if self.recorder_thread is None:
            self.start_recording_session("manual")
            return
        self.stop_recording_session("manual")

    def recording_consent_confirmed(self) -> bool:
        return bool(
            hasattr(self, "check_recording_consent")
            and self.check_recording_consent.isChecked()
        )

    def require_recording_consent(self, event_name: str, trigger: str) -> bool:
        if self.recording_consent_confirmed():
            return True
        self.audit.record(
            event_name,
            category="workflow.recording",
            actor="user" if trigger != "scheduled" else "system",
            workflow="recording",
            outcome="rejected",
            severity="warning",
            details={"reason": "consent_not_confirmed", "trigger": trigger},
        )
        if trigger == "scheduled":
            self.status_label.setText(self.strings.recording_consent_required)
        else:
            QMessageBox.warning(
                self,
                self.strings.recording_consent_title,
                self.strings.recording_consent_required,
            )
        return False

    def start_recording_session(self, trigger: str) -> bool:
        if vars(self).get("summary_workflow_busy", False):
            self.audit.record(
                "recording.start_rejected",
                category="workflow.recording",
                actor="user" if trigger == "manual" else "system",
                workflow="recording",
                outcome="rejected",
                severity="warning",
                details={"reason": "summary_active", "trigger": trigger},
            )
            self.status_label.setText(self.strings.summary_already_running)
            return False
        if not self.require_recording_consent("recording.start_rejected", trigger):
            return False
        if self.transcriber_thread.model is None:
            self.audit.record(
                "recording.start_rejected",
                category="workflow.recording",
                actor="user" if trigger == "manual" else "system",
                workflow="recording",
                outcome="rejected",
                severity="warning",
                details={"reason": "model_not_ready", "trigger": trigger},
            )
            if trigger == "manual":
                QMessageBox.warning(self, self.strings.please_wait_title, self.strings.model_not_ready)
            else:
                self.status_label.setText(self.strings.scheduled_recording_model_not_ready)
            return False
        if self.file_import_active():
            self.audit.record(
                "recording.start_rejected",
                category="workflow.recording",
                actor="user" if trigger == "manual" else "system",
                workflow="recording",
                outcome="rejected",
                severity="warning",
                details={"reason": "import_active", "trigger": trigger},
            )
            self.status_label.setText(self.strings.scheduled_recording_start_failed)
            return False

        self.current_review_session_dir = None
        self.current_review_meeting_id = None
        self.current_review_audio_path = None
        self.review_audio_path = None

        suffix = safe_recording_suffix(self.name_input.text())
        timestamp = datetime.datetime.now().strftime("%y%m%d_%H%M%S_%f")[:-3]
        base_name = f"{timestamp}_{suffix}"

        self.current_folder = os.path.join(os.getcwd(), base_name)
        self.current_filename = base_name
        full_path = self.default_transcript_base_path()
        try:
            ensure_output_directory_writable(Path(full_path).parent)
        except OSError as exc:
            self.status_label.setText(f"輸出資料夾目前無法寫入，錄音尚未啟動：{exc}")
            self.audit.record(
                "recording.start_rejected",
                category="workflow.recording",
                actor="user" if trigger == "manual" else "system",
                workflow="recording",
                outcome="error",
                severity="error",
                details={"reason": "output_unavailable", "error_class": type(exc).__name__},
            )
            return False
        self.update_output_folder_controls()
        self.current_recording_metrics = self.new_metrics(
            "recording",
            f"{full_path}.wav",
            self.default_transcript_base_path(),
        )
        try:
            self.start_recording_runtime_log(self.default_transcript_base_path())
        except OSError as exc:
            self.current_recording_metrics = None
            self.status_label.setText(f"錄音活動紀錄目前無法建立，錄音尚未啟動：{exc}")
            self.audit.record(
                "recording.start_rejected",
                category="workflow.recording",
                actor="user" if trigger == "manual" else "system",
                workflow="recording",
                outcome="error",
                severity="error",
                details={"reason": "runtime_log_unavailable", "error_class": type(exc).__name__},
            )
            return False
        self.current_recording_metrics["recording_started_at"] = self.timestamp_now()
        self.current_recording_metrics["recording_start_trigger"] = trigger
        self.current_recording_metrics["capture_source"] = self.selected_live_capture_source()
        meeting_distance_policy = self.selected_meeting_distance_policy()
        self.current_recording_metrics.update(meeting_distance_policy.metadata())
        self.current_recording_metrics["effective_denoise_preset"] = self.selected_denoise_preset()
        recording_runtime_config = {
            "asr_model_id": self.settings.model_id,
            "asr_device": self.settings.device,
            "asr_compute_type": self.settings.compute_type,
            "beam_size": self.spin_beam.value(),
            "language": self.combo_lang.currentData(),
            "initial_prompt_configured": bool(self.prompt_input.text()),
            "capture_source": self.selected_live_capture_source(),
            "live_max_segment_len_sec": self.settings.live_max_segment_len_sec,
            "live_energy_gate_rms": (
                meeting_distance_policy.live_energy_gate_rms
                if meeting_distance_policy.mode != MEETING_DISTANCE_OFF
                else self.settings.live_energy_gate_rms
            ),
            "live_energy_bridge_ms": meeting_distance_policy.live_energy_bridge_ms,
            "meeting_distance_mode": meeting_distance_policy.mode,
            "meeting_distance_backend": meeting_distance_policy.enhancement_backend,
            "meeting_distance_backend_role": meeting_distance_policy.backend_role,
            "live_agc_enabled": meeting_distance_policy.live_agc_enabled,
            "live_agc_target_rms": meeting_distance_policy.live_agc_target_rms,
            "live_agc_max_gain": meeting_distance_policy.live_agc_max_gain,
            "denoise_enabled": self.denoise_enabled(),
            "denoise_preset": self.selected_denoise_preset(),
            "target_dbfs": float(self.spin_norm.value()),
            "recording_audio_format": self.selected_recording_audio_format(),
            "chinese_punctuation_enabled": self.settings.chinese_punctuation_enabled,
            "llm_summary_enabled": self.check_llm_summary.isChecked(),
            "llm_summary_model": BASE_MODEL_ID,
            "llm_summary_quantization": OLLAMA_MODEL_TAG,
            "recording_consent_confirmed": True,
            "output_folder": str(Path(full_path).parent),
        }
        self.current_recording_metrics["recording_runtime_config"] = recording_runtime_config
        self.append_recording_event(
            "recording_runtime_config",
            "Recording runtime configuration captured.",
            **recording_runtime_config,
        )
        if trigger == "scheduled":
            self.current_recording_metrics["scheduled_start_at"] = (
                self.scheduled_start_at.isoformat(timespec="seconds") if self.scheduled_start_at else None
            )
            self.current_recording_metrics["scheduled_stop_at"] = (
                self.scheduled_stop_at.isoformat(timespec="seconds") if self.scheduled_stop_at else None
            )

        self.transcriber_thread.update_live_settings(
            beam_size=self.spin_beam.value(),
            language=self.combo_lang.currentData(),
            initial_prompt=self.prompt_input.text(),
        )

        self.recorder_thread = AudioRecorderThread(
            full_path,
            self.transcriber_thread,
            enable_denoise=self.denoise_enabled(),
            denoise_preset=self.selected_denoise_preset(),
            meeting_distance_mode=meeting_distance_policy.mode,
            capture_mode=self.selected_live_capture_source(),
            max_segment_len_sec=self.settings.live_max_segment_len_sec,
            energy_gate_rms=self.settings.live_energy_gate_rms,
        )
        recorder_thread = self.recorder_thread
        recorder_thread.waveform_signal.connect(self.update_plot)
        recorder_thread.finished_signal.connect(
            lambda wav_path, thread=recorder_thread: self.on_recording_thread_finished(thread, wav_path)
        )
        recorder_thread.status_signal.connect(self.update_status_only)

        self.btn_import.setEnabled(False)
        self.btn_reload_model.setEnabled(False)
        self.recorder_thread.start()
        self.append_recording_event("recording_started", f"Recording started: {base_name}")
        self.audit.record(
            "recording.started",
            category="workflow.recording",
            actor="user" if trigger == "manual" else "system",
            workflow="recording",
            details={
                "trigger": trigger,
                "capture_source": self.selected_live_capture_source(),
                "meeting_distance_mode": meeting_distance_policy.mode,
                "denoise_preset": self.selected_denoise_preset(),
                "language": self.combo_lang.currentData(),
                "summary_enabled": self.check_llm_summary.isChecked(),
            },
        )

        self.update_record_button_label()
        self.update_schedule_controls()
        self.status_label.setText(self.strings.recording(base_name))
        self.reset_summary_claims()
        self.text_area.clear()
        self.transcript_revision += 1
        return True

    def stop_recording_session(self, trigger: str, recorder_thread=None, thread_already_finished: bool = False):
        recorder_thread = recorder_thread or self.recorder_thread
        if recorder_thread is None:
            return
        self.scheduled_stop_timer.stop()
        if not thread_already_finished:
            recorder_thread.running = False
            recorder_thread.quit()
        else:
            self.recorder_thread = None

        self.btn_record.setEnabled(False)
        self.btn_import.setEnabled(False)
        self.btn_summary.setEnabled(False)
        self.status_label.setText(self.strings.recording_finished_processing)
        self.finalize_recording_pending = True
        if self.current_recording_metrics is not None:
            self.current_recording_metrics["recording_stop_requested_at"] = self.timestamp_now()
            self.current_recording_metrics["recording_stop_trigger"] = trigger
            self.current_recording_metrics["recording_auto_stopped_for_no_voice"] = bool(
                getattr(recorder_thread, "auto_stopped_for_no_voice", False)
            )
            self.current_recording_metrics["no_voice_auto_stop_minutes"] = getattr(
                recorder_thread,
                "no_voice_auto_stop_minutes",
                None,
            )
            trimmed_frames = int(getattr(recorder_thread, "trimmed_trailing_no_voice_frames", 0) or 0)
            if trimmed_frames:
                self.current_recording_metrics["trimmed_trailing_no_voice_frames"] = trimmed_frames
                self.current_recording_metrics["trimmed_trailing_no_voice_seconds"] = round(
                    trimmed_frames * CHUNK_MS / 1000,
                    3,
                )
            self.current_recording_metrics["_stop_requested_perf"] = time.perf_counter()
            self.add_stage_duration(
                self.current_recording_metrics,
                "recording_capture",
                self.current_recording_metrics.get("_started_perf"),
            )
            self.append_recording_event("recording_stop_requested", f"Recording stop requested: {trigger}")
        started_perf = (
            self.current_recording_metrics.get("_started_perf")
            if self.current_recording_metrics is not None
            else None
        )
        duration_ms = round((time.perf_counter() - started_perf) * 1000, 3) if started_perf else None
        self.audit.record(
            "recording.stop_requested",
            category="workflow.recording",
            actor="user" if trigger == "manual" else "system",
            workflow="recording",
            outcome="attempted",
            details={
                "trigger": trigger,
                "duration_ms": duration_ms,
                "auto_stopped_for_no_voice": bool(
                    getattr(recorder_thread, "auto_stopped_for_no_voice", False)
                ),
            },
        )
        self.scheduled_start_at = None
        self.scheduled_stop_at = None
        self.update_record_button_label()
        self.update_schedule_controls()
        QTimer.singleShot(1000, self.enable_reload_after_live_asr_idle)
        QTimer.singleShot(1000, self.finalize_recording_after_live_asr_idle)

    def arm_scheduled_recording(self):
        if not self.require_recording_consent("recording.schedule_rejected", "schedule"):
            return
        if self.transcriber_thread.model is None:
            self.audit.record(
                "recording.schedule_rejected",
                category="workflow.recording",
                actor="user",
                workflow="recording",
                outcome="rejected",
                severity="warning",
                details={"reason": "model_not_ready"},
            )
            QMessageBox.warning(self, self.strings.please_wait_title, self.strings.model_not_ready)
            return
        if self.file_import_active() or self.recorder_thread is not None:
            self.audit.record(
                "recording.schedule_rejected",
                category="workflow.recording",
                actor="user",
                workflow="recording",
                outcome="rejected",
                severity="warning",
                details={"reason": "workflow_active"},
            )
            self.status_label.setText(self.strings.scheduled_recording_start_failed)
            return

        start_at, stop_at = self.selected_schedule_datetime()
        now = datetime.datetime.now().astimezone()
        self.scheduled_recording_pending = True
        self.scheduled_start_at = start_at
        self.scheduled_stop_at = stop_at
        self.scheduled_start_timer.start(milliseconds_until(now, start_at))

        self.btn_import.setEnabled(False)
        self.btn_reload_model.setEnabled(False)
        self.btn_summary.setEnabled(False)
        self.update_record_button_label()
        self.update_schedule_controls()
        self.status_label.setText(self.strings.scheduled_recording_armed(start_at, stop_at))
        self.audit.record(
            "recording.schedule_armed",
            category="workflow.recording",
            actor="user",
            workflow="recording",
            details={"auto_stop_enabled": stop_at is not None},
        )

    def cancel_scheduled_recording(self):
        self.scheduled_start_timer.stop()
        self.scheduled_stop_timer.stop()
        self.scheduled_recording_pending = False
        self.scheduled_start_at = None
        self.scheduled_stop_at = None
        import_active = self.file_import_active()
        self.btn_record.setEnabled(not import_active)
        self.btn_import.setEnabled(not import_active)
        self.btn_reload_model.setEnabled(not import_active)
        self.check_recording_consent.setChecked(False)
        self.update_summary_button_state()
        self.update_record_button_label()
        self.update_schedule_controls()
        self.status_label.setText(self.strings.scheduled_recording_cancelled)
        self.audit.record(
            "recording.schedule_cancelled",
            category="workflow.recording",
            actor="user",
            workflow="recording",
            outcome="cancelled",
        )

    def start_scheduled_recording(self):
        if not self.scheduled_recording_pending:
            return
        self.scheduled_recording_pending = False
        stop_at = self.scheduled_stop_at
        if not self.start_recording_session("scheduled"):
            self.scheduled_start_at = None
            self.scheduled_stop_at = None
            self.update_record_button_label()
            self.update_schedule_controls()
            return
        if stop_at:
            now = datetime.datetime.now().astimezone()
            self.scheduled_stop_timer.start(milliseconds_until(now, stop_at))
            self.status_label.setText(self.strings.recording_with_scheduled_stop(self.current_filename, stop_at))

    def stop_scheduled_recording(self):
        if self.recorder_thread is None:
            self.scheduled_stop_at = None
            self.update_record_button_label()
            self.update_schedule_controls()
            return
        self.stop_recording_session("scheduled_stop")

    def default_transcript_base_path(self) -> str:
        return self.transcript_base_path(self.current_folder, self.current_filename)

    def default_transcript_path(self) -> str:
        return str(transcript_artifact_paths(self.default_transcript_base_path())["final"])

    def finalize_recording_after_live_asr_idle(self):
        if not self.finalize_recording_pending:
            return
        if self.recorder_thread is not None:
            QTimer.singleShot(250, self.finalize_recording_after_live_asr_idle)
            return
        if not self.transcriber_thread.is_idle():
            QTimer.singleShot(1000, self.finalize_recording_after_live_asr_idle)
            return
        if self.current_recording_metrics is not None:
            self.current_recording_metrics["final_asr_idle_at"] = self.timestamp_now()
            self.add_stage_duration(
                self.current_recording_metrics,
                "final_asr_drain",
                self.current_recording_metrics.get("_stop_requested_perf"),
            )
            self.append_recording_event("final_asr_idle", "Live ASR queue drained before saving artifacts.")
        metrics = self.current_recording_metrics
        if metrics is not None and not metrics.get("final_recording_pass_completed"):
            if self.final_recording_thread is not None:
                return
            if self.start_final_recording_pass():
                return
            metrics["final_recording_pass_completed"] = True
            metrics["final_recording_pass_status"] = "skipped_no_durable_audio"
        if self.check_llm_summary.isChecked() and self.transcript_without_summary():
            summary_holder = {"text": ""}
            if self.current_recording_metrics is not None:
                self.current_recording_metrics["llm_summary_started_at"] = self.timestamp_now()
                self.current_recording_metrics["_llm_summary_started_perf"] = time.perf_counter()
                self.append_recording_event("llm_summary_started", "LLM summary started for recording transcript.")
            self.prepare_llm_runtime_then_summarize(
                self.transcript_without_summary(),
                finished_callback=lambda: self.save_and_clear_recording_transcript(
                    summary_holder["text"] or getattr(self.summary_thread, "summary_block", "")
                ),
                summary_ready_callback=lambda summary: summary_holder.update(text=summary),
            )
            return
        self.save_and_clear_recording_transcript()

    def start_final_recording_pass(self) -> bool:
        durable_audio = (self.current_recording_metrics or {}).get(
            "recording_raw_wav_path"
        )
        audio_path = Path(durable_audio) if durable_audio else None
        if not audio_path or not audio_path.exists() or self.transcriber_thread.model is None:
            return False
        min_speakers, max_speakers = self.selected_speaker_range()
        self.final_recording_thread = FileTranscriberThread(
            self.transcriber_thread.model,
            str(audio_path),
            target_dbfs=float(self.spin_norm.value()),
            beam_size=self.spin_beam.value(),
            initial_prompt=self.prompt_input.text(),
            language=self.combo_lang.currentData(),
            meeting_distance_mode=self.selected_meeting_distance_mode(),
            enable_denoise=self.denoise_enabled(),
            denoise_preset=self.selected_denoise_preset(),
            enable_speaker_diarization=self.check_speaker_diarization.isChecked(),
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        if self.current_recording_metrics is not None:
            self.current_recording_metrics["final_recording_pass_started_at"] = self.timestamp_now()
            self.current_recording_metrics["_final_recording_pass_started_perf"] = time.perf_counter()
        self.append_recording_event(
            "final_recording_pass_started",
            "Offline final ASR and diarization started from durable audio.",
        )
        self.status_label.setText("⏳ 正在從已保存音訊產生會後精確逐字稿…")
        self.final_recording_thread.status_updated.connect(self.update_status_only)
        self.final_recording_thread.error_signal.connect(self.on_final_recording_pass_error)
        self.final_recording_thread.finished_signal.connect(self.on_final_recording_pass_finished)
        self.final_recording_thread.start()
        return True

    @pyqtSlot(str)
    def on_final_recording_pass_error(self, error: str):
        if self.current_recording_metrics is not None:
            self.current_recording_metrics["final_recording_pass_error"] = str(error)
        self.append_recording_event(
            "final_recording_pass_failed",
            "Offline final ASR failed; the provisional transcript remains available.",
            error_class="final_recording_pass_error",
        )
        self.update_status_only(f"⚠️ 會後精確逐字稿未完成，將保存會中暫定版本：{error}")

    def on_final_recording_pass_finished(self):
        thread = self.final_recording_thread
        self.final_recording_thread = None
        metrics = self.current_recording_metrics
        if metrics is not None:
            self.add_stage_duration(
                metrics,
                "final_recording_pass",
                metrics.get("_final_recording_pass_started_perf"),
            )
            metrics["final_recording_pass_finished_at"] = self.timestamp_now()
            metrics["final_recording_pass_completed"] = True
        segments = list(getattr(thread, "result_segments", []) or [])
        if segments:
            self.text_area.set_segments(segments)
            if metrics is not None:
                metrics["final_recording_pass_status"] = "final"
                metrics["final_segment_count"] = len(segments)
            self.append_recording_event(
                "final_recording_pass_completed",
                "Durable audio replaced the provisional transcript with final timestamped segments.",
                segment_count=len(segments),
            )
        else:
            if metrics is not None:
                metrics["final_recording_pass_status"] = "provisional_fallback"
            self.append_recording_event(
                "final_recording_pass_fallback",
                "No final segments were produced; preserving the provisional transcript.",
            )
        self.finalize_recording_after_live_asr_idle()

    def save_and_clear_recording_transcript(self, summary_override: str = ""):
        if not self.finalize_recording_pending:
            return
        self.finalize_recording_pending = False
        self.status_label.setText(self.strings.auto_save_transcript_pending)
        metrics = self.current_recording_metrics
        if metrics is not None and metrics.get("_llm_summary_started_perf") is not None:
            self.add_stage_duration(metrics, "llm_summary", metrics.get("_llm_summary_started_perf"))
            metrics["llm_summary_finished_at"] = self.timestamp_now()
            self.append_event_to_metrics(metrics, "llm_summary_finished", "LLM summary finished for recording transcript.")

        raw_transcript, summary = split_transcript_sections(self.text_area.toPlainText())
        prepared = self.prepare_transcript_input(raw_transcript)
        summary = summary_override or summary
        if not prepared.raw_text and not summary:
            if metrics is not None:
                self.append_event_to_metrics(metrics, "save_skipped", "No transcript or summary content to save.")
                finished_metrics = self.finish_metrics(metrics)
                base_path = self.default_transcript_base_path()
                runtime_log_path = transcript_artifact_paths(base_path)["runtime_log"]
                self.close_recording_runtime_log()
                event_log_path = write_event_log_file(base_path, finished_metrics)
                outputs = dict(finished_metrics.get("outputs", {}))
                outputs["event_log"] = str(event_log_path)
                if runtime_log_path.exists():
                    outputs["runtime_log"] = str(runtime_log_path)
                finished_metrics["outputs"] = outputs
                metrics_path = transcript_artifact_paths(base_path)["metrics"]
                write_json_file(metrics_path, finished_metrics)
            self.status_label.setText(self.strings.no_content_to_save)
            self.audit.record(
                "recording.save_skipped",
                category="workflow.recording",
                workflow="recording",
                outcome="rejected",
                severity="warning",
                details={"reason": "empty_content"},
            )
            self.current_recording_metrics = None
            self.restore_post_recording_controls()
            return

        base_path = self.default_transcript_base_path()
        save_started = time.perf_counter()
        if metrics is not None:
            metrics["save_started_at"] = self.timestamp_now()
            if prepared.punctuation_backend != "skipped":
                metrics["punctuation_restoration_backend"] = prepared.punctuation_backend
            self.append_event_to_metrics(metrics, "save_started", "Saving recording transcript artifacts.")
        try:
            saved = self.save_session_artifacts(
                base_path,
                prepared,
                summary,
                metrics,
                default_workflow="recording",
            )
        except (OSError, ValueError) as exc:
            self.status_label.setText(
                f"錄音與逐字稿仍保留；輸出寫入需要協助確認：{exc}"
            )
            self.audit.record(
                "recording.artifact_save_failed",
                category="workflow.recording",
                workflow="recording",
                outcome="error",
                severity="error",
                details={"error_class": type(exc).__name__},
            )
            self.restore_post_recording_controls()
            return
        if metrics is not None:
            self.add_stage_duration(metrics, "save_outputs", save_started)
            finished_metrics = self.finish_metrics(metrics)
            runtime_log_path = transcript_artifact_paths(base_path)["runtime_log"]
            self.close_recording_runtime_log()
            saved["event_log"] = transcript_artifact_paths(base_path)["event_log"]
            if runtime_log_path.exists():
                saved["runtime_log"] = runtime_log_path
            output_paths = dict(finished_metrics.get("outputs", {}))
            output_paths.update({name: str(path) for name, path in saved.items()})
            finished_metrics["outputs"] = output_paths
            self.append_event_to_metrics(
                finished_metrics,
                "save_finished",
                "Recording transcript artifacts saved.",
                outputs=dict(finished_metrics["outputs"]),
            )
            saved["event_log"] = write_event_log_file(base_path, finished_metrics)
            output_paths = dict(finished_metrics.get("outputs", {}))
            output_paths.update({name: str(path) for name, path in saved.items()})
            finished_metrics["outputs"] = output_paths
            metrics_path = transcript_artifact_paths(base_path)["metrics"]
            saved["metrics"] = write_json_file(metrics_path, finished_metrics)
        final_path = saved.get("final") or saved.get("raw")
        if final_path:
            self.transcript_revision += 1
            remove_transcript_backup()
            self.remember_output_folder(final_path.parent)
            elapsed = metrics.get("total_seconds", 0.0) if metrics else 0.0
            self.audit.record(
                "recording.artifact_saved",
                category="workflow.recording",
                workflow="recording",
                details={
                    "duration_ms": round(elapsed * 1000, 3),
                    "summary_included": bool(summary),
                },
            )
            if metrics and metrics.get("recording_outcome") == "partial":
                self.status_label.setText(
                    f"⚠️ 已保存可用的部分錄音與逐字稿：{final_path}；請由人員覆核錄音結束位置。"
                )
            else:
                self.status_label.setText(
                    self.strings.transcript_artifacts_saved_message(
                        str(final_path),
                        elapsed,
                    )
                )
            self.current_recording_metrics = None
            self.restore_post_recording_controls()
            return
        self.status_label.setText(self.strings.no_content_to_save)
        self.current_recording_metrics = None
        self.restore_post_recording_controls()

    def restore_post_recording_controls(self):
        import_active = self.file_import_active()
        self.check_recording_consent.setChecked(False)
        self.btn_record.setEnabled(not import_active)
        self.btn_import.setEnabled(not import_active)
        self.btn_reload_model.setEnabled(not import_active)
        self.update_record_button_label()
        self.update_schedule_controls()
        self.update_summary_button_state()

    def set_summary_workflow_busy(self, busy: bool):
        self.summary_workflow_busy = bool(busy)
        attributes = vars(self)
        text_area = attributes.get("text_area")
        if text_area is not None:
            text_area.setReadOnly(self.summary_workflow_busy)
            set_enabled = getattr(text_area, "setEnabled", None)
            if set_enabled is not None:
                set_enabled(not self.summary_workflow_busy)
        for name in (
            "btn_confirm_segment",
            "btn_rename_speaker",
            "btn_export_review",
            "btn_confirm_claim",
            "btn_reject_claim",
            "btn_edit_claim",
        ):
            button = attributes.get(name)
            if button is not None:
                button.setEnabled(not self.summary_workflow_busy)
        if self.summary_workflow_busy:
            for name in ("btn_summary", "btn_record", "btn_import", "btn_reload_model"):
                button = attributes.get(name)
                if button is not None:
                    button.setEnabled(False)
            return

        import_active = self.file_import_active() if "pending_files" in attributes else False
        recording_active = attributes.get("recorder_thread") is not None
        scheduled = bool(attributes.get("scheduled_recording_pending", False))
        for name in ("btn_record", "btn_import", "btn_reload_model"):
            button = attributes.get(name)
            if button is not None:
                button.setEnabled(not import_active and not recording_active and not scheduled)
        if "btn_summary" in attributes:
            self.update_summary_button_state()
        if "check_schedule_recording" in attributes:
            self.update_schedule_controls()

    def update_summary_button_state(self):
        self.btn_summary.setEnabled(
            bool(self.transcript_without_summary().strip())
            and not vars(self).get("summary_workflow_busy", False)
            and not self.file_import_active()
            and not self.finalize_recording_pending
            and not self.scheduled_recording_pending
            and self.recorder_thread is None
            and not (self.summary_thread and self.summary_thread.isRunning())
            and not (self.ollama_runtime_thread and self.ollama_runtime_thread.isRunning())
            and not (self.ollama_pull_thread and self.ollama_pull_thread.isRunning())
        )

    @pyqtSlot(np.ndarray)
    def update_plot(self, data):
        data_len = len(data)
        plot_len = len(self.plot_data)

        if data_len >= plot_len:
            self.plot_data[:] = data[-plot_len:]
        else:
            self.plot_data = np.roll(self.plot_data, -data_len)
            self.plot_data[-data_len:] = data

        self.curve.setData(self.plot_data)

    @pyqtSlot(str)
    def update_log(self, text):
        self.text_area.append(text)
        self.text_area.verticalScrollBar().setValue(self.text_area.verticalScrollBar().maximum())
        self.update_summary_button_state()
        if self.recording_log_active():
            self.append_recording_event("live_transcript_update", "Live transcript text appended.", text=text)

    @pyqtSlot(object)
    def on_review_changed(self, _change):
        self.transcript_revision += 1
        self.update_summary_button_state()
        events = self.text_area.review.events
        if events and events[-1].get("event") == "segment.edited":
            self.reset_summary_claims()
        session_dir = getattr(self, "current_review_session_dir", None)
        meeting_id = getattr(self, "current_review_meeting_id", None)
        if session_dir and meeting_id:
            try:
                self.text_area.review.save(
                    session_dir,
                    meeting_id=meeting_id,
                    audio_path=getattr(self, "current_review_audio_path", None),
                )
            except OSError as exc:
                self.status_label.setText(
                    f"覆核內容仍保留在畫面中；寫入工作階段時發生錯誤：{exc}"
                )
                self.audit.record(
                    "review.autosave_failed",
                    category="workflow.review",
                    actor="user",
                    workflow="review",
                    outcome="error",
                    severity="error",
                    details={"error_class": type(exc).__name__},
                )
                return
        self.audit.record(
            "review.transcript_changed",
            category="workflow.review",
            actor="user",
            workflow="review",
        )

    def confirm_selected_segment(self):
        row = self.text_area.currentRow()
        if row < 0:
            self.status_label.setText("請先選取要確認的逐字稿片段。")
            return
        self.text_area.confirm_row(row)
        self.status_label.setText("✅ 已確認選取片段。")

    def play_selected_segment(self):
        row = self.text_area.currentRow()
        if row < 0 or row >= len(self.text_area.review.segments):
            self.status_label.setText("請先選取要播放的逐字稿片段。")
            return
        self.play_review_segment(self.text_area.review.segments[row].start_ms)

    def select_next_pending_segment(self):
        segment = self.text_area.select_next_pending()
        if segment is None:
            self.status_label.setText("✅ 本場逐字稿片段皆已完成覆核。")
            return
        self.status_label.setText(f"待覆核片段：{segment.segment_id}")

    def rename_selected_speaker(self):
        row = self.text_area.currentRow()
        if row < 0 or row >= len(self.text_area.review.segments):
            self.status_label.setText("請先選取要命名的講者片段。")
            return
        current_name = self.text_area.review.segments[row].speaker
        new_name, accepted = QInputDialog.getText(
            self,
            "套用本場講者名稱",
            f"將本場所有「{current_name}」改為：",
        )
        if not accepted or not new_name.strip():
            return
        changed = self.text_area.rename_speaker(current_name, new_name.strip())
        self.status_label.setText(f"✅ 已更新 {changed} 個講者片段。")

    def set_review_audio_source(self, audio_path: str | Path):
        path = Path(audio_path).expanduser().resolve()
        self.review_audio_path = path if path.exists() else None

    @pyqtSlot(int)
    def play_review_segment(self, start_ms: int):
        if not self.review_audio_path or not self.review_audio_path.exists():
            self.status_label.setText("這個工作階段目前沒有可播放的原始音訊。")
            return
        if self.review_player is None:
            self.review_audio_output = QAudioOutput(self)
            self.review_player = QMediaPlayer(self)
            self.review_player.setAudioOutput(self.review_audio_output)
        source = QUrl.fromLocalFile(str(self.review_audio_path))
        if self.review_player.source() != source:
            self.review_player.setSource(source)
        self.review_player.setPosition(max(0, int(start_ms)))
        self.review_player.play()
        self.status_label.setText(f"▶ 從 {start_ms / 1000:.1f} 秒播放原始音訊。")

    @pyqtSlot(str)
    def open_claim_source(self, segment_id: str):
        segment = self.text_area.select_segment(segment_id)
        if segment is None:
            self.status_label.setText(f"找不到來源片段 {segment_id}。")
            return
        self.play_review_segment(segment.start_ms)

    def review_selected_claim(self, review_status: str):
        try:
            self.summary_claims.review_selected(review_status)
        except OSError as exc:
            self.status_label.setText("覆核內容仍保留；覆核紀錄尚未寫入，請確認輸出空間後重試。")
            self.audit.record(
                "review.claim_write_failed",
                category="workflow.review",
                actor="user",
                workflow="review",
                outcome="error",
                severity="error",
                details={"error_class": type(exc).__name__},
            )
            return
        except ValueError:
            self.status_label.setText("這項主張需要來源片段後才能確認；可先退回並重新摘要。")
            return
        if self.summary_claims.currentRow() >= 0:
            action = "確認" if review_status == "confirmed" else "退回"
            self.status_label.setText(f"✅ 已{action}選取的摘要主張並保存覆核紀錄。")

    def edit_selected_claim(self):
        row = self.summary_claims.currentRow()
        if row < 0:
            self.status_label.setText("請先選取要編輯的摘要主張。")
            return
        current = self.summary_claims.item(
            row, self.summary_claims.CLAIM_COLUMN
        ).text()
        replacement, accepted = QInputDialog.getText(
            self,
            "編輯摘要主張",
            "人員校訂內容：",
            text=current,
        )
        if accepted and replacement.strip():
            try:
                self.summary_claims.edit_selected(replacement)
            except (OSError, ValueError, KeyError) as exc:
                self.status_label.setText("摘要主張維持原內容；覆核紀錄尚未寫入，請確認輸出空間後重試。")
                self.audit.record(
                    "review.claim_write_failed",
                    category="workflow.review",
                    actor="user",
                    workflow="review",
                    outcome="error",
                    severity="error",
                    details={
                        "action": "edit",
                        "error_class": type(exc).__name__,
                    },
                )
                return
            self.status_label.setText("✅ 已保存摘要主張的人員校訂紀錄。")

    def load_current_summary_claims(self):
        session_dir = self.current_summary_session_dir
        if not session_dir or not (Path(session_dir) / "summary.json").exists():
            return
        self.summary_claims.load_session(session_dir)
        visible = self.summary_claims.rowCount() > 0
        self.summary_claims.setVisible(visible)
        self.btn_confirm_claim.setVisible(visible)
        self.btn_reject_claim.setVisible(visible)
        self.btn_edit_claim.setVisible(visible)
        if visible:
            self.artifact_hint.setVisible(False)

    def reset_summary_claims(self):
        self.current_summary_session_dir = None
        self.summary_claims.clear_session()
        self.summary_claims.setVisible(False)
        self.btn_confirm_claim.setVisible(False)
        self.btn_reject_claim.setVisible(False)
        self.btn_edit_claim.setVisible(False)

    def save_review_artifacts(self, base_path: str | Path, metrics: dict | None = None) -> dict[str, Path]:
        if not self.text_area.review.segments:
            return {}
        base = Path(base_path)
        workflow = str((metrics or {}).get("workflow") or "review")
        source_path = (metrics or {}).get("source_path")
        session = ensure_transcript_session(
            base,
            workflow=workflow,
            source_path=source_path,
        )
        meeting_id = session.meeting_id
        if metrics is not None:
            metrics["meeting_id"] = meeting_id
        self.current_meeting_id = meeting_id
        audio_path = (
            (metrics or {}).get("recording_audio_path")
            or self.review_audio_path
            or (metrics or {}).get("source_path")
        )
        saved = self.text_area.review.save(
            session.directory,
            meeting_id=str(meeting_id),
            audio_path=audio_path,
        )
        self.current_review_session_dir = session.directory
        self.current_review_meeting_id = str(meeting_id)
        self.current_review_audio_path = audio_path
        exports = export_segments(self.text_area.review.segments, base.with_name(f"{base.name}_review"))
        saved.update({f"review_{name}": path for name, path in exports.items()})
        return saved

    def save_session_artifacts(
        self,
        base_path: str | Path,
        prepared: PreparedTranscript,
        summary: str,
        metrics: dict | None,
        *,
        default_workflow: str,
    ) -> dict[str, Path]:
        session = ensure_transcript_session(
            base_path,
            workflow=str((metrics or {}).get("workflow") or default_workflow),
            source_path=(metrics or {}).get("source_path"),
        )
        if metrics is not None:
            metrics["meeting_id"] = session.meeting_id
        saved = write_transcript_artifacts(
            base_path,
            prepared,
            summary_text=summary,
            metrics=metrics,
            session=session,
        )
        saved.update(self.save_review_artifacts(base_path, metrics))
        return saved

    def export_current_review(self):
        if not self.text_area.review.segments:
            self.status_label.setText("目前沒有可匯出的覆核片段。")
            return
        saved = self.save_review_artifacts(
            self.default_transcript_base_path(),
            self.current_recording_metrics or self.current_import_metrics,
        )
        if saved:
            self.remember_output_folder(next(iter(saved.values())).parent)
            self.status_label.setText("✅ 已匯出 JSON、Markdown、SRT 與 VTT 覆核結果。")

    @pyqtSlot(str)
    def update_status_only(self, text):
        self.status_label.setText(text)
        self.append_recording_event("status", text)
        if hasattr(self, "runtime_log"):
            self.runtime_log.append(f"{datetime.datetime.now().strftime('%H:%M:%S')} {text}")
            self.runtime_log.verticalScrollBar().setValue(self.runtime_log.verticalScrollBar().maximum())

    @pyqtSlot(object)
    def on_live_asr_telemetry(self, telemetry):
        if not isinstance(telemetry, dict):
            self.append_recording_event("live_asr_telemetry", str(telemetry))
            return
        fields = dict(telemetry)
        category = fields.pop("category", "live_asr_telemetry")
        message = fields.pop("message", "Live ASR telemetry captured.")
        self.append_recording_event(category, message, **fields)

    def summary_settings(self, prepared: PreparedTranscript | None = None) -> SummarySettings:
        metrics = self.current_recording_metrics or self.current_import_metrics
        base_path = metrics["base_path"] if metrics else self.default_transcript_base_path()
        session = ensure_transcript_session(
            base_path,
            workflow=str((metrics or {}).get("workflow") or "summary"),
            source_path=(metrics or {}).get("source_path"),
        )
        session_dir = str(session.directory)
        meeting_id = session.meeting_id
        self.current_summary_session_dir = session.directory
        if metrics:
            metrics["meeting_id"] = meeting_id
        self.current_meeting_id = meeting_id
        segments = tuple(segment.to_dict() for segment in self.text_area.review.segments)
        return SummarySettings(
            session_dir=session_dir,
            meeting_id=meeting_id,
            evidence_segments=segments,
            transcript_sha256=prepared.content_sha256 if prepared else "",
        )

    def prepare_transcript_input(self, transcript: str | PreparedTranscript) -> PreparedTranscript:
        if isinstance(transcript, PreparedTranscript):
            return transcript
        language = self.combo_lang.currentData() if hasattr(self, "combo_lang") else None
        punctuation_enabled = getattr(self.settings, "chinese_punctuation_enabled", True)
        return prepare_transcript(
            transcript,
            language=language,
            enable_punctuation=punctuation_enabled,
            enable_punctuation_model=False,
        )

    def transcript_without_summary(self) -> str:
        content = self.text_area.toPlainText()
        marker = "===== LLM Summary ====="
        if marker in content:
            return content.split(marker, 1)[0].strip()
        return content.strip()

    def summarize_current_transcript(self):
        transcript = self.transcript_without_summary()
        self.summary_audit_actor = "user"
        length = len(transcript)
        length_bucket = "empty" if not length else "short" if length < 1000 else "medium" if length < 10000 else "long"
        self.audit.record(
            "summary.requested",
            category="workflow.summary",
            actor="user",
            workflow="summary",
            outcome="attempted",
            details={"transcript_length_bucket": length_bucket},
        )
        self.prepare_llm_runtime_then_summarize(transcript)

    def prepare_llm_runtime_then_summarize(
        self,
        transcript: str | PreparedTranscript,
        finished_callback=None,
        summary_ready_callback=None,
    ):
        prepared = self.prepare_transcript_input(transcript)
        transcript = prepared.corrected_text
        if self.summary_audit_actor is None:
            self.summary_audit_actor = "system" if finished_callback else "user"
        if not transcript.strip():
            if finished_callback:
                QTimer.singleShot(0, finished_callback)
            return
        if self.summary_thread and self.summary_thread.isRunning():
            if finished_callback:
                self.summary_thread.finished.connect(finished_callback)
            return
        if self.ollama_runtime_thread and self.ollama_runtime_thread.isRunning():
            return
        if self.ollama_pull_thread and self.ollama_pull_thread.isRunning():
            return

        settings = self.summary_settings(prepared)
        summary_revision = self.transcript_revision
        self.set_summary_workflow_busy(True)
        self.ollama_runtime_thread = OllamaRuntimeThread()
        self.ollama_runtime_thread.status_updated.connect(self.update_status_only)
        self.ollama_runtime_thread.server_process_started.connect(self.on_ollama_server_process_started)
        self.ollama_runtime_thread.ready.connect(
            lambda prepared=prepared, settings=settings, summary_revision=summary_revision, finished_callback=finished_callback, summary_ready_callback=summary_ready_callback: self.start_summary(
                prepared,
                finished_callback=finished_callback,
                summary_ready_callback=summary_ready_callback,
                settings=settings,
                summary_revision=summary_revision,
            )
        )
        self.ollama_runtime_thread.model_missing.connect(
            lambda model_tag, prepared=prepared, settings=settings, summary_revision=summary_revision, finished_callback=finished_callback, summary_ready_callback=summary_ready_callback: self.on_ollama_model_missing(
                model_tag,
                prepared,
                finished_callback=finished_callback,
                summary_ready_callback=summary_ready_callback,
                settings=settings,
                summary_revision=summary_revision,
            )
        )
        self.ollama_runtime_thread.failed.connect(
            lambda err_msg, finished_callback=finished_callback: self.on_ollama_runtime_failed(
                err_msg,
                finished_callback=finished_callback,
            )
        )
        self.ollama_runtime_thread.start()

    @pyqtSlot(object)
    def on_ollama_server_process_started(self, process):
        self.ollama_server_process = process
        self.ollama_server_started_by_aura = True

    @pyqtSlot(str)
    def on_ollama_runtime_failed(self, err_msg: str, finished_callback=None):
        self.audit.record(
            "summary.runtime_failed",
            category="workflow.summary",
            actor=self.summary_audit_actor or "system",
            workflow="summary",
            outcome="error",
            severity="error",
            details={"error_class": "ollama_runtime_error"},
        )
        self.summary_audit_actor = None
        self.summary_audit_started_perf = None
        self.set_summary_workflow_busy(False)
        self.show_diagnostic_error(self.strings.summary_failed, err_msg)
        if finished_callback:
            QTimer.singleShot(0, finished_callback)

    def on_ollama_model_missing(
        self,
        model_tag: str,
        transcript: str | PreparedTranscript,
        finished_callback=None,
        summary_ready_callback=None,
        *,
        settings: SummarySettings | None = None,
        summary_revision: int | None = None,
    ):
        self.audit.record(
            "summary.model_missing",
            category="workflow.summary",
            actor=self.summary_audit_actor or "system",
            workflow="summary",
            outcome="rejected",
            severity="warning",
            details={"model_id": model_tag},
        )
        command = f"ollama pull {model_tag}"
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Warning)
        message.setWindowTitle(self.strings.ollama_model_missing_title)
        message.setText(self.strings.ollama_model_missing_message.format(model_tag=model_tag))
        pull_button = message.addButton(self.strings.ollama_pull_model, QMessageBox.ButtonRole.AcceptRole)
        copy_button = message.addButton(self.strings.ollama_copy_command, QMessageBox.ButtonRole.ActionRole)
        cancel_button = message.addButton(self.strings.ollama_cancel, QMessageBox.ButtonRole.RejectRole)
        message.setDefaultButton(pull_button)
        message.exec()
        clicked = message.clickedButton()
        if clicked is pull_button:
            self.audit.record(
                "summary.model_pull_selected",
                category="workflow.summary",
                actor="user",
                workflow="summary",
                outcome="attempted",
                details={"model_id": model_tag},
            )
            self.pull_ollama_model_then_summarize(
                model_tag,
                transcript,
                finished_callback=finished_callback,
                summary_ready_callback=summary_ready_callback,
                settings=settings,
                summary_revision=summary_revision,
            )
            return
        if clicked is copy_button:
            QApplication.clipboard().setText(command)
            self.update_status_only(self.strings.ollama_pull_command_copied)
        if clicked in (copy_button, cancel_button) or clicked is None:
            self.summary_audit_actor = None
            self.summary_audit_started_perf = None
            self.set_summary_workflow_busy(False)
        if (clicked in (copy_button, cancel_button) or clicked is None) and finished_callback:
            QTimer.singleShot(0, finished_callback)

    def pull_ollama_model_then_summarize(
        self,
        model_tag: str,
        transcript: str | PreparedTranscript,
        finished_callback=None,
        summary_ready_callback=None,
        *,
        settings: SummarySettings | None = None,
        summary_revision: int | None = None,
    ):
        self.btn_summary.setEnabled(False)
        self.ollama_pull_thread = OllamaPullThread(model_tag)
        self.ollama_pull_thread.status_updated.connect(self.update_status_only)
        self.ollama_pull_thread.pulled.connect(
            lambda transcript=transcript, settings=settings, summary_revision=summary_revision, finished_callback=finished_callback, summary_ready_callback=summary_ready_callback: self.start_summary(
                transcript,
                finished_callback=finished_callback,
                summary_ready_callback=summary_ready_callback,
                settings=settings,
                summary_revision=summary_revision,
            )
        )
        self.ollama_pull_thread.failed.connect(
            lambda err_msg, finished_callback=finished_callback: self.on_ollama_runtime_failed(
                err_msg,
                finished_callback=finished_callback,
            )
        )
        self.ollama_pull_thread.start()

    def summarize_after_live_asr_idle(self):
        if self.transcriber_thread.is_idle():
            self.summarize_current_transcript()
            return
        QTimer.singleShot(1000, self.summarize_after_live_asr_idle)

    def enable_reload_after_live_asr_idle(self):
        if self.recorder_thread is not None or self.file_import_active():
            return
        if self.transcriber_thread.is_idle():
            self.btn_reload_model.setEnabled(True)
            return
        QTimer.singleShot(1000, self.enable_reload_after_live_asr_idle)

    def start_summary(
        self,
        transcript: str | PreparedTranscript,
        finished_callback=None,
        summary_ready_callback=None,
        *,
        settings: SummarySettings | None = None,
        summary_revision: int | None = None,
    ):
        prepared = self.prepare_transcript_input(transcript)
        transcript = prepared.corrected_text
        if not transcript:
            self.set_summary_workflow_busy(False)
            if finished_callback:
                QTimer.singleShot(0, finished_callback)
            return
        if self.summary_thread and self.summary_thread.isRunning():
            if finished_callback:
                self.summary_thread.finished.connect(finished_callback)
            return
        self.btn_summary.setEnabled(False)
        self.summary_audit_started_perf = time.perf_counter()
        self.audit.record(
            "summary.started",
            category="workflow.summary",
            actor=self.summary_audit_actor or "system",
            workflow="summary",
        )
        self.summary_thread = SummaryThread(
            transcript,
            settings or self.summary_settings(prepared),
        )
        summary_revision = (
            self.transcript_revision
            if summary_revision is None
            else summary_revision
        )
        self.summary_thread.summary_ready.connect(
            lambda text, revision=summary_revision: self.update_summary_log(text, revision)
        )
        if summary_ready_callback:
            self.summary_thread.summary_ready.connect(
                lambda text, revision=summary_revision: (
                    summary_ready_callback(text)
                    if revision == self.transcript_revision
                    else None
                )
            )
        self.summary_thread.status_updated.connect(self.update_status_only)
        self.summary_thread.error_signal.connect(self.on_summary_error)
        self.summary_thread.finished.connect(
            lambda: self.set_summary_workflow_busy(False)
        )
        if finished_callback:
            self.summary_thread.finished.connect(finished_callback)
        self.summary_thread.start()

    def update_summary_log(self, text: str, revision: int):
        if revision == self.transcript_revision:
            self.update_log(text)
            duration_ms = (
                round((time.perf_counter() - self.summary_audit_started_perf) * 1000, 3)
                if self.summary_audit_started_perf is not None
                else None
            )
            self.audit.record(
                "summary.completed",
                category="workflow.summary",
                actor=self.summary_audit_actor or "system",
                workflow="summary",
                details={"duration_ms": duration_ms},
            )
            self.summary_audit_actor = None
            self.summary_audit_started_perf = None
            self.load_current_summary_claims()

    @pyqtSlot(str)
    def on_summary_error(self, err_msg):
        self.audit.record(
            "summary.generation_failed",
            category="workflow.summary",
            actor=self.summary_audit_actor or "system",
            workflow="summary",
            outcome="error",
            severity="error",
            details={"error_class": "summary_generation_error"},
        )
        self.summary_audit_actor = None
        self.summary_audit_started_perf = None
        self.show_diagnostic_error(self.strings.summary_failed, err_msg)

    def on_recording_thread_finished(self, recorder_thread, wav_path):
        if Path(wav_path).exists():
            self.set_review_audio_source(wav_path)
            if self.current_recording_metrics is not None:
                recording_session = getattr(recorder_thread, "recording_session", None)
                recording_outcome = (
                    getattr(recording_session, "manifest", {}).get("recording_outcome")
                    if recording_session is not None
                    else None
                )
                if recording_outcome == "partial":
                    self.current_recording_metrics["recording_outcome"] = "partial"
                    self.current_recording_metrics["requires_human_confirmation"] = True
                    self.append_recording_event(
                        "recording_partial_preserved",
                        "Capture ended early; durable partial audio remains available for review.",
                    )
                self.current_recording_metrics["recording_raw_wav_path"] = str(Path(wav_path).resolve())
                self.current_recording_metrics.setdefault("outputs", {})["recording_mixed_wav"] = str(
                    Path(wav_path).resolve()
                )
        self.process_audio(wav_path)
        if self.recorder_thread is not recorder_thread:
            return
        if self.finalize_recording_pending:
            self.recorder_thread = None
            QTimer.singleShot(0, self.finalize_recording_after_live_asr_idle)
            return
        trigger = (
            "no_voice_auto_stop"
            if getattr(recorder_thread, "auto_stopped_for_no_voice", False)
            else "recorder_thread_finished"
        )
        self.stop_recording_session(
            trigger,
            recorder_thread=recorder_thread,
            thread_already_finished=True,
        )

    @pyqtSlot(str)
    def process_audio(self, wav_path):
        if Path(wav_path).suffix.lower() != ".wav" or not Path(wav_path).is_file():
            self.append_recording_event("recording_audio_unavailable", wav_path)
            self.audit.record(
                "recording.audio_export_failed",
                category="workflow.recording",
                workflow="recording",
                outcome="error",
                severity="error",
                details={"error_class": "audio_unavailable"},
            )
            return
        metrics = self.current_recording_metrics
        base_path = self.default_transcript_base_path() if metrics is not None else None
        target_dbfs = float(self.spin_norm.value())
        runtime_config = metrics.get("recording_runtime_config", {}) if metrics is not None else {}
        audio_format = runtime_config.get("recording_audio_format") or self.selected_recording_audio_format()
        audio_spec = recording_audio_format_spec(audio_format)
        self.append_event_to_metrics(
            metrics,
            "recording_audio_export_started",
            "Recording audio export started.",
            audio_format=audio_format,
            codec=audio_spec.codec,
            wav_path=wav_path,
            target_dbfs=target_dbfs,
        )
        self.executor.submit(self._normalization_task, wav_path, target_dbfs, audio_format, metrics, base_path)

    def _normalization_task(self, wav_path, target_dbfs, audio_format="m4a", metrics=None, base_path=None):
        audio_spec = recording_audio_format_spec(audio_format)
        try:
            audio_path = normalize_wav_to_recording_audio(
                wav_path,
                target_dbfs,
                audio_format,
                remove_source=False,
            )
            if metrics is not None:
                metrics["recording_audio_path"] = str(audio_path)
                metrics["recording_audio_format"] = audio_format
                metrics["recording_audio_codec"] = audio_spec.codec
                metrics["recording_audio_export_finished_at"] = self.timestamp_now()
                metrics.setdefault("outputs", {})["recording_audio"] = str(audio_path)
            self.append_event_to_metrics(
                metrics,
                "recording_audio_export_finished",
                "Recording audio export finished.",
                audio_format=audio_format,
                codec=audio_spec.codec,
                wav_path=wav_path,
                audio_path=str(audio_path),
                target_dbfs=target_dbfs,
            )
            self.audit.record(
                "recording.audio_export_completed",
                category="workflow.recording",
                workflow="recording",
                details={"audio_format": audio_format, "codec": audio_spec.codec},
            )
            if base_path and metrics is not None:
                write_event_log_file(base_path, metrics)
                write_json_file(transcript_artifact_paths(base_path)["metrics"], metrics)
        except Exception as e:
            logger.exception("Recording normalization failed: %s", e)
            self.append_event_to_metrics(
                metrics,
                "recording_audio_export_failed",
                "Recording audio export failed.",
                audio_format=audio_format,
                codec=audio_spec.codec,
                wav_path=wav_path,
                target_dbfs=target_dbfs,
                error=str(e),
            )
            self.audit.record(
                "recording.audio_export_failed",
                category="workflow.recording",
                workflow="recording",
                outcome="error",
                severity="error",
                details={"error_class": type(e).__name__, "audio_format": audio_format},
            )
            if base_path and metrics is not None:
                write_event_log_file(base_path, metrics)
                write_json_file(transcript_artifact_paths(base_path)["metrics"], metrics)

    def stop_threads(self):
        self.scheduled_start_timer.stop()
        self.scheduled_stop_timer.stop()
        if self.recorder_thread:
            self.recorder_thread.running = False
            if not self.recorder_thread.wait(5000):
                logger.warning("Recorder did not finalize within 5 seconds; its PCM journal remains recoverable.")
        try:
            self.shutdown_backup_preserved = self.preserve_recording_shutdown_transcript()
        except (OSError, ValueError):
            self.shutdown_backup_preserved = False
            logger.exception(
                "Could not copy the provisional transcript into the recording session; "
                "the runtime backup will be retained."
            )
        self.close_recording_runtime_log()
        self.transcriber_thread.stop()
        if self.file_thread and self.file_thread.isRunning():
            self.file_thread.request_cancel()
            self.file_thread.wait(2000)
        final_recording_thread = getattr(self, "final_recording_thread", None)
        if final_recording_thread and final_recording_thread.isRunning():
            final_recording_thread.request_cancel()
            final_recording_thread.wait(5000)
        if self.summary_thread and self.summary_thread.isRunning():
            self.summary_thread.quit()
            self.summary_thread.wait(2000)
        if self.ollama_runtime_thread and self.ollama_runtime_thread.isRunning():
            self.ollama_runtime_thread.quit()
            self.ollama_runtime_thread.wait(2000)
        if self.ollama_pull_thread and self.ollama_pull_thread.isRunning():
            self.ollama_pull_thread.quit()
            self.ollama_pull_thread.wait(2000)
        if self.ollama_server_started_by_aura and self.ollama_server_process is not None:
            if self.ollama_server_process.poll() is None:
                self.ollama_server_process.terminate()
            self.ollama_server_process = None
            self.ollama_server_started_by_aura = False

    def preserve_recording_shutdown_transcript(self):
        attributes = vars(self)
        metrics = attributes.get("current_recording_metrics") or attributes.get(
            "current_import_metrics"
        )
        backup = transcript_backup_path()
        if not metrics:
            return not backup.is_file()
        if not backup.is_file():
            return True
        text = backup.read_text(encoding="utf-8").strip()
        if not text:
            return True
        session = ensure_transcript_session(
            metrics["base_path"],
            workflow=str(metrics.get("workflow") or "recording"),
            source_path=metrics.get("source_path"),
        )
        provisional_path = session.directory / "provisional_transcript.txt"
        write_transcript_file(provisional_path, text)
        manifest_path = session.directory / "session.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["provisional_transcript"] = provisional_path.name
        manifest["recovery_next_action"] = "review_or_retranscribe_audio"
        write_session_manifest(manifest_path, manifest)
        return True

    def update_runtime_model_status(self):
        if hasattr(self, "runtime_model_label"):
            self.runtime_model_label.setText(
                self.strings.runtime_model_status.format(status=self.asr_model_status)
            )
        if hasattr(self, "top_model_label"):
            self.top_model_label.setText(self.strings.top_model_status.format(status=self.asr_model_status))

    def refresh_runtime_diagnostics(self):
        diagnostics = collect_runtime_diagnostics(
            asr_model_status=self.asr_model_status,
            output_folder=self.resolved_output_folder(self.current_folder),
        )
        self.latest_runtime_report = format_runtime_report(diagnostics)
        self.runtime_gpu_label.setText(
            self.strings.runtime_gpu_status.format(status="yes" if diagnostics.gpu.gpu_detected else "no")
        )
        self.top_gpu_label.setText(
            self.strings.top_gpu_status.format(status="ready" if diagnostics.gpu.gpu_detected else "not detected")
        )
        self.runtime_cuda_label.setText(
            self.strings.runtime_cuda_status.format(
                status="ready" if diagnostics.gpu.cuda_ready else "incomplete"
            )
        )
        self.runtime_model_label.setText(
            self.strings.runtime_model_status.format(status=diagnostics.asr_model_status)
        )
        self.runtime_audio_label.setText(
            self.strings.runtime_audio_status.format(status=diagnostics.audio.status_line)
        )
        self.runtime_output_label.setText(
            self.strings.runtime_output_status.format(
                status="yes" if diagnostics.output_folder_writable else "no"
            )
        )
        self.update_first_launch_checks(diagnostics)
        ready = {
            "gpu_ready": bool(diagnostics.gpu.gpu_detected),
            "cuda_ready": bool(diagnostics.gpu.cuda_ready),
            "audio_ready": bool(diagnostics.audio.input_ready),
            "output_ready": bool(diagnostics.output_folder_writable),
            "disk_space_ready": bool(diagnostics.output_folder_space_ready),
            "ollama_ready": bool(diagnostics.ollama.ready),
        }
        self.audit.record(
            "diagnostics.completed",
            category="system.runtime",
            workflow="diagnostics",
            outcome="success" if all(ready.values()) else "rejected",
            severity="info" if all(ready.values()) else "warning",
            details=ready,
        )

    def update_first_launch_checks(self, diagnostics):
        for check in first_launch_checks(diagnostics):
            status = self.strings.first_launch_ready if check.ready else self.strings.first_launch_needs_attention
            if check.key in self.first_launch_check_labels:
                self.first_launch_check_labels[check.key].setText(
                    self.strings.first_launch_status.format(label=check.label, status=status)
                )
                self.first_launch_check_labels[check.key].setToolTip(check.detail)
            if check.key in self.first_launch_fix_buttons:
                self.first_launch_fix_buttons[check.key].setEnabled(not check.ready)
                self.first_launch_fix_buttons[check.key].setToolTip(check.fix_guidance)
            for button in self.first_launch_action_buttons.get(check.key, ()):
                button.setEnabled(not check.ready)
            self.first_launch_guidance[check.key] = {
                "label": check.label,
                "detail": check.detail,
                "fix_guidance": check.fix_guidance,
            }

    def show_first_launch_fix(self, key: str):
        guidance = self.first_launch_guidance.get(key)
        if not guidance:
            self.refresh_runtime_diagnostics()
            guidance = self.first_launch_guidance.get(key)
        if not guidance:
            return
        self.audit.record(
            "diagnostics.fix_guide_opened",
            category="system.runtime",
            actor="user",
            workflow="diagnostics",
            details={"check": key},
        )
        QMessageBox.information(
            self,
            guidance["label"],
            f"{guidance['detail']}\n\n{guidance['fix_guidance']}",
        )

    def setup_folder_path(self) -> Path:
        current = Path(os.getcwd()).resolve()
        candidates = [
            current / "docs",
            current.parent / "docs",
        ]
        for candidate in candidates:
            if (candidate / "windows_setup.md").exists():
                return candidate
        return current

    def open_setup_folder(self):
        webbrowser.open(self.setup_folder_path().as_uri())
        self.audit.record(
            "diagnostics.setup_folder_opened",
            category="system.runtime",
            actor="user",
            workflow="diagnostics",
        )

    def current_runtime_report(self) -> str:
        if not self.latest_runtime_report:
            self.latest_runtime_report = build_runtime_report(asr_model_status=self.asr_model_status)
        return self.latest_runtime_report

    def copy_runtime_report(self):
        self.refresh_runtime_diagnostics()
        QApplication.clipboard().setText(self.current_runtime_report())
        self.status_label.setText(self.strings.runtime_report_copied)
        self.audit.record(
            "diagnostics.report_copied",
            category="system.runtime",
            actor="user",
            workflow="diagnostics",
        )

    def show_diagnostic_error(self, title: str, message: str):
        self.audit.record(
            "diagnostics.error_shown",
            category="system.runtime",
            workflow="diagnostics",
            outcome="error",
            severity="error",
            details={"error_class": "runtime_diagnostic_error"},
        )
        self.refresh_runtime_diagnostics()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(message)
        box.setDetailedText(self.current_runtime_report())
        copy_button = box.addButton(self.strings.runtime_copy_report, QMessageBox.ButtonRole.ActionRole)
        box.exec()
        if box.clickedButton() is copy_button:
            QApplication.clipboard().setText(self.current_runtime_report())
            self.status_label.setText(self.strings.runtime_report_copied)
