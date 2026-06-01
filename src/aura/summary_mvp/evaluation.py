from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from aura.summary_mvp.validation import ValidationResult


@dataclass(frozen=True)
class EvaluationMetrics:
    schema_validity_rate: float
    evidence_support_rate: float
    unsupported_claim_rate: float
    topic_coverage: float
    decision_capture_accuracy: float | None
    risk_constraint_capture_accuracy: float | None
    open_question_capture_accuracy: float | None
    human_preference_ranking: str
    human_correction_time: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_summaries(
    validation_results: dict[str, ValidationResult],
    expected_topics: list[str] | None = None,
    summary_outputs: dict[str, dict[str, Any]] | None = None,
) -> EvaluationMetrics:
    if not validation_results:
        return EvaluationMetrics(0.0, 0.0, 0.0, 0.0, None, None, None, "pending human review", "pending human review")

    total = len(validation_results)
    schema_valid = sum(
        1
        for result in validation_results.values()
        if result.valid_json and result.required_fields_present and result.evidence_required_fields_present
    )
    unsupported = sum(result.unsupported_claim_count for result in validation_results.values())
    evidence_failures = sum(1 for result in validation_results.values() if not result.evidence_chunks_exist)
    evidence_support_rate = max(0.0, 1.0 - ((unsupported + evidence_failures) / max(1, total * 8)))
    unsupported_claim_rate = unsupported / max(1, total)

    topic_coverage = 0.0
    if expected_topics and summary_outputs:
        covered = 0
        combined_topics = " ".join(
            str(topic.get("topic", ""))
            for output in summary_outputs.values()
            for topic in output.get("main_topics", [])
            if isinstance(topic, dict)
        ).lower()
        for topic in expected_topics:
            if topic.lower() in combined_topics:
                covered += 1
        topic_coverage = covered / len(expected_topics)

    return EvaluationMetrics(
        schema_validity_rate=schema_valid / total,
        evidence_support_rate=round(evidence_support_rate, 4),
        unsupported_claim_rate=round(unsupported_claim_rate, 4),
        topic_coverage=round(topic_coverage, 4),
        decision_capture_accuracy=None,
        risk_constraint_capture_accuracy=None,
        open_question_capture_accuracy=None,
        human_preference_ranking="pending human review",
        human_correction_time="pending human review",
    )


def render_markdown_report(metrics: EvaluationMetrics, model_status: dict[str, Any]) -> str:
    lines = [
        "# Meeting Summary MVP Experiment Report",
        "",
        "This offline MVP evaluates whether graph-aware RAG improves structured, evidence-grounded meeting summaries for noisy ASR transcripts.",
        "",
        "## Primary Metrics",
        "",
        f"- Unsupported claim rate: {metrics.unsupported_claim_rate}",
        f"- Evidence support rate: {metrics.evidence_support_rate}",
        f"- Topic coverage: {metrics.topic_coverage}",
        "",
        "## Full Metrics",
        "",
        f"- Schema validity rate: {metrics.schema_validity_rate}",
        f"- Decision capture accuracy: {metrics.decision_capture_accuracy}",
        f"- Risk / constraint capture accuracy: {metrics.risk_constraint_capture_accuracy}",
        f"- Open question capture accuracy: {metrics.open_question_capture_accuracy}",
        f"- Human preference ranking: {metrics.human_preference_ranking}",
        f"- Human correction time: {metrics.human_correction_time}",
        "",
        "## Model Execution Status",
        "",
    ]
    for setting, status in model_status.items():
        lines.append(f"- {setting}: {status}")
    lines.extend(
        [
            "",
            "## Scope",
            "",
            "The run keeps the MVP boundary: no speaker diarization, no ASR correction, no owner-specific action item extraction, and no PyQt integration.",
            "",
        ]
    )
    return "\n".join(lines)
