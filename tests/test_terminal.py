import contextlib
import io
import json
import unittest
from unittest.mock import patch, MagicMock
from aura.cli import parser, main
from aura.terminal import TerminalStatus, graph, bar, safe_text


class TerminalTests(unittest.TestCase):
    def test_actual_metrics_bounded_graphs_and_narrow_layout(self):
        view = TerminalStatus()
        for i in range(100):
            view.update(dict(id='a', state='recording', samples=i*480, audio_level=.1,
                             work={'queued':2,'running':1,'done':3,'failed':0}))
        self.assertEqual(len(view.audio),60)
        self.assertEqual(len(view.queue),60)
        self.assertIn('2 pending',view.lines()[0][1])
        self.assertNotIn('%',' '.join(t for _,t in view.lines()))
        view.session['state']='draining'
        self.assertIn('50%', ' '.join(t for _,t in view.lines()))
        self.assertTrue(all(len(t)<30 for _,t in view.toolbar(30)))
        view.connected=False
        self.assertIn('Disconnected',view.lines()[0][1])
        self.assertNotIn('Audio',view.lines()[0][1])
        self.assertEqual(graph([]),'unavailable')
        self.assertIn('100%',bar(200,100))
        self.assertEqual(safe_text('\x1b[31m你好\x1b[0m'),'你好')

    def test_direct_record_and_legacy_flag(self):
        self.assertFalse(parser().parse_args(['record']).consent)
        self.assertTrue(parser().parse_args(['record','--consent']).consent)
        self.assertNotIn('--consent',parser().format_help())

    def test_json_mode_has_no_terminal_decoration(self):
        out=io.StringIO()
        with patch('aura.cli.AuraClient') as factory, contextlib.redirect_stdout(out):
            factory.return_value.__enter__.return_value.request.return_value=[]
            self.assertEqual(main(['--json']),0)
        self.assertEqual(json.loads(out.getvalue()),[])
        self.assertNotIn('\x1b',out.getvalue())

    def test_redirected_bare_command_does_not_start_service(self):
        with patch('aura.cli.sys.stdin.isatty',return_value=False), patch('aura.cli.AuraClient') as factory, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]),2)
            factory.assert_not_called()
