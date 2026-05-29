#!/usr/bin/env python3
"""Print a Project AURA runtime diagnostic report."""

from aura.system.runtime_report import build_runtime_report


def main() -> int:
    print(build_runtime_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
