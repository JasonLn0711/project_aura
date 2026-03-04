"""
Ultimate Audio Assistant - 全方位錄音助理
====================================
整合「即時語音/音檔轉逐字稿」與「智慧音軌切割」的雙核心工具。

版本管理策略 (Semantic Versioning):
- MAJOR: 重大架構改變或不相容的修改
- MINOR: 新增向下相容的功能
- PATCH: 向下相容的錯誤修正 (Bug fixes)
"""

__version__ = "2.0.1"
__author__ = "Jason Chia-Sheng Lin (PhD. Student)"
__organization__ = "NYCU"
__date__ = "2026-02-23"

import time
import sys
import os
import queue
import wave
import datetime
import numpy as np
import pyaudio
import webrtcvad
from concurrent.futures import ThreadPoolExecutor
from ctypes import *
from contextlib import contextmanager

# 影音處理
from pydub import AudioSegment
from pydub.silence import detect_silence
from faster_whisper import WhisperModel

# PyQt6 UI & 視覺化
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTextEdit, 
                             QLineEdit, QMessageBox, QFileDialog, QTabWidget,
                             QProgressBar, QSpinBox)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, pyqtSlot
from PyQt6.QtGui import QFont
import pyqtgraph as pg
from qt_material import apply_stylesheet

# ==========================================
# 系統設定與 ALSA 錯誤遮蔽 (針對 Linux 環境)
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
# [核心執行緒] 逐字稿功能區
# ==========================================
class FileTranscriberThread(QThread):
    text_updated = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, model, file_path):
        super().__init__()
        self.model = model
        self.file_path = file_path

    def run(self):
        self.status_updated.emit("⏳ 正在分析音檔，請稍候...")
        try:
            # faster-whisper 內建支援直接讀取常見影音檔
            segments, info = self.model.transcribe(
                audio_data, # 或 self.file_path
                beam_size=5, 
                language="zh",
                condition_on_previous_text=True, # 確保開啟上下文關聯（預設為 True，但顯式寫出較好）
                initial_prompt="這是一份專業的繁體中文會議紀錄，請務必根據語氣加上正確的全形標點符號（例如：逗號，句號。問號？驚嘆號！）。"
            )


            for segment in segments:
                h, m = divmod(int(segment.start), 3600)
                m, s = divmod(m, 60)
                timestamp = f"{h:02d}:{m:02d}:{s:02d}"
                formatted_text = f"[{timestamp}] {segment.text}"
                self.text_updated.emit(formatted_text)
                
                # 自動備份
                with open("temp_transcript.txt", "a", encoding="utf-8") as f:
                    f.write(formatted_text + "\n")
            self.status_updated.emit("✅ 檔案處理完成！")
        except Exception as e:
            self.status_updated.emit(f"❌ 檔案處理失敗: {e}")
        finally:
            self.finished_signal.emit()

