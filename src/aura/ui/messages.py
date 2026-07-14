from dataclasses import dataclass

from aura.config import SUPPORTED_IMPORT_EXTENSIONS
from aura.metadata import __author__, __date__, __organization__, __version__


def media_filter(label: str, extensions: tuple[str, ...]) -> str:
    patterns = " ".join(f"*.{extension}" for extension in extensions)
    return f"{label} ({patterns});;All Files (*)"


@dataclass(frozen=True)
class UIStrings:
    window_title: str = f"Aura Audio Assistant (Project Aura) | v{__version__}"
    tab_transcribing: str = "Transcription"
    tab_splitting: str = "Track Splitter"
    tray_show_main_window: str = "Show Main Window"
    tray_exit_program: str = "Exit Program"
    tray_message_title: str = "Comprehensive Audio Assistant"
    tray_message_body: str = "Program minimized to tray. Recording and transcription will continue in the background."
    status_idle_gpu: str = "Status: Idle | GPU: Allocating..."

    status_waiting_gpu: str = "Status: Waiting for GPU initialization..."
    recording_suffix_placeholder: str = "Recording filename suffix"
    show_advanced_settings: str = "Show settings"
    hide_advanced_settings: str = "Hide settings"
    meeting_distance_mode_label: str = "Meeting Distance Mode:"
    meeting_distance_off: str = "Off - controlled close capture"
    meeting_distance_normal: str = "Normal - meeting room baseline"
    meeting_distance_far_speaker: str = "Far speaker - weak voice support"
    meeting_distance_rescue_offline: str = "Rescue offline - difficult imports"
    meeting_distance_tooltip: str = (
        "Sets the ASR preprocessing profile for microphone distance. "
        "Far-speaker and rescue modes are conservative fallbacks until model-based enhancement is promoted by transcript evaluation."
    )
    denoise_mode_label: str = "Denoise Mode:"
    denoise_off: str = "Off - preserve original audio"
    denoise_light: str = "Light - normal room noise"
    denoise_medium: str = "Medium - stronger noise reduction"
    denoise_tooltip: str = (
        "Applies noise reduction to live recording and imported media before ASR. "
        "Use Off in quiet environments; stronger modes may remove speech detail."
    )
    live_capture_source_label: str = "Live Capture Source:"
    live_capture_system: str = "System audio only"
    live_capture_microphone: str = "Microphone only"
    live_capture_system_microphone: str = "System audio + microphone"
    live_capture_source_tooltip: str = (
        "Controls live recording input. System+microphone uses PulseAudio/PipeWire sources "
        "when available and falls back to the default input if separate sources are not exposed."
    )
    schedule_recording_label: str = "Schedule recording start"
    schedule_start_time_label: str = "Start at:"
    schedule_auto_stop_label: str = "Auto-stop at:"
    schedule_recording_tooltip: str = (
        "Arms the recording button to start live recording and transcription at the selected wall-clock time."
    )
    schedule_stop_tooltip: str = "Optionally stops the scheduled recording at the selected wall-clock time."
    speaker_diarization_label: str = "Identify speakers after import transcription"
    speaker_diarization_tooltip: str = (
        "Uses optional pyannote diarization on imported files and labels transcript segments by speaker. "
        "Requires pyannote.audio and a Hugging Face token."
    )
    speaker_min_label: str = "Min Speakers:"
    speaker_max_label: str = "Max Speakers:"
    llm_summary_label: str = "Summarize transcript after ASR"
    llm_summary_tooltip: str = (
        "Runs optional local Gemma 4 E4B FP8 summary after imported-file ASR finishes or shortly after recording stops. "
        "Output is constrained to Taiwanese Traditional Chinese."
    )
    llm_summary_button: str = "Summarize Transcript"
    output_policy_label: str = "Transcript Output:"
    output_policy_same_folder: str = "Same folder as source/recording"
    output_policy_session_folder: str = "Project outputs/transcripts folder"
    output_policy_custom_folder: str = "Custom folder"
    output_policy_tooltip: str = "Controls where auto-saved transcript artifacts and processing metrics are written."
    select_output_folder: str = "Select Folder"
    output_folder_selected: str = "Output folder: {folder}"
    recording_audio_format_label: str = "Recording Audio Format:"
    recording_audio_m4a: str = "M4A / AAC-LC 96k (recommended)"
    recording_audio_mp3: str = "MP3 / LAME VBR q0 (legacy)"
    recording_audio_format_tooltip: str = (
        "Controls the saved recording audio artifact. M4A/AAC keeps clearer speech at practical file sizes; "
        "MP3 is retained for legacy workflows."
    )
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
    reload_model: str = "Reload Model"
    loading_model: str = "⏳ Loading..."
    runtime_diagnostics_title: str = "Runtime Diagnostics"
    runtime_gpu_status: str = "GPU detected: {status}"
    runtime_cuda_status: str = "CUDA runtime: {status}"
    runtime_model_status: str = "ASR model load: {status}"
    runtime_audio_status: str = "Audio I/O: {status}"
    runtime_output_status: str = "Output folder writable: {status}"
    runtime_refresh: str = "Refresh Diagnostics"
    runtime_copy_report: str = "Copy Diagnostic Report"
    runtime_report_copied: str = "📋 Runtime diagnostic report copied to clipboard"
    audit_status_local: str = "Audit: local"
    audit_status_off: str = "Audit: off"
    audit_status_unavailable: str = "Audit: unavailable"
    audit_trail_title: str = "Local audit trail"
    audit_local_scope: str = "Local-only, content-free usage and system events. Transcript and audio content stay outside this audit log."
    audit_open_folder: str = "Open Audit Folder"
    audit_generate_report: str = "Generate Audit Report"
    audit_report_ready: str = "Audit report ready: {path}"
    audit_report_failed: str = "Audit report could not be generated."
    first_launch_title: str = "First Launch Check"
    first_launch_status: str = "{label}: {status}"
    first_launch_ready: str = "✓"
    first_launch_needs_attention: str = "✗"
    first_launch_fix_guide: str = "Fix Guide"
    first_launch_open_setup: str = "Open Setup Folder"
    runtime_log_title: str = "Activity log"
    show_runtime_log: str = "Show activity log"
    hide_runtime_log: str = "Hide activity log"
    top_gpu_status: str = "GPU: {status}"
    top_model_status: str = "Model: {status}"
    top_device_status: str = "Device: {status}"
    workstation_workflows_title: str = "Capture"
    transcript_workspace_title: str = "Live transcript"
    transcript_placeholder: str = "Your live or imported transcript will appear here."
    artifact_panel_title: str = "Output & review"
    artifact_empty_hint: str = "Completed transcripts, metrics, and logs stay together in the session output folder."
    open_split_workspace: str = "Track Splitter"
    windows_system_audio_guidance: str = (
        "Windows system audio may require Stereo Mix, WASAPI loopback support, or a virtual audio cable. "
        "Use Microphone when system audio is not exposed."
    )
    live_waveform_title: str = "Live Waveform"
    start_recording: str = "Start Recording"
    stop_recording: str = "Stop Recording"
    schedule_recording_button: str = "Schedule Recording"
    cancel_scheduled_recording: str = "Cancel Scheduled Recording"
    import_media: str = "Import Media"
    import_media_tooltip: str = "Select audio/video files. Transcription starts automatically after import."
    cancel_import: str = "Cancel Import"
    open_output_folder: str = "Open Output Folder"
    batch_hint: str = "Imported files begin batch transcription automatically. No separate ASR start button is required."
    please_wait_title: str = "Please wait"
    model_not_ready: str = "Model is not ready."
    error_title: str = "Error"
    stop_recording_before_import: str = "Please stop recording before importing files."
    select_media_files: str = "Select Media Files"
    media_files_filter: str = media_filter("Media Files", SUPPORTED_IMPORT_EXTENSIONS)
    batch_tasks_completed: str = "✅ All batch tasks completed"
    batch_tasks_cancelled: str = "⚠️ Batch import cancelled"
    import_cancel_requested: str = "⚠️ Cancelling import and skipping remaining files..."
    import_cancel_after_current: str = "⚠️ Current file is finishing; remaining imports will be skipped..."
    summary_already_running: str = "A transcript summary is already running. Please wait for it to finish before importing files."
    file_transcription_failed: str = "File Transcription Failed"
    summary_failed: str = "LLM Summary Failed"
    ollama_model_missing_title: str = "Local Gemma model not installed"
    ollama_model_missing_message: str = (
        "AURA found Ollama, but the required local model is not installed:\n\n"
        "{model_tag}\n\n"
        "This model is required for local transcript summary. AURA will not use a fallback model or cloud API."
    )
    ollama_pull_model: str = "Pull Model"
    ollama_copy_command: str = "Copy Command"
    ollama_cancel: str = "Cancel"
    ollama_pull_command_copied: str = "📋 Ollama pull command copied to clipboard"
    transcript_artifacts_saved: str = "💾 Transcript artifacts saved: {file_path} ({elapsed_seconds:.1f}s)"
    transcript_artifacts_saved_remaining_skipped: str = (
        "💾 Transcript artifacts saved: {file_path} ({elapsed_seconds:.1f}s); remaining imports skipped"
    )
    recording_finished_processing: str = "✅ Recording finished, waiting for final transcript..."
    scheduled_recording_cancelled: str = "⚠️ Scheduled recording cancelled"
    scheduled_recording_start_failed: str = "⚠️ Scheduled recording could not start because another workflow is active."
    scheduled_recording_model_not_ready: str = "⚠️ Scheduled recording could not start because the model is not ready."
    auto_save_transcript_pending: str = "💾 Saving transcript and clearing the workspace..."
    output_folder_unavailable: str = "Output folder is not available yet."
    notice_title: str = "Notice"
    no_content_to_save: str = "There is currently no content to save."
    success_title: str = "Success"
    model_loading_failed: str = "Model Loading Failed"
    new_version_found: str = "New Version Found"

    splitter_header: str = "Track splitter"
    splitter_description: str = "Automatically find speaker pauses or breaths for cutting to avoid abrupt interruptions."
    splitter_target_length: str = "Target Segment Length (minutes):"
    splitter_tolerance: str = " Tolerance (minutes):"
    splitter_select_source: str = "1. Select Source Audio"
    splitter_select_output: str = "2. Select Output Folder"
    splitter_start: str = "3. Start Intelligent Splitting"
    splitter_no_file_selected: str = "No file selected"
    splitter_log_placeholder: str = "Processing details will appear here after splitting starts."
    splitter_select_audio: str = "Select audio to split"
    splitter_media_filter: str = "Audio/Video Files (*.mp3 *.wav *.m4a *.mp4 *.flac *.ogg *.aac *.mkv *.mov *.wma *.aiff *.opus)"
    splitter_select_output_folder: str = "Select output folder"
    splitter_completed_title: str = "Completed"
    splitter_completed: str = "Intelligent splitting completed."

    def footer(self) -> str:
        return f"© {__date__[:4]}  {__organization__}  |  v{__version__} ({__date__})  |  {__author__}"

    def audit_report_ready_message(self, path: str) -> str:
        return self.audit_report_ready.format(path=path)

    def update_found(self, version: str) -> str:
        return f"Detected new version v{version}!\nGo to GitHub to download?"

    def model_ready(self, device: str, compute_type: str) -> str:
        return f"✅ Model is ready ({device}/{compute_type})"

    def batch_processing(self, remaining_count: int, base_name: str) -> str:
        return f"📂 Batch processing in progress (remaining {remaining_count} files): {base_name}"

    def recording(self, base_name: str) -> str:
        return f"🔴 Recording: {base_name}"

    def scheduled_recording_armed(self, start_at, stop_at=None) -> str:
        message = f"⏱️ Scheduled recording armed: starts {start_at:%Y-%m-%d %H:%M}"
        if stop_at:
            message += f"; auto-stops {stop_at:%Y-%m-%d %H:%M}"
        return message

    def recording_with_scheduled_stop(self, base_name: str, stop_at) -> str:
        return f"🔴 Recording: {base_name} | auto-stop {stop_at:%Y-%m-%d %H:%M}"

    def transcript_artifacts_saved_message(self, file_path: str, elapsed_seconds: float) -> str:
        return self.transcript_artifacts_saved.format(file_path=file_path, elapsed_seconds=elapsed_seconds)

    def transcript_artifacts_saved_cancelled_message(self, file_path: str, elapsed_seconds: float) -> str:
        return self.transcript_artifacts_saved_remaining_skipped.format(
            file_path=file_path,
            elapsed_seconds=elapsed_seconds,
        )

    def splitter_status(self, file_name: str, output_dir: str) -> str:
        return f"Source: {file_name} | Output to: {output_dir}"

    def splitter_error(self, error_message: str) -> str:
        return f"An error occurred during processing:\n{error_message}"


UI_TEXT = UIStrings()
