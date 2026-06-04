from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from scripts.run_gemma4_e4b_summary_impact import (  # noqa: E402
    DEFAULT_CONFIG,
    FIXED_MODEL_ID,
    FIXED_OLLAMA_MODEL,
    check_model_available,
    load_config,
    ollama_request,
    runner_config,
)

DEFAULT_PROMPT = REPO_ROOT / "prompts" / "meeting_summary_v1.txt"
DEFAULT_SAMPLE_TRANSCRIPT = REPO_ROOT / "tests" / "fixtures" / "asr_transcripts" / "synthetic_meeting_001.json"
DEFAULT_REPORT_MD = REPO_ROOT / "reports" / "sample_meeting_summary.md"
DEFAULT_REPORT_JSON = REPO_ROOT / "reports" / "sample_meeting_summary.json"
SUMMARY_FIELDS = (
    "participants",
    "key_points",
    "decisions",
    "action_items",
    "open_questions",
    "risks",
    "next_steps",
)
FIELD_LIMITS = {
    "participants": 8,
    "key_points": 5,
    "decisions": 5,
    "action_items": 5,
    "open_questions": 5,
    "risks": 5,
    "next_steps": 5,
}
MAX_ITEM_CHARS = 220
MAX_EXECUTIVE_SUMMARY_CHARS = 600


