#!/usr/bin/env python3
"""Retired ASR model benchmark entry point."""

import sys


def main() -> int:
    print(
        "This ASR model benchmark is retired. Use one explicitly activated "
        "availability-validation smoke to confirm that the pinned system works. "
        "Use the separate preprocessing-effect study only to evaluate VAD or "
        "denoise changes with a fixed ASR runtime and reviewed ground truth.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
