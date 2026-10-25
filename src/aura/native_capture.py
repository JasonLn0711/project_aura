"""Small Python supervisor for the Rust client; no audio or inference imports."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from aura.sdk import AuraClient, connection_file


def helper():
    candidates = [os.environ.get('AURA_CAPTURE_BINARY'),
                  str(Path(sys.executable).parent / 'aura-capture'), shutil.which('aura-capture'),
                  str(Path(__file__).resolve().parents[2] / 'native/aura-capture/target/release/aura-capture')]
    for path in candidates:
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return path
    raise RuntimeError('Rust capture helper is missing. Run make install-capture, or explicitly select --capture-backend python.')


def preflight(mode=None):
    binary = helper()
    info = json.loads(subprocess.check_output([binary, '--version'], text=True, timeout=10))
    if info.get('audio_stream_version') != 2:
        raise RuntimeError('Capture helper is incompatible; run make install-capture')
    for command in ('pactl', 'parec'):
        if not shutil.which(command):
            raise RuntimeError(f'{command} is required for Linux capture; install pulseaudio-utils and enable PulseAudio/PipeWire.')
    if mode is not None:
        sources(mode)
    return binary


def sources(mode):
    def pactl(*args):
        return subprocess.check_output(['pactl', *args], text=True, timeout=10).strip()
    rows = json.loads(pactl('-f', 'json', 'list', 'sources'))
    microphone = pactl('get-default-source') if mode in ('microphone', 'system_microphone') else ''
    monitor = pactl('get-default-sink') + '.monitor' if mode in ('system', 'system_microphone') else ''
    names = {s['name'] for s in rows}
    if microphone.endswith('.monitor'):
        microphone = next((s['name'] for s in rows if not s['name'].endswith('.monitor')), '')
    selected = []
    if mode in ('system', 'system_microphone'):
        selected.append(dict(name=monitor, track='system'))
    if mode in ('microphone', 'system_microphone'):
        selected.append(dict(name=microphone, track='microphone'))
    if not selected:
        raise RuntimeError(f'Unknown capture source: {mode}')
    if mode in ('microphone', 'system_microphone') and microphone not in names:
        raise RuntimeError('No microphone is available. Connect or enable a microphone, or use /record --source system to capture desktop audio only.')
    if mode in ('system', 'system_microphone') and monitor not in names:
        raise RuntimeError('The default output has no system-audio monitor. Enable an audio output, or use /record --source microphone.')
    return selected


def capture(session_id, ssh=None, *, input_pcm=None, connection=None):
    binary = helper() if input_pcm else preflight()
    client = AuraClient(connection=connection, ssh=ssh)
    process = None
    try:
        while True:
            session = client.request('get', {'session_id': session_id})
            if session['state'] != 'starting':
                break
            time.sleep(.1)
        if not client.request('capabilities').get('audio_stream_v2'):
            raise RuntimeError('The running service lacks Rust capture support. Finish active work, then restart the service from the updated installation.')
        directory = connection_file().parent / 'capture_sources' / session_id / 'native'
        init = dict(version=1, connection=client.connection, session_id=session_id,
                    directory=str(directory), sources=[] if input_pcm else sources(session['source']))
        if input_pcm:
            init['input_pcm'] = str(Path(input_pcm).resolve())
        if session.get('stop_at'):
            end = datetime.datetime.fromisoformat(session['stop_at'])
            init['stop_after_ms'] = max(0, int((end - datetime.datetime.now(datetime.timezone.utc)).total_seconds() * 1000))
        process = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        process.stdin.write(json.dumps(init) + '\n')
        process.stdin.flush()
        last_renewal = 0.0
        for line in process.stdout:
            event = json.loads(line)
            # Never display or persist initialization messages or connection credentials.
            print(json.dumps(event), flush=True)
            if event.get('event') == 'reconnecting' and time.monotonic() - last_renewal >= 5:
                last_renewal = time.monotonic()
                replacement = None
                try:
                    replacement = AuraClient(ssh=ssh) if connection is None else AuraClient(connection=connection)
                    replacement.request('capabilities')
                    previous, client = client, replacement
                    process.stdin.write(json.dumps(client.connection) + '\n')
                    process.stdin.flush()
                    previous.close()
                except Exception:
                    if replacement is not None and replacement is not client:
                        replacement.close()
                    pass  # Native capture continues spooling while the service is unreachable.
        if process.wait() != 0:
            raise RuntimeError(f'Native capture stopped; preserved audio: {directory}')
    except Exception as exc:
        try:
            client.request('capture.failed', {'session_id': session_id, 'error': str(exc)})
        except Exception:
            pass
        raise
    finally:
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdin.close()
            process.stdout.close()
        client.close()