class TranscriberThread(QThread):
    text_updated = pyqtSignal(str)
    status_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.audio_queue = queue.Queue()
        self.running = True
        self.model = None

    def run(self):
        self.status_updated.emit(f"🚀 初始化 GPU 模型: {MODEL_ID}...")
        try:
            self.model = WhisperModel(MODEL_ID, device=DEVICE, compute_type=COMPUTE_TYPE)
            self.status_updated.emit(f"✅ 模型載入完成 ({DEVICE})")
        except Exception as e:
            self.status_updated.emit(f"❌ 載入失敗: {e}")
            return

        while self.running:
            try:
                audio_data = self.audio_queue.get(timeout=1)
                segments, info = self.model.transcribe(
                    audio_data, beam_size=5, language="zh",
                    initial_prompt="以下是繁體中文的會議記錄。"
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
                print(f"轉錄錯誤: {e}")

    def add_audio(self, audio_np):
        self.audio_queue.put(audio_np)

    def stop(self):
        self.running = False

class AudioRecorderThread(QThread):
    waveform_signal = pyqtSignal(np.ndarray)
    finished_signal = pyqtSignal(str)
    
    def __init__(self, filename, transcriber_thread):
        super().__init__()
        self.filename = filename
        self.transcriber = transcriber_thread
        self.running = True
        self.vad = webrtcvad.Vad(VAD_LEVEL)
        self.full_frames = []

    def run(self):
        with no_alsa_err():
            pa = pyaudio.PyAudio()
        
        # 1. 優先尋找 pulse 虛擬裝置 (支援自動重新取樣，解決 Invalid sample rate)
        target_device_index = None
        target_channels = 1
        
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if 'pulse' in info['name'].lower():
                target_device_index = i
                target_channels = int(info['maxInputChannels']) if info['maxInputChannels'] > 0 else 1
                break
        
        try:
            # 嘗試使用找到的 pulse 裝置或系統預設裝置
            if target_device_index is not None:
                print(f"🚀 掛載 PulseAudio 虛擬設備: Index {target_device_index}, Channels: {target_channels}")
                stream = pa.open(format=pyaudio.paInt16, channels=target_channels, rate=SAMPLE_RATE,
                                 input=True, input_device_index=target_device_index, frames_per_buffer=CHUNK_SIZE)
            else:
                print("⚠️ 找不到 pulse 設備，嘗試系統預設裝置...")
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                                 input=True, frames_per_buffer=CHUNK_SIZE)
                target_channels = 1
        except Exception as e:
            # 終極 Fallback：如果連預設都失敗，直接拋出錯誤讓後續處理
            self.finished_signal.emit(f"硬體掛載失敗: {str(e)}")
            pa.terminate()
            return

        silence_frames = 0
        speech_buffer = []
        min_speech_len = 0.5 

        while self.running:
            try:
                raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                np_data = np.frombuffer(raw_data, dtype=np.int16)
                
                # 動態降維：將多聲道重塑並只提取第一個聲道 (Channel 0)
                if target_channels > 1:
                    # reshape 成 [幀數, 聲道數]，然後取第一列
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
                    # 將收集到的語音合併
                    audio_np = np.concatenate(speech_buffer).flatten().astype(np.float32) / 32768.0
                    
                    # 🌟 關鍵 3：在結尾強制加上 0.5 秒的純靜音 (Zero Padding)
                    padding_length = int(SAMPLE_RATE * 0.5) 
                    silence_padding = np.zeros(padding_length, dtype=np.float32)
                    padded_audio_np = np.concatenate([audio_np, silence_padding])
                    
                    self.transcriber.add_audio(padded_audio_np) # 送出加上靜音尾巴的音訊
                    speech_buffer = [] 
                    silence_frames = 0 # 重置計數
                    
            except Exception as e:
                print(f"音訊迴圈錯誤: {e}")
                break

        stream.stop_stream()
        stream.close()
        pa.terminate()
        
        # 錄音中斷但沒有資料時防呆
        if not self.full_frames:
            self.finished_signal.emit("未錄製到任何音訊")
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
        try:
            self.log_signal.emit(f"⏳ 正在載入音檔...\n檔案: {self.file_path}")
            self.progress_signal.emit(5)
            
            audio = AudioSegment.from_file(self.file_path)
            total_duration_ms = len(audio)
            self.log_signal.emit(f"✅ 載入成功！總長度: {total_duration_ms / 60000:.2f} 分鐘")
            
            base_name = os.path.splitext(os.path.basename(self.file_path))[0]
            ext = os.path.splitext(self.file_path)[1].lower().replace(".", "")
            if ext not in ["mp3", "wav", "m4a", "ogg", "flac"]:
                ext = "mp3" 
            
            current_pos = 0
            chunk_index = 1
            
            while current_pos < total_duration_ms:
                if (total_duration_ms - current_pos) <= (self.target_ms + self.tolerance_ms):
                    self.log_signal.emit(f"✂️ 正在匯出最後一段 (第 {chunk_index} 段)...")
                    final_chunk = audio[current_pos:]
                    self.export_chunk(final_chunk, base_name, chunk_index, ext)
                    self.progress_signal.emit(100)
                    break
                
                search_start = current_pos + self.target_ms - self.tolerance_ms
                search_end = min(current_pos + self.target_ms + self.tolerance_ms, total_duration_ms)
                self.log_signal.emit(f"🔍 分析第 {chunk_index} 段最佳斷點 ({search_start/60000:.1f} ~ {search_end/60000:.1f} 分)...")
                
                window = audio[search_start:search_end]
                silences = detect_silence(window, min_silence_len=1000, silence_thresh=audio.dBFS - 16)
                
                if silences:
                    best_silence = silences[len(silences)//2]
                    cut_point = search_start + (best_silence[0] + best_silence[1]) // 2
                    self.log_signal.emit(f"🎯 找到合適停頓點！於 {cut_point/60000:.2f} 分鐘處切割。")
                else:
                    cut_point = current_pos + self.target_ms
                    self.log_signal.emit(f"⚠️ 找不到明顯停頓，於 {cut_point/60000:.2f} 分鐘處平滑切割。")
                
                chunk = audio[current_pos:cut_point]
                if not silences: chunk = chunk.fade_out(100)
                
                self.log_signal.emit(f"💾 正在儲存第 {chunk_index} 段...")
                self.export_chunk(chunk, base_name, chunk_index, ext)
                
                current_pos = cut_point
                chunk_index += 1
                self.progress_signal.emit(int((current_pos / total_duration_ms) * 90) + 5)

            self.log_signal.emit("🎉 所有片段切割並儲存完畢！")
            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))

    def export_chunk(self, chunk, base_name, index, ext):
        out_path = os.path.join(self.output_dir, f"{base_name}_part{index:02d}.{ext}")
        export_kwargs = {"format": ext}
        if ext == "mp3": export_kwargs["bitrate"] = "192k"
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
        
        self.current_folder = os.getcwd()
        self.current_filename = "transcript"
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        
        info_layout = QHBoxLayout()
        self.status_label = QLabel("狀態: 等待 GPU 初始化...")
        self.status_label.setStyleSheet("font-weight: bold; color: #00bcd4; font-size: 14px;")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("錄音檔名稱後綴")
        info_layout.addWidget(self.status_label, stretch=2)
        info_layout.addWidget(self.name_input, stretch=1)
        layout.addLayout(info_layout)

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
        self.btn_record = QPushButton("🎙️ 開始錄製")
        self.btn_record.clicked.connect(self.toggle_record)
        self.btn_record.setFixedHeight(50)
        self.btn_record.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.btn_import = QPushButton("📁 匯入音檔/影片轉錄")
        self.btn_import.clicked.connect(self.import_file)
        self.btn_import.setFixedHeight(50)
        
        self.btn_save_txt = QPushButton("💾 儲存逐字稿 (.txt)")
        self.btn_save_txt.clicked.connect(self.save_transcript)
        self.btn_save_txt.setFixedHeight(50)
        
        btn_layout.addWidget(self.btn_record, stretch=2)
        btn_layout.addWidget(self.btn_import, stretch=2)
        btn_layout.addWidget(self.btn_save_txt, stretch=1)
        layout.addLayout(btn_layout)

    def import_file(self):
        if self.transcriber_thread.model is None:
            QMessageBox.warning(self, "請稍候", "模型尚未就緒。")
            return
        if self.recorder_thread is not None:
            QMessageBox.warning(self, "錯誤", "請先停止錄製再匯入檔案。")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "選擇影音檔案", "", "Media Files (*.mp4 *.m4a *.mp3 *.wav *.flac *.mkv)")
        if file_path:
            # 防呆：鎖定按鈕
            self.btn_record.setEnabled(False)
            self.btn_import.setEnabled(False)
            self.text_area.clear()
            
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            self.current_filename = f"transcript_{base_name}"
            self.current_folder = os.path.dirname(file_path)
            self.status_label.setText(f"📂 處理檔案中: {base_name}")
            
            self.file_thread = FileTranscriberThread(self.transcriber_thread.model, file_path)
            self.file_thread.text_updated.connect(self.update_log)
            self.file_thread.status_updated.connect(self.update_status_only)
            self.file_thread.finished_signal.connect(self.on_file_finished)
            self.file_thread.start()

    @pyqtSlot()
    def on_file_finished(self):
        # 恢復按鈕狀態
        self.btn_record.setEnabled(True)
        self.btn_import.setEnabled(True)

    def toggle_record(self):
        if self.recorder_thread is None:
            if self.transcriber_thread.model is None:
                QMessageBox.warning(self, "請稍候", "模型尚未就緒。")
                return
            
            suffix = self.name_input.text().strip() or "record"
            timestamp = datetime.datetime.now().strftime('%y%m%d_%H%M')
            base_name = f"{timestamp}_{suffix}"
            
            self.current_folder = os.path.join(os.getcwd(), base_name)
            if not os.path.exists(self.current_folder): os.makedirs(self.current_folder)
            self.current_filename = base_name
            full_path = os.path.join(self.current_folder, base_name)

            self.recorder_thread = AudioRecorderThread(full_path, self.transcriber_thread)
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
        # 防呆過濾
        if "硬體掛載失敗" in wav_path or "未錄製到任何音訊" in wav_path:
            return
        self.executor.submit(self._normalization_task, wav_path)

    def _normalization_task(self, wav_path):
        try:
            audio = AudioSegment.from_wav(wav_path)
            normalized = audio.apply_gain(-20.0 - audio.dBFS)
            mp3_path = wav_path.replace(".wav", ".mp3")
            normalized.export(mp3_path, format="mp3")
        except Exception as e: print(f"處理失敗: {e}")

    def stop_threads(self):
        self.transcriber_thread.stop()
        if self.recorder_thread: self.recorder_thread.running = False

