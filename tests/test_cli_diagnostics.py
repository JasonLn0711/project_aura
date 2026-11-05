"""Doctor preserves server-side prerequisite diagnostics for remote clients."""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aura.cli import diagnostics


class DoctorTests(unittest.TestCase):
    def test_record_uses_saved_source_and_explicit_choice_wins(self):
        from aura.cli import execute, parser
        from contextlib import redirect_stdout
        import io
        for extra, expected in (([], 'system'), (['--source', 'microphone'], 'microphone')):
            def request(command, args=None):
                if command == 'preferences.get':
                    return {'capture_source': 'system'}
                if command == 'capabilities':
                    return {'audio_stream_v2': True}
                self.assertEqual(command, 'record')
                self.assertEqual(args['source'], expected)
                return {'id': 'test-recording'}
            client = SimpleNamespace(request=Mock(side_effect=request))
            with redirect_stdout(io.StringIO()):
                execute(client, parser().parse_args(['--json', 'record', '--detach', *extra]))

    def test_diarization_prerequisites_reach_operator(self):
        status = dict(default_enabled=True, interpreter_available=False,
                      runtime_probe='not_performed',
                      install='python3 scripts/setup_nemotron.py')
        client = SimpleNamespace(ssh='gpu-host', request=Mock(return_value={
            'diarization': status}))
        result = diagnostics(client)
        self.assertEqual(result['capabilities']['diarization'], status)
        client.request.assert_called_once_with('capabilities')

    def test_service_checks_interpreter_without_loading_model(self):
        from reuse_fixtures import SessionCore
        with tempfile.TemporaryDirectory() as root:
            core = SessionCore(root, executor=lambda *args: {})
            try:
                interpreter = Path(root) / 'nemotron-python'
                with patch('aura.diarization.nemotron.runtime_python', return_value=interpreter):
                    missing = core.request('capabilities')['diarization']
                    self.assertFalse(missing['interpreter_available'])
                    interpreter.touch()
                    present = core.request('capabilities')['diarization']
                    self.assertTrue(present['interpreter_available'])
                    self.assertEqual(present['runtime_probe'], 'not_performed')
            finally:
                core.close()
