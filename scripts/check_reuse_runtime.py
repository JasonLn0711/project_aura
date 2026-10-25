#!/usr/bin/env python3
"""Exercise both actual pinned RE-USE models without touching the live service."""
import argparse
import json
from pathlib import Path
import sys
import wave
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from aura.audio.reuse import ReuseWorker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Authorized 16 kHz mono PCM WAV')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(validation_mode='availability_validation', execution_status='RUNTIME_IMPL_IN_PROGRESS',
                  input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  accuracy='not_evaluated', preprocessing_effect='not_evaluated', variants={})
    try:
        with wave.open(str(args.input), 'rb') as f:
            if (f.getframerate(), f.getnchannels(), f.getsampwidth()) != (16000, 1, 2):
                raise ValueError('Input must be 16 kHz mono PCM16 WAV')
            total = f.getnframes()
            live_path = args.output / 'live.wav'
            events = []
            with ReuseWorker('live', log_path=args.output / 'live.log') as worker, wave.open(str(live_path), 'wb') as target:
                target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                received = emitted = 0
                while raw := f.readframes(480):
                    received += len(raw) // 2
                    enhanced = worker.push(raw)
                    emitted += len(enhanced) // 2
                    target.writeframesraw(enhanced)
                    events.append(dict(input_samples=received, output_samples=emitted, final=False))
                tail = worker.flush()
                target.writeframesraw(tail)
                emitted += len(tail) // 2
                events.append(dict(input_samples=received, output_samples=emitted, final=True))
                if emitted != total or not any(e['output_samples'] and e['input_samples'] < total for e in events):
                    raise RuntimeError('Actual live output/length validation failed')
                report['variants']['live'] = dict(runtime_validity='valid_target_runtime', real_runs=1,
                                                 output_samples=emitted, runtime=worker.receipt)
            (args.output / 'stream-events.json').write_text(json.dumps(events, indent=2) + '\n')
        def progress(value):
            print('Offline RE-USE: ' + json.dumps(value), file=sys.stderr, flush=True)
        with ReuseWorker('offline', progress=progress, log_path=args.output / 'offline.log') as worker:
            path = args.output / 'offline.wav'
            worker.enhance_file(args.input.resolve(), path.resolve())
            with wave.open(str(path), 'rb') as f:
                if f.getnframes() != total:
                    raise RuntimeError('Offline length mismatch')
            report['variants']['offline'] = dict(runtime_validity='valid_target_runtime', real_runs=1,
                                                output_samples=total, runtime=worker.receipt)
        report['execution_status'] = 'LIVE_MINIMUM_COMPLETED'
        report['production_activation'] = 'pending_service_integration_validation'
    except Exception as exc:
        report.update(execution_status='BLOCKED_UNRESOLVED', error=str(exc), production_activation='not_activated')
        raise
    finally:
        (args.output / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
