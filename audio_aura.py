"""
Ultimate Audio Assistant
====================================
A dual-core tool integrating "Real-time Voice/Audio-to-Transcript" and "Intelligent Track Splitting." (Comprehensive Audio Assistant)

Version Management Strategy (Semantic Versioning):
- MAJOR: Significant architectural changes or incompatible modifications.
- MINOR: New backward-compatible features.
- PATCH: Backward-compatible bug fixes.
"""

__version__ = "2.1.0"
__author__ = "Jason Chia-Sheng Lin (PhD. Student)"
__organization__ = "NYCU"
__date__ = "2026-03-04"

import time
import sys
import os
import queue
import gc
import wave
import requests
import webbrowser
import datetime
import numpy as np
import pyaudio
import webrtcvad
from concurrent.futures import ThreadPoolExecutor
from ctypes import *
from contextlib import contextmanager

# Video & Audio Processing
from pydub import AudioSegment
from pydub.silence import detect_silence
import noisereduce as nr
from pydub.utils import mediainfo
from faster_whisper import WhisperModel

# PyQt6 UI & Visualization
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTextEdit, 
                             QLineEdit, QMessageBox, QFileDialog, QTabWidget,
                             QProgressBar, QSpinBox, QComboBox, QCheckBox,
                             QSystemTrayIcon, QMenu, QStyle)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, pyqtSlot
from PyQt6.QtGui import QFont, QAction, QIcon
import pyqtgraph as pg
from qt_material import apply_stylesheet

# ==========================================
# System Settings & ALSA Error Masking (For Linux Environments)
# ==========================================
SAMPLE_RATE = 16000
CHUNK_MS = 30
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_MS / 1000)
VAD_LEVEL = 3
MODEL_ID = "SoybeanMilk/faster-whisper-Breeze-ASR-25"
DEVICE = "cuda" 
COMPUTE_TYPE = "float16" 

ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
def py_error_handler(filename, line, function, err, fmt):
    pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

@contextmanager
def no_alsa_err():
    try:
        asound = cdll.LoadLibrary('libasound.so.2')
        asound.snd_lib_error_set_handler(c_error_handler)
        yield
        asound.snd_lib_error_set_handler(None)
    except:
        yield


# ==========================================
# [Core Thread] Transcript Functionality
# ==========================================
class FileTranscriberThread(QThread):
    text_updated = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, model, file_path, target_dbfs=-20.0, beam_size=5, initial_prompt="", language="zh"):
        super().__init__()
        self.model = model
        self.file_path = file_path
        self.target_dbfs = target_dbfs
        self.beam_size = beam_size
        self.initial_prompt = initial_prompt
        self.language = language

    def run(self):
        self.status_updated.emit("⏳ Analyzing audio file, please wait...")
        temp_path = None
        audio = None
        normalized = None
        try:
            # 1. Pre-normalize Volume (Normalize)
            self.status_updated.emit("🔊 Analyzing audio volume...")
            audio = AudioSegment.from_file(self.file_path)
            normalized = audio.apply_gain(self.target_dbfs - audio.dBFS)
            temp_path = os.path.join(os.getcwd(), "temp_normalized.wav")
            normalized.export(temp_path, format="wav")

                # faster-whisper natively supports direct reading of common media files
            segments, info = self.model.transcribe(
                temp_path,
                beam_size=self.beam_size, 
                language=self.language,
                condition_on_previous_text=True, # Ensure context association is enabled (Default is True, but explicit is better)
                initial_prompt=self.initial_prompt
            )


            for segment in segments:
                h, m = divmod(int(segment.start), 3600)
                m, s = divmod(m, 60)
                timestamp = f"{h:02d}:{m:02d}:{s:02d}"
                formatted_text = f"[{timestamp}] {segment.text}"
                self.text_updated.emit(formatted_text)
                
                # Auto-backup
                with open("temp_transcript.txt", "a", encoding="utf-8") as f:
                    f.write(formatted_text + "\n")
            self.status_updated.emit("✅ File processing completed!")
        except Exception as e:
            self.status_updated.emit(f"❌ File processing failed: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            
            # Proactively release memory
            if audio: del audio
            if normalized: del normalized
            gc.collect()
            self.finished_signal.emit()

class ModelLoaderThread(QThread):
    """Thread specialized for asynchronous loading of the Whisper model to avoid UI freezing"""
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, device, compute_type):
        super().__init__()
        self.device = device
        self.compute_type = compute_type

    def run(self):
        try:
            self.status_signal.emit(f"🚀 Loading model in background ({self.device}/{self.compute_type})...")
            # Execute time-consuming model initialization
            model = WhisperModel(MODEL_ID, device=self.device, compute_type=self.compute_type)
            self.finished_signal.emit(model)
        except Exception as e:
            # Capture potential CUDA out-of-memory or driver issues
            error_msg = str(e)
            if "out of memory" in error_msg.lower():
                error_msg = "Insufficient GPU memory. Try switching to int8 precision or closing other programs."
            self.error_signal.emit(error_msg)

