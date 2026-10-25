"""Negotiated durable audio transport. All operations hold the core's lock."""
import json
import uuid

from aura.audio.recording_session import RecordingSession, write_session_manifest

FRAME_BYTES = 960
PACKET_FRAMES = 4
WINDOW_FRAMES = 32


def snapshot(s):
    return {k: s.get(k) for k in ('id', 'state', 'source', 'stop_at', 'input_sequence',
                                  'producer_connected', 'error', 'stream', 'enhancement', 'delivery_committed')}


def open_stream(core, sid, producer_id, tracks):
    if str(uuid.UUID(producer_id)) != producer_id:
        raise ValueError('Invalid producer ID')
    with core.changed:
        s = core._get(sid)
        old = s.get('stream')
        if old and (old['producer_id'] != producer_id or old['tracks'] != tracks):
            raise ValueError('Session belongs to another capture producer or track layout')
        if not old and (s['state'] != 'recording' or s['producer_connected']):
            raise ValueError('Session is not accepting a capture producer')
        if s['state'] not in ('recording', 'pausing', 'paused', 'stopping', 'recoverable', 'draining', 'exporting', 'ready'):
            raise ValueError('Session no longer accepts capture reconnection')
        # After process interruption, reconcile the common complete PCM prefix.
        manifest_path = core.directory(sid) / 'session.json'
        if old and s['state'] == 'recoverable' and sid not in core.recordings and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            journals = [core.directory(sid) / '.capture' / (t + '.pcm') for t in tracks]
            if not all(p.is_file() for p in journals):
                raise RuntimeError('Capture journals are unavailable; recover the saved session')
            frames = min(p.stat().st_size // FRAME_BYTES for p in journals)
            for p in journals:
                with p.open('r+b') as f:
                    f.truncate(frames * FRAME_BYTES)
            s.update(samples=frames * 480, input_sequence=frames)
            if s['options'].get('profile') != 'reuse-v1':
                core._recover_unqueued_audio(s, journals[tracks.index('mixed')])
            manifest['status'] = 'recording'
            write_session_manifest(manifest_path, manifest)
            core.recordings[sid] = RecordingSession(core.directory(sid), manifest)
        if s['state'] == 'recoverable':
            s['state'] = s.pop('interrupted_state', 'recording')
            if s['state'] not in ('recording', 'pausing', 'paused', 'stopping'):
                raise ValueError('Use explicit recovery for this interrupted operation')
            s['error'] = None
            if s['options'].get('diarization') and sid not in core.diarizers:
                s['diarization'] = dict(state='recovering', active=[], processed_sample=0)
        generation = uuid.uuid4().hex
        s['stream'] = dict(version=2, producer_id=producer_id, generation=generation,
                           tracks=tracks, durable_sequence=s['input_sequence'])
        s['producer_connected'] = True
        if s['options'].get('profile') == 'reuse-v1' and s['state'] in ('recording', 'pausing', 'paused', 'stopping') and s['samples']:
            core._start_enhancer(s)
        s.pop('warning', None)
        core.producers.add(sid)
        core._save(s)
        return snapshot(s)


def validate_owner(s, generation):
    if s.get('stream', {}).get('generation') != generation:
        raise ValueError('This capture connection has been superseded')


def ingest_packet(core, sid, generation, sequence, pcm, tracks):
    with core.changed:
        s = core._get(sid)
        validate_owner(s, generation)
        width = FRAME_BYTES * len(tracks)
        if not width or len(pcm) % width or not 1 <= len(pcm) // width <= PACKET_FRAMES:
            raise ValueError('Audio packet requires 1–4 complete PCM frames')
        if tracks != s['stream']['tracks'] or sequence > s['input_sequence']:
            raise ValueError('Audio sequence or track layout mismatch')
        for i in range(len(pcm) // width):
            index = sequence + i
            frame = pcm[i * width:(i + 1) * width]
            if index < s['input_sequence']:
                rec = core.recordings.get(sid)
                if rec:
                    rec._flush()
                for j, track in enumerate(tracks):
                    with (core.directory(sid) / '.capture' / (track + '.pcm')).open('rb') as f:
                        f.seek(index * FRAME_BYTES)
                        if f.read(FRAME_BYTES) != frame[j * FRAME_BYTES:(j + 1) * FRAME_BYTES]:
                            raise ValueError('Conflicting replay of accepted audio')
            else:
                core.ingest(sid, index, frame, tracks)
        if sid in core.recordings:
            core.recordings[sid].checkpoint()
        s['stream']['durable_sequence'] = s['input_sequence']
        core.db.execute('INSERT OR REPLACE INTO stream_cursors VALUES (?,?)', (sid, s['input_sequence']))
        core.db.commit()
        return dict(state=s['state'], input_sequence=s['input_sequence'],
                    durable_sequence=s['input_sequence'])


def finish(core, sid, generation, sequence, action):
    with core.changed:
        s = core._get(sid)
        validate_owner(s, generation)
        if sequence != s['input_sequence']:
            raise ValueError('Capture must deliver its final sequence before acknowledgement')
        if action not in ('pause', 'stop'):
            raise ValueError('Unknown capture boundary')
        if action == 'stop':
            if s['state'] not in ('stopping', 'draining', 'exporting', 'ready'):
                core._request('stop', {'session_id': sid})
            if s['state'] == 'stopping':
                core._request('producer.stopped', {'session_id': sid})
        elif s['state'] != 'paused':
            if s['state'] != 'pausing':
                core._request('pause', {'session_id': sid})
            core._request('producer.paused', {'session_id': sid})
        return snapshot(s)
