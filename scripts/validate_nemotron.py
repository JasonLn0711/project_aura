#!/usr/bin/env python3
"""Owner-local real-audio acceptance through AURA's production transport."""
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


def wait_state(client, sid, wanted, timeout=3600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = client.request('get', {'session_id': sid})
        if s['state'] in wanted:
            return s
        if s['state'] == 'failed':
            raise RuntimeError(s.get('error'))
        time.sleep(.2)
    raise TimeoutError('Functional completion watchdog expired')


def run(source, output, mode):
    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    with source.open('rb') as audio:
        digest = hashlib.file_digest(audio, 'sha256').hexdigest()
    repo = Path(__file__).resolve().parents[1]
    code = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (repo/'src/aura').rglob('*.py')}
    (output/'code-manifest.json').write_text(json.dumps(code, indent=2))
    (output/'input.json').write_text(json.dumps(dict(path=str(source), sha256=digest, mode=mode)))
    root = output/'service'
    env = dict(os.environ, AURA_DATA_DIR=str(root))
    log = (output/'service.log').open('w')
    service = subprocess.Popen([sys.executable, '-m', 'aura.cli', 'serve'], env=env, stdout=log, stderr=log)
    clients = []
    decoder = None
    observer = None
    try:
        deadline = time.monotonic() + 30
        while not (root/'connection.json').exists():
            if service.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Validation service failed to start')
            time.sleep(.1)
        connection = json.loads((root/'connection.json').read_text())
        client = AuraClient(connection); clients.append(client)
        if mode == 'file':
            session = client.request('transcribe', dict(path=str(source), options={'diarization': True}))
            result = wait_state(client, session['id'], {'ready'})
            if not result['transcript'].strip() or not result.get('segments') or result.get('diarization',{}).get('state') != 'completed':
                raise AssertionError('Full-file functional output is incomplete')
            report = dict(status='LIVE_FULL_COMPLETED', runtime_validity='valid_target_runtime', mode=mode,
                session_id=result['id'], segments=len(result['segments']), accuracy='not_evaluated', asr_latency='not_evaluated')
        else:
            session = client.request('record', dict(capture_location='client', source='microphone',
                title='Nemotron authorized recording replay', options={'diarization': True}))
            sid = session['id']
            wait_state(client, sid, {'recording'}, timeout=600)
            observer = AuraClient(connection); clients.append(observer)
            producer = AuraClient(connection); clients.append(producer)
            producer.open_audio(sid, ['mixed'])
            sent = []
            latencies = []
            errors = []
            events_seen = []
            finished = threading.Event()
            def observe():
                last = 0
                previous_sample = 0
                try:
                    with (output/'diarization-events.jsonl').open('w') as journal:
                        for event in observer.subscribe(sid):
                            received = time.monotonic()
                            s = event.get('session', {})
                            d = s.get('diarization', {})
                            seq = d.get('sequence', 0)
                            if d.get('state') == 'failed':
                                raise RuntimeError(d.get('error'))
                            if seq > last:
                                if seq != last + 1:
                                    raise AssertionError('Missing diarization event sequence')
                                # Include the oldest sample scored by this update, not just its end.
                                index = previous_sample // 480
                                if index >= len(sent):
                                    raise AssertionError('Output arrived before its input was sent')
                                latency = received - sent[index]
                                latencies.append(latency)
                                previous_sample = d['processed_sample']
                                last = seq
                                events_seen.append(seq)
                                journal.write(json.dumps(dict(sequence=seq, processed_sample=previous_sample,
                                    received_monotonic=received, input_monotonic=sent[index], latency_seconds=latency))+'\n')
                                journal.flush()
                            if s.get('state') in ('ready','failed'):
                                break
                except Exception as exc:
                    errors.append(str(exc))
                finally:
                    finished.set()
            thread = threading.Thread(target=observe, daemon=True); thread.start()
            decoder = subprocess.Popen(['ffmpeg','-nostdin','-v','error','-i',str(source),'-ar','16000','-ac','1','-f','s16le','-'],
                stdout=subprocess.PIPE, stderr=log)
            sequence = 0
            started = time.monotonic()
            while True:
                pcm = decoder.stdout.read(960)
                if not pcm:
                    break
                pcm += bytes(960-len(pcm))
                target = started + sequence*.03
                time.sleep(max(0, target-time.monotonic()))
                sent.append(time.monotonic())
                producer.send_audio(sid, sequence, pcm)
                sequence += 1
                if errors:
                    raise RuntimeError(errors[0])
            decoder.stdout.close()
            if decoder.wait() != 0:
                raise RuntimeError('Source decoding failed')
            client.request('stop', {'session_id': sid})
            producer.request('producer.stopped', {'session_id': sid})
            producer.close()
            result = wait_state(client, sid, {'ready'})
            finished.wait(5)
            if errors:
                raise RuntimeError(errors[0])
            if not finished.is_set() or not latencies or not result['transcript'].strip():
                raise AssertionError('Stream observer or ASR output incomplete')
            p95 = sorted(latencies)[math.ceil(.95*len(latencies))-1]
            if result['diarization']['processed_sample'] != sequence*480:
                raise AssertionError('Diarization did not cover all input samples')
            report = dict(status='LIVE_FULL_COMPLETED', runtime_validity='valid_target_runtime', mode=mode,
                session_id=sid, frames=sequence, updates=len(latencies), p95_seconds=p95,
                max_seconds=max(latencies), gate_outcome='pass' if p95 <= 3 else 'fail',
                accuracy='not_evaluated', asr_latency='not_evaluated', microphone_acceptance='not_evaluated')
        export = client.request('export', {'session_id':result['id'], 'format':'json'})
        (output/'export.json').write_text(export['text'])
        (output/'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
        return report
    except BaseException as exc:
        (output/'blocked_unresolved_report.json').write_text(json.dumps(dict(status='BLOCKED_UNRESOLVED',error=str(exc))))
        raise
    finally:
        for client in clients:
            client.close()
        if decoder:
            if decoder.stdout:
                decoder.stdout.close()
            if decoder.poll() is None:
                decoder.terminate()
                try:
                    decoder.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    decoder.kill(); decoder.wait()
        service.terminate()
        try:
            service.wait(timeout=30)
        except subprocess.TimeoutExpired:
            service.kill(); service.wait()
        log.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--mode',choices=['file','stream'],required=True)
    args=p.parse_args()
    run(args.source.resolve(),args.output.resolve(),args.mode)


if __name__=='__main__':
    main()