class UpdateCheckerThread(QThread):
    """Check GitHub for new versions"""
    found_update = pyqtSignal(str, str) # version, url

    def run(self):
        try:
            # Please replace this with your actual GitHub Repo (User/Repo)
            # This is an example path; modify it during implementation
            repo_url = "https://api.github.com/repos/JasonLin/UltimateAudioAssistant/releases/latest"
            response = requests.get(repo_url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                latest_ver = data['tag_name'].lstrip('v')
                current_ver = __version__.lstrip('v')
                if latest_ver > current_ver:
                    self.found_update.emit(latest_ver, data['html_url'])
        except:
            pass # Silent failure on network issues or API limits, does not affect main program

class TranscriberThread(QThread):
    text_updated = pyqtSignal(str)
    status_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.audio_queue = queue.Queue()
        self.running = True
        self.model = None
        self.device = DEVICE
        self.compute_type = COMPUTE_TYPE

    def run(self):
        # After thread starts, enter loop waiting for model and audio
        while self.running:
            try:
                if self.model is None:
                    time.sleep(0.5)
                    continue
                    
                audio_data = self.audio_queue.get(timeout=1)
                segments, info = self.model.transcribe(
                    audio_data, beam_size=5, language="zh",
                    initial_prompt="The following is a professional meeting record."
                )
                text_segment = "".join([s.text for s in segments])
                if text_segment.strip():
                    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                    formatted_text = f"[{timestamp}] {text_segment}"
                    self.text_updated.emit(formatted_text)
                    with open("temp_transcript.txt", "a", encoding="utf-8") as f:
                        f.write(formatted_text + "\n")
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Transcription error: {e}")

    def add_audio(self, audio_np):
        self.audio_queue.put(audio_np)

    def stop(self):
        self.running = False

class AudioRecorderThread(QThread):
    waveform_signal = pyqtSignal(np.ndarray)
    finished_signal = pyqtSignal(str)
    
    def __init__(self, filename, transcriber_thread, enable_denoise=False):
        super().__init__()
        self.filename = filename
        self.transcriber = transcriber_thread
        self.enable_denoise = enable_denoise
        self.running = True
        self.vad = webrtcvad.Vad(VAD_LEVEL)
        self.full_frames = []

    def run(self):
        with no_alsa_err():
            pa = pyaudio.PyAudio()
        
        # 1. Prioritize finding pulse virtual device (supports auto-resampling, solves Invalid sample rate)
        target_device_index = None
        target_channels = 1
        
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if 'pulse' in info['name'].lower():
                target_device_index = i
                target_channels = int(info['maxInputChannels']) if info['maxInputChannels'] > 0 else 1
                break
        
        try:
            # Try using the found pulse device or system default device
            if target_device_index is not None:
                print(f"🚀 Mounting PulseAudio virtual device: Index {target_device_index}, Channels: {target_channels}")
                stream = pa.open(format=pyaudio.paInt16, channels=target_channels, rate=SAMPLE_RATE,
                                 input=True, input_device_index=target_device_index, frames_per_buffer=CHUNK_SIZE)
            else:
                print("⚠️ Pulse device not found, trying system default device...")
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                                 input=True, frames_per_buffer=CHUNK_SIZE)
                target_channels = 1
        except Exception as e:
            # Ultimate Fallback: If even default fails, emit error for subsequent handling
            self.finished_signal.emit(f"Hardware mounting failed: {str(e)}")
            pa.terminate()
            return

        silence_frames = 0
        speech_buffer = []
        min_speech_len = 0.5 

        while self.running:
            try:
                raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                np_data = np.frombuffer(raw_data, dtype=np.int16)
                
                # Dynamic down-mixing: Reshape multi-channel and extract only the first channel (Channel 0)
                if target_channels > 1:
                    # reshape to [frames, channels], then take the first column
                    np_data = np_data.reshape(-1, target_channels)[:, 0].copy()
                    vad_data = np_data.tobytes() 
                else:
                    vad_data = raw_data

                self.waveform_signal.emit(np_data)
                
                if self.vad.is_speech(vad_data, SAMPLE_RATE):
                    self.full_frames.append(vad_data)
                    speech_buffer.append(np_data)
                    silence_frames = 0
                else:
                    self.full_frames.append(vad_data) 
                    silence_frames += 1

                if len(speech_buffer) > 0 and silence_frames > (1000/CHUNK_MS * min_speech_len):
                    # Merge collected speech
                    audio_np = np.concatenate(speech_buffer).flatten().astype(np.float32) / 32768.0
                    
                    # 🌟 Denoising: Denoise the entire sentence; better effect and more efficient than per-frame
                    if self.enable_denoise:
                        try:
                            audio_np = nr.reduce_noise(y=audio_np, sr=SAMPLE_RATE, stationary=True, prop_decrease=0.75)
                        except Exception as e:
                            print(f"Denoising failed (skipped): {e}")
                    
                    # 🌟 Key 3: Force 0.5s of silence at the end (Zero Padding)
                    padding_length = int(SAMPLE_RATE * 0.5) 
                    silence_padding = np.zeros(padding_length, dtype=np.float32)
                    padded_audio_np = np.concatenate([audio_np, silence_padding])
                    
                    self.transcriber.add_audio(padded_audio_np) # Send audio with silence tail
                    speech_buffer = [] 
                    silence_frames = 0 # Reset counter
                    
            except Exception as e:
                print(f"Audio loop error: {e}")
                break

        stream.stop_stream()
        stream.close()
        pa.terminate()
        
        # Safety check for no data when recording stops
        if not self.full_frames:
            self.finished_signal.emit("No audio recorded")
            return

        wav_path = self.filename + ".wav"
        with wave.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(self.full_frames))
        self.finished_signal.emit(wav_path)

