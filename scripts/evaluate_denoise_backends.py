#!/usr/bin/env python3
import argparse
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from pydub import AudioSegment

from aura.audio.denoise import reduce_audio_segment_noise
from aura.audio.enhancement_backends import enhance_import_audio_if_available
from aura.audio.meeting_distance import (
    MEETING_DISTANCE_FAR_SPEAKER,
    MEETING_DISTANCE_NORMAL,
    MEETING_DISTANCE_OFF,
    MEETING_DISTANCE_RESCUE_OFFLINE,
)


SUPPORTED_BACKENDS = (
    "off",
    "noisereduce-light",
    "noisereduce-medium",
    "deepfilternet3",
    "clearvoice",
    "wpe",
)


@dataclass(frozen=True)
class EvalCase:
    category: str
    input_path: Path
    reference_text: str | None
    rare_terms: list[str]


@dataclass
class BackendResult:
    category: str
    backend: str
    meeting_distance_mode: str
    status: str
    input_path: str
    processed_path: str | None = None
    transcript_path: str | None = None
    cer: float | None = None
    wer: float | None = None
    rare_term_hits: list[str] | None = None
    rare_term_misses: list[str] | None = None
    runtime_seconds: float | None = None
    note: str = ""


@dataclass(frozen=True)
class CategoryRecommendation:
    category: str
    recommended_backend: str | None
    recommended_mode: str | None
    compared_backends: list[str]
    skipped_backends: list[str]
    reason: str