def empty_summary() -> dict[str, Any]:
    return {
        "meeting_topic": "",
        "participants": [],
        "executive_summary": "",
        "key_points": [],
        "decisions": [],
        "action_items": [],
        "open_questions": [],
        "risks": [],
        "next_steps": [],
    }


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def transcript_from_json_fixture(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = payload.get("asr_transcript", [])
    if not isinstance(segments, list):
        return ""
    return "\n".join(str(segment.get("text", "")).strip() for segment in segments if isinstance(segment, dict)).strip()


def load_transcript(path: Path) -> str:
    if path.suffix.lower() == ".json":
        text = transcript_from_json_fixture(path)
        if text:
            return text
    return read_text(path).strip()


def build_prompt(corrected_transcript: str, prompt_path: Path = DEFAULT_PROMPT) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    return template.replace("{{CORRECTED_TRANSCRIPT}}", corrected_transcript.strip())


def parse_json_object(text: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(text, dict):
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, dict):
            raw = item.get("item") or item.get("text") or item.get("content") or item.get("name")
        else:
            raw = item
        text = str(raw or "").strip()
        if text:
            items.append(text)
    return items


def _clip_text(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    compacted = empty_summary()
    compacted["meeting_topic"] = _clip_text(str(summary.get("meeting_topic") or ""), 120)
    compacted["executive_summary"] = _clip_text(
        str(summary.get("executive_summary") or ""),
        MAX_EXECUTIVE_SUMMARY_CHARS,
    )
    for field in SUMMARY_FIELDS:
        values = summary.get(field, [])
        if not isinstance(values, list):
            values = []
        compacted[field] = [_clip_text(str(item), MAX_ITEM_CHARS) for item in values[: FIELD_LIMITS[field]]]
    return compacted


def normalize_summary(payload: str | dict[str, Any]) -> dict[str, Any]:
    parsed = parse_json_object(payload)
    summary = empty_summary()
    for key in ("meeting_topic", "executive_summary"):
        value = parsed.get(key)
        if isinstance(value, str):
            summary[key] = value.strip()
    for field in SUMMARY_FIELDS:
        summary[field] = _string_list(parsed.get(field))
    return compact_summary(summary)


def dry_run_summary(transcript: str) -> dict[str, Any]:
    lower = transcript.lower()
    decisions: list[str] = []
    next_steps: list[str] = []
    risks: list[str] = []
    open_questions: list[str] = []
    if "暫定結論" in transcript or "先做離線實驗" in transcript:
        decisions.append("暫定先做離線實驗，schema validation 和 evidence support 比較完成後再看 PyQt 整合。")
    if "510k" in lower or "tfda" in lower:
        next_steps.append("整理 510k summary、TFDA 文件，確認哪些內容可用於展示。")
    if "friday meeting" in lower or "不確定" in transcript:
        open_questions.append("Friday meeting 前是否能產出 graph RAG、vector RAG 和 direct summary 的比較表仍不確定。")
    if "沒有 gpu" in lower or "gpu" in lower:
        risks.append("沒有 GPU 時，完整 LLM 本地執行可能不實際。")
    return compact_summary(
        {
            "meeting_topic": "英文版 demo、本地部署與摘要實驗規劃",
            "participants": [],
            "executive_summary": (
                "會議聚焦英文版 demo、本地部署限制、法規素材整理，以及 direct/vector/graph RAG 摘要比較的下一步。"
            ),
            "key_points": [
                "英文版 demo 需要能穩定呈現，並考慮 all in one device 的本地部署。",
                "INT8 小模型與 evidence chunk 可追溯性是目前實驗重點。",
                "法規素材需要整理 510k summary 與 TFDA 文件。",
            ],
            "decisions": decisions,
            "action_items": [],
            "open_questions": open_questions,
            "risks": risks,
            "next_steps": next_steps,
        }
    )


class LocalGemmaMeetingSummaryRunner:
    def __init__(self, config_path: Path = DEFAULT_CONFIG) -> None:
        payload = load_config(config_path)
        self.config = runner_config(payload)
        if self.config.model_id != FIXED_MODEL_ID or self.config.ollama_model != FIXED_OLLAMA_MODEL:
            raise RuntimeError("Meeting summary v1 requires the fixed approved local Gemma 4 E4B runner.")

    def generate(self, corrected_transcript: str, prompt_path: Path = DEFAULT_PROMPT) -> dict[str, Any]:
        available, reason = check_model_available(self.config)
        if not available:
            raise RuntimeError(reason)
        response = ollama_request(
            self.config.ollama_host,
            "/api/generate",
            payload={
                "model": self.config.ollama_model,
                "prompt": build_prompt(corrected_transcript, prompt_path),
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": self.config.temperature,
                    "seed": self.config.seed,
                    "num_predict": self.config.max_output_tokens,
                    "num_ctx": self.config.ollama_num_ctx,
                },
            },
            timeout=self.config.timeout_sec,
        )
        return normalize_summary(str(response.get("response") or ""))


def render_list(items: list[str]) -> str:
    if not items:
        return "- 未提及"
    return "\n".join(f"- {item}" for item in items)


def render_markdown(summary: dict[str, Any]) -> str:
    topic = summary.get("meeting_topic") or "未命名會議"
    participants = render_list(summary.get("participants", []))
    executive_summary = summary.get("executive_summary") or "未提及"
    return "\n".join(
        [
            "# Meeting Summary",
            "",
            f"**Topic:** {topic}",
            "",
            "## Participants",
            "",
            participants,
            "",
            "## Executive Summary",
            "",
            executive_summary,
            "",
            "## Key Points",
            "",
            render_list(summary.get("key_points", [])),
            "",
            "## Decisions",
            "",
            render_list(summary.get("decisions", [])),
            "",
            "## Action Items",
            "",
            render_list(summary.get("action_items", [])),
            "",
            "## Open Questions",
            "",
            render_list(summary.get("open_questions", [])),
            "",
            "## Risks",
            "",
            render_list(summary.get("risks", [])),
            "",
            "## Next Steps",
            "",
            render_list(summary.get("next_steps", [])),
            "",
        ]
    )


def write_outputs(summary: dict[str, Any], markdown_path: Path, json_path: Path) -> None:
    summary = compact_summary(summary)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate practical Project AURA meeting notes from a corrected transcript.")
    parser.add_argument("--transcript", type=Path, default=DEFAULT_SAMPLE_TRANSCRIPT)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    transcript = load_transcript(args.transcript)
    if not transcript:
        raise RuntimeError(f"Corrected transcript is empty: {args.transcript}")
    if args.dry_run:
        summary = dry_run_summary(transcript)
    else:
        summary = LocalGemmaMeetingSummaryRunner(args.config).generate(transcript, args.prompt)
    write_outputs(summary, args.output_md, args.output_json)
    print(json.dumps({"output_md": str(args.output_md), "output_json": str(args.output_json)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
