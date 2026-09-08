#!/usr/bin/env python3
"""Bounded denoise/VAD comparison with an acoustic-review gate and fixed ASR."""
import argparse
import hashlib
import json
from pathlib import Path

from aura.config import MODEL_ID

STUDY = "STUDY-AURA-FRONTEND-001"
DENOISE = ("off", "noisereduce-light", "fastenhancer-b", "dpdfnet2")
VADS = ("silero-bundled", "silero-6.2.1", "firered-stream")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_readiness(dataset, reviews):
    manifest = json.loads((dataset / "manifest.json").read_text())
    errors, cases = [], []
    for case in manifest["cases"]:
        sid = case["caseId"]
        if Path(sid).name != sid:
            raise ValueError("Invalid dataset case ID")
        folder = dataset / sid
        review = reviews.get(sid, {})
        for name in ("input.wav", "ground-truth.txt", "rare-terms.txt"):
            if not (folder / name).is_file():
                errors.append(f"{sid}: missing {name}")
        if review.get("status") != "ACOUSTICALLY_REVIEWED" or not review.get("reviewer"):
            errors.append(f"{sid}: acoustic review required")
        if (folder / "input.wav").exists() and review.get("audio_sha256") != digest(folder / "input.wav"):
            errors.append(f"{sid}: reviewed audio hash required")
        if (folder / "ground-truth.txt").exists() and review.get("reference_sha256") != digest(folder / "ground-truth.txt"):
            errors.append(f"{sid}: reviewed reference hash required")
        if review.get("numbers_and_terms_reviewed") is not True:
            errors.append(f"{sid}: numbers and rare terms require review")
        spans = review.get("speech_intervals_samples")
        if not isinstance(spans, list) or any(not isinstance(x, list) or len(x) != 2 or
                any(type(n) is not int for n in x) or not 0 <= x[0] < x[1] for x in spans):
            errors.append(f"{sid}: reviewed 16 kHz speech boundaries required")
        cases.append(sid)
    if len(cases) < 10 or len(set(cases)) != len(cases):
        errors.append("At least ten unique paired cases are required")
    return cases, errors


def run_arm(case, backend, vad_name, output, args):
    import numpy as np
    from pydub import AudioSegment
    from evaluate_denoise_backends import EvalCase, process_backend, evaluation_model, mixed_error_rate, character_error_rate, rare_term_report
    from aura.audio.vad import SileroStreamVAD, SpeechIntervals
    from aura.audio.vad_candidates import Silero621, FireRedStream
    directory = output / case.name / backend / vad_name
    directory.mkdir(parents=True)
    source = AudioSegment.from_file(case / "input.wav").set_channels(1).set_frame_rate(16000).set_sample_width(2)
    normalized = directory / "source.wav"
    source.export(normalized, format="wav")
    reference = (case / "ground-truth.txt").read_text(encoding="utf-8")
    terms = (case / "rare-terms.txt").read_text(encoding="utf-8").splitlines()
    evaluation = EvalCase(case.name, normalized, reference, terms)
    enhanced = directory / "processed.wav"
    # Candidate study applies whole-clip enhancement. Product live enhancement
    # remains per utterance; promotion requires a subsequent live integration check.
    process_backend(evaluation, backend, enhanced)
    # Match product topology: VAD sees the preserved source; enhancement feeds ASR.
    source_samples = np.array(source.get_array_of_samples(), dtype=np.int16)
    prepared = AudioSegment.from_file(enhanced).set_frame_rate(16000).set_channels(1).set_sample_width(2)
    samples = np.array(prepared.get_array_of_samples(), dtype=np.int16)
    if len(samples) != len(source_samples):
        raise ValueError("Enhancement changed the audio sample count")
    if vad_name == "silero-bundled":
        vad = SileroStreamVAD()
    elif vad_name == "silero-6.2.1":
        vad = Silero621(args.silero_model)
    else:
        vad = FireRedStream(args.firered_model)
    intervals = SpeechIntervals(480)
    chunks, activity = [], []
    for offset in range(0, len(source_samples), 480):
        frame = source_samples[offset:offset + 480]
        speech = vad.is_speech(frame.astype("<i2").tobytes(), 16000)
        activity.extend([speech] * len(frame))
        chunk = intervals.push(frame, speech)
        if chunk:
            chunks.append(chunk)
    last = intervals.finish()
    if last:
        chunks.append(last)
    if not hasattr(args, "asr_model"):
        args.asr_model = evaluation_model(MODEL_ID, "cuda", "int8")
    model = args.asr_model
    texts = []
    for chunk in chunks:
        segments, _ = model.transcribe(samples[chunk.start_sample:chunk.end_sample].astype(np.float32) / 32768,
            language="zh", beam_size=5, condition_on_previous_text=False)
        texts.append("".join(s.text for s in segments))
    text = "".join(texts)
    (directory / "transcript.txt").write_text(text, encoding="utf-8")
    expected = np.zeros(len(samples), dtype=bool)
    review = args.reviews[case.name]
    for start, end in review["speech_intervals_samples"]:
        if end > len(expected):
            raise ValueError("Speech annotation exceeds audio length")
        expected[start:end] = True
    activity = np.array(activity, dtype=bool)
    hits, misses = rare_term_report(terms, text)
    return dict(case_id=case.name, backend=backend, vad=vad_name, status="ok", runtime_validity="valid_target_runtime",
        mer=mixed_error_rate(reference, text), cer=character_error_rate(reference, text), rare_term_hits=hits,
        rare_term_misses=misses, missed_speech_samples=int(np.sum(expected & ~activity)),
        false_speech_samples=int(np.sum(~expected & activity)), processed_sha256=digest(enhanced))


