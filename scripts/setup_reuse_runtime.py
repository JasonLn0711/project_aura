#!/usr/bin/env python3
"""Provision the isolated NVIDIA RE-USE runtime, never the ASR environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sysconfig
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from aura.audio.reuse_model import REVISIONS


def run(command, **kwargs):
    print('RE-USE: ' + ' '.join(map(str, command)), file=sys.stderr, flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def download(root):
    for repo, revision in REVISIONS.values():
        directory = root / repo.split('/')[-1]
        directory.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{revision}') as response:
            info = json.load(response)
        hashes = {}
        files = [f['rfilename'] for f in info['siblings'] if f['rfilename'].endswith(('.py', '.json', '.safetensors', '.md'))]
        for i, name in enumerate(files, 1):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f'RE-USE snapshot {repo}: {i}/{len(files)} {name}', file=sys.stderr, flush=True)
            temp = path.with_suffix(path.suffix + '.download')
            with urllib.request.urlopen(f'https://huggingface.co/{repo}/resolve/{revision}/{name}') as response, temp.open('wb') as target:
                while block := response.read(1024 * 1024):
                    target.write(block)
            temp.replace(path)
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (directory / 'snapshot.json').write_text(json.dumps(dict(repository=repo, revision=revision, sha256=hashes), indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-only', action='store_true')
    parser.add_argument('--headers-root', type=Path, help='Optional extracted usr/include containing python3.12/Python.h')
    args = parser.parse_args()
    runtime = ROOT / 'runtime'
    python = runtime / 'reuse-venv/bin/python'
    if not args.download_only:
        if not python.exists():
            run(['uv', 'venv', '--python', '3.12', python.parent.parent])
        run(['uv', 'pip', 'install', '--python', python, 'torch==2.9.1', 'torchaudio==2.9.1',
             '--index-url', 'https://download.pytorch.org/whl/cu130'])
        run(['uv', 'pip', 'install', '--python', python, 'setuptools', 'wheel', 'packaging', 'ninja',
             'numpy', 'einops', 'huggingface-hub', 'safetensors', 'pyyaml', 'transformers'])
        env = dict(os.environ, MAX_JOBS='4', MAMBA_FORCE_BUILD='TRUE', CAUSAL_CONV1D_FORCE_BUILD='TRUE')
        if args.headers_root:
            headers = args.headers_root.resolve()
            if not (headers / 'python3.12/Python.h').is_file():
                raise ValueError('--headers-root must contain python3.12/Python.h')
            retained = runtime / 'reuse-headers'
            for name in ('python3.12', sysconfig.get_config_var('MULTIARCH') + '/python3.12'):
                if (headers / name).is_dir():
                    shutil.copytree(headers / name, retained / name, dirs_exist_ok=True)
            env['CPATH'] = os.pathsep.join([str(retained / 'python3.12'), str(retained), env.get('CPATH', '')])
        constraints = runtime / 'reuse-constraints.txt'
        constraints.write_text('torch==2.9.1+cu130\ntorchaudio==2.9.1\ntriton==3.5.1\n')
        run(['uv', 'pip', 'install', '--python', python, '--no-build-isolation',
             'causal-conv1d==1.7.0', 'mamba-ssm==2.3.2.post1', '--constraint', constraints], env=env)
        with (runtime / 'reuse-environment.txt').open('w') as receipt:
            subprocess.run(['uv', 'pip', 'freeze', '--python', str(python)], check=True, stdout=receipt)
    download(runtime / 'reuse-source')
    print('RE-USE provisioning finished; both real model preflights are still required.', file=sys.stderr)


if __name__ == '__main__':
    main()
