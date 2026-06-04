from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from summary.field_schemas import (
    EXTRACTOR_FIELDS,
    LAYER1_EXTRACTORS,
    LAYER2_EXTRACTORS,
    default_value,
    empty_summary,
    expected_extractor_schema,
    metadata,
    validate_extractor_value,
    validate_final_summary,
)
from summary.markdown_renderer import render_markdown
from summary.ollama_gemma4_client import OllamaGemma4Client


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAYER_PROMPT_DIR = REPO_ROOT / "prompts" / "meeting_summary_layers"
DEFAULT_LOCAL_OUTPUT_DIR = REPO_ROOT / "local_outputs" / "meeting_summary"


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


def read_extractor_prompt(extractor: str, prompt_dir: Path = DEFAULT_LAYER_PROMPT_DIR) -> str:
    return (prompt_dir / f"{extractor}.system.txt").read_text(encoding="utf-8")


def build_extractor_prompt(
    extractor: str,
    corrected_transcript: str,
    prompt_dir: Path = DEFAULT_LAYER_PROMPT_DIR,
) -> str:
    return read_extractor_prompt(extractor, prompt_dir).replace("{{CORRECTED_TRANSCRIPT}}", corrected_transcript.strip())


def build_repair_prompt(
    extractor: str,
    invalid_output: str,
    prompt_dir: Path = DEFAULT_LAYER_PROMPT_DIR,
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
    prompt_dir: Path = DEFAULT_LAYER_PROMPT_DIR,
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
    prompt_dir: Path = DEFAULT_LAYER_PROMPT_DIR,
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
    prompt_dir: Path = DEFAULT_LAYER_PROMPT_DIR,
) -> LayeredSummaryResult:
    if not corrected_transcript.strip():
        raise ValueError("corrected_transcript is empty")
    client = client or OllamaGemma4Client()
    summary = empty_summary()
    validation_log: list[dict[str, object]] = []
    field_outputs: dict[str, object] = {}

    for extractors in (LAYER1_EXTRACTORS, LAYER2_EXTRACTORS):
        for extractor, value, log, raw_output in run_extractors_parallel(
            extractors,
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


def save_layered_outputs(result: LayeredSummaryResult, output_dir: Path = DEFAULT_LOCAL_OUTPUT_DIR) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "field_outputs": output_dir / "field_outputs.json",
        "final_summary": output_dir / "final_summary.json",
        "final_markdown": output_dir / "final_summary.md",
        "validation_log": output_dir / "validation_log.json",
    }
    paths["field_outputs"].write_text(
        json.dumps(result.field_outputs, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["final_summary"].write_text(
        json.dumps(result.summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["final_markdown"].write_text(result.markdown, encoding="utf-8")
    paths["validation_log"].write_text(
        json.dumps(result.validation_log, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths
