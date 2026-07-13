#!/usr/bin/env python3
"""Materialize the fixed Common Voice 24 zh-TW minimum benchmark."""

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import hf_hub_download

DATASET = "OKHand/Clean_Common_Voice_Speech_24.0-TW"
REVISION = "96d8e4fcc3b0d0db304fec018d4b813360160e2b"
PARQUET_FILE = "data/train-00000-of-00009.parquet"
ROW_INDICES = (0, 6, 20, 61, 96)


def prepare(output_dir: Path) -> Path:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise SystemExit(
            "The benchmark dependency group activates dataset preparation; "
            "run `uv sync --extra benchmark`."
        ) from exc

    source = hf_hub_download(
        repo_id=DATASET,
        repo_type="dataset",
        revision=REVISION,
        filename=PARQUET_FILE,
    )
    table = parquet.read_table(source)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.jsonl"

    with manifest_path.open("w", encoding="utf-8") as manifest:
        for row_index in ROW_INDICES:
            row = table.slice(row_index, 1).to_pylist()[0]
            audio_bytes = row["audio"]["bytes"]
            audio_path = audio_dir / row["file_name"]
            audio_path.write_bytes(audio_bytes)
            record = {
                "case_id": f"cv24-{row_index:03d}",
                "audio_path": str(Path("audio") / row["file_name"]),
                "reference": row["sentence"],
                "gender": row["gender"],
                "predicted_mos": row["predicted_mos"],
                "sha256": hashlib.sha256(audio_bytes).hexdigest(),
                "source_dataset": DATASET,
                "source_revision": REVISION,
                "source_row_index": row_index,
            }
            manifest.write(json.dumps(record, ensure_ascii=False) + "\n")

    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output))


if __name__ == "__main__":
    main()
