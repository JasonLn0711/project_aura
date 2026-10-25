#!/usr/bin/env python3
"""Synthetic capture/transport comparison. No model weights or ASR inference."""
import argparse
import json
import multiprocessing
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

from aura.sdk import AuraClient


class Speech:
    def is_speech(self, *_):
        return True


def execute(kind, payload):
    if kind == 'load':
        return dict(device='test_double', model='synthetic')
    if kind == 'chunk':
        return dict(text='synthetic', start_sample=payload['start'], end_sample=payload['end'])
    if kind == 'export':
        from aura.session_runtime import execute as export
        return export(kind, payload)
    raise ValueError(kind)


def server(root):
    from aura.service import serve
    from aura.session_core import SessionCore
    with patch('aura.audio.vad.SileroStreamVAD', return_value=Speech()):
        serve(root, core=SessionCore(root, executor=execute))


def python_producer():
    import numpy as np
    from aura.producer import capture
    init = json.loads(sys.stdin.readline())
    audio = open(init['input_pcm'], 'rb')
    control = AuraClient(init['connection'])
    class Reader:
        def read_tracks(self):
            raw = audio.read(960)
            if not raw:
                control.request('stop', {'session_id': init['session_id']})
                time.sleep(.25)  # Let the existing capture-stop observer close admission.
                return {'mixed': np.zeros(480, np.int16)}
            time.sleep(.03)
            return {'mixed': np.frombuffer(raw, dtype='<i2')}
        def close(self):
            pass
    try:
        with patch('aura.producer.AuraClient', side_effect=lambda *a, **kw: AuraClient(init['connection'])), \
                patch('aura.audio.inputs.open_audio_reader', return_value=Reader()):
            capture(init['session_id'])
    finally:
        audio.close(); control.close()


def wait(client, sid, state):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        s = client.request('get', {'session_id': sid})
        if s['state'] == state:
            return s
        if s['state'] == 'failed':
            raise RuntimeError(s.get('error'))
        time.sleep(.02)
    raise RuntimeError('Synthetic transport watchdog expired')


def measure(output):
    from urllib.parse import urlsplit
    from aura.native_capture import helper
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for backend in ('python', 'rust'):
        print(f'Synthetic transport: {backend}, 100 frames, 100 ms emulated RTT', file=sys.stderr, flush=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = multiprocessing.get_context('spawn').Process(target=server, args=(str(root/'service'),))
            process.start()
            capture = proxy = None
            try:
                deadline = time.monotonic() + 10
                while not (root/'service/connection.json').exists():
                    if time.monotonic() > deadline: raise RuntimeError('Server did not start')
                    time.sleep(.02)
                connection = json.loads((root/'service/connection.json').read_text())
                remote_port = urlsplit(connection['url']).port
                class Relay(socketserver.BaseRequestHandler):
                    def handle(self):
                        with socket.create_connection(('127.0.0.1', remote_port)) as target:
                            def forward(source, destination):
                                try:
                                    while data := source.recv(65536):
                                        time.sleep(.05)
                                        destination.sendall(data)
                                except OSError:
                                    pass
                                finally:
                                    try: destination.shutdown(socket.SHUT_WR)
                                    except OSError: pass
                            thread = threading.Thread(target=forward, args=(self.request,target), daemon=True)
                            thread.start(); forward(target,self.request); thread.join(timeout=2)
                class Proxy(socketserver.ThreadingTCPServer):
                    daemon_threads = True
                proxy = Proxy(('127.0.0.1',0), Relay)
                threading.Thread(target=proxy.serve_forever, daemon=True).start()
                routed = {**connection, 'url':f'ws://127.0.0.1:{proxy.server_address[1]}'}
                with AuraClient(connection) as client:
                    sid = client.request('record', {'capture_location':'client'})['id']
                    wait(client,sid,'recording')
                    pcm = root/'input.pcm'; pcm.write_bytes(b'\xe8\x03' * 480 * 100)
                    init = dict(version=1, connection=routed, session_id=sid, sources=[],
                                directory=str(root/'spool'), input_pcm=str(pcm))
                    command = [helper()] if backend == 'rust' else [sys.executable, __file__, '--python-producer']
                    usage = root/'usage.json'
                    command = ['/usr/bin/time','-o',str(usage),'-f','{"user_cpu_seconds":%U,"system_cpu_seconds":%S,"peak_rss_kib":%M}',*command]
                    with (output/f'{backend}-events.jsonl').open('w') as events:
                        capture = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=events,stderr=subprocess.PIPE,text=True,
                                                   env={**os.environ,'AURA_DATA_DIR':str(root/'client')})
                        capture.stdin.write(json.dumps(init)+'\n'); capture.stdin.flush()
                        deadline = time.monotonic()+60
                        peak_pending = 0
                        while capture.poll() is None:
                            if time.monotonic()>deadline: raise RuntimeError('Producer watchdog expired')
                            if backend == 'rust':
                                spools = [root/'spool/frames.pcm']
                            else:
                                spools = list((root/'client/capture_sources').glob('**/.capture/mixed.pcm'))
                            produced = max((p.stat().st_size//960 for p in spools if p.exists()), default=0)
                            received = client.request('get',{'session_id':sid})['input_sequence']
                            peak_pending = max(peak_pending, produced-received)
                            time.sleep(.05)
                        error = capture.stderr.read()
                        if capture.returncode: raise RuntimeError(error)
                    s = wait(client,sid,'ready')
                    if s['samples'] != 480*100: raise RuntimeError(f'Lost/extra frames: {s["samples"]}')
                    rows.append(dict(backend=backend, **json.loads(usage.read_text()),
                                     input_frames=100, accepted_frames=s['input_sequence'], peak_pending_frames=peak_pending))
            finally:
                if capture:
                    if capture.poll() is None: capture.kill();capture.wait()
                    capture.stdin.close();capture.stderr.close()
                if proxy: proxy.shutdown();proxy.server_close()
                process.terminate();process.join(timeout=10)
                if process.is_alive():process.kill();process.join()
    report = dict(validation_mode='synthetic_capture_transport', runtime_validity='test_double',
                  asr_inference=False, emulated_rtt_ms=100, samples_per_frame=480, rows=rows,
                  limitation='One controlled workload per backend; excludes ASR performance and physical microphone acceptance.')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-producer',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.python_producer: python_producer()
    elif args.output: measure(args.output)
    else: parser.error('--output is required')
