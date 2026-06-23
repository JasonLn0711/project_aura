#!/usr/bin/env python3
import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromotionCase:
    category: str
    comparable: bool
    baseline_wer: float | None
    candidate_wer: float | None
    baseline_cer: float | None
    candidate_cer: float | None
    baseline_rare_hit_rate: float | None
    candidate_rare_hit_rate: float | None
    reason: str


@dataclass(frozen=True)
class PromotionGate:
    ready: bool
    report_path: str
    baseline_backend: str
    candidate_backend: str
    comparable_case_count: int
    min_cases: int
    average_wer_delta: float | None
    average_cer_delta: float | None
    average_rare_hit_rate_delta: float | None
    errors: list[str]
    warnings: list[str]
    cases: list[PromotionCase]


def rare_hit_rate(result: dict) -> float | None:
    hits = result.get("rare_term_hits") or []
    misses = result.get("rare_term_misses") or []
    total = len(hits) + len(misses)
    if total == 0:
        return None
    return len(hits) / total


def load_results(report_path: Path) -> list[dict]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("expected evaluation JSON to contain a list of backend results")
    return data


def result_has_metrics(result: dict | None) -> bool:
    if not result or result.get("status") != "ok":
        return False
    return result.get("wer") is not None or result.get("cer") is not None


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _metric_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def evaluate_promotion_gate(
    results: list[dict],
    report_path: Path,
    baseline_backend: str,
    candidate_backend: str,
    min_cases: int,
    max_average_wer_delta: float,
    max_average_cer_delta: float,
    min_average_rare_hit_rate_delta: float,
) -> PromotionGate:
    by_category: dict[str, dict[str, dict]] = {}
    for result in results:
        category = str(result.get("category", "")).strip()
        backend = str(result.get("backend", "")).strip()
        if not category or not backend:
            continue
        by_category.setdefault(category, {})[backend] = result

    cases = []
    wer_deltas = []
    cer_deltas = []
    rare_deltas = []
    errors = []
    warnings = []

    for category in sorted(by_category):
        baseline = by_category[category].get(baseline_backend)
        candidate = by_category[category].get(candidate_backend)
        if not baseline or not candidate:
            cases.append(
                PromotionCase(
                    category=category,
                    comparable=False,
                    baseline_wer=None,
                    candidate_wer=None,
                    baseline_cer=None,
                    candidate_cer=None,
                    baseline_rare_hit_rate=None,
                    candidate_rare_hit_rate=None,
                    reason=f"missing {baseline_backend if not baseline else candidate_backend} result",
                )
            )
            continue
        if not result_has_metrics(baseline) or not result_has_metrics(candidate):
            cases.append(
                PromotionCase(
                    category=category,
                    comparable=False,
                    baseline_wer=baseline.get("wer"),
                    candidate_wer=candidate.get("wer"),
                    baseline_cer=baseline.get("cer"),
                    candidate_cer=candidate.get("cer"),
                    baseline_rare_hit_rate=rare_hit_rate(baseline),
                    candidate_rare_hit_rate=rare_hit_rate(candidate),
                    reason="missing reference-backed ASR metrics",
                )
            )
            continue

        baseline_rare_hit_rate = rare_hit_rate(baseline)
        candidate_rare_hit_rate = rare_hit_rate(candidate)
        wer_delta = _metric_delta(candidate.get("wer"), baseline.get("wer"))
        cer_delta = _metric_delta(candidate.get("cer"), baseline.get("cer"))
        rare_delta = _metric_delta(candidate_rare_hit_rate, baseline_rare_hit_rate)
        if wer_delta is not None:
            wer_deltas.append(wer_delta)
        if cer_delta is not None:
            cer_deltas.append(cer_delta)
        if rare_delta is not None:
            rare_deltas.append(rare_delta)
        cases.append(
            PromotionCase(
                category=category,
                comparable=True,
                baseline_wer=baseline.get("wer"),
                candidate_wer=candidate.get("wer"),
                baseline_cer=baseline.get("cer"),
                candidate_cer=candidate.get("cer"),
                baseline_rare_hit_rate=baseline_rare_hit_rate,
                candidate_rare_hit_rate=candidate_rare_hit_rate,
                reason="reference-backed ASR metrics available",
            )
        )

    comparable_case_count = sum(1 for case in cases if case.comparable)
    average_wer_delta = average(wer_deltas)
    average_cer_delta = average(cer_deltas)
    average_rare_delta = average(rare_deltas)

    if comparable_case_count < min_cases:
        errors.append(f"comparable case count {comparable_case_count} is below required minimum {min_cases}")
    if average_wer_delta is None:
        errors.append("average WER delta is unavailable")
    elif average_wer_delta > max_average_wer_delta:
        errors.append(
            f"average WER delta {average_wer_delta:.4f} exceeds allowed {max_average_wer_delta:.4f}"
        )
    if average_cer_delta is None:
        errors.append("average CER delta is unavailable")
    elif average_cer_delta > max_average_cer_delta:
        errors.append(
            f"average CER delta {average_cer_delta:.4f} exceeds allowed {max_average_cer_delta:.4f}"
        )
    if average_rare_delta is None:
        warnings.append("rare-term hit-rate delta is unavailable")
    elif average_rare_delta < min_average_rare_hit_rate_delta:
        errors.append(
            "average rare-term hit-rate delta "
            f"{average_rare_delta:.4f} is below required {min_average_rare_hit_rate_delta:.4f}"
        )

    return PromotionGate(
        ready=not errors,
        report_path=str(report_path),
        baseline_backend=baseline_backend,
        candidate_backend=candidate_backend,
        comparable_case_count=comparable_case_count,
        min_cases=min_cases,
        average_wer_delta=average_wer_delta,
        average_cer_delta=average_cer_delta,
        average_rare_hit_rate_delta=average_rare_delta,
        errors=errors,
        warnings=warnings,
        cases=cases,
    )


