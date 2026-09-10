import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch, MagicMock
from aura.cli import parser, main
from aura.terminal import (TerminalStatus, graph, bar, safe_text, welcome, picker_rows,
                           unicode_terminal, terminal_color_depth, terminal_style, garden_rows, GARDEN)


class TerminalTests(unittest.TestCase):
    def test_help_lists_each_workspace_command_with_english_description(self):
        from aura.cli import interactive
        client = MagicMock(ssh=None)
        client.request.return_value = {}
        with patch('aura.cli.AuraClient'), patch('prompt_toolkit.PromptSession') as prompts, \
                patch('prompt_toolkit.patch_stdout.patch_stdout', side_effect=contextlib.nullcontext), \
                patch('prompt_toolkit.print_formatted_text'), patch('aura.cli.execute') as execute, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            prompts.return_value.prompt.side_effect = ['/help', '/quit']
            self.assertEqual(interactive(client), 0)
        rows = [line for line in out.getvalue().splitlines() if line.startswith('/')]
        completer = prompts.call_args.kwargs['completer']
        self.assertEqual([row.split()[0] for row in rows], completer.commands)
        for row in rows:
            self.assertEqual(row.count('/'), 1)
            self.assertRegex(row[21:], r'^[A-Z][A-Za-z ,;]+$')
        self.assertIn('/graphs on|off', out.getvalue())
        self.assertIn('/animations on|off', out.getvalue())
        execute.assert_not_called()

    def test_actual_metrics_bounded_graphs_and_narrow_layout(self):
        view = TerminalStatus()
        for i in range(100):
            view.update(dict(id='a', state='recording', samples=i*480, audio_level=.1,
                             work={'queued':2,'running':1,'done':3,'failed':0}))
        self.assertEqual(len(view.audio),60)
        self.assertEqual(len(view.queue),60)
        self.assertIn('2 pending', ' '.join(t for _, t in view.lines()))
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

    def test_record_stop_at_forwarding_and_old_service_guard(self):
        from aura.cli import execute
        client = MagicMock()
        args = parser().parse_args(["record", "--stop-at", "2099-01-01T19:00:00+08:00", "--detach"])
        client.request.return_value = {}
        with self.assertRaisesRegex(RuntimeError, "restart the service"):
            execute(client, args)
        client.request.assert_called_once_with("capabilities")
        client.reset_mock()
        client.request.return_value = {"record_stop_at": True}
        with patch("aura.cli.show"):
            execute(client, args)
        self.assertEqual(client.request.call_args.args[0], "record")
        self.assertEqual(client.request.call_args.args[1]["stop_at"], args.stop_at)

    def test_segmentation_flags_reach_shared_service(self):
        from aura.cli import execute
        for command, extra in (("record", []), ("schedule", ["--start-at", "2027-01-01T09:00:00+08:00",
                                                            "--stop-at", "2027-01-01T10:00:00+08:00"])):
            client = MagicMock()
            args = parser().parse_args([command, *extra, "--segmentation", "fixed",
                                       "--max-segment-seconds", "12", "--silence-ms", "800", "--detach"])
            with patch("aura.cli.show"):
                execute(client, args)
            self.assertEqual(client.request.call_args.args[1]["options"],
                dict(live_segmentation="fixed", live_max_segment_len_sec=12, live_silence_ms=800))

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

    def test_stdout_redirect_does_not_open_interactive_workspace(self):
        with patch('aura.cli.sys.stdin.isatty', return_value=True), patch('aura.cli.sys.stdout.isatty', return_value=False), \
                patch('aura.cli.AuraClient') as factory, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 2)
            factory.assert_not_called()

    def test_garden_layout_encoding_and_color_fallback(self):
        report = {'service_version': '1.18.0', 'version_status': 'matched'}
        with patch('aura.terminal.unicode_terminal', return_value=True):
            wide = ''.join(t for _, t in welcome('AURA test', 'local', report, size=(80, 30)))
            small = ''.join(t for _, t in welcome('AURA test', 'local', report, size=(79, 30)))
            self.assertEqual(wide.count('AURA test'), 1)
            self.assertIn(')))', wide)
            self.assertIn('/model    Choose an ASR model', wide)
            self.assertIn('▁▁▂▁▁▁▂▁▁▁▂▃▅▃▂▁▁▂▁▁▁▂▁▁▂▁▁▁▂▁▁▁▂▁▁▁▂▁▁▂▃▅▃▂▁▂▁', wide)
            self.assertNotIn(')))', small)
            self.assertIn('o v o', small)
        with patch.dict(os.environ, {'TERM': 'dumb', 'NO_COLOR': '1'}):
            self.assertFalse(unicode_terminal())
            text = ''.join(t for _, t in welcome('AURA test', 'local', report, size=(80, 30)))
            self.assertTrue(text.isascii())
            self.assertEqual(terminal_color_depth().value, 'DEPTH_1_BIT')
        with patch('aura.terminal.sys.stdout') as stream:
            stream.encoding = 'ascii'
            self.assertFalse(unicode_terminal())

    def test_palettes_override_framework_reverse_and_preserve_art(self):
        from prompt_toolkit.styles import default_ui_style, merge_styles
        self.assertEqual('\n'.join(''.join(t for _, t in row) for row in garden_rows()), GARDEN)
        colors = []
        for palette in ('slate', 'sage'):
            style = merge_styles([default_ui_style(), terminal_style(palette)])
            colors.append(style.get_attrs_for_style_str('class:owl').color)
            for token in ('class:muted', 'class:owl', 'class:shadow', 'class:heading', 'class:error', ''):
                attrs = style.get_attrs_for_style_str('class:bottom-toolbar class:bottom-toolbar.text ' + token)
                self.assertFalse(attrs.reverse)
                self.assertIn(attrs.bgcolor, ('', 'default'))
            self.assertEqual(style.get_attrs_for_style_str('class:muted').color, 'default')
            self.assertTrue(style.get_attrs_for_style_str('class:error').bold)
            self.assertFalse(style.get_attrs_for_style_str('class:completion-menu.completion.current').reverse)
            self.assertFalse(style.get_attrs_for_style_str('class:completion-menu.meta.completion.current').reverse)
            art_colors = {style.get_attrs_for_style_str(token).color for row in garden_rows() for token, text in row if text.strip()}
            self.assertGreaterEqual(len(art_colors), 5)
        self.assertNotEqual(*colors)
        self.assertEqual(parser().parse_args([]).palette, 'slate')
        with patch('aura.cli.AuraClient') as client, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(['--palette', 'unknown'])
            self.assertEqual(error.exception.code, 2)
            client.assert_not_called()

    def test_animation_states_freeze_and_warning_priority(self):
        view = TerminalStatus()
        session = dict(id='a', state='recording', samples=16000, work={'queued': 2, 'running': 1, 'done': 0})
        def render(at):
            with patch('aura.terminal.time.monotonic', return_value=at):
                return ''.join(t for _, t in view.toolbar(100, 30))
        with patch('aura.terminal.unicode_terminal', return_value=True), patch.dict(os.environ, {'TERM': 'xterm'}):
            view.update(session)
            self.assertNotEqual(render(1), render(1.5))
            view.animations = False
            self.assertEqual(render(1), render(1.5))
            view.animations = True
            with patch('aura.terminal.time.monotonic', return_value=10):
                view.update({**session, 'state': 'ready'})
            self.assertNotEqual(render(10.5), render(12))
            self.assertIn('^ v ^', render(12))
            view.update({**session, 'state': 'paused'})
            self.assertIn('- v -', render(12))
            self.assertEqual(render(12), render(12.5))
            view.update({**session, 'state': 'ready', 'asr_issues': [{'status': 'pending'}]})
            view.progress(1, 2)
            self.assertIn('! v !', render(12))
            self.assertIn('transcription gaps', render(12))
            self.assertNotIn('^ v ^', render(12))
            self.assertNotIn('(^.^)', ''.join(t for _, t in view.toolbar(40, 12)))
            view.connected = False
            view.error = 'Connection lost'
            text = render(12)
            self.assertIn('Disconnected', text)
            self.assertNotIn('Audio', text)
            self.assertEqual(text, render(12.5))

    def test_cell_width_short_picker_and_untrusted_titles(self):
        from prompt_toolkit.utils import get_cwidth
        view = TerminalStatus()
        view.update(dict(id='a', state='failed', samples=0, error='裝置無法使用'))
        rows = [dict(id=str(i), state='ready', title='中文\x1b[31m meeting') for i in range(12)]
        with patch('aura.terminal.unicode_terminal', return_value=True):
            for width, height in ((100, 30), (80, 24), (60, 20), (40, 12), (30, 8)):
                for fragments in (view.toolbar(width, height), picker_rows(rows, '', 0, width, height)):
                    text = ''.join(t for _, t in fragments)
                    self.assertNotIn('\x1b', text)
                    self.assertTrue(all(get_cwidth(line) < width for line in text.splitlines()), text)
            short = ''.join(t for _, t in picker_rows(rows, '', 5, 80, 10))
            self.assertEqual(len(short.splitlines()), 5)
            self.assertIn('> 5', short)
            self.assertIn('0 matching', ''.join(t for _, t in picker_rows(rows, 'missing', 0, 80, 10)))
