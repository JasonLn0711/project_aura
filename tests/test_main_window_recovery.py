import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from aura.ui.main_window import MainWindow


class MainWindowRecoveryTests(unittest.TestCase):
    def test_selected_session_outside_cwd_uses_explicit_recovery_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            window = SimpleNamespace(sys_status=MagicMock(), audit=MagicMock())
            manifest_path = Path(tmpdir) / "custom" / "meeting_session" / "session.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps({"recording_outcome": "partial"}),
                encoding="utf-8",
            )

            with (
                patch(
                    "aura.ui.main_window.QFileDialog.getOpenFileName",
                    return_value=(str(manifest_path), "Aura session"),
                ),
                patch(
                    "aura.ui.main_window.recover_recording_session",
                    return_value={"mixed": manifest_path.parent / "meeting.wav"},
                ) as recover,
            ):
                MainWindow.select_recording_for_recovery(window)

            recover.assert_called_once_with(manifest_path)
            window.sys_status.setText.assert_called_once_with(
                f"部分錄音音訊已復原：{manifest_path.parent}；"
                "請先覆核可用範圍，再使用「匯入媒體」選取復原的 WAV"
            )
            window.audit.record.assert_called_once()


if __name__ == "__main__":
    unittest.main()