def render_markdown(gate: PromotionGate) -> str:
    avg_wer = "" if gate.average_wer_delta is None else f"{gate.average_wer_delta:.4f}"
    avg_cer = "" if gate.average_cer_delta is None else f"{gate.average_cer_delta:.4f}"
    avg_rare = "" if gate.average_rare_hit_rate_delta is None else f"{gate.average_rare_hit_rate_delta:.4f}"
    lines = [
        "# Denoise Default Promotion Gate",
        "",
        f"- Ready: `{gate.ready}`",
        f"- Report: `{gate.report_path}`",
        f"- Baseline: `{gate.baseline_backend}`",
        f"- Candidate: `{gate.candidate_backend}`",
        f"- Comparable cases: `{gate.comparable_case_count}/{gate.min_cases}`",
        f"- Average WER delta: `{avg_wer}`",
        f"- Average CER delta: `{avg_cer}`",
        f"- Average rare-term hit-rate delta: `{avg_rare}`",
        "",
        "| Category | Comparable | Baseline WER | Candidate WER | Baseline CER | Candidate CER | Baseline rare hit rate | Candidate rare hit rate | Reason |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for case in gate.cases:
        baseline_wer = "" if case.baseline_wer is None else f"{case.baseline_wer:.4f}"
        candidate_wer = "" if case.candidate_wer is None else f"{case.candidate_wer:.4f}"
        baseline_cer = "" if case.baseline_cer is None else f"{case.baseline_cer:.4f}"
        candidate_cer = "" if case.candidate_cer is None else f"{case.candidate_cer:.4f}"
        baseline_rare = "" if case.baseline_rare_hit_rate is None else f"{case.baseline_rare_hit_rate:.4f}"
        candidate_rare = "" if case.candidate_rare_hit_rate is None else f"{case.candidate_rare_hit_rate:.4f}"
        reason = case.reason.replace("|", "/")
        lines.append(
            f"| {case.category} | {case.comparable} | {baseline_wer} | {candidate_wer} | "
            f"{baseline_cer} | {candidate_cer} | {baseline_rare} | {candidate_rare} | {reason} |"
        )
    if gate.errors:
        lines.extend(["", "## Blocking Errors"])
        lines.extend(f"- {error}" for error in gate.errors)
    if gate.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in gate.warnings)
    lines.append("")
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="Gate AURA denoise default promotion from an evaluation JSON report.")
    parser.add_argument("--report-json", required=True, type=Path)
    parser.add_argument("--baseline", default="off")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--min-cases", default=10, type=int)
    parser.add_argument("--max-average-wer-delta", default=0.0, type=float)
    parser.add_argument("--max-average-cer-delta", default=0.0, type=float)
    parser.add_argument("--min-average-rare-hit-rate-delta", default=0.0, type=float)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    return parser.parse_args()


def main():
    args = parse_args()
    results = load_results(args.report_json)
    gate = evaluate_promotion_gate(
        results=results,
        report_path=args.report_json,
        baseline_backend=args.baseline,
        candidate_backend=args.candidate,
        min_cases=args.min_cases,
        max_average_wer_delta=args.max_average_wer_delta,
        max_average_cer_delta=args.max_average_cer_delta,
        min_average_rare_hit_rate_delta=args.min_average_rare_hit_rate_delta,
    )
    if args.json:
        print(json.dumps(asdict(gate), ensure_ascii=False, indent=2))
    else:
        print(render_markdown(gate))
    raise SystemExit(0 if gate.ready else 1)


if __name__ == "__main__":
    main()
