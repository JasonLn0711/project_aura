from dataclasses import dataclass

from aura.config import SUPPORTED_IMPORT_EXTENSIONS
from aura.metadata import __author__, __organization__, __version__


def media_filter(label: str, extensions: tuple[str, ...]) -> str:
    patterns = " ".join(f"*.{extension}" for extension in extensions)
    return f"{label} ({patterns});;All Files (*)"


@dataclass(frozen=True)
class UIStrings:
    window_title: str = f"Aura Audio Assistant (Project Aura) | v{__version__}"
    tab_transcribing: str = "📝 Transcribing"
    tab_splitting: str = "✂️ Track Splitting"
    tray_show_main_window: str = "Show Main Window"
    tray_exit_program: str = "Exit Program"
    tray_message_title: str = "Comprehensive Audio Assistant"
    tray_message_body: str = "Program minimized to tray. Recording and transcription will continue in the background."
    status_idle_gpu: str = "Status: Idle | GPU: Allocating..."

    status_waiting_gpu: str = "Status: Waiting for GPU initialization..."
    recording_suffix_placeholder: str = "Recording filename suffix"
    show_advanced_settings: str = "▶ Show Advanced Settings"
    hide_advanced_settings: str = "▼ Hide Advanced Settings"
    denoise_mode_label: str = "Denoise Mode:"
    denoise_off: str = "Off - preserve original audio"
    denoise_light: str = "Light - normal room noise"
    denoise_medium: str = "Medium - stronger noise reduction"
    denoise_tooltip: str = (
        "Applies noise reduction to live recording and imported media before ASR. "
        "Use Off in quiet environments; stronger modes may remove speech detail."
    )
    speaker_diarization_label: str = "Identify speakers after import transcription"
    speaker_diarization_tooltip: str = (
        "Uses optional pyannote diarization on imported files and labels transcript segments by speaker. "
        "Requires pyannote.audio and a Hugging Face token."
    )
    speaker_min_label: str = "Min Speakers:"
    speaker_max_label: str = "Max Speakers:"
    llm_summary_label: str = "Summarize transcript after ASR"
    llm_summary_tooltip: str = (
        "Runs optional local Qwen3.5-9B summary after imported-file ASR finishes or shortly after recording stops. "
        "Output is constrained to Taiwanese Traditional Chinese."
    )
    llm_summary_button: str = "🧠 Summarize Current Transcript"
    target_volume_label: str = "Target Volume Normalization (dBFS):"
    beam_size_label: str = "Beam Size (Recommended: 5):"
    initial_prompt_label: str = "Initial Prompt:"
    language_label: str = "Recognition Language:"
    language_auto: str = "Auto Detect"
    language_zh: str = "  Traditional Chinese  "
    language_en: str = "English"
    language_ja: str = "Japanese"
    compute_precision_label: str = "Compute Precision:"
    compute_float16: str = "float16 (GPU High Throughput)"
    compute_int8: str = "int8 (RTX GPU Default/Save Memory)"
    compute_float32: str = "float32 (High Precision)"
    reload_model: str = "🔄 Reload Model"
    loading_model: str = "⏳ Loading..."
    live_waveform_title: str = "Live Waveform"
    start_recording: str = "🎙️ Start Recording"
    stop_recording: str = "🛑 Stop Recording"
    import_media: str = "📁 Import Audio/Video and Start Transcription"
    save_transcript: str = "💾 Save Transcript (.txt)"
    clear_transcript: str = "🧹 Clear Transcript"
    clear_transcript_confirm: str = "Clear the current transcript from the screen and temporary backup?"
    transcript_cleared: str = "Transcript cleared."
    no_content_to_clear: str = "There is currently no transcript content to clear."
    batch_hint: str = "Imported files begin batch transcription automatically. No separate ASR start button is required."
    please_wait_title: str = "Please wait"
    model_not_ready: str = "Model is not ready."
    error_title: str = "Error"
    stop_recording_before_import: str = "Please stop recording before importing files."
    select_media_files: str = "Select Media Files"
    media_files_filter: str = media_filter("Media Files", SUPPORTED_IMPORT_EXTENSIONS)
    batch_tasks_completed: str = "✅ All batch tasks completed"
    file_transcription_failed: str = "File Transcription Failed"
    summary_failed: str = "LLM Summary Failed"
    recording_finished_processing: str = "✅ Recording finished, processing..."
    notice_title: str = "Notice"
    no_content_to_save: str = "There is currently no content to save."
    save_file: str = "Save File"
    text_files_filter: str = "Text Files (*.txt)"
    success_title: str = "Success"
    model_loading_failed: str = "Model Loading Failed"
    new_version_found: str = "New Version Found"

    splitter_header: str = "✂️ Intelligent Track Splitter"
    splitter_description: str = "Automatically find speaker pauses or breaths for cutting to avoid abrupt interruptions."
    splitter_target_length: str = "Target Segment Length (minutes):"
    splitter_tolerance: str = " Tolerance (minutes):"
    splitter_select_source: str = "1. Select Source Audio"
    splitter_select_output: str = "2. Select Output Folder"
    splitter_start: str = "3. Start Intelligent Splitting"
    splitter_no_file_selected: str = "No file selected"
    splitter_select_audio: str = "Select audio to split"
    splitter_media_filter: str = "Audio/Video Files (*.mp3 *.wav *.m4a *.mp4 *.flac *.ogg *.aac *.mkv *.mov *.wma *.aiff *.opus)"
    splitter_select_output_folder: str = "Select output folder"
    splitter_completed_title: str = "Completed"
    splitter_completed: str = "Intelligent splitting completed!"

    def footer(self, build_date: str) -> str:
        return f"© {build_date[:4]}  {__organization__}  |  v{__version__} ({build_date})  |  {__author__}"

    def update_found(self, version: str) -> str:
        return f"Detected new version v{version}!\nGo to GitHub to download?"

    def model_ready(self, device: str, compute_type: str) -> str:
        return f"✅ Model is ready ({device}/{compute_type})"

    def batch_processing(self, remaining_count: int, base_name: str) -> str:
        return f"📂 Batch processing in progress (remaining {remaining_count} files): {base_name}"

    def recording(self, base_name: str) -> str:
        return f"🔴 Recording: {base_name}"

    def transcript_saved(self, file_path: str) -> str:
        return f"Transcript saved successfully!\n{file_path}"

    def splitter_status(self, file_name: str, output_dir: str) -> str:
        return f"Source: {file_name} | Output to: {output_dir}"

    def splitter_error(self, error_message: str) -> str:
        return f"An error occurred during processing:\n{error_message}"


UI_TEXT = UIStrings()
