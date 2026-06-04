from __future__ import annotations

from typing import Any


def _render_string_list(items: list[str]) -> str:
    if not items:
        return "- 未提及"
    return "\n".join(f"- {item}" for item in items)


def _render_decisions(items: list[dict[str, str]]) -> str:
    if not items:
        return "- 未提及"
    return "\n".join(f"- {item.get('decision', '').strip()}" for item in items if item.get("decision", "").strip())


def _render_action_items(items: list[dict[str, str]]) -> str:
    if not items:
        return "- 未提及"
    lines: list[str] = []
    for item in items:
        task = item.get("task", "").strip()
        if not task:
            continue
        owner = item.get("owner", "").strip() or "未提及"
        deadline = item.get("deadline", "").strip() or "未提及"
        status = item.get("status", "").strip() or "unknown"
        lines.append(f"- {task} (owner: {owner}; deadline: {deadline}; status: {status})")
    return "\n".join(lines) if lines else "- 未提及"


def render_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Meeting Summary",
            "",
            "## Topic",
            "",
            str(summary.get("meeting_topic") or "Untitled Meeting"),
            "",
            "## Participants",
            "",
            _render_string_list(summary.get("participants", [])),
            "",
            "## Executive Summary",
            "",
            str(summary.get("executive_summary") or "未提及"),
            "",
            "## Key Points",
            "",
            _render_string_list(summary.get("key_points", [])),
            "",
            "## Decisions",
            "",
            _render_decisions(summary.get("decisions", [])),
            "",
            "## Action Items",
            "",
            _render_action_items(summary.get("action_items", [])),
            "",
            "## Open Questions",
            "",
            _render_string_list(summary.get("open_questions", [])),
            "",
            "## Risks",
            "",
            _render_string_list(summary.get("risks", [])),
            "",
            "## Next Steps",
            "",
            _render_string_list(summary.get("next_steps", [])),
            "",
        ]
    )
