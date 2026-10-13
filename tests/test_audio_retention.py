import contextlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

from aura.audio.cleanup import cleanup_manifest, cleanup_service_sessions, main, service_lock
from aura.audio.recording_session import RecordingSession, write_session_manifest
from aura.audio.retention import complete_recording_m4a, prepare_recording_m4a, recording_audio_plan, validate_m4a


def recording(directory, *, seconds=0.2):
    session = RecordingSession.start(directory, recording_name='meeting', capture_mode='system_microphone',
                                     sample_rate=16000, sample_width=2)
    session.append_pcm({name: b'\x01\x00' * int(16000 * seconds) for name in ('mixed', 'system', 'microphone')})
    session.finalize(keep_pcm=True)
    return Path(directory) / 'session.json'


class AudioRetentionTests(unittest.TestCase):
    def test_preview_is_read_only_and_apply_removes_only_registered_audio(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            manifest = recording(directory)
            (directory / 'meeting.mp3').write_bytes(b'legacy duplicate')
            (directory / 'meeting_system.m4a').write_bytes(b'legacy separate track')
            unrelated = directory / 'imported.wav'
            unrelated.write_bytes(b'original source')
            transcript = directory / 'transcript.txt'
            transcript.write_text('Human edits\n')
            (directory / 'segments.json').write_text(json.dumps({'segments': [], 'audio_path': str(directory / 'meeting.wav')}))
            before = manifest.read_bytes()
            preview = cleanup_manifest(manifest)
            self.assertEqual(preview['status'], 'preview')
            self.assertEqual(manifest.read_bytes(), before)
            self.assertFalse((directory / 'meeting.m4a').exists())
            result = cleanup_manifest(manifest, apply=True)
            self.assertEqual(result['status'], 'cleaned', result)
            self.assertEqual(len(result['deleted']), 8)
            self.assertTrue(unrelated.exists())
            self.assertEqual(transcript.read_text(), 'Human edits\n')
            self.assertEqual(json.loads(manifest.read_text())['audio_tracks'], {'mixed': 'meeting.m4a'})
            self.assertEqual(json.loads((directory / 'segments.json').read_text())['audio_path'], result['retained'])
            repeated = cleanup_manifest(manifest, apply=True)
            self.assertEqual(repeated['status'], 'cleaned')
            self.assertEqual(repeated['released_bytes'], 0)

    def test_m4a_layout_mismatch_preserves_sources(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = recording(root)
            output = prepare_recording_m4a(manifest)
            stereo = Path(root) / 'stereo.wav'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i',
                            str(Path(root) / 'meeting.wav'), '-ac', '2', str(stereo)],
                           check=True)
            with self.assertRaisesRegex(ValueError, 'track layout'):
                validate_m4a(output, stereo)
            self.assertTrue((Path(root) / 'meeting.wav').exists())

    def test_export_failure_keeps_all_sources_and_removes_temporary_output(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = recording(root)
            before = manifest.read_bytes()
            def fail(source, target_dbfs, audio_format, **kwargs):
                kwargs['output_path'].write_bytes(b'incomplete export')
                raise RuntimeError('encoder failed')
            with patch('aura.audio.export.normalize_wav_to_recording_audio', side_effect=fail):
                result = cleanup_manifest(manifest, apply=True)
            self.assertEqual(result['status'], 'skipped')
            self.assertEqual(manifest.read_bytes(), before)
            self.assertEqual(len(list(Path(root).glob('*.wav'))), 3)
            self.assertFalse(list(Path(root).glob('*.m4a')))

    def test_corrupt_or_wrong_length_existing_m4a_preserves_sources(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            manifest = recording(root)
            output = Path(root) / 'meeting.m4a'
            output.write_bytes(b'broken')
            self.assertEqual(cleanup_manifest(manifest, apply=True)['status'], 'skipped')
            self.assertEqual(output.read_bytes(), b'broken')
            other_manifest = recording(other, seconds=1.0)
            other_output = prepare_recording_m4a(other_manifest)
            output.write_bytes(other_output.read_bytes())
            result = cleanup_manifest(manifest, apply=True)
            self.assertEqual(result['status'], 'skipped')
            self.assertIn('duration', result['reason'])
            self.assertEqual(len(list(Path(root).glob('*.wav'))), 3)

    def test_decode_failure_does_not_remove_sources(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = recording(root)
            prepare_recording_m4a(manifest)
            run = subprocess.run
            def reject_decode(command, **kwargs):
                if '-xerror' in command:
                    raise subprocess.CalledProcessError(1, command)
                return run(command, **kwargs)
            with patch('aura.audio.retention.subprocess.run', side_effect=reject_decode):
                result = cleanup_manifest(manifest, apply=True)
            self.assertEqual(result['status'], 'skipped')
            self.assertEqual(len(list(Path(root).glob('*.wav'))), 3)

    def test_persistence_failure_and_partial_deletion_are_retryable(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = recording(root)
            output = prepare_recording_m4a(manifest)
            with self.assertRaisesRegex(OSError, 'database full'):
                complete_recording_m4a(manifest, output, persist=lambda _: (_ for _ in ()).throw(OSError('database full')))
            self.assertEqual(len(list(Path(root).glob('*.wav'))), 3)
            self.assertTrue(json.loads(manifest.read_text())['audio_cleanup_pending'])
            unlink = Path.unlink
            def fail_one(path, *args, **kwargs):
                if path.name == 'meeting_system.wav':
                    raise OSError('file busy')
                return unlink(path, *args, **kwargs)
            with patch.object(Path, 'unlink', fail_one):
                result = cleanup_manifest(manifest, apply=True)
            self.assertEqual(result['status'], 'incomplete')
            self.assertGreater(result['released_bytes'], 0)
            self.assertTrue(result['deleted'])
            self.assertTrue(output.exists())
            self.assertTrue(json.loads(manifest.read_text())['audio_cleanup_pending'])
            self.assertEqual(cleanup_manifest(manifest, apply=True)['status'], 'cleaned')
            self.assertFalse(list(Path(root).rglob('*.wav')))
            self.assertFalse(list(Path(root).rglob('*.pcm')))

    def test_unsafe_paths_and_unfinished_or_imported_sessions_are_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = recording(root)
            original = json.loads(manifest.read_text())
            for update in ({'status': 'recording'}, {'status': 'failed'}, {'workflow': 'import'},
                           {'audio_tracks': {'mixed': '../outside.wav'}},
                           {'audio_tracks': {'mixed': '/tmp/outside.wav'}},
                           {'audio_tracks': {'mixed': 'missing.wav'}}):
                with self.subTest(update=update):
                    write_session_manifest(manifest, {**original, **update})
                    self.assertEqual(cleanup_manifest(manifest, apply=True)['status'], 'skipped')
                    self.assertEqual(len(list(Path(root).glob('*.wav'))), 3)

    def test_symlinked_track_or_session_is_rejected(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            manifest = recording(root)
            source = Path(root) / 'meeting.wav'
            source.unlink()
            source.symlink_to(Path(other) / 'outside.wav')
            self.assertEqual(cleanup_manifest(manifest, apply=True)['status'], 'skipped')
            linked = Path(other) / 'linked'
            linked.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                recording_audio_plan(linked / 'session.json')

    def test_offline_service_migration_updates_database_before_deletion(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            sid = str(uuid.uuid4())
            manifest = recording(directory / 'sessions' / sid)
            session = dict(id=sid, state='ready', options={'audio_format': 'mp3'},
                           artifacts={'wav': str(manifest.parent / 'meeting.wav')})
            with contextlib.closing(sqlite3.connect(directory / 'sessions.sqlite3')) as db:
                db.executescript('CREATE TABLE sessions(id TEXT, data TEXT); CREATE TABLE jobs(session TEXT, state TEXT, kind TEXT); '
                                 'CREATE TABLE events(session TEXT, data TEXT); CREATE TABLE commands(command TEXT, result TEXT);')
                db.execute('INSERT INTO sessions VALUES (?,?)', (sid, json.dumps(session)))
                db.commit()
            unlink = Path.unlink
            def check_database_before_delete(path, *args, **kwargs):
                if path.suffix in ('.wav', '.pcm'):
                    with contextlib.closing(sqlite3.connect(directory / 'sessions.sqlite3')) as db:
                        snapshot = json.loads(db.execute('SELECT data FROM sessions').fetchone()[0])
                    self.assertNotIn('wav', snapshot['artifacts'])
                    self.assertTrue(Path(snapshot['artifacts']['m4a']).exists())
                return unlink(path, *args, **kwargs)
            with service_lock(directory), patch.object(Path, 'unlink', check_database_before_delete):
                results = list(cleanup_service_sessions(directory, apply=True))
            self.assertEqual(results[0]['status'], 'cleaned', results)
            with contextlib.closing(sqlite3.connect(directory / 'sessions.sqlite3')) as db:
                saved = json.loads(db.execute('SELECT data FROM sessions').fetchone()[0])
            self.assertNotIn('wav', saved['artifacts'])
            self.assertEqual(saved['options']['audio_format'], 'm4a')
            self.assertTrue(Path(saved['artifacts']['m4a']).is_file())

    def test_running_service_blocks_apply(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / 'sessions.sqlite3').touch()
            with service_lock(directory), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(['--data-root', root, '--apply']), 1)
            self.assertIn('AURA service is running', out.getvalue())

    def test_service_migration_skips_active_imported_and_pending_sessions(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            sid = str(uuid.uuid4())
            manifest = recording(directory / 'sessions' / sid)
            base = dict(id=sid, state='ready', options={}, artifacts={})
            with contextlib.closing(sqlite3.connect(directory / 'sessions.sqlite3')) as db:
                db.executescript('CREATE TABLE sessions(id TEXT, data TEXT); CREATE TABLE jobs(session TEXT, state TEXT, kind TEXT);')
                for update in ({'state': 'recording'}, {'state': 'recoverable'}, {'source_path': '/external/import.wav'},
                               {'producer_connected': True}, {'asr_issues': [{'status': 'pending'}]}):
                    db.execute('DELETE FROM sessions')
                    db.execute('INSERT INTO sessions VALUES (?,?)', (sid, json.dumps({**base, **update})))
                    db.commit()
                    with patch('aura.audio.cleanup.cleanup_manifest') as cleanup:
                        result = list(cleanup_service_sessions(directory, apply=True))
                        self.assertEqual(result[0]['status'], 'skipped')
                        cleanup.assert_not_called()
                db.execute('UPDATE sessions SET data=?', (json.dumps(base),))
                db.execute('INSERT INTO jobs VALUES (?, ?, ?)', (sid, 'failed', 'chunk'))
                db.commit()
                self.assertEqual(list(cleanup_service_sessions(directory, apply=True))[0]['status'], 'skipped')
            self.assertTrue((manifest.parent / 'meeting.wav').exists())


if __name__ == '__main__':
    unittest.main()
