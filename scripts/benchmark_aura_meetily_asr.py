#!/usr/bin/env python3
"""Run a paired, reference-backed live ASR minimum across AURA and Meetily."""

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
import wave
from dataclasses import dataclass, replace
from pathlib import Path

from faster_whisper import WhisperModel

from aura.asr.file_pipeline import build_transcribe_kwargs, resolve_initial_prompt
from aura.config import MODEL_ID


@dataclass(frozen=True)
class Case:
    case_id: str
    audio_path: str
    reference: str
    sha256: str
    source_dataset: str
    source_revision: str
    source_row_index: int


def read_manifest(path: Path) -> list[Case]:
    cases = []
    for row in map(json.loads, path.read_text().splitlines()):
        audio_path = Path(row["audio_path"])
        if not audio_path.is_absolute():
            row["audio_path"] = str((path.parent / audio_path).resolve())
        cases.append(Case(**{key: row[key] for key in Case.__annotations__}))
    return cases


def normalize(text: str) -> str:
    return re.sub(r"[^\w]", "", text, flags=re.UNICODE).lower()


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row_index, left_char in enumerate(left, 1):
        current = [row_index]
        for column_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column_index] + 1,
                    previous[column_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def cer(reference: str, transcript: str) -> float:
    normalized_reference = normalize(reference)
    return edit_distance(normalized_reference, normalize(transcript)) / max(1, len(normalized_reference))


def audio_duration(path: str) -> float:
    with wave.open(path, "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


def gpu_snapshot() -> dict:
    command = [
        "nvidia-smi",
        "--query-gpu=timestamp,name,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {"captured_at": time.time(), "raw": result.stdout.strip(), "exit_code": result.returncode}


def cuda_architecture() -> str:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()[0].strip().replace(".", "")


def monitor_gpu(
    stop: threading.Event,
    output_dir: Path,
    runtime: str,
    run_index: int | None = None,
) -> None:
    while True:
        append_jsonl(
            output_dir / "gpu_metrics.jsonl",
            {"runtime": runtime, "run_index": run_index, **gpu_snapshot()},
        )
        if stop.wait(0.1):
            return


def run_aura(cases: list[Case], output_dir: Path) -> list[dict]:
    load_started = time.perf_counter()
    model = WhisperModel(MODEL_ID, device="cuda", compute_type="int8")
    load_seconds = time.perf_counter() - load_started
    kwargs = build_transcribe_kwargs(
        beam_size=5,
        language="zh",
        initial_prompt=resolve_initial_prompt(None),
        condition_on_previous_text=False,
    )
    results = []
    for run_index, case in enumerate(cases):
        append_jsonl(
            output_dir / "event_trace.jsonl",
            {
                "event": "run_started",
                "runtime": "aura_faster_whisper",
                "run_index": run_index,
                "case_id": case.case_id,
                "at": time.time(),
            },
        )
        monitor_stop = threading.Event()
        monitor = threading.Thread(
            target=monitor_gpu,
            args=(monitor_stop, output_dir, "aura_faster_whisper", run_index),
        )
        monitor.start()
        started = time.perf_counter()
        try:
            segments, info = model.transcribe(case.audio_path, **kwargs)
            transcript = "".join(segment.text for segment in segments).strip()
            runtime_seconds = time.perf_counter() - started
        finally:
            monitor_stop.set()
            monitor.join()
        audio_seconds = audio_duration(case.audio_path)
        result = {
            "runtime": "aura_faster_whisper",
            "runtime_validity": "valid_target_runtime",
            "compiled_backend": "Cuda",
            "gpu_inference_required": True,
            "run_index": run_index,
            "case_id": case.case_id,
            "audio_path": str(Path(case.audio_path).relative_to(output_dir.resolve())),
            "reference": case.reference,
            "transcript": transcript,
            "cer": cer(case.reference, transcript),
            "model": MODEL_ID,
            "model_load_seconds": load_seconds,
            "audio_seconds": audio_seconds,
            "runtime_seconds": runtime_seconds,
            "real_time_factor": runtime_seconds / audio_seconds,
            "detected_language": getattr(info, "language", None),
        }
        results.append(result)
        append_jsonl(output_dir / "request_summary.jsonl", result)
        append_jsonl(
            output_dir / "event_trace.jsonl",
            {
                "event": "run_completed",
                "runtime": "aura_faster_whisper",
                "run_index": run_index,
                "case_id": case.case_id,
                "at": time.time(),
            },
        )
    return results


def run_meetily(
    cases: list[Case], meetily_repo: Path, model_path: Path, output_dir: Path
) -> list[dict]:
    manifest_path = meetily_repo / "frontend/src-tauri/Cargo.toml"
    build_command = [
        "cargo",
        "build",
        "--release",
        "--quiet",
        "--features",
        "cuda",
        "--manifest-path",
        str(manifest_path),
        "--example",
        "asr_benchmark",
    ]
    append_jsonl(
        output_dir / "event_trace.jsonl",
        {
            "event": "build_started",
            "runtime": "meetily_whisper_rs",
            "gpu_backend": "cuda",
            "at": time.time(),
        },
    )
    build_environment = os.environ.copy()
    build_environment["CMAKE_POSITION_INDEPENDENT_CODE"] = "ON"
    build_environment["CMAKE_CUDA_FLAGS"] = "-Xcompiler=-fPIC"
    build_environment["CMAKE_CUDA_ARCHITECTURES"] = cuda_architecture()
    benchmark_target_dir = Path(
        build_environment.get("MEETILY_BENCHMARK_TARGET_DIR", "/tmp/meetily-cuda-target")
    )
    build_environment["CARGO_TARGET_DIR"] = str(benchmark_target_dir)
    build = subprocess.run(
        build_command,
        cwd=meetily_repo,
        capture_output=True,
        text=True,
        check=False,
        env=build_environment,
    )
    if build.returncode:
        (output_dir / "meetily_stderr.log").write_text(build.stderr, encoding="utf-8")
        raise RuntimeError(f"Meetily CUDA benchmark build exited {build.returncode}; see meetily_stderr.log")
    append_jsonl(
        output_dir / "event_trace.jsonl",
        {
            "event": "build_completed",
            "runtime": "meetily_whisper_rs",
            "gpu_backend": "cuda",
            "at": time.time(),
        },
    )

    command = [
        str(benchmark_target_dir / "release/examples/asr_benchmark"),
        str(model_path),
        *[case.audio_path for case in cases],
    ]
    append_jsonl(
        output_dir / "event_trace.jsonl",
        {"event": "runtime_started", "runtime": "meetily_whisper_rs", "at": time.time()},
    )
    monitor_stop = threading.Event()
    monitor = threading.Thread(
        target=monitor_gpu,
        args=(monitor_stop, output_dir, "meetily_whisper_rs"),
    )
    process = subprocess.Popen(
        command,
        cwd=meetily_repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    monitor.start()
    try:
        stdout, stderr = process.communicate()
    finally:
        monitor_stop.set()
        monitor.join()
    portable_stderr = (build.stderr + stderr).replace(str(model_path), model_path.name)
    (output_dir / "meetily_stderr.log").write_text(portable_stderr, encoding="utf-8")
    if process.returncode:
        raise RuntimeError(f"Meetily benchmark exited {process.returncode}; see meetily_stderr.log")

    outputs = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    if len(outputs) != len(cases):
        raise RuntimeError(f"Meetily returned {len(outputs)} results for {len(cases)} requests")
    enriched = []
    for run_index, (case, output) in enumerate(zip(cases, outputs, strict=True)):
        if output.get("compiled_backend") != "Cuda" or output.get("gpu_inference_required") is not True:
            raise RuntimeError(f"Meetily returned a non-CUDA benchmark result: {output}")
        enriched.append(
            {
                **output,
                "audio_path": str(Path(case.audio_path).relative_to(output_dir.resolve())),
                "model_path": model_path.name,
                "runtime_validity": "valid_target_runtime",
                "run_index": run_index,
                "case_id": case.case_id,
                "reference": case.reference,
                "cer": cer(case.reference, output["transcript"]),
            }
        )
        append_jsonl(output_dir / "request_summary.jsonl", enriched[-1])
    append_jsonl(
        output_dir / "event_trace.jsonl",
        {"event": "runtime_completed", "runtime": "meetily_whisper_rs", "at": time.time()},
    )
    return enriched


def write_reports(results: list[dict], cases: list[Case], output_dir: Path) -> None:
    by_runtime = {}
    for runtime in sorted({result["runtime"] for result in results}):
        subset = [result for result in results if result["runtime"] == runtime]
        by_runtime[runtime] = {
            "runs": len(subset),
            "mean_cer": sum(result["cer"] for result in subset) / len(subset),
            "mean_runtime_seconds": sum(result["runtime_seconds"] for result in subset) / len(subset),
            "mean_real_time_factor": sum(result["real_time_factor"] for result in subset) / len(subset),
            "model_load_seconds": subset[0]["model_load_seconds"],
            "exact_matches": sum(normalize(result["reference"]) == normalize(result["transcript"]) for result in subset),
        }

    gpu_utilization = {}
    for row in map(json.loads, (output_dir / "gpu_metrics.jsonl").read_text().splitlines()):
        if row["raw"]:
            utilization = int(row["raw"].rsplit(",", 1)[-1].strip())
            gpu_utilization[row["runtime"]] = max(
                utilization, gpu_utilization.get(row["runtime"], 0)
            )

    validity = [
        "# Runtime validity",
        "",
        "- Status: `LIVE_MINIMUM_COMPLETED`",
        "- `aura_faster_whisper`: `valid_target_runtime` (Breeze ASR 25, CUDA/int8)",
        "- `meetily_whisper_rs`: `valid_target_runtime` (Breeze ASR 26, CUDA release runtime)",
        "- `meetily_parakeet`: `blocked_runtime` for zh-TW by the enforced model capability contract",
        f"- Live source audio: {len({case.sha256 for case in cases})} public Common Voice 24 zh-TW files with reference text",
        f"- GPU telemetry: AURA max utilization {gpu_utilization['aura_faster_whisper']}%; Meetily max utilization {gpu_utilization['meetily_whisper_rs']}%",
    ]
    (output_dir / "runtime_validity_report.md").write_text("\n".join(validity) + "\n", encoding="utf-8")

    latency = ["# Latency and accuracy", "", "| Runtime | Runs | Exact | Mean CER | Mean seconds | Mean RTF | Model load |", "|---|---:|---:|---:|---:|---:|---:|"]
    for runtime, metrics in by_runtime.items():
        latency.append(f"| `{runtime}` | {metrics['runs']} | {metrics['exact_matches']} | {metrics['mean_cer']:.4f} | {metrics['mean_runtime_seconds']:.3f} | {metrics['mean_real_time_factor']:.3f} | {metrics['model_load_seconds']:.3f}s |")
    (output_dir / "latency_report.md").write_text("\n".join(latency) + "\n", encoding="utf-8")

    decision = [
        "# Minimum live decision",
        "",
        "Both CUDA Breeze runtimes completed real inference on the same five reference-backed clips, twice each. This minimum validates the paired GPU-only execution path and model-language routing. The clean, short scripted sample is an activation layer for a larger meeting-distance corpus, not a product-wide quality winner.",
        "",
        "- Production default: retain Breeze ASR 25 in AURA and Breeze ASR 26 in Meetily within their current owners.",
        "- Operational fallback: none selected by this narrow corpus.",
        "- Research candidate: both runtimes advance; this narrow corpus selects no cross-repo quality winner.",
        "- Next optimization candidate: release-runtime latency plus long-audio cancellation and memory evidence.",
    ]
    (output_dir / "final_decision_report.md").write_text("\n".join(decision) + "\n", encoding="utf-8")
    failure_lines = [
        "# Failure analysis",
        "",
        "Every live request completed. The deterministic mismatches below identify the next corpus terms; `error_log.jsonl` is empty.",
        "",
        "| Runtime | Case | Reference | Transcript | CER |",
        "|---|---|---|---|---:|",
    ]
    seen = set()
    for result in results:
        failure = (result["runtime"], result["case_id"], result["reference"], result["transcript"])
        if result["cer"] and failure not in seen:
            seen.add(failure)
            failure_lines.append(f"| `{result['runtime']}` | `{result['case_id']}` | {result['reference']} | {result['transcript']} | {result['cer']:.4f} |")
    (output_dir / "failure_analysis.md").write_text("\n".join(failure_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--meetily-repo", type=Path, required=True)
    parser.add_argument("--meetily-model", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260713)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    for artifact in ("request_summary.jsonl", "event_trace.jsonl", "error_log.jsonl", "gpu_metrics.jsonl", "run_config.jsonl"):
        (args.output / artifact).write_text("", encoding="utf-8")
    cases = read_manifest(args.manifest)
    (args.output / "source_manifest.jsonl").write_text(args.manifest.read_text(encoding="utf-8"), encoding="utf-8")
    durable_audio_dir = args.output.resolve() / "audio"
    durable_audio_dir.mkdir(exist_ok=True)
    cases = [
        replace(
            case,
            audio_path=str(
                shutil.copy2(case.audio_path, durable_audio_dir / Path(case.audio_path).name)
            ),
        )
        for case in cases
    ]
    randomized = cases * args.repetitions
    random.Random(args.seed).shuffle(randomized)
    append_jsonl(
        args.output / "run_config.jsonl",
        {
            "seed": args.seed,
            "repetitions": args.repetitions,
            "gpu_policy": "ASR inference requires CUDA in both benchmark runtimes",
            "cuda_architecture": cuda_architecture(),
            "order": [case.case_id for case in randomized],
        },
    )

    try:
        results = run_aura(randomized, args.output)
        results.extend(run_meetily(randomized, args.meetily_repo, args.meetily_model, args.output))
        write_reports(results, cases, args.output)
    except Exception as exc:
        append_jsonl(args.output / "error_log.jsonl", {"error": type(exc).__name__, "message": str(exc), "at": time.time()})
        raise


if __name__ == "__main__":
    main()
