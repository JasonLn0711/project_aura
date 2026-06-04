from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aura.llm.summary import DEFAULT_SUMMARY_MODEL  # noqa: E402
from scripts.evaluate_summary_impact import (  # noqa: E402
    EVALUATED_CATEGORIES,
    ArtifactSet,
    correction_term_evidence,
    discover_artifact_sets,
    load_domain_terms,
    read_correction_entries,
    term_present,
    terms_in_text,
)

GATE_NAME = "G4E4B-SummaryImpact"
MODEL_DISPLAY_NAME = "Gemma 4 E4B"
DEFAULT_CONFIG = REPO_ROOT / "config" / "gemma4_e4b_summary_impact.yaml"
DEFAULT_MANIFEST = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_manifest.json"
DEFAULT_REPORT_JSON = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_report.json"
DEFAULT_REPORT_MD = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_report.md"
DEFAULT_PRIVACY_CLEARANCE = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact_privacy_clearance.json"
DEFAULT_LOCAL_OUTPUT_DIR = REPO_ROOT / "reports" / "gemma4_e4b_summary_impact" / "local_outputs"
DEFAULT_CORRECTION_LOG_DIR = REPO_ROOT / "reports" / "asr_fuzzy_correction_logs"
FIXED_MODEL_ID = "google/gemma-4-E4B-it"
FIXED_OLLAMA_MODEL = "gemma4:e4b-it-q4_K_M"
REQUIRED_REPORT_FIELDS = (
    "gate",
    "model",
    "fixed_model_id",
    "model_id",
    "runner",
    "endpoint",
    "ollama_model",
    "model_source",
    "precision_variant",
    "fp8_checkpoint",
    "download_during_gate",
    "local_files_only",
    "model_available",
    "external_calls",
    "cloud_calls",
    "raw_transcript_context_emitted",
    "raw_email_pdf_read",
    "complete_artifact_sets",
    "evaluated_files",
    "files_with_both_summaries",
    "domain_terms_raw_summary",
    "domain_terms_corrected_summary",
    "domain_term_delta",
    "raw_asr_error_spans_in_raw_summaries",
    "canonical_terms_in_corrected_summaries",
    "rejected_leakage",
    "manual_review_leakage",
    "decision_changes",
    "hallucinated_entity_watch_count",
    "claim_scope",
)


@dataclass(frozen=True)
class RunnerConfig:
    model_id: str
    runner: str
    max_output_tokens: int
    temperature: float
    timeout_sec: int
    seed: int
    local_only: bool
    allow_fallback_model: bool
    allow_download: bool
    local_files_only: bool
    precision_variant: str
    fp8_checkpoint: bool
    load_in_8bit: bool
    cuda_max_memory: str
    cpu_max_memory: str
    ollama_model: str
    ollama_host: str


