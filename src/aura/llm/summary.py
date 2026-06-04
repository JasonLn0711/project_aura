from dataclasses import dataclass

from summary.field_schemas import BASE_MODEL_ID, OLLAMA_MODEL_TAG
from summary.layered_summary_pipeline import generate_layered_summary, save_layered_outputs


DEFAULT_SUMMARY_MODEL = BASE_MODEL_ID
DEFAULT_SUMMARY_LANGUAGE = "台灣繁體中文"


class SummaryDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class SummarySettings:
    enabled: bool = False
    model_id: str = DEFAULT_SUMMARY_MODEL
    quantization: str = "ollama_q4_K_M_local_tag"
    device_map: str = "auto"
    max_new_tokens: int = 768
    temperature: float = 0.2
    language: str = DEFAULT_SUMMARY_LANGUAGE


def transcript_has_content(transcript: str) -> bool:
    return bool(transcript and transcript.strip())


def build_summary_prompt(transcript: str, language: str = DEFAULT_SUMMARY_LANGUAGE) -> str:
    """Compatibility helper for tests and diagnostics.

    Runtime summary generation uses parallel layered extractor prompts under
    prompts/meeting_summary_layers/ instead of this one-shot prompt.
    """
    return (
        "Project AURA meeting summary uses parallel layered extractor prompts, not one-shot full-summary generation.\n"
        f"Approved local runner: ollama model {OLLAMA_MODEL_TAG}; base model {DEFAULT_SUMMARY_MODEL}.\n"
        "Input policy: use corrected transcript only; do not include raw transcript or correction_log.\n"
        f"輸出語言：{language}\n\n"
        "Corrected transcript:\n"
        f"{transcript.strip()}\n"
    )


def summarize_transcript(transcript: str, settings: SummarySettings | None = None) -> str:
    settings = settings or SummarySettings(enabled=True)
    if not transcript_has_content(transcript):
        return ""
    result = generate_layered_summary(transcript)
    save_layered_outputs(result)
    return result.markdown


def format_summary_block(summary: str) -> str:
    return "\n\n===== LLM Summary =====\n" + summary.strip()
