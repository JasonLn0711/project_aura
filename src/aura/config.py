SAMPLE_RATE = 16000
CHUNK_MS = 30
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_MS / 1000)
VAD_LEVEL = 3

MODEL_ID = "SoybeanMilk/faster-whisper-Breeze-ASR-25"
DIARIZATION_MODEL_ID = "pyannote/speaker-diarization-community-1"
CHINESE_PUNCTUATION_MODEL_ID = "p208p2002/zh-wiki-punctuation-restore"
CHINESE_PUNCTUATION_FALLBACK_MODEL_ID = ""
DEVICE = "cuda"
COMPUTE_TYPE = "int8"
GITHUB_REPOSITORY = "JasonLn0711/project_aura"

LIVE_CAPTURE_SYSTEM = "system"
LIVE_CAPTURE_MICROPHONE = "microphone"
LIVE_CAPTURE_SYSTEM_MICROPHONE = "system_microphone"
DEFAULT_LIVE_CAPTURE_SOURCE = LIVE_CAPTURE_SYSTEM_MICROPHONE

DEFAULT_PROMPT = "這是一份專業的繁體中文會議紀錄，請務必根據語氣加上正確的全形標點符號。"
DEFAULT_LIVE_PROMPT = "The following is a professional meeting record."

SUPPORTED_SPLIT_EXTENSIONS = {
    "mp3",
    "wav",
    "m4a",
    "ogg",
    "flac",
    "aac",
    "wma",
    "aiff",
    "opus",
}

SUPPORTED_IMPORT_EXTENSIONS = (
    "mp3",
    "mp4",
    "m4a",
    "wav",
    "flac",
    "mkv",
    "mov",
    "ogg",
    "aac",
    "wma",
    "aiff",
    "aif",
    "opus",
    "webm",
    "avi",
    "m4v",
    "3gp",
    "3g2",
)
