from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_meeting_summary import (
    build_prompt,
    compact_summary,
    dry_run_summary,
    load_transcript,
    normalize_summary,
    render_markdown,
    write_outputs,
)


class PracticalMeetingSummaryTests(unittest.TestCase):
    def test_prompt_uses_corrected_transcript_only(self) -> None:
        prompt = build_prompt("智德萬 討論 510k summary。")

        self.assertIn("Use the corrected transcript only", prompt)
        self.assertIn("Do not use correction logs", prompt)
        self.assertIn("Preserve names exactly", prompt)
        self.assertIn("Preserve technical terms exactly", prompt)
        self.assertIn("Use no more than 5 bullets", prompt)
        self.assertIn("智德萬 討論 510k summary。", prompt)

    def test_json_normalization_has_fixed_schema(self) -> None:
        summary = normalize_summary(
            json.dumps(
                {
                    "meeting_topic": "demo",
                    "participants": ["Jason"],
                    "executive_summary": "討論 demo。",
                    "key_points": [{"text": "保留 510k summary"}],
                    "decisions": [{"content": "先做離線實驗"}],
                    "action_items": [{"item": "整理 TFDA 文件"}],
                    "open_questions": [{"text": "Friday meeting 前是否完成仍不確定"}],
                    "risks": [{"text": "沒有 GPU 可能不實際"}],
                    "next_steps": [{"item": "比較 graph RAG 和 vector RAG"}],
                },
                ensure_ascii=False,
            )
        )

        self.assertEqual(
            sorted(summary),
            [
                "action_items",
                "decisions",
                "executive_summary",
                "key_points",
                "meeting_topic",
                "next_steps",
                "open_questions",
                "participants",
                "risks",
            ],
        )
        self.assertEqual(summary["key_points"], ["保留 510k summary"])
        self.assertEqual(summary["action_items"], ["整理 TFDA 文件"])

    def test_markdown_report_has_user_facing_sections(self) -> None:
        markdown = render_markdown(
            {
                "meeting_topic": "Project AURA",
                "participants": [],
                "executive_summary": "討論 corrected transcript 到 meeting notes 的流程。",
                "key_points": ["使用 corrected transcript。"],
                "decisions": ["先做 practical pipeline。"],
                "action_items": [],
                "open_questions": ["是否接 UI 未決。"],
                "risks": ["不要產生 speculative action items。"],
                "next_steps": ["產出 Markdown。"],
            }
        )

        self.assertIn("# Meeting Summary", markdown)
        self.assertIn("## Executive Summary", markdown)
        self.assertIn("## Decisions", markdown)
        self.assertIn("## Action Items", markdown)
        self.assertIn("- 未提及", markdown)
        self.assertIn("先做 practical pipeline", markdown)

    def test_dry_run_extracts_practical_notes_without_speculative_action_items(self) -> None:
        summary = dry_run_summary(
            "暫定結論是先做離線實驗。法規素材需要整理 510k summary、TFDA 文件。"
            "如果沒有 GPU，完整 LLM 在本地跑可能不實際。"
        )

        self.assertTrue(summary["decisions"])
        self.assertEqual(summary["action_items"], [])
        self.assertTrue(any("510k summary" in item for item in summary["next_steps"]))
        self.assertTrue(summary["risks"])

    def test_compact_summary_limits_lists_and_item_length(self) -> None:
        summary = compact_summary(
            {
                "meeting_topic": "demo",
                "executive_summary": "x" * 700,
                "key_points": [f"point {index} " + ("x" * 300) for index in range(8)],
                "decisions": [f"decision {index}" for index in range(8)],
                "action_items": [],
                "open_questions": [],
                "risks": [],
                "next_steps": [],
                "participants": [],
            }
        )

        self.assertEqual(len(summary["key_points"]), 5)
        self.assertEqual(len(summary["decisions"]), 5)
        self.assertLessEqual(len(summary["executive_summary"]), 600)
        self.assertTrue(summary["key_points"][0].endswith("…"))

    def test_load_transcript_supports_json_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meeting.json"
            path.write_text(
                json.dumps({"asr_transcript": [{"text": "第一段"}, {"text": "第二段"}]}, ensure_ascii=False),
                encoding="utf-8",
            )

            self.assertEqual(load_transcript(path), "第一段\n第二段")

    def test_write_outputs_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            markdown_path = Path(temp_dir) / "summary.md"
            json_path = Path(temp_dir) / "summary.json"
            summary = normalize_summary({"meeting_topic": "demo", "executive_summary": "完成。"})

            write_outputs(summary, markdown_path, json_path)

            self.assertIn("# Meeting Summary", markdown_path.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["meeting_topic"], "demo")

    def test_no_correction_log_read_during_prompt_build(self) -> None:
        prompt = build_prompt("corrected transcript only")

        self.assertIn("corrected transcript only", prompt)
        self.assertNotIn("correction_log.json", prompt)


if __name__ == "__main__":
    unittest.main()