def select_candidate(rows, key, incumbent, candidates):
    """Strict paired gate: protect every case's terms and macro MER/CER."""
    baseline = {r["case_id"]: r for r in rows if r[key] == incumbent and r["status"] == "ok"}
    accepted = []
    for name in candidates:
        candidate = {r["case_id"]: r for r in rows if r[key] == name and r["status"] == "ok"}
        if len(baseline) < 10 or candidate.keys() != baseline.keys():
            continue
        if any(not set(baseline[c]["rare_term_hits"]) <= set(candidate[c]["rare_term_hits"]) for c in baseline):
            continue
        metrics = ("mer", "cer") + (("missed_speech_samples", "false_speech_samples") if key == "vad" else ())
        if any(any(candidate[c][m] is None or baseline[c][m] is None for c in baseline) or
               sum(candidate[c][m] for c in baseline) > sum(baseline[c][m] for c in baseline) for m in metrics):
            continue
        score = sum(candidate[c]["mer"] for c in baseline)
        if score < sum(baseline[c]["mer"] for c in baseline):
            accepted.append((score, name))
    return min(accepted)[1] if accepted else incumbent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--reviews", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--activate-preprocessing-effect", action="store_true")
    p.add_argument("--silero-model", type=Path)
    p.add_argument("--firered-model", type=Path)
    args = p.parse_args()
    args.reviews = json.loads(args.reviews.read_text()) if args.reviews else {}
    cases, errors = review_readiness(args.dataset, args.reviews)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    protocol = dict(study_id=STUDY, validation_mode="preprocessing_effect", model=MODEL_ID,
        device="cuda", compute_type="int8", language="zh", beam_size=5, prompt="", hotwords="", punctuation=False,
        denoise_arms=DENOISE, vad_arms=VADS, dataset_sha256=digest(args.dataset / "manifest.json"),
        enhancement_scope="whole_clip_candidate_comparison", live_integration="separate_validation_gate",
        accuracy="not_evaluated", latency="not_evaluated", errors=errors)
    if errors or not args.activate_preprocessing_effect:
        protocol["status"] = "PREFLIGHT_ONLY"
        template = {}
        for sid in cases:
            folder = args.dataset / sid
            template[sid] = dict(status="AWAITING_ACOUSTIC_REVIEW", reviewer="", audio_sha256=digest(folder / "input.wav"),
                reference_sha256=digest(folder / "ground-truth.txt"), speech_intervals_samples=[],
                numbers_and_terms_reviewed=False, clean_control_reviewed=False)
        (args.output / "review-template.json").write_text(json.dumps(template, indent=2) + "\n")
        (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
        print(json.dumps({"status": protocol["status"], "cases": len(cases), "review_gates": len(errors)}))
        return 2 if errors else 0
    if not args.silero_model or not args.silero_model.is_file() or not args.firered_model or not args.firered_model.is_dir():
        raise SystemExit("Pin local Silero 6.2.1 and FireRed Stream-VAD model paths before running")
    protocol["silero_sha256"] = digest(args.silero_model)
    protocol["firered_files"] = {str(p.relative_to(args.firered_model)): digest(p) for p in args.firered_model.rglob("*") if p.is_file()}
    protocol["status"] = "RUNTIME_IMPL_IN_PROGRESS"
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2))
    rows = []
    def execute(backend, vad):
        for sid in cases:
            try:
                row = run_arm(args.dataset / sid, backend, vad, args.output, args)
            except Exception as exc:
                row = dict(case_id=sid, backend=backend, vad=vad, status="blocked", runtime_validity="blocked_runtime", error=str(exc))
            rows.append(row)
            with (args.output / "results.jsonl").open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    for backend in DENOISE:
        execute(backend, "silero-bundled")
    chosen = select_candidate(rows, "backend", "noisereduce-light", DENOISE[2:])
    for vad in VADS[1:]:
        execute(chosen, vad)
    vad_rows = [r for r in rows if r["backend"] == chosen]
    chosen_vad = select_candidate(vad_rows, "vad", "silero-bundled", VADS[1:])
    valid = all(r["status"] == "ok" for r in rows)
    decision = dict(status="LIVE_FULL_COMPLETED" if valid else "BLOCKED_UNRESOLVED",
        runtime_validity="valid_target_runtime" if valid else "blocked_runtime", selected_denoise=chosen if valid else None,
        selected_vad=chosen_vad if valid else None, product_default="noisereduce-light", promotion="requires protected-number and clean-control review",
        latency="not_evaluated", live_counts={f'{b}/{v}': sum(r["status"] == "ok" and r["backend"] == b and r["vad"] == v for r in rows) for b,v in {(r["backend"],r["vad"]) for r in rows}})
    (args.output / "decision.json").write_text(json.dumps(decision, indent=2))
    print(json.dumps(decision))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
