from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aura.summary_mvp.chunking import build_sliding_window_chunks, build_time_chunks
from aura.summary_mvp.embeddings import embed_chunks_with_backend
from aura.summary_mvp.evaluation import evaluate_summaries, render_markdown_report
from aura.summary_mvp.graph import build_evidence_graph
from aura.summary_mvp.models import DEFAULT_MODEL_IDS, ModelRunnerConfig, run_model_or_dry_run
from aura.summary_mvp.prompts import assemble_summary_prompt
from aura.summary_mvp.retrieval import build_evidence_packets
from aura.summary_mvp.schema import SummaryMode, load_transcript_payload
from aura.summary_mvp.validation import validate_summary


EXPERIMENT_SETTINGS: tuple[tuple[str, str, SummaryMode], ...] = (
    ("qwen_direct", "qwen", "direct"),
    ("qwen_vector_rag", "qwen", "vector_rag"),
    ("qwen_graph_rag", "qwen", "graph_rag"),
    ("gemma_direct", "gemma", "direct"),
    ("gemma_vector_rag", "gemma", "vector_rag"),
    ("gemma_graph_rag", "gemma", "graph_rag"),
)


@dataclass(frozen=True)
class ExperimentConfig:
    transcript_path: Path
    output_dir: Path
    chunking_mode: str = "time"
    dry_run: bool = True
    qwen_model_id: str = DEFAULT_MODEL_IDS["qwen"]
    gemma_model_id: str = DEFAULT_MODEL_IDS["gemma"]
    top_k: int = 4
    expected_topics: tuple[str, ...] = ("demo", "部署", "法規")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_transcript(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return load_transcript_payload(payload)


def _build_chunks(config: ExperimentConfig):
    transcript = _load_transcript(config.transcript_path)
    if config.chunking_mode == "time":
        chunks = build_time_chunks(transcript)
    elif config.chunking_mode == "sliding":
        chunks = build_sliding_window_chunks(transcript)
    else:
        raise ValueError("chunking_mode must be 'time' or 'sliding'.")
    return transcript, chunks


def run_experiment(config: ExperimentConfig) -> dict[str, Any]:
    transcript, chunks = _build_chunks(config)
    embeddings = embed_chunks_with_backend(chunks)
    graph = build_evidence_graph(chunks)

    _write_json(config.output_dir / "chunks.json", [chunk.to_dict() for chunk in chunks])
    _write_json(config.output_dir / "graph.json", graph.to_dict())

    packets_by_setting = {}
    prompts_by_setting = {}
    summaries: dict[str, dict[str, Any]] = {}
    validation_results = {}
    model_status: dict[str, str] = {}

    for setting_name, model_key, mode in EXPERIMENT_SETTINGS:
        packets = build_evidence_packets(chunks, embeddings, graph, mode, top_k=config.top_k)
        prompt = assemble_summary_prompt(transcript.meeting_id, packets, graph)
        packets_by_setting[setting_name] = [packet.to_dict() for packet in packets]
        prompts_by_setting[setting_name] = prompt
        model_id = config.qwen_model_id if model_key == "qwen" else config.gemma_model_id
        runner_config = ModelRunnerConfig(dry_run=config.dry_run, model_id=model_id)
        try:
            summary, status = run_model_or_dry_run(setting_name, prompt, packets, runner_config)
        except Exception as exc:
            summary = {
                "meeting_summary": "",
                "main_topics": [],
                "key_points": [],
                "decisions_or_tentative_conclusions": [],
                "open_questions": [],
                "risks_and_constraints": [],
                "possible_next_steps": [],
                "low_confidence_sections": [{"reason": "weak evidence", "evidence_chunks": [chunks[0].chunk_id] if chunks else []}],
            }
            status = f"blocked: {exc}"
        summaries[setting_name] = summary
        model_status[setting_name] = status
        validation_results[setting_name] = validate_summary(summary, chunks)
        _write_json(config.output_dir / "summaries" / f"{setting_name}.json", summary)

    _write_json(config.output_dir / "evidence_packets.json", packets_by_setting)
    _write_json(config.output_dir / "prompts.json", prompts_by_setting)
    _write_json(config.output_dir / "validation_results.json", {key: value.to_dict() for key, value in validation_results.items()})

    metrics = evaluate_summaries(
        validation_results,
        expected_topics=list(config.expected_topics),
        summary_outputs=summaries,
    )
    report_payload = {
        "meeting_id": transcript.meeting_id,
        "chunking_mode": config.chunking_mode,
        "dry_run": config.dry_run,
        "settings": [name for name, _, _ in EXPERIMENT_SETTINGS],
        "model_ids": {"qwen": config.qwen_model_id, "gemma": config.gemma_model_id},
        "model_status": model_status,
        "metrics": metrics.to_dict(),
    }
    _write_json(config.output_dir / "evaluation_report.json", report_payload)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "evaluation_report.md").write_text(
        render_markdown_report(metrics, model_status),
        encoding="utf-8",
    )
    return report_payload
