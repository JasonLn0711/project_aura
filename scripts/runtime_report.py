#!/usr/bin/env python3
"""Print a Project AURA runtime diagnostic report."""

import argparse

from aura.llm.ollama_runtime import DEFAULT_OLLAMA_HOST
from aura.system.runtime_report import build_runtime_report
from summary.field_schemas import OLLAMA_MODEL_TAG


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-folder", default=".")
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    parser.add_argument("--ollama-model-tag", default=OLLAMA_MODEL_TAG)
    args = parser.parse_args(argv)
    print(
        build_runtime_report(
            output_folder=args.output_folder,
            ollama_host=args.ollama_host,
            ollama_model_tag=args.ollama_model_tag,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
