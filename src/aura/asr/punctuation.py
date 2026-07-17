import re
from dataclasses import dataclass

from aura.config import CHINESE_PUNCTUATION_FALLBACK_MODEL_ID, CHINESE_PUNCTUATION_MODEL_ID


CHINESE_PUNCTUATION = "，。？！、；："
TERMINAL_PUNCTUATION = "。？！.!?"
ASCII_TO_FULLWIDTH_PUNCTUATION = {
    ",": "，",
    ".": "。",
    "?": "？",
    "!": "！",
    ";": "；",
    ":": "：",
}
LABEL_TO_CHINESE_PUNCTUATION = {
    "0": "",
    "1": "，",
    "2": "。",
    "3": "？",
    "4": "！",
    "5": "、",
    "NONE": "",
    "NULL": "",
    "O": "",
    "COMMA": "，",
    "PERIOD": "。",
    "FULLSTOP": "。",
    "QUESTION": "？",
    "EXCLAMATION": "！",
    "ENUMERATION": "、",
}
TRADITIONAL_HINT_CHARS = set(
    "這個們會與為對時後國學體開關門臺灣語聽錄製標點號聲音系統檔案處理優化閱讀體驗"
)
SIMPLIFIED_HINT_CHARS = set(
    "这个们会与为对时后国学体开关门台湾语听录制标点号声音系统档案处理优化阅读体验"
)
LINE_PREFIX_RE = re.compile(r"^(\[\d{2}:\d{2}:\d{2}\]\s*(?:[A-Z][A-Z0-9_ -]{0,48}:\s*)?)(.*)$")
JAPANESE_KANA_RE = re.compile(r"[\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
PUNCTUATION_SETUP_GUIDANCE = (
    "Activate local punctuation model support with `make setup-app` in a uv checkout or "
    "`python -m pip install -e \".[punctuation]\"` in a pip environment, then restart AURA."
)

_DEFAULT_RESTORER = None


@dataclass(frozen=True)
class PunctuationResult:
    text: str
    backend: str = "skipped"
    changed: bool = False
    detail: str = ""


def contains_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text or ""))


def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text or ""))


def is_chinese_language(language: str | None) -> bool:
    if not language:
        return False
    normalized = str(language).strip().lower().replace("_", "-")
    return (
        normalized.startswith("zh")
        or "chinese" in normalized
        or "mandarin" in normalized
        or "taiwan" in normalized
        or "traditional" in normalized
    )


def looks_like_traditional_chinese(text: str, language: str | None = None) -> bool:
    if not contains_cjk(text) or JAPANESE_KANA_RE.search(text or ""):
        return False

    traditional_hits = sum(1 for char in text if char in TRADITIONAL_HINT_CHARS)
    simplified_hits = sum(1 for char in text if char in SIMPLIFIED_HINT_CHARS)
    if traditional_hits:
        return traditional_hits >= simplified_hits
    if simplified_hits:
        return False
    return is_chinese_language(language)


def should_restore_traditional_chinese_punctuation(text: str, language: str | None = None) -> bool:
    return looks_like_traditional_chinese(text, language)


def split_line_prefix(line: str) -> tuple[str, str]:
    match = LINE_PREFIX_RE.match(line)
    if not match:
        return "", line
    return match.group(1), match.group(2)


def has_readable_chinese_punctuation(text: str) -> bool:
    return any(char in CHINESE_PUNCTUATION for char in text or "")


def needs_model_punctuation(text: str) -> bool:
    body = (text or "").strip()
    return cjk_count(body) >= 6 and not has_readable_chinese_punctuation(body)