def repo_relative(path: Path, base: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return payload


def nested(config: dict[str, Any], section: str, key: str, default: Any) -> Any:
    values = config.get(section) or {}
    if not isinstance(values, dict):
        return default
    return values.get(key, default)


def runner_config(config: dict[str, Any]) -> RunnerConfig:
    return RunnerConfig(
        model_id=str(nested(config, "model", "model_id", DEFAULT_SUMMARY_MODEL)),
        runner=str(nested(config, "model", "runner", "transformers")),
        max_output_tokens=int(nested(config, "generation", "max_output_tokens", 768)),
        temperature=float(nested(config, "generation", "temperature", 0.0)),
        timeout_sec=int(nested(config, "generation", "timeout_sec", 180)),
        seed=int(nested(config, "generation", "seed", 20260604)),
        local_only=bool(nested(config, "model", "local_only", True)),
        allow_fallback_model=bool(nested(config, "model", "allow_fallback_model", False)),
        allow_download=bool(nested(config, "model", "allow_download", False)),
        local_files_only=bool(nested(config, "model", "local_files_only", True)),
        precision_variant=str(nested(config, "model", "precision_variant", "native_or_cache_default")),
        fp8_checkpoint=bool(nested(config, "model", "fp8_checkpoint", False)),
        load_in_8bit=bool(nested(config, "model", "load_in_8bit", False)),
        cuda_max_memory=str(nested(config, "model", "cuda_max_memory", "8GiB")),
        cpu_max_memory=str(nested(config, "model", "cpu_max_memory", "96GiB")),
        ollama_model=str(nested(config, "model", "ollama_model", FIXED_OLLAMA_MODEL)),
        ollama_host=str(nested(config, "model", "ollama_host", "http://127.0.0.1:11434")).rstrip("/"),
    )


def empty_summary() -> dict[str, Any]:
    return {
        "executive_summary": "",
        "key_decisions": [],
        "action_items": [],
        "open_questions": [],
        "domain_terms": {category: [] for category in EVALUATED_CATEGORIES},
    }


def build_summary_prompt(transcript: str) -> str:
    schema = {
        "executive_summary": "",
        "key_decisions": [],
        "action_items": [],
        "open_questions": [],
        "domain_terms": {
            "organizations": [],
            "people": [],
            "technical_terms": [],
            "medical_terms": [],
            "regulatory_terms": [],
        },
    }
    return (
        "You are a local meeting summarization evaluator. Summarize only the transcript below.\n"
        "Do not infer missing facts. Preserve domain-specific names exactly as written.\n"
        "If a term is unclear, keep the transcript wording.\n"
        "Return valid JSON only using this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        "Transcript:\n"
        f"{transcript.strip()}\n"
    )


def prompt_uses_correction_log(prompt: str) -> bool:
    return "correction_log" in prompt or "correction log" in prompt.lower()


def import_available(module: str) -> bool:
    try:
        __import__(module)
    except Exception:
        return False
    return True


def hf_cache_model_dir(model_id: str) -> Path:
    cache_root = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return cache_root / f"models--{model_id.replace('/', '--')}"


def model_cache_available(model_id: str) -> bool:
    model_dir = hf_cache_model_dir(model_id)
    if not model_dir.exists():
        return False
    refs = model_dir / "refs"
    snapshots = model_dir / "snapshots"
    blobs = model_dir / "blobs"
    return refs.exists() and (snapshots.exists() or blobs.exists())


def check_model_available(config: RunnerConfig) -> tuple[bool, str]:
    if config.allow_fallback_model:
        return False, "Fallback model is forbidden for this gate"
    if config.model_id != FIXED_MODEL_ID:
        return False, f"Configured model must exactly match {FIXED_MODEL_ID}"
    if not config.local_only:
        return False, "Model config must be local_only"
    if config.allow_download:
        return False, "Downloads are forbidden during this gate"
    if not config.local_files_only:
        return False, "Runner must use local_files_only"
    if config.runner == "transformers":
        if not import_available("transformers") or not import_available("torch"):
            return False, "Gemma 4 E4B local model runner dependencies not found"
        if not model_cache_available(config.model_id):
            return False, "Gemma 4 E4B local model not found"
        return True, "Gemma 4 E4B local model found"
    if config.runner == "ollama":
        return check_ollama_available(config)
    if config.runner in {"llama.cpp", "llama_cpp", "llama-cli"}:
        if subprocess.run(["sh", "-lc", "command -v llama-cli"], capture_output=True, text=True).returncode != 0:
            return False, "llama.cpp runner not found"
        return True, "llama.cpp runner found"
    return False, f"Unsupported local runner: {config.runner}"


def ollama_request(host: str, endpoint: str, payload: dict[str, Any] | None = None, timeout: int = 10) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{host}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_ollama_available(config: RunnerConfig) -> tuple[bool, str]:
    if config.ollama_model != FIXED_OLLAMA_MODEL:
        return False, f"Ollama model must exactly match {FIXED_OLLAMA_MODEL}"
    if not config.ollama_host.startswith("http://127.0.0.1:") and not config.ollama_host.startswith("http://localhost:"):
        return False, "Ollama host must be localhost"
    try:
        tags = ollama_request(config.ollama_host, "/api/tags", timeout=2)
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False, "Ollama localhost runner not available"
    models = tags.get("models") or []
    names = {str(model.get("name") or "") for model in models if isinstance(model, dict)}
    if config.ollama_model not in names:
        return False, f"Ollama model not found: {config.ollama_model}"
    return True, f"Ollama local model found: {config.ollama_model}"


def safe_report_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": row["file_id"],
        "raw_summary_domain_terms": row["raw_summary_domain_terms"],
        "corrected_summary_domain_terms": row["corrected_summary_domain_terms"],
        "domain_term_delta": row["domain_term_delta"],
        "raw_asr_error_spans_in_raw_summary_count": len(row["raw_asr_error_spans_in_raw_summary"]),
        "canonical_terms_in_corrected_summary_count": len(row["canonical_terms_in_corrected_summary"]),
        "rejected_leakage_count": len(row["rejected_leakage_terms"]),
        "manual_review_leakage_count": len(row["manual_review_leakage_terms"]),
        "decision_change_category": row["decision_change_category"],
        "hallucinated_entity_watch": row["hallucinated_entity_watch"],
        "hallucinated_entity_watch_count": len(row["hallucinated_entities"]),
    }


