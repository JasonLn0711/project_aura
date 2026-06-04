import json
from pathlib import Path
from typing import Any

from asr_postprocess.fuzzy_corrector import DEFAULT_GLOSSARY_PATH, correct_transcript, write_correction_log


SUMMARY_MARKER = "===== LLM Summary ====="


def transcript_text_for_save(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        return ""
    return f"{cleaned}\n"


def write_transcript_file(file_path: str | Path, content: str) -> bool:
    text = transcript_text_for_save(content)
    if not text:
        return False
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def summary_text_for_save(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        return ""
    if SUMMARY_MARKER in cleaned:
        cleaned = cleaned.split(SUMMARY_MARKER, 1)[1].strip()
    return cleaned


def split_transcript_sections(content: str) -> tuple[str, str]:
    cleaned = content.strip()
    if SUMMARY_MARKER not in cleaned:
        return cleaned, ""
    raw, summary = cleaned.split(SUMMARY_MARKER, 1)
    return raw.strip(), summary.strip()


def final_transcript_text(raw_transcript: str, summary_text: str | None = None) -> str:
    raw = raw_transcript.strip()
    summary = summary_text_for_save(summary_text or "")
    if raw and summary:
        return f"{raw}\n\n{SUMMARY_MARKER}\n{summary}"
    if summary:
        return f"{SUMMARY_MARKER}\n{summary}"
    return raw


def transcript_artifact_paths(base_path: str | Path) -> dict[str, Path]:
    path = Path(base_path)
    if path.suffix:
        path = path.with_suffix("")
    return {
        "raw": path.with_name(f"{path.name}_raw.txt"),
        "corrected": path.with_name(f"{path.name}_corrected.txt"),
        "final": path.with_name(f"{path.name}_final.txt"),
        "summary": path.with_name(f"{path.name}_summary.txt"),
        "correction_log": path.with_name(f"{path.name}_correction_log.json"),
        "metrics": path.with_name(f"{path.name}_processing_metrics.json"),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def write_json_file(file_path: str | Path, payload: dict[str, Any]) -> Path:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_transcript_artifacts(
    base_path: str | Path,
    raw_transcript: str,
    summary_text: str | None = None,
    metrics: dict[str, Any] | None = None,
    enable_glossary_correction: bool = True,
    glossary_path: str | Path = DEFAULT_GLOSSARY_PATH,
) -> dict[str, Path]:
    paths = transcript_artifact_paths(base_path)
    saved: dict[str, Path] = {}

    if write_transcript_file(paths["raw"], raw_transcript):
        saved["raw"] = paths["raw"]

    transcript_for_final = raw_transcript
    correction_log: list[dict[str, Any]] = []
    if raw_transcript.strip() and enable_glossary_correction:
        correction_result = correct_transcript(raw_transcript, glossary_path=glossary_path)
        transcript_for_final = correction_result.corrected_transcript
        correction_log = correction_result.correction_log
        if write_transcript_file(paths["corrected"], transcript_for_final):
            saved["corrected"] = paths["corrected"]
        saved["correction_log"] = write_correction_log(paths["correction_log"], correction_log)

    summary = summary_text_for_save(summary_text or "")
    if summary and write_transcript_file(paths["summary"], summary):
        saved["summary"] = paths["summary"]

    final_text = final_transcript_text(transcript_for_final, summary)
    if write_transcript_file(paths["final"], final_text):
        saved["final"] = paths["final"]

    if metrics is not None:
        metrics["glossary_correction"] = {
            "enabled": enable_glossary_correction,
            "llm_verification": False,
            "correction_count": len(correction_log),
            "method": "rapidfuzz",
        }
        metrics_payload = dict(metrics)
        metrics_payload["outputs"] = {name: str(path) for name, path in saved.items()}
        saved["metrics"] = write_json_file(paths["metrics"], metrics_payload)

    return saved
