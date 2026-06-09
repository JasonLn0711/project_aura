from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from aura.summary_mvp.embeddings import tokenize
from aura.summary_mvp.schema import TranscriptChunk


REQUIRED_FIELDS = {
    "meeting_summary",
    "main_topics",
    "key_points",
    "decisions_or_tentative_conclusions",
    "open_questions",
    "risks_and_constraints",
    "possible_next_steps",
    "low_confidence_sections",
}
EVIDENCE_REQUIRED_FIELDS = {
    "main_topics": "topic",
    "key_points": "point",
    "decisions_or_tentative_conclusions": "content",
    "open_questions": "question",
    "risks_and_constraints": "risk",
    "possible_next_steps": "step",
    "low_confidence_sections": "reason",
}
SPEAKER_ATTRIBUTION_RE = re.compile(
    r"\b(?:Jason|Prof\.?|Professor|Dr\.?|Mr\.?|Ms\.?)\b|(?:說|表示|提到)[:：]",
    re.IGNORECASE,
)
OWNER_CLAIM_RE = re.compile(r"(負責人|owner|由[A-Za-z\u4e00-\u9fff]{1,8}負責|指派給)", re.IGNORECASE)


@dataclass(frozen=True)
class ValidationResult:
    valid_json: bool
    required_fields_present: bool
    evidence_chunks_exist: bool
    evidence_required_fields_present: bool
    no_speaker_attribution: bool
    no_owner_specific_next_steps: bool
    unsupported_claim_count: int
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_summary_json(raw_output: str | dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    if isinstance(raw_output, dict):
        return raw_output, []
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        return None, [f"Output is not valid JSON: {exc}"]
    if not isinstance(parsed, dict):
        return None, ["Output JSON must be an object."]
    return parsed, []


def _item_text(item: dict[str, Any], value_key: str) -> str:
    value = item.get(value_key, "")
    return value if isinstance(value, str) else ""


def _evidence_supports(text: str, evidence_chunks: list[str], chunk_text_by_id: dict[str, str]) -> bool:
    if not text.strip() or not evidence_chunks:
        return False
    claim_tokens = {token for token in tokenize(text) if len(token) > 1}
    if not claim_tokens:
        return True
    evidence_text = " ".join(chunk_text_by_id.get(chunk_id, "") for chunk_id in evidence_chunks)
    evidence_tokens = set(tokenize(evidence_text))
    if not evidence_tokens:
        return False
    overlap = claim_tokens & evidence_tokens
    return len(overlap) >= max(1, min(3, len(claim_tokens) // 4))


def validate_summary(raw_output: str | dict[str, Any], chunks: list[TranscriptChunk]) -> ValidationResult:
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    chunk_text_by_id = {chunk.chunk_id: chunk.text for chunk in chunks}
    parsed, errors = parse_summary_json(raw_output)
    if parsed is None:
        return ValidationResult(
            valid_json=False,
            required_fields_present=False,
            evidence_chunks_exist=False,
            evidence_required_fields_present=False,
            no_speaker_attribution=False,
            no_owner_specific_next_steps=False,
            unsupported_claim_count=0,
            errors=errors,
        )

    missing_fields = sorted(REQUIRED_FIELDS - set(parsed))
    if missing_fields:
        errors.append(f"Missing required fields: {', '.join(missing_fields)}")

    evidence_chunks_exist = True
    evidence_required_fields_present = True
    unsupported_claim_count = 0

    for field_name, value_key in EVIDENCE_REQUIRED_FIELDS.items():
        values = parsed.get(field_name, [])
        if not isinstance(values, list):
            evidence_required_fields_present = False
            errors.append(f"{field_name} must be a list.")
            continue
        for index, item in enumerate(values, start=1):
            if not isinstance(item, dict):
                evidence_required_fields_present = False
                errors.append(f"{field_name}[{index}] must be an object.")
                continue
            evidence = item.get("evidence_chunks")
            if not isinstance(evidence, list) or not evidence or not all(isinstance(chunk_id, str) for chunk_id in evidence):
                evidence_required_fields_present = False
                errors.append(f"{field_name}[{index}] must include evidence_chunks.")
                evidence = []
            missing = sorted(set(evidence) - chunk_ids)
            if missing:
                evidence_chunks_exist = False
                errors.append(f"{field_name}[{index}] references unknown chunks: {', '.join(missing)}")
            if value_key not in item or not isinstance(item.get(value_key), str):
                evidence_required_fields_present = False
                errors.append(f"{field_name}[{index}] must include string field {value_key}.")
            if field_name != "low_confidence_sections" and not _evidence_supports(
                _item_text(item, value_key),
                evidence,
                chunk_text_by_id,
            ):
                unsupported_claim_count += 1

    all_text = json.dumps(parsed, ensure_ascii=False)
    no_speaker_attribution = SPEAKER_ATTRIBUTION_RE.search(all_text) is None
    if not no_speaker_attribution:
        errors.append("Output includes speaker attribution.")

    next_steps_text = json.dumps(parsed.get("possible_next_steps", []), ensure_ascii=False)
    no_owner_specific_next_steps = OWNER_CLAIM_RE.search(next_steps_text) is None
    if not no_owner_specific_next_steps:
        errors.append("possible_next_steps includes owner-specific action item claims.")

    return ValidationResult(
        valid_json=True,
        required_fields_present=not missing_fields,
        evidence_chunks_exist=evidence_chunks_exist,
        evidence_required_fields_present=evidence_required_fields_present,
        no_speaker_attribution=no_speaker_attribution,
        no_owner_specific_next_steps=no_owner_specific_next_steps,
        unsupported_claim_count=unsupported_claim_count,
        errors=errors,
    )
