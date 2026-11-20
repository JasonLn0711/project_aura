#!/usr/bin/env python3
"""Explicit, fixed-runtime end-to-end validation with independently paced capture."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from aura.sdk import AuraClient


def source_endpoints(pcm):
    import numpy as np
    from aura.audio.vad import SileroStreamVAD
    vad = SileroStreamVAD()
    ends, last_voice, quiet, active = [], 0, 0, False
    for offset in range(0, len(pcm), 960):
        frame = pcm[offset:offset + 960]
        values = np.frombuffer(frame, '<i2').astype(np.float32)
        speech = vad.is_speech(frame, 16000) and float(np.sqrt(np.mean(values ** 2))) >= 80
        if speech:
            last_voice, quiet, active = (offset + len(frame)) // 2, 0, True
        else:
            quiet += len(frame) // 2
            if active and quiet >= 12800:
                ends.append(last_voice)
                active = False
    if active: ends.append(last_voice)
    return ends


def endpoint_results(endpoints, events, origin):
    results = []
    for end in endpoints:
        shown = [e['monotonic'] for e in events if any(
            left < end / 16 and right >= end / 16 - 30 for left, right in e['ranges'])]
        delay = max(0, min(shown) - origin - end / 16000) if shown else None
        results.append(dict(end_sample=end, display_delay_seconds=delay, within_target=delay is not None and delay <= 5))
    delays = sorted(r['display_delay_seconds'] if r['display_delay_seconds'] is not None else math.inf for r in results)
    p95 = delays[math.ceil(.95 * len(delays)) - 1] if delays else math.inf
    return dict(endpoints=results, p95_seconds=p95 if math.isfinite(p95) else None,
                missing=sum(r['display_delay_seconds'] is None for r in results),
                pass_gate=bool(results) and p95 <= 5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcm', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=60, help='Longer than input repeats the source with continuous model state')
    parser.add_argument('--implementation', choices=('legacy-v1', 'stream-v2'), default='stream-v2')
    parser.add_argument('--gui-python', type=Path, default=Path('runtime/test-venv/bin/python'))
    parser.add_argument('--capture-binary', type=Path, default=Path('native/aura-capture/target/release/aura-capture'))
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    if not args.activate or not math.isfinite(args.seconds) or not 1 <= args.seconds <= 7200:
        parser.error('Use --activate with 1–7200 seconds for real model execution')
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = args.pcm.read_bytes()
    if not source or len(source) % 960:
        parser.error('Source must contain complete mono PCM16 30 ms frames')
    count = math.ceil(args.seconds / .03) * 960
    pcm = (source * math.ceil(count / len(source)))[:count]
    (root / 'input.pcm').write_bytes(pcm)
    ends = source_endpoints(pcm)
    (root / 'source-endpoints.json').write_text(json.dumps(ends))
    receipt = dict(study_id='STUDY-AURA-STREAMING-001', experiment_id='EXP-20261022-01-streaming-system',
        run_id=root.name, validation_mode='streaming_system_validation', execution_status='PREFLIGHT_ONLY',
        runtime_validity='blocked_runtime', gate_outcome='not_evaluated',
        implementation=args.implementation, input_sha256=hashlib.sha256(pcm).hexdigest(),
        source_sha256=hashlib.sha256(source).hexdigest(), source_samples=len(pcm) // 2,
        repeated_source=count > len(source), endpoint_definition='source_silero_v6_rms80_silence800ms_v1',
        accuracy='not_evaluated', denoising_quality='not_evaluated', asr_model_comparison='not_evaluated',
        client_surface='CLI stdout and offscreen Qt widget, production client paths')
    receipt['code_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path('src/aura').rglob('*.py'))}
    receipt['capture_sha256'] = hashlib.sha256(args.capture_binary.read_bytes()).hexdigest()
    env = {**os.environ, 'AURA_DATA_DIR': str(root / 'service'),
           'AURA_LIVE_IMPLEMENTATION': args.implementation, 'AURA_LIVE_ENHANCEMENT_POLICY': 'speech-guard-v1',
           'QT_QPA_PLATFORM': 'offscreen', 'XDG_CONFIG_HOME': str(root / 'config')}
    processes, handles, native_events, samples = [], [], [], []
    def launch(command, name, **kwargs):
        log = (root / f'{name}.log').open('wb'); handles.append(log)
        p = subprocess.Popen(command, env=env, stdout=kwargs.pop('stdout', log), stderr=log, **kwargs)
        processes.append(p)
        return p
    try:
        print('Streaming validation: preparing isolated service and models; capture has not started', file=sys.stderr, flush=True)
        startup = time.monotonic()
        service = launch([sys.executable, '-m', 'aura.cli', 'serve'], 'service')
        connection_path = root / 'service/connection.json'
        deadline = time.monotonic() + 300
        while not connection_path.exists():
            if service.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Isolated service did not start')
            time.sleep(.1)
        connection = json.loads(connection_path.read_text())
        with AuraClient(connection) as client:
            options = dict(asr_model='breeze', language='zh', beam_size=5, punctuation=True,
                           live_max_segment_len_sec=8, live_silence_ms=800, live_segmentation='adaptive')
            receipt['options'] = options
            s = client.request('record', dict(title='Private streaming system validation',
                capture_location='client', source='system', options=options))
            sid = s['id']; receipt['session_id'] = sid
            while s['state'] == 'starting':
                if time.monotonic() > deadline: raise RuntimeError('Model startup watchdog expired')
                time.sleep(.1)
                s = client.request('get', {'session_id': sid})
            if s['state'] != 'recording': raise RuntimeError(s.get('error') or s['state'])
            receipt['startup_seconds'] = time.monotonic() - startup
            receipt['asr_runtime'] = s.get('runtime')
            probes = []
            for view, python in [('cli', Path(sys.executable)), ('gui', args.gui_python)]:
                probes.append(launch([str(python), 'scripts/streaming_display_probe.py', '--view', view,
                    '--session', sid, '--output', str(root / f'{view}-display.jsonl')], view))
            native = launch([str(args.capture_binary)], 'capture', stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            def read_native():
                with (root / 'capture-events.jsonl').open('w') as output:
                    for line in native.stdout:
                        value = json.loads(line)
                        native_events.append(value)
                        output.write(json.dumps(value) + '\n'); output.flush()
            reader = threading.Thread(target=read_native, daemon=True); reader.start()
            native.stdin.write(json.dumps(dict(version=1, connection=connection, session_id=sid,
                directory=str(root / 'capture'), sources=[], input_pcm=str(root / 'input.pcm'))) + '\n')
            native.stdin.flush()
            deadline = time.monotonic() + args.seconds * 4 + 600
            last_notice = 0
            with (root / 'progress.jsonl').open('w') as progress:
                while s['state'] not in ('ready', 'failed', 'recoverable'):
                    s = client.request('get', {'session_id': sid})
                    now = time.monotonic()
                    e = s.get('enhancement', {})
                    captured = s.get('capture_progress', {}).get('captured_frames', s['input_sequence']) * 480
                    row = dict(monotonic=now, state=s['state'], captured_samples=captured,
                        durable_samples=s['samples'], processed_samples=e.get('processed_samples', 0),
                        lag_seconds=max(0, captured-e.get('processed_samples', 0)) / 16000,
                        asr_work=s.get('work'), pending_gaps=sum(g['status']=='pending' for g in e.get('gaps', [])))
                    samples.append(row); progress.write(json.dumps(row) + '\n'); progress.flush()
                    if now - last_notice >= 5:
                        print(f'Streaming validation: {s["state"]} · captured {captured}/{len(pcm)//2} samples · enhancement lag {row["lag_seconds"]:.2f}s · pending intervals {row["pending_gaps"]}', file=sys.stderr, flush=True)
                        last_notice = now
                    if now > deadline: raise RuntimeError('Streaming validation watchdog expired; private source retained')
                    if native.poll() not in (None, 0): raise RuntimeError('Native capture failed')
                    if any(p.poll() not in (None, 0) for p in probes): raise RuntimeError('Display probe failed; see client logs')
                    time.sleep(.1)
            if s['state'] != 'ready': raise RuntimeError(s.get('error') or s['state'])
            native.wait(timeout=30); reader.join(timeout=5)
            for p in probes:
                if p.wait(timeout=30) != 0: raise RuntimeError('Display probe failed')
            origin = next(e['monotonic'] for e in native_events if e['event'] == 'capture_started')
            receipt['views'] = {}
            for view in ('cli', 'gui'):
                events = [json.loads(line) for line in (root / f'{view}-display.jsonl').read_text().splitlines()]
                receipt['views'][view] = endpoint_results(ends, events, origin)
            lags = sorted(r['lag_seconds'] for r in samples if r['state']=='recording' and r['captured_samples'] > 0)
            receipt['enhancement_lag'] = dict(p95_seconds=lags[math.ceil(.95*len(lags))-1], max_seconds=max(lags))
            lag_pass = receipt['enhancement_lag']['p95_seconds'] <= 1 and max(lags) <= 3
            receipt['gate_outcome'] = 'pass' if lag_pass and all(v['pass_gate'] for v in receipt['views'].values()) else 'fail'
            receipt['enhancement'] = s['enhancement']
            receipt['delivered_m4a'] = bool(s.get('artifacts', {}).get('m4a'))
            receipt['execution_status'] = 'LIVE_FULL_COMPLETED'
            receipt['runtime_validity'] = 'valid_target_runtime'
    except BaseException as exc:
        receipt.update(execution_status='BLOCKED_UNRESOLVED', gate_outcome='fail', error=str(exc))
        raise
    finally:
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    p.kill(); p.wait(timeout=10)
        for handle in handles: handle.close()
        (root / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt), flush=True)
    return 0 if receipt['gate_outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