# ==========================================
# [UI] 頁籤 2: 智慧音檔切割 (Splitter Tab)
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

        header = QLabel("✂️ 智慧音軌切割器")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #00bcd4;")
        layout.addWidget(header, alignment=Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("自動尋找講者換氣或停頓處進行切割，避免話說到一半被生硬打斷。")
        desc.setStyleSheet("font-size: 14px; color: #aaaaaa;")
        layout.addWidget(desc, alignment=Qt.AlignmentFlag.AlignCenter)

        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("目標切割長度 (分鐘):"))
        self.spin_target = QSpinBox()
        self.spin_target.setRange(5, 120)
        self.spin_target.setValue(40)
        settings_layout.addWidget(self.spin_target)

        settings_layout.addWidget(QLabel(" 容許誤差 (分鐘):"))
        self.spin_tol = QSpinBox()
        self.spin_tol.setRange(1, 15)
        self.spin_tol.setValue(5)
        settings_layout.addWidget(self.spin_tol)
        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        btn_layout = QHBoxLayout()
        self.btn_select = QPushButton("1. 選擇來源音檔")
        self.btn_select.setFixedHeight(50)
        self.btn_select.clicked.connect(self.select_file)

        self.btn_outdir = QPushButton("2. 選擇儲存資料夾")
        self.btn_outdir.setFixedHeight(50)
        self.btn_outdir.clicked.connect(self.select_outdir)

        self.btn_start = QPushButton("3. 開始智慧切割")
        self.btn_start.setFixedHeight(50)
        self.btn_start.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.btn_start.clicked.connect(self.start_split)
        self.btn_start.setEnabled(False)

        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(self.btn_outdir)
        btn_layout.addWidget(self.btn_start)
        layout.addLayout(btn_layout)

        self.lbl_file = QLabel("目前尚未選擇檔案")
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
        path, _ = QFileDialog.getOpenFileName(self, "選擇要切割的音檔", "", "Audio/Video Files (*.mp3 *.wav *.m4a *.mp4 *.flac)")
        if path:
            self.file_path = path
            self.output_dir = os.path.dirname(path)
            self.update_status()

    def select_outdir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "選擇儲存資料夾")
        if dir_path:
            self.output_dir = dir_path
            self.update_status()

    def update_status(self):
        if self.file_path and self.output_dir:
            file_name = os.path.basename(self.file_path)
            self.lbl_file.setText(f"來源: {file_name} | 輸出至: {self.output_dir}")
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
        QMessageBox.critical(self, "錯誤", f"處理過程中發生錯誤：\n{err_msg}")
        self.reset_ui()

    def process_finished(self):
        self.progress_bar.setValue(100)
        QMessageBox.information(self, "完成", "智慧切割處理完成！")
        self.reset_ui()

    def reset_ui(self):
        self.btn_select.setEnabled(True)
        self.btn_outdir.setEnabled(True)
        self.btn_start.setEnabled(True)