class TransformersGemmaRunner:
    def __init__(self, config: RunnerConfig) -> None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoTokenizer, BitsAndBytesConfig, set_seed

        set_seed(config.seed)
        self.config = config
        self.tokenizer = AutoTokenizer.from_pretrained(
            config.model_id,
            trust_remote_code=True,
            local_files_only=config.local_files_only,
        )
        model_kwargs = {
            "trust_remote_code": True,
            "local_files_only": config.local_files_only,
            "device_map": "auto",
            "max_memory": {0: config.cuda_max_memory, "cpu": config.cpu_max_memory},
        }
        if config.load_in_8bit:
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_8bit=True,
                llm_int8_enable_fp32_cpu_offload=True,
            )
        else:
            model_kwargs["torch_dtype"] = "auto" if torch.cuda.is_available() else torch.float32
        self.model = AutoModelForImageTextToText.from_pretrained(config.model_id, **model_kwargs)

    def generate(self, transcript: str) -> str:
        prompt = build_summary_prompt(transcript)
        if prompt_uses_correction_log(prompt):
            raise RuntimeError("Summary prompt must not include correction log content.")
        messages = [
            {"role": "system", "content": "Return valid JSON only. Use only the supplied transcript."},
            {"role": "user", "content": prompt},
        ]
        try:
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_tensors="pt",
                return_dict=True,
            )
        except TypeError:
            prompt_text = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
            inputs = self.tokenizer(prompt_text, return_tensors="pt")
        except AttributeError:
            prompt_text = "\n\n".join(f"{message['role']}: {message['content']}" for message in messages) + "\nassistant:"
            inputs = self.tokenizer(prompt_text, return_tensors="pt")
        device = getattr(self.model, "device", None)
        if device is not None and hasattr(inputs, "to"):
            inputs = inputs.to(device)
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=self.config.max_output_tokens,
            do_sample=self.config.temperature > 0,
            temperature=self.config.temperature,
        )
        input_length = inputs["input_ids"].shape[-1]
        generated = outputs[0][input_length:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()


def build_runner(config: RunnerConfig) -> TransformersGemmaRunner:
    if config.runner == "transformers":
        return TransformersGemmaRunner(config)
    if config.runner == "ollama":
        return OllamaGemmaRunner(config)  # type: ignore[return-value]
    raise RuntimeError(f"Runner is not implemented for generation: {config.runner}")


class OllamaGemmaRunner:
    def __init__(self, config: RunnerConfig) -> None:
        self.config = config

    def generate(self, transcript: str) -> str:
        prompt = build_summary_prompt(transcript)
        if prompt_uses_correction_log(prompt):
            raise RuntimeError("Summary prompt must not include correction log content.")
        response = ollama_request(
            self.config.ollama_host,
            "/api/generate",
            payload={
                "model": self.config.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": self.config.temperature,
                    "seed": self.config.seed,
                    "num_predict": self.config.max_output_tokens,
                },
            },
            timeout=self.config.timeout_sec,
        )
        return str(response.get("response") or "")


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")[:100] or "sample"


