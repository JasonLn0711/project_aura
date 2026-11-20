#!/usr/bin/env python3
"""Paired enhancement-only execution. No ASR accuracy or model ranking."""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from aura.audio.reuse import ReuseWorker
from aura.audio.vad import SileroStreamVAD


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcm', type=Path, required=True, help='Authorized mono PCM16 / 16 kHz source')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--candidate', choices=('layer6-fp32', 'layer8-bf16'))
    parser.add_argument('--profile', action='store_true', help='Collect a separate short CPU/CUDA trace; not comparable to unprofiled timing')
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    if not args.activate or not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error('Use --activate and a positive finite duration for real model execution')
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    with args.pcm.open('rb') as source:
        raw = source.read(int(args.seconds * 16000) * 2)
    raw = raw[:len(raw) // 960 * 960]
    if not raw:
        parser.error('Source has no complete capture frame')
    vad = SileroStreamVAD()
    flags = []
    for offset in range(0, len(raw), 960):
        frame = raw[offset:offset + 960]
        values = np.frombuffer(frame, '<i2').astype(np.float32)
        flags.append(bool(vad.is_speech(frame, 16000)) and float(np.sqrt(np.mean(values ** 2))) >= 80)
    report = dict(study_id='STUDY-AURA-STREAMING-001', experiment_id='EXP-20261022-01-streaming-system',
        run_id=root.name, validation_mode='enhancement_streaming_validation',
        execution_status='PREFLIGHT_ONLY', runtime_validity='blocked_runtime',
        source_sha256=hashlib.sha256(raw).hexdigest(), source_samples=len(raw) // 2,
        accuracy='not_evaluated', denoising_quality='not_evaluated', runs=[])
    try:
        for implementation in (('stream-v2',) if args.candidate or args.profile else ('legacy-v1', 'stream-v2')):
            print(f'Enhancement probe: loading {implementation}', file=sys.stderr, flush=True)
            with ReuseWorker('live', live_policy='speech-guard-v1', implementation=implementation, candidate=args.candidate,
                             log_path=root / f'{implementation}.log') as worker:
                if args.profile:
                    worker.call(action='profile_start')
                started = last_notice = time.monotonic()
                first_output = None
                with (root / f'{implementation}.pcm').open('wb') as output, \
                        (root / f'{implementation}.events.jsonl').open('w') as events:
                    width = 3840 if implementation == 'stream-v2' else 960
                    for offset in range(0, len(raw), width):
                        block = raw[offset:offset + width]
                        if implementation == 'stream-v2':
                            pcm = worker.push_frames(block, start_sample=offset // 2,
                                source_speech=flags[offset // 960:(offset + len(block)) // 960])
                        else:
                            pcm = worker.push(block, source_speech=flags[offset // 960])
                        output.write(pcm)
                        now = time.monotonic()
                        if pcm and first_output is None:
                            first_output = offset + len(block) < len(raw)
                        events.write(json.dumps(dict(monotonic=now, input_samples=(offset + len(block)) // 2,
                                                     output_bytes=output.tell())) + '\n')
                        if now - last_notice >= 5:
                            print(f'Enhancement probe: {implementation} · {(offset + len(block)) // 2}/{len(raw) // 2} samples', file=sys.stderr, flush=True)
                            last_notice = now
                    output.write(worker.flush())
                elapsed = time.monotonic() - started
                if args.profile:
                    profile = worker.call(action='profile_stop', path=str(root / 'profile.json'))
                    (root / 'profile-table.txt').write_text(profile['table'])
                report['runs'].append(dict(implementation=implementation, runtime=worker.receipt,
                    runtime_validity='valid_baseline' if implementation == 'legacy-v1' else 'valid_target_runtime',
                    enhancement_seconds=elapsed, profiled=args.profile, candidate=args.candidate,
                    output_samples=(root / f'{implementation}.pcm').stat().st_size // 2,
                    output_sha256=hashlib.sha256((root / f'{implementation}.pcm').read_bytes()).hexdigest(),
                    diagnostics=worker.diagnostics, output_before_source_eof=first_output))
        if not args.candidate and not args.profile:
            a, b = [np.fromfile(root / f'{name}.pcm', dtype='<i2').astype(np.int32) for name in ('legacy-v1', 'stream-v2')]
            report['length_equal'] = len(a) == len(b) == len(raw) // 2
            report['max_pcm16_difference'] = int(np.max(np.abs(a - b))) if len(a) == len(b) else None
            report['diagnostics_equal'] = report['runs'][0]['diagnostics'] == report['runs'][1]['diagnostics']
            report['gate_outcome'] = 'pass' if (report['length_equal'] and report['max_pcm16_difference'] <= 1
                and report['diagnostics_equal'] and all(r['output_before_source_eof'] for r in report['runs'])) else 'fail'
        else:
            report['gate_outcome'] = 'not_evaluated'
            report['production_activation'] = 'held_for_quality_validation' if args.candidate else 'diagnostic_only'
        enhanced = np.fromfile(root / 'stream-v2.pcm', dtype='<i2').astype(np.float64)
        original = np.frombuffer(raw, '<i2').astype(np.float64)
        suppressed = voice = 0
        for i, speech in enumerate(flags):
            if speech:
                voice += 1
                source_rms = float(np.sqrt(np.mean(original[i*480:(i+1)*480] ** 2)))
                output_rms = float(np.sqrt(np.mean(enhanced[i*480:(i+1)*480] ** 2)))
                suppressed += output_rms < 8 and output_rms < source_rms * .01
        report['signal'] = dict(source_voice_frames=voice, suppressed_source_voice_frames=suppressed,
                               definition='30ms_source_vad_rms80_output_below8_and1percent')
        report.update(execution_status='LIVE_FULL_COMPLETED', runtime_validity='valid_target_runtime')
    except BaseException as exc:
        report.update(execution_status='BLOCKED_UNRESOLVED', error=str(exc), gate_outcome='fail')
        raise
    finally:
        report['code_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path('src/aura/audio').glob('reuse*.py'))}
        (root / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
    return 0 if report['gate_outcome'] == 'pass' or args.candidate or args.profile else 1


if __name__ == '__main__':
    raise SystemExit(main())