# ==========================================
# [UI] 主視窗 (Main Application Window)
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f"Ultimate Audio Assistant v{__version__} | 全方位錄音助理")
        self.resize(1000, 800)
        
        # 建立 Tab Widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # 實例化兩個功能分頁
        self.tab_transcription = TranscriptionTab()
        self.tab_splitter = SplitterTab()
        
        # 加入分頁並設定標籤名稱
        self.tabs.addTab(self.tab_transcription, "📝 錄音與逐字稿")
        self.tabs.addTab(self.tab_splitter, "✂️ 智慧音軌切割")

        # 底部狀態列 (可顯示版權資訊)
        # ==========================================
        # 狀態列工程化佈局 (Status Bar)
        # ==========================================
        # 抓取主程式最後修改時間 (自動化 Ground Truth)
        build_date = time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(__file__)))

        # 左側：動態系統狀態 (Telemetry)
        self.sys_status = QLabel("Status: Idle | GPU: Allocating...")
        self.sys_status.setStyleSheet("padding: 5px; color: #00ff00; font-weight: bold; font-size: 11px;")
        self.statusBar().addWidget(self.sys_status, 1) # 佔據剩餘空間向右推

        # 右側：靜態版本與版權資訊 (Metadata)
        footer_text = f"© {build_date[:4]}  {__organization__}  |  v{__version__} ({build_date})  |  {__author__}"
        footer = QLabel(footer_text)
        footer.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        footer.setStyleSheet("padding: 5px; color: #888888; font-size: 11px;")
        self.statusBar().addPermanentWidget(footer) # 強制錨定右側



    def closeEvent(self, event):
        """視窗關閉時，安全釋放所有背景執行緒與暫存資源"""
        self.tab_transcription.stop_threads()
        if os.path.exists("temp_transcript.txt"):
            os.remove("temp_transcript.txt") 
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 套用深色現代化主題 (需 pip install qt-material)
    apply_stylesheet(app, theme='dark_teal.xml')
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())