def clean_log_slug(value: str) -> str:
    name = Path(value).name
    if name.endswith("_correction_log.json"):
        name = name[: -len("_correction_log.json")]
    name = re.sub(r"^\d+_", "", name)
    return name


def artifact_from_real_pair(raw_path: Path, corrected_path: Path, log_path: Path) -> ArtifactSet:
    base = raw_path.with_name(raw_path.stem[: -len("_raw")])
    return ArtifactSet(
        file_id=repo_relative(base),
        raw_transcript=raw_path,
        corrected_transcript=corrected_path,
        correction_log=log_path,
        raw_summary=None,
        corrected_summary=None,
    )


def discover_real_transcript_artifact_sets(roots: list[Path], log_dir: Path = DEFAULT_CORRECTION_LOG_DIR) -> list[ArtifactSet]:
    logs_by_slug: dict[str, Path] = {}
    if log_dir.exists():
        for log_path in sorted(log_dir.glob("*_correction_log.json"), key=lambda item: item.as_posix()):
            logs_by_slug[clean_log_slug(log_path.name)] = log_path

    artifact_sets: list[ArtifactSet] = []
    for root in roots:
        if not root.exists():
            continue
        for raw_path in sorted(root.rglob("*_raw.txt"), key=lambda item: item.as_posix()):
            if ".venv" in raw_path.parts or ".git" in raw_path.parts or "reports" in raw_path.parts:
                continue
            base = raw_path.with_name(raw_path.stem[: -len("_raw")])
            corrected_path = raw_path.with_name(f"{base.name}_corrected.txt")
            if not corrected_path.exists():
                corrected_path = raw_path.with_name(f"{base.name}_final.txt")
            if not corrected_path.exists():
                continue
            log_path = logs_by_slug.get(raw_path.stem) or logs_by_slug.get(base.name)
            if log_path is None:
                continue
            artifact_sets.append(artifact_from_real_pair(raw_path, corrected_path, log_path))
    return artifact_sets


def candidate_score(artifact: ArtifactSet) -> tuple[int, int, str]:
    entries = read_correction_entries(artifact.correction_log)
    evidence = correction_term_evidence(entries)
    accepted = evidence["accepted"]
    categories = {entry["category"] for entry in accepted if entry.get("category")}
    category_hits = len(categories & set(EVALUATED_CATEGORIES))
    return (-category_hits, -len(accepted), artifact.file_id)


def select_artifacts(
    artifact_sets: list[ArtifactSet],
    max_samples: int,
    exclude_paths: list[str],
    max_input_chars_per_transcript: int | None = None,
) -> list[ArtifactSet]:
    excluded = tuple(str(path) for path in exclude_paths)

    def included(artifact: ArtifactSet) -> bool:
        paths = [
            repo_relative(artifact.raw_transcript),
            repo_relative(artifact.corrected_transcript),
            repo_relative(artifact.correction_log),
        ]
        return not any(any(path.startswith(prefix) for prefix in excluded) for path in paths)

    candidates = [artifact for artifact in artifact_sets if included(artifact)]
    if max_input_chars_per_transcript is not None:
        candidates = [
            artifact
            for artifact in candidates
            if artifact.raw_transcript.stat().st_size <= max_input_chars_per_transcript
            and artifact.corrected_transcript.stat().st_size <= max_input_chars_per_transcript
        ]
    return sorted(candidates, key=candidate_score)[:max_samples]


def discover_candidate_artifact_sets(
    roots: list[Path],
    max_samples: int,
    exclude_paths: list[str],
    max_input_chars_per_transcript: int | None = None,
) -> list[ArtifactSet]:
    real_sets = discover_real_transcript_artifact_sets(roots)
    selected = select_artifacts(
        real_sets,
        max_samples=max_samples,
        exclude_paths=exclude_paths,
        max_input_chars_per_transcript=max_input_chars_per_transcript,
    )
    if selected:
        return selected
    return select_artifacts(
        discover_artifact_sets(roots),
        max_samples=max_samples,
        exclude_paths=exclude_paths,
        max_input_chars_per_transcript=max_input_chars_per_transcript,
    )


