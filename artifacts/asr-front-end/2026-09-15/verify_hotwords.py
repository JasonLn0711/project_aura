"""Run from the repository root with .venv/bin/python; uses cached tokenizer only."""

import hashlib
import inspect
import json
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

from faster_whisper import WhisperModel
from faster_whisper.tokenizer import Tokenizer as WhisperTokenizer
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from aura.asr.hotwords import validate_context
from aura.config import MODEL_ID

root = Path(__file__).resolve().parents[3]
path = root / "hotwords-computer_vision_anomaly_detection-260915.txt"
raw = path.read_bytes()
text = raw.decode("utf-8").strip()
cached = Path(hf_hub_download(MODEL_ID, "tokenizer.json", local_files_only=True))
hf = Tokenizer.from_file(str(cached))
tokenizer = WhisperTokenizer(hf, multilingual=True, task="transcribe", language="zh")
tokens = tokenizer.encode(" " + text)
assert len(text.split("，")) == 27
assert len(tokens) == 223
assert "self.max_length = 448" in inspect.getsource(WhisperModel.__init__)
prompt = WhisperModel.get_prompt(SimpleNamespace(max_length=448), tokenizer, [], hotwords=text)
assert prompt == [tokenizer.sot_prev] + tokens + list(tokenizer.sot_sequence)
try:
    validate_context(hf, "", text)
except ValueError as error:
    aura_result = str(error)
else:
    raise AssertionError("Expected AURA's 200-token preflight to reject this list")
print(json.dumps({
    "date": "2026-09-15",
    "file": path.name,
    "sha256": hashlib.sha256(raw).hexdigest(),
    "model_id": MODEL_ID,
    "tokenizer_sha256": hashlib.sha256(cached.read_bytes()).hexdigest(),
    "faster_whisper_version": version("faster-whisper"),
    "terms": 27,
    "hotword_tokens": len(tokens),
    "get_prompt_untruncated": True,
    "aura_preflight": aura_result,
    "audio_inference_run": False,
    "human_accuracy_acceptance": "pending",
}, ensure_ascii=False, indent=2))