def normalize_chinese_punctuation(text: str) -> str:
    if not text:
        return text

    chars = []
    for index, char in enumerate(text):
        previous_char = text[index - 1] if index > 0 else ""
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if char in ASCII_TO_FULLWIDTH_PUNCTUATION and (contains_cjk(previous_char) or contains_cjk(next_char)):
            chars.append(ASCII_TO_FULLWIDTH_PUNCTUATION[char])
        else:
            chars.append(char)

    normalized = "".join(chars)
    normalized = re.sub(r"\s+([，。？！、；：])", r"\1", normalized)
    normalized = re.sub(r"([，。？！、；：])\s+", r"\1", normalized)
    normalized = re.sub(r"([，。？！、；：])\1+", r"\1", normalized)

    stripped = normalized.rstrip()
    if cjk_count(stripped) >= 4 and stripped[-1:] and stripped[-1] not in TERMINAL_PUNCTUATION:
        normalized = stripped + "。"
    return normalized


def punctuation_label_to_text(label) -> str:
    label_text = str(label).strip()
    if label_text in CHINESE_PUNCTUATION:
        return label_text
    for punctuation in CHINESE_PUNCTUATION:
        if label_text.endswith(punctuation):
            return punctuation
    upper_label = label_text.upper().replace("LABEL_", "").replace("PUNCT_", "")
    return LABEL_TO_CHINESE_PUNCTUATION.get(upper_label, "")


def insert_punctuation_by_offsets(text: str, punctuation_by_end: dict[int, str]) -> str:
    if not punctuation_by_end:
        return text

    output = []
    for index, char in enumerate(text):
        output.append(char)
        char_end = index + 1
        punctuation = punctuation_by_end.get(char_end, "")
        next_char = text[char_end] if char_end < len(text) else ""
        char_is_punctuation = char in CHINESE_PUNCTUATION or char in TERMINAL_PUNCTUATION
        next_is_punctuation = bool(next_char) and (
            next_char in CHINESE_PUNCTUATION or next_char in TERMINAL_PUNCTUATION
        )
        if (
            punctuation
            and not char_is_punctuation
            and not next_is_punctuation
        ):
            output.append(punctuation)
    return "".join(output)


def chunk_text(text: str, max_chars: int = 320) -> list[str]:
    stripped = (text or "").strip()
    if not stripped:
        return []
    return [stripped[index : index + max_chars] for index in range(0, len(stripped), max_chars)]


class TransformersChinesePunctuationRestorer:
    def __init__(
        self,
        model_id: str = CHINESE_PUNCTUATION_MODEL_ID,
        fallback_model_id: str = CHINESE_PUNCTUATION_FALLBACK_MODEL_ID,
        device: str = "auto",
    ):
        self.model_ids = tuple(model for model in (model_id, fallback_model_id) if model)
        self.model_id = self.model_ids[0] if self.model_ids else model_id
        self.requested_device = device
        self.tokenizer = None
        self.model = None
        self.torch = None
        self.device = "cpu"
        self.load_error = ""

    def _load(self):
        if self.model is not None and self.tokenizer is not None:
            return
        if self.load_error:
            raise RuntimeError(self.load_error)

        try:
            import torch
            from transformers import AutoModelForTokenClassification, AutoTokenizer
        except ModuleNotFoundError as exc:
            missing = exc.name or "punctuation model dependency"
            self.load_error = f"Dependency `{missing}` needs activation. {PUNCTUATION_SETUP_GUIDANCE}"
            raise RuntimeError(self.load_error) from exc

        self.torch = torch
        self.device = "cuda" if self.requested_device == "auto" and torch.cuda.is_available() else self.requested_device
        if self.device == "auto":
            self.device = "cpu"

        errors = []
        for model_id in self.model_ids:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)
                self.model = AutoModelForTokenClassification.from_pretrained(model_id)
                self.model_id = model_id
                break
            except Exception as exc:
                self.tokenizer = None
                self.model = None
                errors.append(f"{model_id}: {exc}")
        if self.model is None or self.tokenizer is None:
            # ponytail: retry once per process; restart AURA after repairing model access.
            self.load_error = "; ".join(errors) or "No Chinese punctuation model could be loaded."
            raise RuntimeError(self.load_error)

        self.model.to(self.device)
        self.model.eval()

    def restore(self, text: str) -> str:
        self._load()
        restored_chunks = [self._restore_chunk(chunk) for chunk in chunk_text(text)]
        return normalize_chinese_punctuation("".join(restored_chunks))

    def _restore_chunk(self, text: str) -> str:
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            return_offsets_mapping=True,
            truncation=True,
            max_length=510,
        )
        offsets = inputs.pop("offset_mapping")[0].tolist()
        model_inputs = {key: value.to(self.device) for key, value in inputs.items()}

        with self.torch.inference_mode():
            logits = self.model(**model_inputs).logits[0]
            predictions = logits.argmax(dim=-1).detach().cpu().tolist()

        id2label = getattr(self.model.config, "id2label", {})
        punctuation_by_end = {}
        for prediction, offset in zip(predictions, offsets):
            if not offset or len(offset) != 2:
                continue
            start, end = offset
            if end <= start:
                continue
            label = id2label.get(int(prediction), prediction)
            punctuation = punctuation_label_to_text(label)
            if punctuation:
                punctuation_by_end[int(end)] = punctuation

        return insert_punctuation_by_offsets(text, punctuation_by_end)


