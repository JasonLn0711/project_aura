"""Output discovery uses existing service metadata and preserves capture state."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from aura.cli import execute, interactive, parser
from aura.sdk import AuraClient

SID = '00000000-0000-4000-8000-000000000001'


class FilesTests(unittest.TestCase):
    def test_discovery_and_selection_use_existing_read_only_requests(self):
        client = AuraClient.__new__(AuraClient)
        client.ssh = None
        session = dict(id=SID, title='Meeting', state='recording', transcript='private text',
                       updated_at='2026-09-10T01:00:00+00:00',
                       artifacts={'live.txt': f'/custom root/sessions/{SID}/live.txt'})
        def request(command, args=None):
            return {'sessions': [session], 'get': session,
                    'capabilities': {'diagnostics': {'data_dir': '/custom root'}}}[command]
        client.request = MagicMock(side_effect=request)
        for selection in ([], ['--last'], [SID[:8]], [SID]):
            with self.subTest(selection=selection), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(execute(client, parser().parse_args(['--json', 'files', *selection])), 0)
                result = json.loads(out.getvalue())
                self.assertEqual(result['session_id'], SID)
                self.assertEqual(result['directory'], f'/custom root/sessions/{SID}')
                self.assertEqual(result['artifacts'], session['artifacts'])
                self.assertEqual(result['state'], 'recording')
                self.assertNotIn('private text', out.getvalue())
        self.assertEqual({call.args[0] for call in client.request.call_args_list}, {'sessions', 'get', 'capabilities'})
        with self.assertRaisesRegex(ValueError, 'Choose a session ID or --last'):
            execute(client, parser().parse_args(['files', SID, '--last']))
        client.request.side_effect = lambda *_: []
        with self.assertRaisesRegex(ValueError, 'No saved sessions'):
            execute(client, parser().parse_args(['files']))

    def test_files_open_and_remote_or_missing_folder_errors(self):
        client = MagicMock(ssh=None)
        client.resolve_session.return_value = dict(id=SID, title='Meeting', state='ready', artifacts={})
        with tempfile.TemporaryDirectory(prefix='aura files ') as root:
            folder = Path(root) / 'sessions' / SID
            folder.mkdir(parents=True)
            client.request.return_value = {'diagnostics': {'data_dir': root}}
            with patch('aura.cli.sys.platform', 'linux'), patch('aura.cli.subprocess.run') as opener, contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(execute(client, parser().parse_args(['files', '--open'])), 0)
                self.assertIn('No output files registered yet', out.getvalue())
                self.assertEqual(opener.call_args.args[0], ['xdg-open', str(folder)])
                opener.side_effect = subprocess.CalledProcessError(3, ['xdg-open'])
                with self.assertRaisesRegex(RuntimeError, 'Could not open a file manager'):
                    execute(client, parser().parse_args(['files', '--open']))
            with patch('aura.cli.subprocess.run') as opener, contextlib.redirect_stdout(io.StringIO()):
                # Interactive workers share the tunnel connection but receive SSH identity via args.
                with self.assertRaisesRegex(ValueError, 'SSH host'):
                    execute(client, parser().parse_args(['--ssh', 'gpu-host', 'files', '--open']))
                opener.assert_not_called()
            client.request.return_value = {}
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(execute(client, parser().parse_args(['files'])), 0)
                self.assertIn('unavailable from this service', out.getvalue())
                with self.assertRaisesRegex(ValueError, 'unavailable locally'):
                    execute(client, parser().parse_args(['files', '--open']))
            client.request.return_value = {'diagnostics': {'data_dir': r'C:\Aura Data'}}
            with contextlib.redirect_stdout(io.StringIO()) as out:
                execute(client, parser().parse_args(['--json', '--ssh', 'windows-host', 'files']))
                self.assertEqual(json.loads(out.getvalue())['directory'], f'C:\\Aura Data\\sessions\\{SID}')

    def test_interactive_files_selection_last_and_delete_dispatch(self):
        client = MagicMock(ssh=None)
        client.request.return_value = {}
        completed = threading.Event()
        completed.set()
        commands = iter(['/files --open', '/files --last', '/files 1234', f'/delete {SID}', '/quit'])
        def prompt(_):
            self.assertTrue(completed.wait(2), 'Workspace command did not complete')
            completed.clear()
            return next(commands)
        received = []
        def run(_client, args, **_):
            received.append(args)
            completed.set()
            return 0
        with patch('aura.cli.AuraClient') as factory, patch('prompt_toolkit.PromptSession') as prompts, \
                patch('prompt_toolkit.patch_stdout.patch_stdout', side_effect=contextlib.nullcontext), \
                patch('prompt_toolkit.print_formatted_text'), patch('aura.cli.execute', side_effect=run), \
                contextlib.redirect_stdout(io.StringIO()):
            factory.return_value.__enter__.return_value.request.return_value = dict(id=SID, title='Meeting', state='ready', transcript='')
            prompts.return_value.prompt.side_effect = prompt
            interactive(client, ssh='gpu-host', initial=dict(id=SID, state='ready', transcript=''))
        self.assertEqual([args.command for args in received], ['files', 'files', 'files', 'delete'])
        self.assertEqual([args.session_id for args in received], [SID, None, '1234', SID])
        self.assertTrue(received[0].open)
        self.assertTrue(received[1].last)
        self.assertTrue(all(args.ssh == 'gpu-host' for args in received))

    def test_export_reports_absolute_destination(self):
        client = MagicMock()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            execute(client, parser().parse_args(['--json', 'export', SID, '--output', 'meeting.txt']))
            self.assertEqual(json.loads(out.getvalue())['export'], str(Path('meeting.txt').resolve()))
        client.download.assert_called_once_with(SID, 'txt', Path('meeting.txt'), on_progress=None)
