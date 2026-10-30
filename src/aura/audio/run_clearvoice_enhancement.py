#!/usr/bin/env python3
import argparse
from pathlib import Path


def enhance(input_path: Path, output_path: Path):
    from clearvoice import ClearVoice

    output_path.parent.mkdir(parents=True, exist_ok=True)
    clearvoice = ClearVoice(
        task="speech_enhancement",
        model_names=["MossFormer2_SE_48K"],
    )
    output_wav = clearvoice(input_path=str(input_path), online_write=False)
    clearvoice.write(output_wav, output_path=str(output_path))


def main():
    parser = argparse.ArgumentParser(
        description="Run ClearVoice speech enhancement for AURA rescue-offline mode."
    )
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    args = parser.parse_args()
    enhance(args.input_path, args.output_path)


if __name__ == "__main__":
    main()