# ==========================================
# [核心執行緒] 智慧切割功能區
# ==========================================
class SmartSplitterThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, file_path, output_dir, target_minutes=40, tolerance_minutes=5):
        super().__init__()
        self.file_path = file_path
        self.output_dir = output_dir
        self.target_ms = target_minutes * 60 * 1000
        self.tolerance_ms = tolerance_minutes * 60 * 1000

    def run(self):
        audio = None
        try:
            self.log_signal.emit(f"⏳ Loading audio file...\nFile: {self.file_path}")
            self.progress_signal.emit(5)
            
            audio = AudioSegment.from_file(self.file_path)
            total_duration_ms = len(audio)
            self.log_signal.emit(f"✅ Load successful! Total duration: {total_duration_ms / 60000:.2f} minutes")

            # Try to get original bitrate to avoid forced 192k making files larger
            try:
                info = mediainfo(self.file_path)
                original_bitrate = info.get('bit_rate', None)
            except:
                original_bitrate = None
            
            base_name = os.path.splitext(os.path.basename(self.file_path))[0]
            ext = os.path.splitext(self.file_path)[1].lower().replace(".", "")
            if ext not in ["mp3", "wav", "m4a", "ogg", "flac"]:
                ext = "mp3" 
            
            current_pos = 0
            chunk_index = 1
            
            while current_pos < total_duration_ms:
                if (total_duration_ms - current_pos) <= (self.target_ms + self.tolerance_ms):
                    self.log_signal.emit(f"✂️ Exporting final segment (Part {chunk_index})...")
                    final_chunk = audio[current_pos:]
                    self.export_chunk(final_chunk, base_name, chunk_index, ext, original_bitrate)
                    self.progress_signal.emit(100)
                    break
                
                search_start = current_pos + self.target_ms - self.tolerance_ms
                search_end = min(current_pos + self.target_ms + self.tolerance_ms, total_duration_ms)
                self.log_signal.emit(f"🔍 Analyzing best cut point for Part {chunk_index} ({search_start/60000:.1f} ~ {search_end/60000:.1f} min)...")
                
                window = audio[search_start:search_end]
                silences = detect_silence(window, min_silence_len=1000, silence_thresh=audio.dBFS - 16)
                
                if silences:
                    best_silence = silences[len(silences)//2]
                    cut_point = search_start + (best_silence[0] + best_silence[1]) // 2
                    self.log_signal.emit(f"🎯 Found suitable pause point! Cutting at {cut_point/60000:.2f} minutes.")
                else:
                    cut_point = current_pos + self.target_ms
                    self.log_signal.emit(f"⚠️ No obvious pause found, performing smooth cut at {cut_point/60000:.2f} minutes.")
                
                chunk = audio[current_pos:cut_point]
                if not silences: chunk = chunk.fade_out(100)
                
                self.log_signal.emit(f"💾 Saving Part {chunk_index}...")
                self.export_chunk(chunk, base_name, chunk_index, ext, original_bitrate)
                
                current_pos = cut_point
                chunk_index += 1
                self.progress_signal.emit(int((current_pos / total_duration_ms) * 90) + 5)

            self.log_signal.emit("🎉 所有片段切割並儲存完畢！")
            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            # Ensure large audio objects are released
            if audio: del audio
            gc.collect()

    def export_chunk(self, chunk, base_name, index, ext, bitrate=None):
        out_path = os.path.join(self.output_dir, f"{base_name}_part{index:02d}.{ext}")
        export_kwargs = {"format": ext}
        if ext == "mp3":
            # Use original bitrate if detected, otherwise default to 192k
            target_bitrate = str(bitrate) if bitrate else "192k"
            export_kwargs["bitrate"] = target_bitrate
        chunk.export(out_path, **export_kwargs)


# ==========================================
# [UI] 頁籤 1: 逐字稿生成 (Transcription Tab)
# ==========================================
class TranscriptionTab(QWidget):
    def __init__(self):
        super().__init__()
        self.recorder_thread = None
        self.file_thread = None
        self.transcriber_thread = TranscriberThread()
        self.transcriber_thread.text_updated.connect(self.update_log)
        self.transcriber_thread.status_updated.connect(self.update_status_only)
        self.transcriber_thread.start()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.pending_files = [] # Batch task queue
        self.model_loader = None # Async loader
        self.total_batch_count = 0 # Batch total record
        self.update_checker = None
        
        self.current_folder = os.getcwd()
        self.current_filename = "transcript"
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        
        info_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Waiting for GPU initialization...")
        self.status_label.setStyleSheet("font-weight: bold; color: #00bcd4; font-size: 14px;")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Recording filename suffix")
        info_layout.addWidget(self.status_label, stretch=2)
        info_layout.addWidget(self.name_input, stretch=1)
        layout.addLayout(info_layout)

        # --- Advanced Settings Collapsible Area ---
        self.btn_toggle_settings = QPushButton("▶ Show Advanced Settings")
        self.btn_toggle_settings.setCheckable(True)
        # Fix text disappearance: explicitly specify color and ensure minimum height
        self.btn_toggle_settings.setStyleSheet("text-align: left; padding: 5px; background: #333; border-radius: 4px; color: #00bcd4; min-height: 30px;")
        self.btn_toggle_settings.clicked.connect(self.toggle_settings)
        layout.addWidget(self.btn_toggle_settings)

        self.settings_container = QWidget()
        self.settings_container.setVisible(False)
        settings_vbox = QVBoxLayout(self.settings_container)

        # 6. Real-time Denoise Switch
        denoise_layout = QHBoxLayout()
        self.chk_denoise = QCheckBox("Enable Real-time Denoise")
        self.chk_denoise.setChecked(False) # Default off to preserve original quality
        self.chk_denoise.setToolTip("Recommended for noisy environments; keep off in quiet environments to preserve detail")
        denoise_layout.addWidget(self.chk_denoise)
        denoise_layout.addStretch()
        settings_vbox.addLayout(denoise_layout)
        
        norm_layout = QHBoxLayout()
        norm_layout.addWidget(QLabel("Target Volume Normalization (dBFS):"))
        self.spin_norm = QSpinBox()
        self.spin_norm.setRange(-40, -5)
        self.spin_norm.setValue(-20)
        norm_layout.addWidget(self.spin_norm)
        norm_layout.addStretch()
        settings_vbox.addLayout(norm_layout)

        # 2. Beam Size
        beam_layout = QHBoxLayout()
        beam_layout.addWidget(QLabel("Beam Size (Recommended: 5):"))
        self.spin_beam = QSpinBox()
        self.spin_beam.setRange(1, 15)
        self.spin_beam.setValue(5)
        beam_layout.addWidget(self.spin_beam)
        beam_layout.addStretch()
        settings_vbox.addLayout(beam_layout)

        # 3. Initial Prompt
        prompt_layout = QVBoxLayout()
        prompt_layout.addWidget(QLabel("Initial Prompt:"))
        self.prompt_input = QLineEdit()
        self.prompt_input.setText("This is a professional meeting record, please use correct punctuation.")
        prompt_layout.addWidget(self.prompt_input)
        settings_vbox.addLayout(prompt_layout)

        # 4. Language Selection
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Recognition Language:"))
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("Auto Detect", None)
        self.combo_lang.addItem("  Traditional Chinese  ", "zh")
        self.combo_lang.addItem("English", "en")
        self.combo_lang.addItem("Japanese", "ja")
        self.combo_lang.setCurrentIndex(1) # Default Traditional Chinese (Index 1)
        lang_layout.addWidget(self.combo_lang)
        lang_layout.addStretch()
        settings_vbox.addLayout(lang_layout)

        # 5. Model Precision & Reload
        model_settings_layout = QHBoxLayout()
        model_settings_layout.addWidget(QLabel("Compute Precision:"))
        self.combo_compute = QComboBox()
        self.combo_compute.addItem("float16 (GPU Recommended)", "float16")
        self.combo_compute.addItem("int8 (CPU Accel/Save Memory)", "int8")
        self.combo_compute.addItem("float32 (High Precision)", "float32")
        model_settings_layout.addWidget(self.combo_compute)
        
        self.btn_reload_model = QPushButton("🔄 Reload Model")
        self.btn_reload_model.setStyleSheet("background-color: #546e7a; color: white;")
        self.btn_reload_model.clicked.connect(self.apply_model_settings)
        model_settings_layout.addWidget(self.btn_reload_model)
        
        model_settings_layout.addStretch()
        settings_vbox.addLayout(model_settings_layout)

        layout.addWidget(self.settings_container)

        # --- Batch Progress Bar ---
        self.batch_progress = QProgressBar()
        self.batch_progress.setVisible(False)
        layout.addWidget(self.batch_progress)

        self.plot_widget = pg.PlotWidget(title="Live Waveform")
        self.plot_widget.setYRange(-30000, 30000)
        self.plot_data = np.zeros(4000)
        self.curve = self.plot_widget.plot(self.plot_data, pen='c')
        layout.addWidget(self.plot_widget, stretch=1)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFontPointSize(12)
        layout.addWidget(self.text_area, stretch=2)

        btn_layout = QHBoxLayout()
        self.btn_record = QPushButton("🎙️ Start Recording")
        self.btn_record.clicked.connect(self.toggle_record)
        self.btn_record.setFixedHeight(50)
        self.btn_record.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.btn_import = QPushButton("📁 Import Audio/Video for Transcription")
        self.btn_import.clicked.connect(self.import_file)
        self.btn_import.setFixedHeight(50)
        
        self.btn_save_txt = QPushButton("💾 Save Transcript (.txt)")
        self.btn_save_txt.clicked.connect(self.save_transcript)
        self.btn_save_txt.setFixedHeight(50)
        
        btn_layout.addWidget(self.btn_record, stretch=2)
        btn_layout.addWidget(self.btn_import, stretch=2)
        btn_layout.addWidget(self.btn_save_txt, stretch=1)
        layout.addLayout(btn_layout)

        # Use async loading on initial startup (must be called after UI component initialization)
        self.apply_model_settings()

        # Start auto-update check
        self.check_for_updates()

    def check_for_updates(self):
        self.update_checker = UpdateCheckerThread()
        self.update_checker.found_update.connect(self.show_update_dialog)
        self.update_checker.start()

    def show_update_dialog(self, version, url):
        reply = QMessageBox.question(self, "New Version Found", f"Detected new version v{version}!\nGo to GitHub to download?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            webbrowser.open(url)

    def toggle_settings(self):
        """Toggle display/hide of advanced settings area"""
        if self.btn_toggle_settings.isChecked():
            self.btn_toggle_settings.setText("▼ Hide Advanced Settings")
            self.settings_container.setVisible(True)
        else:
            self.btn_toggle_settings.setText("▶ Show Advanced Settings")
            self.settings_container.setVisible(False)

    def import_file(self):
        if self.transcriber_thread.model is None:
            QMessageBox.warning(self, "Please wait", "Model is not ready.")
            return
        if self.recorder_thread is not None:
            QMessageBox.warning(self, "Error", "Please stop recording before importing files.")
            return

        # Changed to support multi-selection
        files, _ = QFileDialog.getOpenFileNames(self, "Select Media Files", "", "Media Files (*.mp4 *.m4a *.mp3 *.wav *.flac *.mkv)")
        if files:
            self.pending_files.extend(files)
            # Initialize progress bar
            self.total_batch_count = len(self.pending_files)
            self.batch_progress.setMaximum(self.total_batch_count)
            self.batch_progress.setValue(0)
            self.batch_progress.setVisible(True)
            
            self.btn_record.setEnabled(False)
            self.btn_import.setEnabled(False)
            if self.file_thread is None or not self.file_thread.isRunning():
                self.process_next_file()

    def apply_model_settings(self):
        """手動觸發模型重新載入"""
        if self.model_loader and self.model_loader.isRunning():
            return

        new_compute = self.combo_compute.currentData()
        self.btn_reload_model.setEnabled(False)
        self.btn_reload_model.setText("⏳ 載入中...")

        self.model_loader = ModelLoaderThread(DEVICE, new_compute)
        self.model_loader.status_signal.connect(self.update_status_only)
        self.model_loader.error_signal.connect(self.on_model_error)
        self.model_loader.finished_signal.connect(self.on_model_loaded)
        self.model_loader.start()

    @pyqtSlot(object)
    def on_model_loaded(self, new_model):
        """當模型載入完成時的處理"""
        # 釋放舊模型
        if self.transcriber_thread.model:
            del self.transcriber_thread.model
            gc.collect()
        
        self.transcriber_thread.model = new_model
        self.btn_reload_model.setEnabled(True)
        self.btn_reload_model.setText("🔄 重新載入模型")
        self.status_label.setText(f"✅ 模型已就緒 ({self.combo_compute.currentText()})")

    @pyqtSlot(str)
    def on_model_error(self, err_msg):
        QMessageBox.critical(self, "模型載入失敗", err_msg)
        self.btn_reload_model.setEnabled(True)
        self.btn_reload_model.setText("🔄 重新載入模型")

    def process_next_file(self):
        """批次處理核心邏輯"""
        if not self.pending_files:
            self.btn_record.setEnabled(True)
            self.btn_import.setEnabled(True)
            self.status_label.setText("✅ 所有批次任務已完成")
            self.batch_progress.setVisible(False)
            self.total_batch_count = 0
            return

        file_path = self.pending_files.pop(0)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # 更新當前存檔路徑資訊
        self.current_filename = f"transcript_{base_name}"
        self.current_folder = os.path.dirname(file_path)
        
        # 更新進度條 (已完成 = 總數 - 剩餘)
        completed = self.total_batch_count - len(self.pending_files)
        self.batch_progress.setValue(completed)
        
        total_left = len(self.pending_files) + 1
        self.status_label.setText(f"📂 批次處理中 (剩餘 {total_left} 個): {base_name}")
        
        self.file_thread = FileTranscriberThread(
            self.transcriber_thread.model, 
            file_path, 
            target_dbfs=float(self.spin_norm.value()),
            beam_size=self.spin_beam.value(),
            initial_prompt=self.prompt_input.text(),
            language=self.combo_lang.currentData()
        )
        self.file_thread.text_updated.connect(self.update_log)
        self.file_thread.status_updated.connect(self.update_status_only)
        self.file_thread.finished_signal.connect(self.process_next_file) # Recursive call to process next
        self.file_thread.start()

    def toggle_record(self):
        if self.recorder_thread is None:
            if self.transcriber_thread.model is None:
                QMessageBox.warning(self, "Please wait", "Model is not ready.")
                return
            
            suffix = self.name_input.text().strip() or "record"
            timestamp = datetime.datetime.now().strftime('%y%m%d_%H%M')
            base_name = f"{timestamp}_{suffix}"
            
            self.current_folder = os.path.join(os.getcwd(), base_name)
            if not os.path.exists(self.current_folder): os.makedirs(self.current_folder)
            self.current_filename = base_name
            full_path = os.path.join(self.current_folder, base_name)

            self.recorder_thread = AudioRecorderThread(
                full_path, 
                self.transcriber_thread, 
                enable_denoise=self.chk_denoise.isChecked()
            )
            self.recorder_thread.waveform_signal.connect(self.update_plot)
            self.recorder_thread.finished_signal.connect(self.process_audio)
            
            # 防呆：鎖定匯入按鈕
            self.btn_import.setEnabled(False)
            self.recorder_thread.start()
            
            self.btn_record.setText("🛑 停止錄製")
            self.btn_record.setStyleSheet("background-color: #e74c3c; color: white; font-size: 16px; font-weight: bold;")
            self.status_label.setText(f"🔴 錄製中: {base_name}")
            self.text_area.clear()
        else:
            self.recorder_thread.running = False
            self.recorder_thread.quit()
            self.recorder_thread = None
            
            # 恢復按鈕狀態
            self.btn_import.setEnabled(True)
            self.btn_record.setText("🎙️ 開始錄製")
            self.btn_record.setStyleSheet("font-size: 16px; font-weight: bold;")
            self.status_label.setText("✅ 錄音結束，處理中...")

    def save_transcript(self):
        content = self.text_area.toPlainText()
        if not content.strip(): 
            QMessageBox.warning(self, "提示", "目前沒有內容可儲存。")
            return
            
        default_path = os.path.join(self.current_folder, f"{self.current_filename}.txt")
        file_path, _ = QFileDialog.getSaveFileName(self, "儲存檔案", default_path, "Text Files (*.txt)")
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f: f.write(content)
            QMessageBox.information(self, "成功", f"逐字稿已儲存！\n{file_path}")

    @pyqtSlot(np.ndarray)
    def update_plot(self, data):
        data_len = len(data)
        plot_len = len(self.plot_data)
        
        # 防呆：如果傳入的音訊片段比畫布還大，只取最後面的點
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

    @pyqtSlot(str)
    def update_status_only(self, text):
        self.status_label.setText(text)

    @pyqtSlot(str)
    def process_audio(self, wav_path):
        # Safety filtering
        if "Hardware mounting failed" in wav_path or "No audio recorded" in wav_path:
            return
        self.executor.submit(self._normalization_task, wav_path, float(self.spin_norm.value()))

    def _normalization_task(self, wav_path, target_dbfs):
        try:
            audio = AudioSegment.from_wav(wav_path)
            normalized = audio.apply_gain(target_dbfs - audio.dBFS)
            mp3_path = wav_path.replace(".wav", ".mp3")
            normalized.export(mp3_path, format="mp3")
            if os.path.exists(wav_path):
                os.remove(wav_path)
            
            # Release resources
            del audio
            del normalized
        except Exception as e: print(f"Processing failed: {e}")
        finally:
            gc.collect()

    def stop_threads(self):
        self.transcriber_thread.stop()
        if self.recorder_thread: 
            self.recorder_thread.running = False
        if self.file_thread and self.file_thread.isRunning():
            self.file_thread.terminate()

# ==========================================
# [UI] Tab 2: Intelligent Track Splitting (Splitter Tab)
# ==========================================
class SplitterTab(QWidget):
    def __init__(self):
        super().__init__()
        self.file_path = None
        self.output_dir = None
        self.thread = None
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        header = QLabel("✂️ Intelligent Track Splitter")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #00bcd4;")
        layout.addWidget(header, alignment=Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Automatically find speaker pauses or breaths for cutting to avoid abrupt interruptions.")
        desc.setStyleSheet("font-size: 14px; color: #aaaaaa;")
        layout.addWidget(desc, alignment=Qt.AlignmentFlag.AlignCenter)

        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("Target Segment Length (minutes):"))
        self.spin_target = QSpinBox()
        self.spin_target.setRange(5, 120)
        self.spin_target.setValue(40)
        settings_layout.addWidget(self.spin_target)

        settings_layout.addWidget(QLabel(" Tolerance (minutes):"))
        self.spin_tol = QSpinBox()
        self.spin_tol.setRange(1, 15)
        self.spin_tol.setValue(5)
        settings_layout.addWidget(self.spin_tol)
        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        btn_layout = QHBoxLayout()
        self.btn_select = QPushButton("1. Select Source Audio")
        self.btn_select.setFixedHeight(50)
        self.btn_select.clicked.connect(self.select_file)

        self.btn_outdir = QPushButton("2. Select Output Folder")
        self.btn_outdir.setFixedHeight(50)
        self.btn_outdir.clicked.connect(self.select_outdir)

        self.btn_start = QPushButton("3. Start Intelligent Splitting")
        self.btn_start.setFixedHeight(50)
        self.btn_start.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.btn_start.clicked.connect(self.start_split)
        self.btn_start.setEnabled(False)

        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(self.btn_outdir)
        btn_layout.addWidget(self.btn_start)
        layout.addLayout(btn_layout)

        self.lbl_file = QLabel("No file selected")
        self.lbl_file.setStyleSheet("color: #ff9800;")
        layout.addWidget(self.lbl_file)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("font-family: Consolas, monospace; font-size: 13px;")
        layout.addWidget(self.log_area)

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select audio to split", "", "Audio/Video Files (*.mp3 *.wav *.m4a *.mp4 *.flac)")
        if path:
            self.file_path = path
            self.output_dir = os.path.dirname(path)
            self.update_status()

    def select_outdir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if dir_path:
            self.output_dir = dir_path
            self.update_status()

    def update_status(self):
        if self.file_path and self.output_dir:
            file_name = os.path.basename(self.file_path)
            self.lbl_file.setText(f"Source: {file_name} | Output to: {self.output_dir}")
            self.btn_start.setEnabled(True)

    def start_split(self):
        if not self.file_path or not self.output_dir: return
        self.btn_select.setEnabled(False)
        self.btn_outdir.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_area.clear()

        self.thread = SmartSplitterThread(self.file_path, self.output_dir, self.spin_target.value(), self.spin_tol.value())
        self.thread.log_signal.connect(self.append_log)
        self.thread.progress_signal.connect(self.progress_bar.setValue)
        self.thread.error_signal.connect(self.handle_error)
        self.thread.finished_signal.connect(self.process_finished)
        self.thread.start()

    def append_log(self, text):
        self.log_area.append(text)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def handle_error(self, err_msg):
        QMessageBox.critical(self, "Error", f"An error occurred during processing:\n{err_msg}")
        self.reset_ui()

    def process_finished(self):
        self.progress_bar.setValue(100)
        QMessageBox.information(self, "Completed", "Intelligent splitting completed!")
        self.reset_ui()

    def reset_ui(self):
        self.btn_select.setEnabled(True)
        self.btn_outdir.setEnabled(True)
        self.btn_start.setEnabled(True)


# ==========================================
# [UI] Main Application Window
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.initSystemTray()

    def initUI(self):
        self.setWindowTitle(f"Ultimate Audio Assistant v{__version__} | Comprehensive Audio Assistant")
        self.resize(1000, 800)
        
        # Create Tab Widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Instantiate two functional tabs
        self.tab_transcription = TranscriptionTab()
        self.tab_splitter = SplitterTab()
        
        # Add tabs and set labels
        self.tabs.addTab(self.tab_transcription, "📝 Recording & Transcription")
        self.tabs.addTab(self.tab_splitter, "✂️ Intelligent Track Splitting")

        # Bottom Status Bar (can display copyright info)
        # ==========================================
        # Status Bar Engineering Layout
        # ==========================================
        # Grab main program last modification time (Automated Ground Truth)
        build_date = time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(__file__)))

        # Left: Dynamic system status (Telemetry)
        self.sys_status = QLabel("Status: Idle | GPU: Allocating...")
        self.sys_status.setStyleSheet("padding: 5px; color: #00ff00; font-weight: bold; font-size: 11px;")
        self.statusBar().addWidget(self.sys_status, 1) # Occupy remaining space and push right

        # Right: Static version and copyright info (Metadata)
        footer_text = f"© {build_date[:4]}  {__organization__}  |  v{__version__} ({build_date})  |  {__author__}"
        footer = QLabel(footer_text)
        footer.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        footer.setStyleSheet("padding: 5px; color: #888888; font-size: 11px;")
        self.statusBar().addPermanentWidget(footer) # Force anchor to right

    def initSystemTray(self):
        """Initialize system tray icon"""
        self.tray_icon = QSystemTrayIcon(self)
        # Use system built-in icon (SP_MediaVolume)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
        self.tray_icon.setIcon(icon)
        
        # Create right-click menu
        tray_menu = QMenu()
        
        show_action = QAction("Show Main Window", self)
        show_action.triggered.connect(self.show_window)
        
        quit_action = QAction("Exit Program", self)
        quit_action.triggered.connect(self.quit_app)
        
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        
        # Behavior on tray icon activation
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def show_window(self):
        self.show()
        self.activateWindow()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def quit_app(self):
        self.perform_cleanup()
        QApplication.quit()

    def perform_cleanup(self):
        """Safely release all background threads and temporary resources when window closes"""
        self.tab_transcription.stop_threads()
        
        # Safely release GPU memory (use hasattr to prevent AttributeError)
        t_thread = self.tab_transcription.transcriber_thread
        if hasattr(t_thread, 'model') and t_thread.model is not None:
            del t_thread.model
            t_thread.model = None
        
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
            
        if os.path.exists("temp_transcript.txt"):
            os.remove("temp_transcript.txt") 

    def closeEvent(self, event):
        """Override close event: minimize to tray instead of exiting directly"""
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "Comprehensive Audio Assistant",
                "Program minimized to tray. Recording and transcription will continue in the background.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            event.ignore()
        else:
            self.perform_cleanup()
            super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Apply dark modern theme (requires pip install qt-material)
    apply_stylesheet(app, theme='dark_teal.xml')
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())