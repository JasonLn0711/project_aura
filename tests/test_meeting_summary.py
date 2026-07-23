from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_meeting_summary import dry_run_summary, load_transcript, write_outputs
from summary.field_schemas import (
    BASE_MODEL_ID,
    OLLAMA_MAX_OUTPUT_TOKENS,
    OLLAMA_MODEL_TAG,
    OLLAMA_NUM_CTX,
    OLLAMA_REASONING_ENABLED,
    validate_final_summary,
)


class PracticalMeetingSummaryTests(unittest.TestCase):
    def test_dry_run_uses_final_schema_with_metadata(self) -> None:
        summary = dry_run_summary(
            "暫定結論是先做離線實驗。法規素材需要整理 510k summary、TFDA 文件。"
            "如果沒有 GPU，完整 LLM 在本地跑可能不實際。"
        )

        self.assertTrue(validate_final_summary(summary))
        self.assertEqual(summary["metadata"]["model"], OLLAMA_MODEL_TAG)
        self.assertEqual(summary["metadata"]["base_model_id"], BASE_MODEL_ID)
        self.assertEqual(summary["metadata"]["ollama_num_ctx"], OLLAMA_NUM_CTX)
        self.assertEqual(
            summary["metadata"]["ollama_max_output_tokens"],
            OLLAMA_MAX_OUTPUT_TOKENS,
        )
        self.assertIs(summary["metadata"]["reasoning_enabled"], OLLAMA_REASONING_ENABLED)
        self.assertFalse(summary["metadata"]["reasoning_trace_retained"])
        self.assertTrue(summary["metadata"]["parallel_field_generation"])
        self.assertFalse(summary["metadata"]["parallel_layered_generation"])
        self.assertFalse(summary["metadata"]["external_calls"])
        self.assertFalse(summary["metadata"]["cloud_calls"])

    def test_dry_run_extracts_practical_notes_without_speculative_action_items(self) -> None:
        summary = dry_run_summary(
            "暫定結論是先做離線實驗。法規素材需要整理 510k summary、TFDA 文件。"
            "如果沒有 GPU，完整 LLM 在本地跑可能不實際。"
        )

        self.assertTrue(summary["decisions"])
        self.assertEqual(summary["decisions"][0]["evidence_style"], "explicit")
        self.assertEqual(summary["action_items"], [])
        self.assertTrue(any("510k summary" in item for item in summary["next_steps"]))
        self.assertTrue(summary["risks"])

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
            summary = dry_run_summary("暫定結論是先做離線實驗。")

            write_outputs(summary, markdown_path, json_path)

            self.assertIn("# Meeting Summary", markdown_path.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["meeting_topic"], summary["meeting_topic"])


if __name__ == "__main__":
    unittest.main()
