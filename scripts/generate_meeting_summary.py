from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from summary.field_schemas import metadata, validate_final_summary  # noqa: E402
from summary.layered_summary_pipeline import LayeredSummaryResult, generate_layered_summary, save_layered_outputs  # noqa: E402
from summary.markdown_renderer import render_markdown  # noqa: E402

DEFAULT_SAMPLE_TRANSCRIPT = REPO_ROOT / "tests" / "fixtures" / "asr_transcripts" / "synthetic_meeting_001.json"
DEFAULT_REPORT_MD = REPO_ROOT / "reports" / "sample_meeting_summary.md"
DEFAULT_REPORT_JSON = REPO_ROOT / "reports" / "sample_meeting_summary.json"


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


def dry_run_summary(transcript: str) -> dict[str, Any]:
    lower = transcript.lower()
    decisions: list[dict[str, str]] = []
    action_items: list[dict[str, str]] = []
    next_steps: list[str] = []
    risks: list[str] = []
    open_questions: list[str] = []
    if "暫定結論" in transcript or "先做離線實驗" in transcript:
        decisions.append(
            {
                "decision": "暫定先做離線實驗，schema validation 和 evidence support 比較完成後再看 PyQt 整合。",
                "evidence_style": "explicit",
            }
        )
    if "510k" in lower or "tfda" in lower:
        next_steps.append("整理 510k summary、TFDA 文件，確認哪些內容可用於展示。")
    if "friday meeting" in lower or "不確定" in transcript:
        open_questions.append("Friday meeting 前是否能產出 graph RAG、vector RAG 和 direct summary 的比較表仍不確定。")
    if "沒有 gpu" in lower or "gpu" in lower:
        risks.append("沒有 GPU 時，完整 LLM 本地執行可能不實際。")
    summary = {
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
        "action_items": action_items,
        "open_questions": open_questions,
        "risks": risks,
        "next_steps": next_steps,
        "metadata": metadata(),
    }
    validate_final_summary(summary)
    return summary


def write_outputs(summary: dict[str, Any], markdown_path: Path, json_path: Path) -> None:
    if not validate_final_summary(summary):
        raise RuntimeError("Final meeting summary schema is invalid.")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate parallel field-batch Project AURA meeting notes from a corrected transcript.")
    parser.add_argument("--transcript", type=Path, default=DEFAULT_SAMPLE_TRANSCRIPT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    transcript = load_transcript(args.transcript)
    if not transcript:
        raise RuntimeError(f"Corrected transcript is empty: {args.transcript}")
    if args.dry_run:
        summary = dry_run_summary(transcript)
        markdown = render_markdown(summary)
    else:
        result: LayeredSummaryResult = generate_layered_summary(transcript)
        save_layered_outputs(result)
        summary = result.summary
        markdown = result.markdown
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown, encoding="utf-8")
    args.output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output_md": str(args.output_md), "output_json": str(args.output_json)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
