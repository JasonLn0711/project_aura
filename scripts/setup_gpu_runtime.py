#!/usr/bin/env python3
"""Check or restore the reviewed, checkout-local GX10 CUDA 13 backend."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, default=Path('runtime/gx10-cuda13/build-receipt.json'))
    parser.add_argument('--restore', action='store_true', help='Restore the reviewed wheel after dependency synchronization')
    parser.add_argument('--sync', action='store_true', help='Synchronize application dependencies, then restore the reviewed native backend')
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    if platform.system() != 'Linux' or platform.machine() != 'aarch64':
        parser.error('This build receipt belongs to Linux ARM64; amd64 GPU servers use the normal server profile')
    if Path(receipt['install_prefix']).resolve() != Path(sys.prefix).resolve():
        parser.error('This local build has an interpreter-specific RPATH. Rebuild on the target host; do not copy its wheel alone.')
    wheel = args.receipt.parent / receipt['wheel']
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != receipt['wheel_sha256']:
        parser.error('Native wheel checksum differs from the reviewed receipt')
    if not Path(receipt['shared_library']).is_file():
        parser.error('The native C++ shared library is missing. Rebuild CTranslate2 using the source commit and CMake receipt.')
    if args.restore or args.sync:
        from aura.sdk import local_connection
        try:
            local_connection(ensure=False)
        except RuntimeError:
            pass
        else:
            parser.error('Finish active work and stop the AURA service before changing its environment')
        if args.sync:
            print('GX10 setup: synchronizing application dependencies', file=sys.stderr, flush=True)
            subprocess.run(['uv', 'sync', '--locked', '--extra', 'cli', '--extra', 'gui', '--extra', 'capture',
                            '--extra', 'server', '--extra', 'punctuation', '--inexact'], check=True)
        print('GX10 setup: restoring reviewed CUDA 13 backend', file=sys.stderr, flush=True)
        subprocess.run(['uv', 'pip', 'install', '--python', sys.executable, '--no-deps', 'nvidia-cudnn-cu13==9.13.0.50'], check=True)
        subprocess.run(['uv', 'pip', 'install', '--python', sys.executable, '--no-deps', '--reinstall', str(wheel)], check=True)
    # Probe in a fresh interpreter so an imported extension cannot mask replacement.
    probe = subprocess.run([sys.executable, '-c',
        'import json,ctranslate2; print(json.dumps({"version":ctranslate2.__version__,"types":sorted(ctranslate2.get_supported_compute_types("cuda"))}))'],
        text=True, capture_output=True, check=True)
    backend = json.loads(probe.stdout)
    if 'int8' not in backend['types']:
        raise RuntimeError('The restored backend does not support required CUDA int8')
    print('GX10 setup: CUDA backend check passed; inference remains a separate validation', file=sys.stderr)
    print(json.dumps(dict(status='PREFLIGHT_ONLY', architecture=platform.machine(), backend=backend,
                         wheel_sha256=receipt['wheel_sha256'], source_commit=receipt['source_commit'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