def parse_summary_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return empty_summary()
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return empty_summary()
    if not isinstance(payload, dict):
        return empty_summary()
    summary = empty_summary()
    for key in ("executive_summary",):
        if isinstance(payload.get(key), str):
            summary[key] = payload[key]
    for key in ("key_decisions", "action_items", "open_questions"):
        if isinstance(payload.get(key), list):
            summary[key] = [str(item) for item in payload[key]]
    terms = payload.get("domain_terms")
    if isinstance(terms, dict):
        for category in EVALUATED_CATEGORIES:
            values = terms.get(category)
            if isinstance(values, list):
                summary["domain_terms"][category] = [str(item) for item in values if str(item)]
    return summary


def domain_term_count(summary: dict[str, Any]) -> int:
    return sum(len(summary["domain_terms"].get(category, [])) for category in EVALUATED_CATEGORIES)


def summary_search_text(summary: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("executive_summary", "key_decisions", "action_items", "open_questions"):
        value = summary.get(key)
        if isinstance(value, list):
            chunks.extend(str(item) for item in value)
        else:
            chunks.append(str(value or ""))
    for values in summary.get("domain_terms", {}).values():
        chunks.extend(str(item) for item in values)
    return "\n".join(chunks)


def rejected_and_manual_terms(entries: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    evidence = correction_term_evidence(entries)
    rejected = {entry["corrected"] for entry in evidence["rejected"] if entry.get("corrected")}
    manual = {entry["corrected"] for entry in evidence["manual_review_required"] if entry.get("corrected")}
    return rejected, manual


def canonical_terms(entries: list[dict[str, Any]], blocked_terms: set[str]) -> set[str]:
    evidence = correction_term_evidence(entries)
    return {
        entry["corrected"]
        for entry in evidence["accepted"]
        if entry.get("corrected") and entry["corrected"] not in blocked_terms
    }


def original_spans(entries: list[dict[str, Any]]) -> set[str]:
    evidence = correction_term_evidence(entries)
    return {entry["original"] for entry in evidence["accepted"] if entry.get("original")}


def classify_decision_change(
    raw_summary: dict[str, Any],
    corrected_summary: dict[str, Any],
    corrected_text: str,
    manual_terms: set[str],
) -> str | None:
    raw_items = set(raw_summary.get("key_decisions", [])) | set(raw_summary.get("action_items", []))
    corrected_items = set(corrected_summary.get("key_decisions", [])) | set(corrected_summary.get("action_items", []))
    if raw_items == corrected_items:
        return None
    corrected_joined = "\n".join(corrected_items)
    if any(term and term_present(corrected_joined, term) for term in manual_terms):
        return "manual_review_needed"
    raw_normalized = {item.lower() for item in raw_items}
    corrected_normalized = {item.lower() for item in corrected_items}
    if raw_normalized == corrected_normalized:
        return "domain_term_only"
    raw_terms = set(re.findall(r"[A-Za-z0-9+().-]+|[\u4e00-\u9fff]{2,}", "\n".join(raw_items)))
    corrected_terms = set(re.findall(r"[A-Za-z0-9+().-]+|[\u4e00-\u9fff]{2,}", corrected_joined))
    introduced = {term for term in corrected_terms - raw_terms if term_present(corrected_text, term)}
    if introduced and len(raw_items) == len(corrected_items):
        return "domain_term_only"
    return "possible_semantic_change"


def hallucinated_terms(summary: dict[str, Any], corrected_text: str) -> list[str]:
    introduced: list[str] = []
    for category in EVALUATED_CATEGORIES:
        for term in summary.get("domain_terms", {}).get(category, []):
            if term and not term_present(corrected_text, term):
                introduced.append(term)
    return sorted(set(introduced))


def evaluate_pair(
    artifact: ArtifactSet,
    raw_summary: dict[str, Any],
    corrected_summary: dict[str, Any],
    domain_terms: dict[str, list[str]],
) -> dict[str, Any]:
    raw_text = artifact.raw_transcript.read_text(encoding="utf-8", errors="replace")
    corrected_text = artifact.corrected_transcript.read_text(encoding="utf-8", errors="replace")
    entries = read_correction_entries(artifact.correction_log)
    rejected_terms, manual_terms = rejected_and_manual_terms(entries)
    blocked_terms = rejected_terms | manual_terms
    corrected_canonical = canonical_terms(entries, blocked_terms)
    raw_original = original_spans(entries)
    raw_search = summary_search_text(raw_summary)
    corrected_search = summary_search_text(corrected_summary)
    raw_terms = terms_in_text(raw_search, domain_terms)
    corrected_terms = terms_in_text(corrected_search, domain_terms)
    raw_count = domain_term_count(raw_summary) or sum(len(values) for values in raw_terms.values())
    corrected_count = domain_term_count(corrected_summary) or sum(len(values) for values in corrected_terms.values())
    raw_error_spans = sorted({span for span in raw_original if term_present(raw_search, span)})
    canonical_hits = sorted({term for term in corrected_canonical if term_present(corrected_search, term)})
    rejected_leaks = sorted({term for term in rejected_terms if term_present(corrected_search, term)})
    manual_leaks = sorted({term for term in manual_terms if term_present(corrected_search, term)})
    decision_category = classify_decision_change(raw_summary, corrected_summary, corrected_text, manual_terms)
    hallucinations = hallucinated_terms(corrected_summary, corrected_text)
    return {
        "file_id": artifact.file_id,
        "raw_summary_domain_terms": raw_count,
        "corrected_summary_domain_terms": corrected_count,
        "domain_term_delta": corrected_count - raw_count,
        "raw_asr_error_spans_in_raw_summary": raw_error_spans,
        "canonical_terms_in_corrected_summary": canonical_hits,
        "rejected_leakage_terms": rejected_leaks,
        "manual_review_leakage_terms": manual_leaks,
        "decision_change_category": decision_category,
        "hallucinated_entity_watch": bool(hallucinations),
        "hallucinated_entities": hallucinations,
    }


def aggregate_report(
    rows: list[dict[str, Any]],
    complete_artifact_sets: int,
    model_available: bool,
    reason: str,
    config: RunnerConfig,
) -> dict[str, Any]:
    decision_changes = Counter(row["decision_change_category"] for row in rows if row["decision_change_category"])
    report = {
        "gate": GATE_NAME,
        "model": MODEL_DISPLAY_NAME,
        "fixed_model_id": FIXED_MODEL_ID,
        "model_id": config.model_id,
        "runner": config.runner,
        "endpoint": config.ollama_host if config.runner == "ollama" else "",
        "ollama_model": config.ollama_model if config.runner == "ollama" else "",
        "model_source": "preloaded_local_cache" if model_available else "local_cache_unavailable",
        "precision_variant": config.precision_variant,
        "fp8_checkpoint": config.fp8_checkpoint,
        "download_during_gate": False,
        "local_files_only": config.local_files_only,
        "model_available": model_available,
        "external_calls": False,
        "cloud_calls": False,
        "raw_transcript_context_emitted": False,
        "raw_email_pdf_read": False,
        "complete_artifact_sets": complete_artifact_sets,
        "evaluated_files": len(rows),
        "files_with_both_summaries": len(rows),
        "domain_terms_raw_summary": sum(row["raw_summary_domain_terms"] for row in rows),
        "domain_terms_corrected_summary": sum(row["corrected_summary_domain_terms"] for row in rows),
        "domain_term_delta": sum(row["domain_term_delta"] for row in rows),
        "raw_asr_error_spans_in_raw_summaries": sum(len(row["raw_asr_error_spans_in_raw_summary"]) for row in rows),
        "canonical_terms_in_corrected_summaries": sum(len(row["canonical_terms_in_corrected_summary"]) for row in rows),
        "rejected_leakage": sum(len(row["rejected_leakage_terms"]) for row in rows),
        "manual_review_leakage": sum(len(row["manual_review_leakage_terms"]) for row in rows),
        "decision_changes": {
            "domain_term_only": decision_changes.get("domain_term_only", 0),
            "possible_semantic_change": decision_changes.get("possible_semantic_change", 0),
            "manual_review_needed": decision_changes.get("manual_review_needed", 0),
        },
        "hallucinated_entity_watch_count": sum(1 for row in rows if row["hallucinated_entity_watch"]),
        "claim_scope": "internal local model-backed summary-impact gate using google/gemma-4-E4B-it, not final empirical claim",
        "reason": reason,
        "per_file": [safe_report_row(row) for row in rows],
    }
    return {field: report[field] for field in REQUIRED_REPORT_FIELDS} | {
        "reason": report["reason"],
        "per_file": report["per_file"],
    }


def write_manifest(
    path: Path,
    selected: list[ArtifactSet],
    model_available: bool,
    reason: str,
    config: RunnerConfig,
    local_output_dir: Path,
) -> dict[str, Any]:
    manifest = {
        "gate": GATE_NAME,
        "model": MODEL_DISPLAY_NAME,
        "fixed_model_id": FIXED_MODEL_ID,
        "model_id": config.model_id,
        "runner": config.runner,
        "endpoint": config.ollama_host if config.runner == "ollama" else "",
        "ollama_model": config.ollama_model if config.runner == "ollama" else "",
        "model_source": "preloaded_local_cache" if model_available else "local_cache_unavailable",
        "precision_variant": config.precision_variant,
        "fp8_checkpoint": config.fp8_checkpoint,
        "download_during_gate": False,
        "local_files_only": config.local_files_only,
        "runner": config.runner,
        "model_available": model_available,
        "reason": reason,
        "external_calls": False,
        "cloud_calls": False,
        "raw_transcript_context_emitted": False,
        "raw_email_pdf_read": False,
        "commit_raw_model_outputs": False,
        "local_output_dir": repo_relative(local_output_dir),
        "selected_artifact_sets": [
            {
                "file_id": artifact.file_id,
                "raw_transcript": repo_relative(artifact.raw_transcript),
                "corrected_transcript": repo_relative(artifact.corrected_transcript),
                "correction_log": repo_relative(artifact.correction_log),
            }
            for artifact in selected
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# G4E4B-SummaryImpact",
            "",
            "Gemma 4 E4B local model-backed ASR correction summary-impact gate.",
            "",
            "## Scope",
            "",
            "- Fixed local summarizer: Gemma 4 E4B.",
            f"- Runner: {report['runner']}.",
            f"- Endpoint: {report['endpoint']}.",
            f"- Ollama tag: {report['ollama_model']}.",
            "- External calls: false.",
            "- Cloud calls: false.",
            "- Transcript context emitted to reports: false.",
            "- Claim scope: internal local model-backed gate, not final empirical claim.",
            f"- Fixed model id: {report['fixed_model_id']}",
            f"- Precision variant: {report['precision_variant']}",
            f"- FP8 checkpoint: {str(report['fp8_checkpoint']).lower()}",
            f"- Download during gate: {str(report['download_during_gate']).lower()}",
            f"- Local files only: {str(report['local_files_only']).lower()}",
            "",
            "## Result",
            "",
            f"- Model available: {str(report['model_available']).lower()}",
            f"- Reason: {report.get('reason', '')}",
            f"- Complete artifact sets: {report['complete_artifact_sets']}",
            f"- Evaluated files: {report['evaluated_files']}",
            f"- Files with both summaries: {report['files_with_both_summaries']}",
            f"- Domain terms in raw summaries: {report['domain_terms_raw_summary']}",
            f"- Domain terms in corrected summaries: {report['domain_terms_corrected_summary']}",
            f"- Domain term delta: {report['domain_term_delta']}",
            f"- Raw ASR error spans in raw summaries: {report['raw_asr_error_spans_in_raw_summaries']}",
            f"- Canonical terms in corrected summaries: {report['canonical_terms_in_corrected_summaries']}",
            f"- Rejected leakage: {report['rejected_leakage']}",
            f"- Manual-review leakage: {report['manual_review_leakage']}",
            f"- Decision changes: {json.dumps(report['decision_changes'], ensure_ascii=False, sort_keys=True)}",
            f"- Hallucinated entity watch count: {report['hallucinated_entity_watch_count']}",
            "",
        ]
    )


def write_report(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def run_model_backed_pairs(
    selected: list[ArtifactSet],
    config: RunnerConfig,
    local_output_dir: Path,
    domain_terms: dict[str, list[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    local_output_dir.mkdir(parents=True, exist_ok=True)
    runner = build_runner(config)
    for artifact in selected:
        sample_dir = local_output_dir / safe_filename(artifact.file_id)
        sample_dir.mkdir(parents=True, exist_ok=True)
        raw_text = artifact.raw_transcript.read_text(encoding="utf-8", errors="replace")
        corrected_text = artifact.corrected_transcript.read_text(encoding="utf-8", errors="replace")
        raw_output = runner.generate(raw_text)
        corrected_output = runner.generate(corrected_text)
        raw_summary = parse_summary_json(raw_output)
        corrected_summary = parse_summary_json(corrected_output)
        (sample_dir / "summary_from_raw.json").write_text(
            json.dumps(raw_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (sample_dir / "summary_from_corrected.json").write_text(
            json.dumps(corrected_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        rows.append(evaluate_pair(artifact, raw_summary, corrected_summary, domain_terms))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Gemma 4 E4B local summary-impact gate for ASR correction.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--privacy-clearance", type=Path, default=DEFAULT_PRIVACY_CLEARANCE)
    return parser.parse_args()


def write_privacy_clearance(path: Path, selected_count: int) -> dict[str, Any]:
    clearance = {
        "gate": GATE_NAME,
        "selected_candidates": selected_count,
        "raw_transcript_review_required": False,
        "local_summary_generation_allowed": True,
        "local_outputs_ignored": True,
        "commit_summary_text_allowed": False,
        "commit_aggregate_report_allowed": True,
        "raw_transcript_text_committed": False,
        "reason": (
            "Selected candidates are used only for local model-backed paired summary generation; "
            "no raw transcript or summary text may be committed."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clearance, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return clearance


def main() -> int:
    args = parse_args()
    config_payload = load_config(args.config)
    config = runner_config(config_payload)
    max_samples = int(nested(config_payload, "sample", "max_samples", 8))
    max_input_chars = nested(config_payload, "sample", "max_input_chars_per_transcript", None)
    max_input_chars = int(max_input_chars) if max_input_chars is not None else None
    artifact_roots = [REPO_ROOT / path for path in nested(config_payload, "sample", "artifact_roots", ["."])]
    exclude_paths = list(nested(config_payload, "sample", "exclude_paths", []))
    local_output_dir = REPO_ROOT / nested(
        config_payload,
        "output",
        "local_output_dir",
        "reports/gemma4_e4b_summary_impact/local_outputs",
    )

    artifact_sets = discover_candidate_artifact_sets(
        artifact_roots,
        max_samples=max_samples,
        exclude_paths=exclude_paths,
        max_input_chars_per_transcript=max_input_chars,
    )
    write_privacy_clearance(args.privacy_clearance, selected_count=len(artifact_sets))
    model_available, reason = check_model_available(config)
    write_manifest(args.manifest, artifact_sets, model_available, reason, config, local_output_dir)

    rows: list[dict[str, Any]] = []
    if model_available:
        domain_terms = load_domain_terms()
        try:
            rows = run_model_backed_pairs(artifact_sets, config, local_output_dir, domain_terms)
        except Exception as exc:
            reason = f"Gemma 4 E4B local generation failed: {type(exc).__name__}: {exc}"

    report = aggregate_report(
        rows,
        complete_artifact_sets=len(artifact_sets),
        model_available=model_available,
        reason=reason,
        config=config,
    )
    if not model_available and "not found" in reason:
        report["reason"] = "Gemma 4 E4B local model not found"
    write_report(report, args.report_json, args.report_md)
    print(json.dumps({field: report[field] for field in REQUIRED_REPORT_FIELDS}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