def default_restorer() -> TransformersChinesePunctuationRestorer:
    global _DEFAULT_RESTORER
    if _DEFAULT_RESTORER is None:
        _DEFAULT_RESTORER = TransformersChinesePunctuationRestorer()
    return _DEFAULT_RESTORER


def restore_chinese_punctuation(
    text: str,
    language: str | None = None,
    restorer=None,
    enable_model: bool = True,
) -> PunctuationResult:
    if not should_restore_traditional_chinese_punctuation(text, language):
        return PunctuationResult(text=text)

    normalized_fallback = normalize_chinese_punctuation(text.strip())
    if not enable_model or not needs_model_punctuation(text):
        return PunctuationResult(
            text=normalized_fallback,
            backend="rule_fallback",
            changed=normalized_fallback != text,
        )

    active_restorer = restorer or default_restorer()
    try:
        restored = active_restorer.restore(text)
        restored = normalize_chinese_punctuation(restored)
        return PunctuationResult(text=restored, backend="model", changed=restored != text)
    except Exception as exc:
        return PunctuationResult(
            text=normalized_fallback,
            backend="rule_fallback",
            changed=normalized_fallback != text,
            detail=str(exc),
        )


def restore_chinese_punctuation_for_line(
    line: str,
    language: str | None = None,
    restorer=None,
    enable_model: bool = True,
) -> PunctuationResult:
    prefix, body = split_line_prefix(line)
    result = restore_chinese_punctuation(body, language=language, restorer=restorer, enable_model=enable_model)
    return PunctuationResult(
        text=f"{prefix}{result.text}",
        backend=result.backend,
        changed=f"{prefix}{result.text}" != line,
        detail=result.detail,
    )


def restore_chinese_punctuation_for_transcript(
    transcript: str,
    language: str | None = None,
    restorer=None,
    enable_model: bool = True,
) -> PunctuationResult:
    lines = transcript.splitlines()
    restored_lines = []
    backends = []
    details = []
    for line in lines:
        result = restore_chinese_punctuation_for_line(
            line,
            language=language,
            restorer=restorer,
            enable_model=enable_model,
        )
        restored_lines.append(result.text)
        if result.backend != "skipped":
            backends.append(result.backend)
        if result.detail:
            details.append(result.detail)

    restored_text = "\n".join(restored_lines)
    backend = "skipped"
    if "model" in backends:
        backend = "model"
    elif "rule_fallback" in backends:
        backend = "rule_fallback"
    return PunctuationResult(
        text=restored_text,
        backend=backend,
        changed=restored_text != transcript,
        detail="; ".join(details[:2]),
    )
