import json
import unittest
from unittest.mock import patch

from aura.native_capture import sources


class NativeSourceTests(unittest.TestCase):
    def pactl(self, rows, default_source='hdmi.monitor', default_sink='hdmi'):
        def run(command, **kwargs):
            if command[-1] == 'sources':
                return json.dumps(rows)
            if command[-1] == 'get-default-source':
                return default_source
            if command[-1] == 'get-default-sink':
                return default_sink
            raise AssertionError(command)
        return patch('aura.native_capture.subprocess.check_output', side_effect=run)

    def test_system_capture_without_microphone(self):
        with self.pactl([{'name': 'hdmi.monitor'}]) as run:
            self.assertEqual(sources('system'), [{'name':'hdmi.monitor', 'track':'system'}])
            self.assertFalse(any(c.args[0][-1] == 'get-default-source' for c in run.call_args_list))

    def test_combined_capture_reports_missing_microphone(self):
        with self.pactl([{'name': 'hdmi.monitor'}]):
            with self.assertRaisesRegex(RuntimeError, '/record --source system'):
                sources('system_microphone')

    def test_microphone_capture_does_not_require_output(self):
        with self.pactl([{'name': 'usb-mic'}], default_source='usb-mic') as run:
            self.assertEqual(sources('microphone'), [{'name':'usb-mic','track':'microphone'}])
            self.assertFalse(any(c.args[0][-1] == 'get-default-sink' for c in run.call_args_list))

    def test_monitor_default_falls_back_to_real_microphone(self):
        with self.pactl([{'name':'hdmi.monitor'}, {'name':'usb-mic'}]):
            self.assertEqual(sources('system_microphone'), [
                {'name':'hdmi.monitor','track':'system'}, {'name':'usb-mic','track':'microphone'}])

    def test_missing_server_device_rejects_before_creating_session(self):
        import tempfile
        from reuse_fixtures import SessionCore
        with tempfile.TemporaryDirectory() as root:
            core = SessionCore(root, executor=lambda *args: {})
            try:
                with patch('aura.native_capture.preflight', side_effect=RuntimeError('No microphone')) as check:
                    with self.assertRaisesRegex(RuntimeError, 'No microphone'):
                        core.request('record', {'capture_backend':'rust', 'source':'system_microphone'})
                    check.assert_called_once_with('system_microphone')
                    self.assertEqual(core.sessions, {})
            finally:
                core.close()
