"""Navigation exercises saved service state without opening devices or loading models."""
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from aura.cli import diagnostics, execute, main, parser
from aura.metadata import __version__
from aura.sdk import AuraClient
from aura.session_core import SessionCore
from aura.terminal import TerminalStatus


class SessionNavigationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = SessionCore(self.tmp.name, executor=lambda *args: {})
        self.client = AuraClient({'url': 'ws://unused', 'token': 'never-displayed'})
        self.client.request = Mock(side_effect=self.core.request)

    def tearDown(self):
        self.client.close()
        self.core.close()
        self.tmp.cleanup()

    def saved(self, state='ready', title='Meeting'):
        with self.core.lock:
            session = self.core._new({'title': title}, state)
            session['transcript'] = 'Saved transcript 中文'
            session['error'] = 'Requested capture sources are unavailable' if state == 'failed' else None
            self.core._save(session)
            return dict(session)

    def test_summaries_order_and_legacy_projection(self):
        first, second = self.saved(), self.saved()
        self.core.sessions[first['id']]['updated_at'] = '2099-01-01T00:00:00+00:00'
        rows = self.client.session_summaries()
        self.assertEqual([r['id'] for r in rows], [first['id'], second['id']])
        self.assertNotIn('transcript', rows[0])
        self.assertIn('transcript', self.core.request('sessions')[0])
        self.client.request.side_effect = lambda *args: self.core.request('sessions')
        self.assertNotIn('transcript', self.client.session_summaries()[0])

    def test_resolution_empty_full_prefix_and_ambiguity(self):
        with self.assertRaisesRegex(ValueError, 'No saved sessions'):
            self.client.resolve_session(last=True)
        row = self.saved()
        self.assertEqual(self.client.resolve_session(row['id'][:8])['id'], row['id'])
        self.assertEqual(self.client.resolve_session(row['id'])['id'], row['id'])
        with self.assertRaisesRegex(ValueError, 'Unknown session'):
            self.client.resolve_session('00000000')
        with self.assertRaisesRegex(ValueError, 'Choose a session ID'):
            self.client.resolve_session(row['id'], last=True)
        with self.assertRaisesRegex(ValueError, 'search titles'):
            self.client.resolve_session('Meeting')
        with patch.object(self.client, 'session_summaries', return_value=[{'id':'abc1'}, {'id':'abc2'}]):
            with self.assertRaisesRegex(ValueError, 'abc1, abc2'):
                self.client.resolve_session('abc')

    def test_reopening_every_state_is_read_only_and_json_is_clean(self):
        for state in ('ready', 'paused', 'recording', 'failed', 'recoverable'):
            with self.subTest(state=state):
                row = self.saved(state)
                output = io.StringIO()
                with patch('aura.cli.AuraClient', return_value=self.client), contextlib.redirect_stdout(output):
                    self.assertEqual(main(['--json', 'resume', row['id']]), 0)
                result = json.loads(output.getvalue())
                self.assertEqual(result['state'], state)
                self.assertEqual(result['transcript'], 'Saved transcript 中文')
                self.assertEqual(self.core.sessions[row['id']]['state'], state)
        self.assertTrue(all(call.args[0] == 'get' for call in self.client.request.call_args_list))

    def test_unpause_uses_existing_service_operation(self):
        row = self.saved('paused')
        with contextlib.redirect_stdout(io.StringIO()):
            execute(self.client, parser().parse_args(['unpause', row['id'][:8]]))
        self.assertEqual(self.core.sessions[row['id']]['state'], 'recording')
        with self.assertRaisesRegex(ValueError, 'paused session'):
            execute(self.client, parser().parse_args(['unpause', row['id']]))

    def test_picker_modes_nonterminal_and_selected_host(self):
        row = self.saved()
        for argv in (['resume'], ['resume', '--all'], ['--json', 'resume', '--all'], ['resume', '--last']):
            with self.subTest(argv=argv), patch('aura.cli.AuraClient', return_value=self.client) as factory, patch('aura.cli.sys.stdin.isatty', return_value=False), patch('aura.terminal.pick_session') as picker, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['--ssh', 'lab', *argv]), 0)
                self.assertIn(row['id'], output.getvalue())
                picker.assert_not_called()
                factory.assert_called_once_with(ssh='lab')
        self.assertTrue(all(c.args[0] in ('get', 'sessions') for c in self.client.request.call_args_list))

    def test_terminal_resume_passes_saved_snapshot(self):
        row = self.saved('failed')
        with patch('aura.cli.AuraClient', return_value=self.client), patch('aura.cli.sys.stdin.isatty', return_value=True), patch('aura.cli.sys.stdout.isatty', return_value=True), patch('aura.cli.interactive', return_value=0) as workspace:
            self.assertEqual(main(['--palette', 'sage', 'resume', '--last']), 0)
        self.assertEqual(workspace.call_args.kwargs['initial']['error'], row['error'])
        self.assertEqual(workspace.call_args.kwargs['palette'], 'sage')
        with patch('aura.cli.AuraClient', return_value=self.client), patch('aura.cli.sys.stdin.isatty', return_value=True), \
                patch('aura.cli.sys.stdout.isatty', return_value=True), patch('aura.terminal.pick_session', return_value=None) as picker:
            self.assertEqual(main(['--palette', 'sage', 'resume']), 0)
        self.assertEqual(picker.call_args.kwargs['palette'], 'sage')

    def test_diagnostics_current_old_mismatched_and_error_presentation(self):
        result = diagnostics(self.client)
        self.assertEqual(result['version_status'], 'matched')
        self.assertEqual(result['service_version'], __version__)
        self.assertIn('capture_log', result['diagnostics'])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            execute(self.client, parser().parse_args(['--ssh', 'lab', '--json', 'doctor']))
        self.assertEqual(json.loads(output.getvalue())['host'], 'lab')
        self.assertNotIn('never-displayed', json.dumps(result))
        for caps, expected in (({'protocol':1}, 'unknown'), ({'service_version':'0.1.0'}, 'mismatch')):
            self.client.request.side_effect = None
            self.client.request.return_value = caps
            self.assertEqual(diagnostics(self.client)['version_status'], expected)
        view = TerminalStatus()
        view.update(self.saved('failed'))
        rendered = '\n'.join(t for _, t in view.lines())
        self.assertIn('Requested capture sources are unavailable', rendered)
        self.assertNotIn('/pause', rendered)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            from aura.cli import inspect_session
            inspect_session(view.session)
        self.assertIn('Requested capture sources are unavailable', output.getvalue())
