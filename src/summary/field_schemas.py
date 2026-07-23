from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal


BASE_MODEL_ID = "google/gemma-4-E4B-it"
OLLAMA_MODEL_TAG = "gemma4:e4b-it-qat"
OLLAMA_NUM_CTX = 32768
OLLAMA_MAX_OUTPUT_TOKENS = 1536
OLLAMA_REASONING_ENABLED = True
ACTION_ITEM_STATUSES = {"open", "done", "blocked", "unknown"}
CLAIM_SUPPORT_STATUSES = {"supported", "partial", "unsupported"}
FIELD_NAMES = (
    "meeting_topic",
    "participants",
    "executive_summary",
    "key_points",
    "decisions",
    "action_items",
    "open_questions",
    "risks",
    "next_steps",
)
EXTRACTOR_FIELDS = {field: (field,) for field in FIELD_NAMES}
EXTRACTOR_NAMES = tuple(EXTRACTOR_FIELDS)
LIST_STRING_FIELDS = {
    "participants",
    "key_points",
    "open_questions",
    "risks",
    "next_steps",
}
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


@dataclass(frozen=True)
class FieldValidationResult:
    field: str
    valid: bool
    repaired: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_value(field: str) -> Any:
    if field == "meeting_topic":
        return "Untitled Meeting"
    if field == "executive_summary":
        return ""
    return []


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


def metadata() -> dict[str, Any]:
    return {
        "model": OLLAMA_MODEL_TAG,
        "base_model_id": BASE_MODEL_ID,
        "runner": "ollama",
        "ollama_num_ctx": OLLAMA_NUM_CTX,
        "ollama_max_output_tokens": OLLAMA_MAX_OUTPUT_TOKENS,
        "reasoning_enabled": OLLAMA_REASONING_ENABLED,
        "reasoning_trace_retained": False,
        "parallel_field_generation": True,
        "parallel_layered_generation": False,
        "external_calls": False,
        "cloud_calls": False,
    }


def expected_schema(field: str) -> dict[str, Any]:
    if field == "meeting_topic":
        return {"meeting_topic": "string"}
    if field == "participants":
        return {"participants": ["string"]}
    if field == "executive_summary":
        return {"executive_summary": "string"}
    if field in {"key_points", "open_questions", "risks", "next_steps"}:
        return {field: ["string"]}
    if field == "decisions":
        return {
            "decisions": [
                {
                    "decision": "string",
                    "evidence_style": "explicit",
                    "source_segment_ids": ["seg-001"],
                    "support_status": "supported",
                    "review_status": "unreviewed",
                }
            ]
        }
    if field == "action_items":
        return {
            "action_items": [
                {
                    "task": "string",
                    "owner": "string",
                    "deadline": "string",
                    "status": "open",
                    "source_segment_ids": ["seg-001"],
                    "support_status": "supported",
                    "review_status": "unreviewed",
                }
            ]
        }
    raise ValueError(f"Unknown summary field: {field}")


def expected_extractor_schema(extractor: str) -> dict[str, Any]:
    if extractor not in EXTRACTOR_FIELDS:
        raise ValueError(f"Unknown summary extractor: {extractor}")
    schema: dict[str, Any] = {}
    for field in EXTRACTOR_FIELDS[extractor]:
        schema.update(expected_schema(field))
    return schema


