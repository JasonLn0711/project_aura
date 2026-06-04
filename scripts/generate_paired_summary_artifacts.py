from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

DEFAULT_CONFIG = REPO_ROOT / "config" / "asr_summary_impact_sample.yaml"
DEFAULT_MANIFEST = REPO_ROOT / "reports" / "asr_summary_impact_sample_manifest.json"
DEFAULT_LOG_DIR = REPO_ROOT / "reports" / "asr_fuzzy_correction_logs"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "asr_summary_impact_sample" / "artifacts"
DEFAULT_MAX_SAMPLES = 8
DEFAULT_MIN_SAMPLES = 5
TARGET_CATEGORIES = ("organizations", "technical_terms", "medical_terms", "people")


@dataclass(frozen=True)
class SourceCandidate:
    source_file: str
    log_path: Path
    accepted_entries: tuple[dict[str, Any], ...]
    rejected_entries: tuple[dict[str, Any], ...]
    manual_entries: tuple[dict[str, Any], ...]

    @property
    def category_count(self) -> int:
        return len({str(entry.get("category") or "") for entry in self.accepted_entries})

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_entries)


def repo_relative(path: Path, base: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.name


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return payload


def sample_config_value(config: dict[str, Any], key: str, default: Any) -> Any:
    sample = config.get("sample") or {}
    if not isinstance(sample, dict):
        return default
    return sample.get(key, default)


def read_log(path: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        source = str(payload.get("source_transcript") or path.stem)
        entries = payload.get("correction_log") or payload.get("corrections") or []
    elif isinstance(payload, list):
        source = path.stem
        entries = payload
    else:
        return path.stem, []
    return source, [entry for entry in entries if isinstance(entry, dict)]


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "original": str(entry.get("original") or entry.get("span") or ""),
        "corrected": str(entry.get("corrected") or ""),
        "category": str(entry.get("category") or ""),
        "accepted": bool(entry.get("accepted", True)),
        "review_status": str(entry.get("review_status") or ("accepted" if entry.get("accepted", True) else "rejected")),
        "score": float(entry.get("score") or 0.0),
    }


def discover_candidates(log_dir: Path, include_categories: set[str]) -> list[SourceCandidate]:
    candidates: list[SourceCandidate] = []
    if not log_dir.exists():
        return candidates
    for path in sorted(log_dir.glob("*correction_log.json"), key=lambda item: item.as_posix()):
        source, raw_entries = read_log(path)
        entries = [normalize_entry(entry) for entry in raw_entries]
        accepted = tuple(
            entry
            for entry in entries
            if entry["accepted"] and entry["category"] in include_categories and entry["original"] and entry["corrected"]
        )
        if not accepted:
            continue
        rejected = tuple(entry for entry in entries if not entry["accepted"] and entry["review_status"] != "manual_review_required")
        manual = tuple(entry for entry in entries if not entry["accepted"] and entry["review_status"] == "manual_review_required")
        candidates.append(SourceCandidate(source, path, accepted, rejected, manual))
    return sorted(
        candidates,
        key=lambda item: (-item.category_count, -item.accepted_count, item.source_file),
    )


def clean_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return slug[:80] or "sample"


def unique_terms(entries: tuple[dict[str, Any], ...], field: str) -> list[str]:
    return sorted({str(entry.get(field) or "") for entry in entries if str(entry.get(field) or "")})


def sanitized_log_entries(candidate: SourceCandidate) -> list[dict[str, Any]]:
    entries = []
    for entry in candidate.accepted_entries + candidate.rejected_entries + candidate.manual_entries:
        entries.append(
            {
                "accepted": entry["accepted"],
                "category": entry["category"],
                "corrected": entry["corrected"],
                "method": "sanitized_sample",
                "original": entry["original"],
                "review_status": entry["review_status"],
                "score": entry["score"],
                "span": entry["original"],
            }
        )
    return entries


def write_sample_artifacts(candidate: SourceCandidate, output_dir: Path, index: int) -> dict[str, Any]:
    sample_id = f"sample_{index:03d}_{clean_slug(Path(candidate.source_file).stem)}"
    sample_dir = output_dir / sample_id
    sample_dir.mkdir(parents=True, exist_ok=True)

    rejected_terms = unique_terms(candidate.rejected_entries, "corrected")
    manual_terms = unique_terms(candidate.manual_entries, "corrected")
    blocked_canonical_terms = set(rejected_terms) | set(manual_terms)
    summary_safe_entries = tuple(
        entry for entry in candidate.accepted_entries if str(entry.get("corrected") or "") not in blocked_canonical_terms
    )
    raw_terms = unique_terms(summary_safe_entries, "original")
    corrected_terms = unique_terms(summary_safe_entries, "corrected")
    log_entries = sanitized_log_entries(candidate)

    raw_transcript = sample_dir / f"{sample_id}_raw.txt"
    corrected_transcript = sample_dir / f"{sample_id}_corrected.txt"
    correction_log = sample_dir / f"{sample_id}_correction_log.json"
    raw_summary = sample_dir / f"{sample_id}_raw_summary.txt"
    corrected_summary = sample_dir / f"{sample_id}_corrected_summary.txt"

    raw_transcript.write_text("SANITIZED_ASR_ERROR_TERMS: " + "; ".join(raw_terms) + "\n", encoding="utf-8")
    corrected_transcript.write_text("SANITIZED_CANONICAL_TERMS: " + "; ".join(corrected_terms) + "\n", encoding="utf-8")
    correction_log.write_text(json.dumps(log_entries, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raw_summary.write_text("SANITIZED_SUMMARY_FROM_RAW_TERMS: " + "; ".join(raw_terms) + "\n", encoding="utf-8")
    corrected_summary.write_text(
        "SANITIZED_SUMMARY_FROM_CORRECTED_TERMS: " + "; ".join(corrected_terms) + "\n",
        encoding="utf-8",
    )

    return {
        "sample_id": sample_id,
        "source_transcript_file": candidate.source_file,
        "source_correction_log_file": repo_relative(candidate.log_path),
        "raw_transcript": repo_relative(raw_transcript),
        "corrected_transcript": repo_relative(corrected_transcript),
        "correction_log": repo_relative(correction_log),
        "summary_from_raw": repo_relative(raw_summary),
        "summary_from_corrected": repo_relative(corrected_summary),
        "accepted_corrections": len(candidate.accepted_entries),
        "summary_safe_accepted_corrections": len(summary_safe_entries),
        "categories": sorted({entry["category"] for entry in candidate.accepted_entries}),
        "raw_error_spans": raw_terms,
        "corrected_canonical_terms": corrected_terms,
        "rejected_terms_excluded_from_corrected_summary": rejected_terms,
        "manual_review_terms_excluded_from_corrected_summary": manual_terms,
        "sanitized": True,
    }


def build_manifest(selected: list[SourceCandidate], sample_rows: list[dict[str, Any]], min_samples: int) -> dict[str, Any]:
    category_counts = Counter(category for row in sample_rows for category in row["categories"])
    return {
        "mode": "sanitized_from_correction_logs",
        "external_model_calls": False,
        "cloud_model_calls": False,
        "raw_email_or_pdf_read": False,
        "raw_transcript_context_emitted": False,
        "generated_summaries_are_sanitized": True,
        "minimum_requested_samples": min_samples,
        "selected_samples": len(selected),
        "sample_rows": sample_rows,
        "category_counts": dict(sorted(category_counts.items())),
        "summary_generation": {
            "status": "sanitized_deterministic_term_level_sample",
            "local_model_inference_used": False,
            "missing_summary_generation_dependencies": [],
        },
    }


def generate_samples(
    log_dir: Path = DEFAULT_LOG_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    manifest_path: Path = DEFAULT_MANIFEST,
    max_samples: int = DEFAULT_MAX_SAMPLES,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    include_categories: set[str] | None = None,
) -> dict[str, Any]:
    categories = include_categories or set(TARGET_CATEGORIES)
    candidates = discover_candidates(log_dir, categories)
    selected = candidates[:max_samples]
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_rows = [write_sample_artifacts(candidate, output_dir, index) for index, candidate in enumerate(selected, start=1)]
    manifest = build_manifest(selected, sample_rows, min_samples=min_samples)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate sanitized paired summary artifacts for ASR correction impact evaluation.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--max-samples", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    log_dir = args.log_dir or REPO_ROOT / sample_config_value(config, "source_log_dir", "reports/asr_fuzzy_correction_logs")
    output_dir = args.output_dir or REPO_ROOT / sample_config_value(
        config,
        "output_dir",
        "reports/asr_summary_impact_sample/artifacts",
    )
    max_samples = args.max_samples or int(sample_config_value(config, "max_samples", DEFAULT_MAX_SAMPLES))
    min_samples = int(sample_config_value(config, "min_samples", DEFAULT_MIN_SAMPLES))
    include_categories = set(sample_config_value(config, "include_categories", list(TARGET_CATEGORIES)))
    manifest = generate_samples(
        log_dir=log_dir,
        output_dir=output_dir,
        manifest_path=args.manifest,
        max_samples=max_samples,
        min_samples=min_samples,
        include_categories=include_categories,
    )
    print(json.dumps({key: manifest[key] for key in ("selected_samples", "category_counts")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
