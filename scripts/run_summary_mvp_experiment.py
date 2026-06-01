from __future__ import annotations

import argparse
import json
from pathlib import Path

from aura.summary_mvp.pipeline import ExperimentConfig, run_experiment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline meeting-summary MVP experiment.")
    parser.add_argument("--transcript", type=Path, required=True, help="Path to ASR transcript JSON.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for experiment artifacts.")
    parser.add_argument("--chunking-mode", choices=["time", "sliding"], default="time")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic summaries and avoid model downloads.")
    parser.add_argument("--model-run", action="store_true", help="Attempt INT8 model execution.")
    parser.add_argument("--qwen-model-id", default="Qwen/Qwen3.5-9B")
    parser.add_argument("--gemma-model-id", default="google/gemma-4-E4B-it")
    parser.add_argument("--top-k", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = True
    if args.model_run:
        dry_run = False
    if args.dry_run:
        dry_run = True

    report = run_experiment(
        ExperimentConfig(
            transcript_path=args.transcript,
            output_dir=args.output_dir,
            chunking_mode=args.chunking_mode,
            dry_run=dry_run,
            qwen_model_id=args.qwen_model_id,
            gemma_model_id=args.gemma_model_id,
            top_k=args.top_k,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