def parse_json_object(text: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(text, dict):
        return text
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _clip_text(value: str, max_chars: int = MAX_ITEM_CHARS) -> str:
    text = re.sub(r"\s+", " ", str(value).strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _normalize_string_list(value: Any, limit: int) -> tuple[list[str], str]:
    if not isinstance(value, list):
        return [], "value is not a list"
    items: list[str] = []
    for item in value[:limit]:
        if not isinstance(item, str):
            return [], "list item is not a string"
        text = _clip_text(item)
        if text:
            items.append(text)
    return items, ""


def _normalize_claim_evidence(item: dict[str, Any]) -> tuple[dict[str, Any], str]:
    source_segment_ids = item.get("source_segment_ids", [])
    support_status = item.get("support_status", "unsupported")
    review_status = item.get("review_status", "unreviewed")
    if not isinstance(source_segment_ids, list) or not all(
        isinstance(segment_id, str) for segment_id in source_segment_ids
    ):
        return {}, "source_segment_ids must be a list of strings"
    if not isinstance(support_status, str) or support_status not in CLAIM_SUPPORT_STATUSES:
        return {}, f"unsupported claim support status: {support_status}"
    if review_status != "unreviewed":
        return {}, "model claim review_status must be unreviewed"
    normalized_ids = list(
        dict.fromkeys(_clip_text(segment_id, 80) for segment_id in source_segment_ids if segment_id.strip())
    )
    if not normalized_ids and support_status != "unsupported":
        support_status = "unsupported"
    return {
        "source_segment_ids": normalized_ids,
        "support_status": support_status,
        "review_status": review_status,
    }, ""


def _normalize_decisions(value: Any) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(value, list):
        return [], "decisions is not a list"
    decisions: list[dict[str, Any]] = []
    for item in value[: FIELD_LIMITS["decisions"]]:
        if not isinstance(item, dict):
            return [], "decision item is not an object"
        decision = item.get("decision")
        evidence_style = item.get("evidence_style", "explicit")
        if not isinstance(decision, str) or not isinstance(evidence_style, str):
            return [], "decision object must contain string decision and evidence_style"
        decision = _clip_text(decision)
        evidence_style = evidence_style.strip() or "explicit"
        evidence, error = _normalize_claim_evidence(item)
        if error:
            return [], error
        if decision:
            decisions.append(
                {
                    "decision": decision,
                    "evidence_style": evidence_style,
                    **evidence,
                }
            )
    return decisions, ""


def _normalize_action_items(value: Any) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(value, list):
        return [], "action_items is not a list"
    action_items: list[dict[str, Any]] = []
    for item in value[: FIELD_LIMITS["action_items"]]:
        if not isinstance(item, dict):
            return [], "action item is not an object"
        task = item.get("task")
        owner = item.get("owner", "")
        deadline = item.get("deadline", "")
        status = item.get("status", "open")
        if not all(isinstance(value, str) for value in (task, owner, deadline, status)):
            return [], "action item object must contain string task, owner, deadline, and status"
        status = status.strip() or "unknown"
        if status not in ACTION_ITEM_STATUSES:
            return [], f"unsupported action item status: {status}"
        evidence, error = _normalize_claim_evidence(item)
        if error:
            return [], error
        task = _clip_text(task)
        if task:
            action_items.append(
                {
                    "task": task,
                    "owner": _clip_text(owner, 80),
                    "deadline": _clip_text(deadline, 80),
                    "status": status,
                    **evidence,
                }
            )
    return action_items, ""


def validate_field_value(field: str, payload: str | dict[str, Any]) -> tuple[Any, FieldValidationResult]:
    parsed = parse_json_object(payload)
    if field not in parsed:
        return default_value(field), FieldValidationResult(field=field, valid=False, error=f"missing field: {field}")
    value = parsed[field]
    if field in {"meeting_topic", "executive_summary"}:
        if not isinstance(value, str):
            return default_value(field), FieldValidationResult(field=field, valid=False, error="value is not a string")
        max_chars = 120 if field == "meeting_topic" else MAX_EXECUTIVE_SUMMARY_CHARS
        value = _clip_text(value, max_chars=max_chars)
        if field == "meeting_topic" and not value:
            value = default_value(field)
        return value, FieldValidationResult(field=field, valid=True)
    if field in LIST_STRING_FIELDS:
        value, error = _normalize_string_list(value, FIELD_LIMITS[field])
        return value, FieldValidationResult(field=field, valid=not error, error=error)
    if field == "decisions":
        value, error = _normalize_decisions(value)
        return value, FieldValidationResult(field=field, valid=not error, error=error)
    if field == "action_items":
        value, error = _normalize_action_items(value)
        return value, FieldValidationResult(field=field, valid=not error, error=error)
    return default_value(field), FieldValidationResult(field=field, valid=False, error=f"unknown field: {field}")


def validate_extractor_value(extractor: str, payload: str | dict[str, Any]) -> tuple[dict[str, Any], FieldValidationResult]:
    parsed = parse_json_object(payload)
    if extractor not in EXTRACTOR_FIELDS:
        return {}, FieldValidationResult(field=extractor, valid=False, error=f"unknown extractor: {extractor}")

    normalized: dict[str, Any] = {}
    errors: list[str] = []
    for field in EXTRACTOR_FIELDS[extractor]:
        value, result = validate_field_value(field, {field: parsed.get(field)})
        normalized[field] = value
        if not result.valid:
            errors.append(f"{field}: {result.error}")

    return normalized, FieldValidationResult(field=extractor, valid=not errors, error="; ".join(errors))


def validate_final_summary(summary: dict[str, Any]) -> bool:
    for field in FIELD_NAMES:
        value, result = validate_field_value(field, {field: summary.get(field)})
        if not result.valid:
            return False
        summary[field] = value
    return isinstance(summary.get("metadata"), dict)
