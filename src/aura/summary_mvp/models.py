from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from aura.summary_mvp.schema import EvidencePacket


DEFAULT_MODEL_IDS = {
    "qwen": "Qwen/Qwen3.5-9B",
    "gemma": "google/gemma-4-E4B-it",
}


class ModelRunError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelRunnerConfig:
    dry_run: bool = True
    model_id: str = ""
    max_new_tokens: int = 1024
    temperature: float = 0.1
    require_idle_gpu: bool = True
    max_gpu_memory_percent: int = 70


def gpu_is_available(max_memory_percent: int = 70) -> tuple[bool, str]:
    if shutil.which("nvidia-smi") is None:
        return False, "nvidia-smi is not available."
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"Unable to query GPU usage: {exc}"
    for line in completed.stdout.splitlines():
        used_text, total_text = [part.strip() for part in line.split(",", maxsplit=1)]
        used = int(used_text)
        total = int(total_text)
        percent = round((used / total) * 100)
        if percent <= max_memory_percent:
            return True, f"GPU memory usage is {percent}% ({used} MiB / {total} MiB)."
    return False, f"No GPU is below the {max_memory_percent}% memory-use threshold."


def dry_run_summary(setting_name: str, packets: list[EvidencePacket]) -> dict[str, Any]:
    chunks_by_id = {
        chunk.chunk_id: chunk
        for packet in packets
        for chunk in packet.retrieved_chunks
    }
    ordered_chunks = [chunks_by_id[chunk_id] for chunk_id in sorted(chunks_by_id)]
    first = ordered_chunks[0] if ordered_chunks else None
    second = ordered_chunks[1] if len(ordered_chunks) > 1 else first
    risk_chunk = next((chunk for chunk in ordered_chunks if "GPU" in chunk.text or "風險" in chunk.text or "限制" in chunk.text), first)
    question_chunk = next((chunk for chunk in ordered_chunks if "確認" in chunk.text or "?" in chunk.text or "？" in chunk.text), first)
    decision_chunk = next((chunk for chunk in ordered_chunks if "先" in chunk.text or "暫定" in chunk.text), first)

    def evidence(chunk) -> list[str]:
        return [chunk.chunk_id] if chunk else []

    return {
        "meeting_summary": f"{setting_name} dry-run 摘要：會議聚焦 demo、部署限制、法規素材與後續驗證。",
        "main_topics": [
            {"topic": "demo 與部署驗證", "evidence_chunks": evidence(first)},
            {"topic": "法規與送審素材整理", "evidence_chunks": evidence(second)},
        ],
        "key_points": [
            {"point": first.text[:80] if first else "逐字稿內容不足", "evidence_chunks": evidence(first)},
        ],
        "decisions_or_tentative_conclusions": [
            {
                "content": decision_chunk.text[:80] if decision_chunk else "目前結論仍待確認",
                "status": "tentative",
                "evidence_chunks": evidence(decision_chunk),
            }
        ],
        "open_questions": [
            {
                "question": question_chunk.text[:80] if question_chunk else "仍需補充人工確認問題",
                "evidence_chunks": evidence(question_chunk),
            }
        ],
        "risks_and_constraints": [
            {
                "risk": risk_chunk.text[:80] if risk_chunk else "逐字稿未提供明確風險",
                "evidence_chunks": evidence(risk_chunk),
            }
        ],
        "possible_next_steps": [
            {
                "step": "整理 evidence-grounded 摘要輸出並比較 direct、vector RAG、graph RAG 結果",
                "confidence": "medium",
                "evidence_chunks": evidence(first),
            }
        ],
        "low_confidence_sections": [
            {
                "reason": "fragmented context",
                "evidence_chunks": evidence(question_chunk),
            }
        ],
    }


def run_transformers_int8(prompt: str, config: ModelRunnerConfig) -> str:
    available, reason = gpu_is_available(config.max_gpu_memory_percent)
    if config.require_idle_gpu and not available:
        raise ModelRunError(reason)
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:
        raise ModelRunError("Missing optional summary dependencies. Install with `python -m pip install -e .[summary]`.") from exc

    if not torch.cuda.is_available():
        raise ModelRunError("CUDA is not available for INT8 model execution.")

    tokenizer = AutoTokenizer.from_pretrained(config.model_id, trust_remote_code=True)
    model_class = AutoModelForImageTextToText if "gemma-4" in config.model_id.lower() else AutoModelForCausalLM
    model = model_class.from_pretrained(
        config.model_id,
        device_map="auto",
        trust_remote_code=True,
        quantization_config=BitsAndBytesConfig(load_in_8bit=True),
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    output_ids = model.generate(
        **inputs,
        max_new_tokens=config.max_new_tokens,
        do_sample=config.temperature > 0,
        temperature=config.temperature,
    )
    generated = output_ids[0][inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


def run_model_or_dry_run(
    setting_name: str,
    prompt: str,
    packets: list[EvidencePacket],
    config: ModelRunnerConfig,
) -> tuple[dict[str, Any], str]:
    if config.dry_run:
        return dry_run_summary(setting_name, packets), "dry-run deterministic summary; no model loaded"
    try:
        raw = run_transformers_int8(prompt, config)
        return json.loads(raw), f"model-run completed with {config.model_id}"
    except json.JSONDecodeError as exc:
        raise ModelRunError(f"Model returned invalid JSON: {exc}") from exc
