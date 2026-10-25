#!/usr/bin/env python3
"""Install AURA's pinned, isolated Nemotron runtime and cache its model weights."""
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    python = root / '.venv-nemotron/bin/python'
    if not python.exists():
        subprocess.run(['uv', 'venv', '--python', '3.12', str(python.parent.parent)], check=True)
    subprocess.run(['uv', 'pip', 'sync', '--python', str(python),
        str(root / 'dependencies/nemotron/requirements.txt'),
        '--extra-index-url', 'https://download.pytorch.org/whl/cu128'], check=True)
    import sys
    sys.path.insert(0, str(root / 'src'))
    from aura.diarization.nemotron import MODEL_ID, MODEL_REVISION
    code = ('from huggingface_hub import snapshot_download; '
            f'snapshot_download({MODEL_ID!r}, revision={MODEL_REVISION!r}, '
            'allow_patterns=["*.json", "*.safetensors"])')
    subprocess.run([str(python), '-c', code], check=True)
    print('Nemotron installed and cached. Run AURA diagnostics before recording.')


if __name__ == '__main__':
    main()
