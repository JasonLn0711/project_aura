from __future__ import annotations

import unittest

from summary.field_schemas import metadata
from summary.markdown_renderer import render_markdown


class MarkdownRendererTests(unittest.TestCase):
    def test_markdown_rendered_from_json_not_llm(self) -> None:
        summary = {
            "meeting_topic": "Field-wise summary design",
            "participants": ["Jason", "Johnny"],
            "executive_summary": "The meeting defined a field-wise extraction pipeline.",
            "key_points": ["Use corrected transcript only.", "Render Markdown deterministically."],
            "decisions": [{"decision": "Use field-wise extraction.", "evidence_style": "explicit"}],
            "action_items": [
                {
                    "task": "Create separate field prompts.",
                    "owner": "Jason",
                    "deadline": "",
                    "status": "open",
                }
            ],
            "open_questions": ["How should validation errors be surfaced in the UI?"],
            "risks": ["Generated summaries may contain private meeting information."],
            "next_steps": ["Validate each field with Python type checks."],
            "metadata": metadata(),
        }

        markdown = render_markdown(summary)

        self.assertIn("# Meeting Summary", markdown)
        self.assertIn("## Topic", markdown)
        self.assertIn("Field-wise summary design", markdown)
        self.assertIn("- Jason", markdown)
        self.assertIn("- Use field-wise extraction.", markdown)
        self.assertIn("- Create separate field prompts. (owner: Jason; deadline: 未提及; status: open)", markdown)
        self.assertNotIn("metadata", markdown)

    def test_empty_sections_render_stable_placeholders(self) -> None:
        markdown = render_markdown(
            {
                "meeting_topic": "",
                "participants": [],
                "executive_summary": "",
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": [],
                "risks": [],
                "next_steps": [],
                "metadata": metadata(),
            }
        )

        self.assertIn("Untitled Meeting", markdown)
        self.assertGreaterEqual(markdown.count("- 未提及"), 7)


if __name__ == "__main__":
    unittest.main()