def normalize_metric_text(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def levenshtein_distance(reference, hypothesis) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, start=1):
        current = [i]
        for j, hyp_item in enumerate(hypothesis, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (ref_item != hyp_item)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def character_error_rate(reference_text: str, hypothesis_text: str) -> float | None:
    reference = normalize_metric_text(reference_text).replace(" ", "")
    hypothesis = normalize_metric_text(hypothesis_text).replace(" ", "")
    if not reference:
        return None
    return levenshtein_distance(reference, hypothesis) / len(reference)


def word_error_rate(reference_text: str, hypothesis_text: str) -> float | None:
    reference = normalize_metric_text(reference_text).split()
    hypothesis = normalize_metric_text(hypothesis_text).split()
    if not reference:
        return None
    return levenshtein_distance(reference, hypothesis) / len(reference)


def rare_term_report(terms: list[str], transcript: str) -> tuple[list[str], list[str]]:
    normalized_transcript = normalize_metric_text(transcript)
    hits = []
    misses = []
    for term in terms:
        normalized_term = normalize_metric_text(term)
        if not normalized_term:
            continue
        if normalized_term in normalized_transcript:
            hits.append(term)
        else:
            misses.append(term)
    return hits, misses


def rare_term_hit_rate(result: BackendResult) -> float | None:
    hits = result.rare_term_hits or []
    misses = result.rare_term_misses or []
    total = len(hits) + len(misses)
    if total == 0:
        return None
    return len(hits) / total


def read_optional_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def read_rare_terms(case_dir: Path) -> list[str]:
    terms_path = case_dir / "rare_terms.txt"
    if not terms_path.exists():
        return []
    return [
        line.strip()
        for line in terms_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def discover_eval_cases(input_dir: Path) -> list[EvalCase]:
    cases = []
    for input_path in sorted(input_dir.glob("*/input.wav")):
        case_dir = input_path.parent
        cases.append(
            EvalCase(
                category=case_dir.name,
                input_path=input_path,
                reference_text=read_optional_text(case_dir / "reference.txt"),
                rare_terms=read_rare_terms(case_dir),
            )
        )
    return cases


def ensure_supported_backends(backends: list[str]) -> list[str]:
    unsupported = [backend for backend in backends if backend not in SUPPORTED_BACKENDS]
    if unsupported:
        raise ValueError(f"Unsupported backends: {', '.join(unsupported)}")
    return backends


def meeting_distance_mode_for_backend(backend: str) -> str:
    if backend == "off":
        return MEETING_DISTANCE_OFF
    if backend == "noisereduce-light":
        return MEETING_DISTANCE_NORMAL
    if backend in {"noisereduce-medium", "deepfilternet3"}:
        return MEETING_DISTANCE_FAR_SPEAKER
    if backend in {"clearvoice", "wpe"}:
        return MEETING_DISTANCE_RESCUE_OFFLINE
    raise ValueError(f"Unsupported backend: {backend}")


def process_off(case: EvalCase, output_path: Path) -> str:
    shutil.copyfile(case.input_path, output_path)
    return "original audio copied"


def process_noisereduce(case: EvalCase, output_path: Path, preset: str) -> str:
    audio = AudioSegment.from_file(case.input_path)
    enhanced = reduce_audio_segment_noise(audio, preset=preset)
    enhanced.export(output_path, format="wav")
    return f"noisereduce {preset}"


def process_deepfilternet(case: EvalCase, output_path: Path) -> str:
    result = enhance_import_audio_if_available(case.input_path, output_path, MEETING_DISTANCE_FAR_SPEAKER)
    if not result.succeeded:
        raise RuntimeError(result.note)
    return result.note


def process_clearvoice(case: EvalCase, output_path: Path) -> str:
    result = enhance_import_audio_if_available(case.input_path, output_path, MEETING_DISTANCE_RESCUE_OFFLINE)
    if not result.succeeded:
        raise RuntimeError(result.note)
    return result.note


def process_wpe(_case: EvalCase, _output_path: Path) -> str:
    try:
        import nara_wpe  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("nara_wpe package is not installed") from exc
    raise RuntimeError("WPE backend is intentionally pending a dedicated dereverb implementation")


def process_backend(case: EvalCase, backend: str, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if backend == "off":
        return process_off(case, output_path)
    if backend == "noisereduce-light":
        return process_noisereduce(case, output_path, "light")
    if backend == "noisereduce-medium":
        return process_noisereduce(case, output_path, "medium")
    if backend == "deepfilternet3":
        return process_deepfilternet(case, output_path)
    if backend == "clearvoice":
        return process_clearvoice(case, output_path)
    if backend == "wpe":
        return process_wpe(case, output_path)
    raise ValueError(f"Unsupported backend: {backend}")


def transcribe_audio(path: Path, model_id: str, device: str, compute_type: str, language: str | None) -> str:
    if device != "cuda":
        raise ValueError(
            "AURA ASR evaluation requires --device cuda; CPU inference is outside the supported runtime."
        )

    from faster_whisper import WhisperModel

    model = WhisperModel(model_id, device=device, compute_type=compute_type)
    kwargs = {"beam_size": 5, "condition_on_previous_text": True}
    if language:
        kwargs["language"] = language
    segments, _info = model.transcribe(str(path), **kwargs)
    return "".join(segment.text for segment in segments).strip()


def evaluate_case_backend(
    case: EvalCase,
    backend: str,
    output_dir: Path,
    model_id: str | None,
    device: str,
    compute_type: str,
    language: str | None,
) -> BackendResult:
    started = time.perf_counter()
    backend_dir = output_dir / case.category / backend
    processed_path = backend_dir / "processed.wav"
    transcript_path = backend_dir / "transcript.txt"
    result = BackendResult(
        category=case.category,
        backend=backend,
        meeting_distance_mode=meeting_distance_mode_for_backend(backend),
        status="ok",
        input_path=str(case.input_path),
    )
    try:
        note = process_backend(case, backend, processed_path)
        result.processed_path = str(processed_path)
        result.note = note
        if model_id:
            transcript = transcribe_audio(processed_path, model_id, device, compute_type, language)
            transcript_path.write_text(transcript + "\n", encoding="utf-8")
            result.transcript_path = str(transcript_path)
            if case.reference_text:
                result.cer = character_error_rate(case.reference_text, transcript)
                result.wer = word_error_rate(case.reference_text, transcript)
            hits, misses = rare_term_report(case.rare_terms, transcript)
            result.rare_term_hits = hits
            result.rare_term_misses = misses
        else:
            result.status = "processed"
            result.note = f"{note}; transcription skipped"
    except Exception as exc:
        result.status = "skipped"
        result.note = str(exc)
    result.runtime_seconds = round(time.perf_counter() - started, 3)
    return result


def _has_transcript_quality_metrics(result: BackendResult) -> bool:
    return result.status == "ok" and (result.wer is not None or result.cer is not None)


def _recommendation_sort_key(result: BackendResult):
    wer = result.wer if result.wer is not None else float("inf")
    cer = result.cer if result.cer is not None else float("inf")
    hit_rate = rare_term_hit_rate(result)
    runtime = result.runtime_seconds if result.runtime_seconds is not None else float("inf")
    return (wer, cer, -(hit_rate if hit_rate is not None else 0.0), runtime, result.backend)


def _recommendation_reason(result: BackendResult) -> str:
    parts = []
    if result.wer is not None:
        parts.append(f"WER {result.wer:.4f}")
    if result.cer is not None:
        parts.append(f"CER {result.cer:.4f}")
    hit_rate = rare_term_hit_rate(result)
    if hit_rate is not None:
        parts.append(f"rare-term hit rate {hit_rate:.2%}")
    if result.runtime_seconds is not None:
        parts.append(f"runtime {result.runtime_seconds:.3f}s")
    return "; ".join(parts) if parts else "transcript metrics unavailable"


def recommend_backends_by_category(results: list[BackendResult]) -> list[CategoryRecommendation]:
    categories = sorted({result.category for result in results})
    recommendations = []
    for category in categories:
        category_results = [result for result in results if result.category == category]
        comparable = [result for result in category_results if _has_transcript_quality_metrics(result)]
        skipped = [result.backend for result in category_results if result.status == "skipped"]
        if not comparable:
            recommendations.append(
                CategoryRecommendation(
                    category=category,
                    recommended_backend=None,
                    recommended_mode=None,
                    compared_backends=[],
                    skipped_backends=skipped,
                    reason="No recommendation: reference-backed ASR metrics are unavailable for this category.",
                )
            )
            continue
        winner = min(comparable, key=_recommendation_sort_key)
        recommendations.append(
            CategoryRecommendation(
                category=category,
                recommended_backend=winner.backend,
                recommended_mode=winner.meeting_distance_mode,
                compared_backends=[result.backend for result in comparable],
                skipped_backends=skipped,
                reason=_recommendation_reason(winner),
            )
        )
    return recommendations


def render_markdown(results: list[BackendResult]) -> str:
    lines = [
        "# Denoise Backend Evaluation",
        "",
        "| Category | Backend | Mode | Status | CER | WER | Rare hits | Rare misses | Runtime | Note |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for result in results:
        hits = ", ".join(result.rare_term_hits or [])
        misses = ", ".join(result.rare_term_misses or [])
        cer = "" if result.cer is None else f"{result.cer:.4f}"
        wer = "" if result.wer is None else f"{result.wer:.4f}"
        runtime = "" if result.runtime_seconds is None else f"{result.runtime_seconds:.3f}"
        note = result.note.replace("|", "/")
        lines.append(
            f"| {result.category} | {result.backend} | {result.meeting_distance_mode} | {result.status} | "
            f"{cer} | {wer} | {hits} | {misses} | {runtime} | {note} |"
        )
    recommendations = recommend_backends_by_category(results)
    lines.extend(
        [
            "",
            "## Recommendation by Category",
            "",
            "| Category | Recommended backend | Mode | Compared backends | Skipped backends | Reason |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for recommendation in recommendations:
        recommended_backend = recommendation.recommended_backend or ""
        recommended_mode = recommendation.recommended_mode or ""
        compared = ", ".join(recommendation.compared_backends)
        skipped = ", ".join(recommendation.skipped_backends)
        reason = recommendation.reason.replace("|", "/")
        lines.append(
            f"| {recommendation.category} | {recommended_backend} | {recommended_mode} | "
            f"{compared} | {skipped} | {reason} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_reports(results: list[BackendResult], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".json":
        output_path.write_text(
            json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    output_path.write_text(render_markdown(results), encoding="utf-8")
    json_path = output_path.with_suffix(".json")
    json_path.write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate AURA denoise/speech-enhancement backends.")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--backends", default="off,noisereduce-light,noisereduce-medium")
    parser.add_argument("--model", default=None, help="faster-whisper model id. Omit to process audio without ASR.")
    parser.add_argument("--device", choices=("cuda",), default="cuda")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--work-dir", default=Path("local_outputs/denoise_eval"), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    backends = ensure_supported_backends([item.strip() for item in args.backends.split(",") if item.strip()])
    cases = discover_eval_cases(args.input_dir)
    if not cases:
        raise SystemExit(f"No eval cases found under {args.input_dir}; expected */input.wav")
    results = []
    for case in cases:
        for backend in backends:
            results.append(
                evaluate_case_backend(
                    case=case,
                    backend=backend,
                    output_dir=args.work_dir,
                    model_id=args.model,
                    device=args.device,
                    compute_type=args.compute_type,
                    language=args.language,
                )
            )
    write_reports(results, args.output)


if __name__ == "__main__":
    main()
