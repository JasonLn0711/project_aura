from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Protocol

from aura.audio.recording_session import write_session_manifest
from summary.field_schemas import (
    EXTRACTOR_FIELDS,
    EXTRACTOR_NAMES,
    default_value,
    empty_summary,
    expected_extractor_schema,
    metadata,
    validate_extractor_value,
    validate_final_summary,
)
from summary.markdown_renderer import render_markdown
from summary.ollama_gemma4_client import OllamaGemma4Client


DEFAULT_LAYER_PROMPT_DIR = resources.files("summary").joinpath(
    "meeting_summary_layers"
)
DEFAULT_LOCAL_OUTPUT_DIR = (
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    / "project_aura"
    / "meeting_summary"
)


class JsonGenerationClient(Protocol):
    def generate_json(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class ExtractorLog:
    extractor: str
    valid: bool
    repaired: bool
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LayeredSummaryResult:
    summary: dict
    markdown: str
    validation_log: list[dict[str, object]]
    field_outputs: dict[str, object]


def _atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as target:
            target.write(text)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def summary_claims(
    summary: dict,
    meeting_id: str,
    segments: list[dict[str, object]],
    transcript_sha256: str = "",
) -> list[dict[str, object]]:
    known_segments = {
        str(segment["segment_id"]): segment
        for segment in segments
    }
    claims = []
    for field, text_key in (("decisions", "decision"), ("action_items", "task")):
        for index, item in enumerate(summary.get(field, [])):
            source_segment_ids = [
                str(segment_id)
                for segment_id in item.get("source_segment_ids", [])
                if str(segment_id) in known_segments
            ]
            support_status = str(item.get("support_status") or "unsupported")
            if not source_segment_ids:
                support_status = "unsupported"
            text = str(item.get(text_key) or "")
            identity = json.dumps(
                [
                    meeting_id,
                    transcript_sha256,
                    field,
                    index,
                    text,
                    [
                        [
                            segment_id,
                            known_segments[segment_id].get("revision", 0),
                            known_segments[segment_id].get("text", ""),
                        ]
                        for segment_id in source_segment_ids
                    ],
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            claims.append(
                {
                    "claim_id": "claim-"
                    + uuid.uuid5(
                        uuid.NAMESPACE_URL, f"project-aura:{identity}"
                    ).hex[:16],
                    "field": field,
                    "text": text,
                    "source_segment_ids": source_segment_ids,
                    "support_status": support_status,
                    "review_status": "unreviewed",
                }
            )
    return claims


def read_extractor_prompt(
    extractor: str,
    prompt_dir: Path | Traversable = DEFAULT_LAYER_PROMPT_DIR,
) -> str:
    return prompt_dir.joinpath(f"{extractor}.system.txt").read_text(
        encoding="utf-8"
    )


def build_extractor_prompt(
    extractor: str,
    corrected_transcript: str,
    prompt_dir: Path | Traversable = DEFAULT_LAYER_PROMPT_DIR,
) -> str:
    return read_extractor_prompt(extractor, prompt_dir).replace("{{CORRECTED_TRANSCRIPT}}", corrected_transcript.strip())


def build_repair_prompt(
    extractor: str,
    invalid_output: str,
    prompt_dir: Path | Traversable = DEFAULT_LAYER_PROMPT_DIR,
) -> str:
    template = read_extractor_prompt("format_repair", prompt_dir)
    return (
        template.replace("{{EXTRACTOR_NAME}}", extractor)
        .replace("{{EXPECTED_SCHEMA}}", json.dumps(expected_extractor_schema(extractor), ensure_ascii=False, indent=2))
        .replace("{{INVALID_OUTPUT}}", invalid_output)
    )


def extract_with_repair(
    extractor: str,
    corrected_transcript: str,
    client: JsonGenerationClient,
    prompt_dir: Path | Traversable = DEFAULT_LAYER_PROMPT_DIR,
) -> tuple[dict[str, object], ExtractorLog, object]:
    raw_output = client.generate_json(build_extractor_prompt(extractor, corrected_transcript, prompt_dir))
    value, result = validate_extractor_value(extractor, raw_output)
    if result.valid:
        return value, ExtractorLog(extractor=extractor, valid=True, repaired=False), raw_output

    repair_output = client.generate_json(build_repair_prompt(extractor, raw_output, prompt_dir))
    value, repair_result = validate_extractor_value(extractor, repair_output)
    if repair_result.valid:
        return value, ExtractorLog(extractor=extractor, valid=True, repaired=True), repair_output

    defaults = {field: default_value(field) for field in EXTRACTOR_FIELDS[extractor]}
    return (
        defaults,
        ExtractorLog(extractor=extractor, valid=False, repaired=True, error=repair_result.error or result.error),
        repair_output,
    )


def run_extractors_parallel(
    extractors: tuple[str, ...],
    corrected_transcript: str,
    client: JsonGenerationClient,
    prompt_dir: Path | Traversable = DEFAULT_LAYER_PROMPT_DIR,
) -> list[tuple[str, dict[str, object], ExtractorLog, object]]:
    with ThreadPoolExecutor(max_workers=len(extractors), thread_name_prefix="aura-summary-extractor") as executor:
        futures = {
            extractor: executor.submit(extract_with_repair, extractor, corrected_transcript, client, prompt_dir)
            for extractor in extractors
        }
        results: list[tuple[str, dict[str, object], ExtractorLog, object]] = []
        for extractor in extractors:
            value, log, raw_output = futures[extractor].result()
            results.append((extractor, value, log, raw_output))
        return results


def generate_layered_summary(
    corrected_transcript: str,
    client: JsonGenerationClient | None = None,
    prompt_dir: Path | Traversable = DEFAULT_LAYER_PROMPT_DIR,
) -> LayeredSummaryResult:
    if not corrected_transcript.strip():
        raise ValueError("corrected_transcript is empty")
    client = client or OllamaGemma4Client()
    summary = empty_summary()
    validation_log: list[dict[str, object]] = []
    field_outputs: dict[str, object] = {}

    for extractor, value, log, raw_output in run_extractors_parallel(
        EXTRACTOR_NAMES,
        corrected_transcript,
        client,
        prompt_dir,
    ):
        summary.update(value)
        validation_log.append(log.to_dict())
        field_outputs[extractor] = raw_output

    summary["metadata"] = metadata()
    if not validate_final_summary(summary):
        raise RuntimeError("Final layered meeting summary schema is invalid.")
    return LayeredSummaryResult(
        summary=summary,
        markdown=render_markdown(summary),
        validation_log=validation_log,
        field_outputs=field_outputs,
    )


def save_layered_outputs(
    result: LayeredSummaryResult,
    output_dir: Path = DEFAULT_LOCAL_OUTPUT_DIR,
    *,
    meeting_id: str | None = None,
    segments: list[dict[str, object]] | None = None,
    session_dir: Path | None = None,
    transcript_sha256: str = "",
) -> dict[str, Path]:
    meeting_id = meeting_id or str(uuid.uuid4())
    if session_dir is not None:
        session_dir = Path(session_dir)
        manifest_path = session_dir / "session.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(manifest.get("meeting_id") or "") != meeting_id:
            raise ValueError("summary meeting_id does not match session.json")
        output_dir = session_dir
    else:
        output_dir = output_dir / meeting_id
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "field_outputs": output_dir / "field_outputs.json",
        "final_summary": output_dir / "summary.json",
        "final_markdown": output_dir / "summary.md",
        "validation_log": output_dir / "validation_log.json",
    }
    _atomic_write_text(
        paths["field_outputs"],
        json.dumps(result.field_outputs, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    claims = summary_claims(
        result.summary,
        meeting_id,
        segments or [],
        transcript_sha256,
    )
    claim_source_coverage = (
        round(
            sum(bool(claim["source_segment_ids"]) for claim in claims)
            / len(claims),
            4,
        )
        if claims
        else None
    )
    _atomic_write_text(
        paths["final_summary"],
        json.dumps(
            {
                "schema_version": 1,
                "meeting_id": meeting_id,
                "transcript_sha256": transcript_sha256,
                "summary": result.summary,
                "claims": claims,
                "claim_source_coverage": claim_source_coverage,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _atomic_write_text(paths["final_markdown"], result.markdown)
    _atomic_write_text(
        paths["validation_log"],
        json.dumps(result.validation_log, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    if session_dir is not None:
        manifest["summary_evidence"] = paths["final_summary"].name
        manifest["summary_status"] = "valid"
        manifest.pop("summary_invalidation_reason", None)
        manifest.pop("summary_invalidated_at", None)
        if transcript_sha256:
            manifest["transcript_sha256"] = transcript_sha256
        write_session_manifest(manifest_path, manifest)
    return paths
