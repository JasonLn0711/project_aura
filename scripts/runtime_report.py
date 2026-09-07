#!/usr/bin/env python3
"""Print a Project AURA runtime diagnostic report."""

import argparse

from aura.system.runtime_report import build_runtime_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-folder", default=".")
    args = parser.parse_args(argv)
    print(
        build_runtime_report(
            output_folder=args.output_folder,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
