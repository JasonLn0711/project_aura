import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from aura.cli import execute, parser
from aura.session_core import ACTIVE, SessionCore


class SessionDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = SessionCore(self.tmp.name, executor=lambda *_: {})
        self.s = self.core._new({}, "ready")
        self.sid = self.s["id"]
        self.directory = self.core.directory(self.sid)
        (self.directory / "audio.wav").write_bytes(b"audio")

    def tearDown(self):
        self.core.close()
        self.tmp.cleanup()

    def test_preview_confirmation_and_complete_cleanup_preserves_external_files(self):
        original = Path(self.tmp.name) / "original.wav"
        original.write_bytes(b"original")
        self.s["source_path"] = str(original)
        self.core._save(self.s)
        self.core.db.execute("INSERT INTO commands VALUES (?,?,?)", ("cached", "get", json.dumps(self.s)))
        self.core.db.commit()
        preview = self.core.request("delete.preview", {"session_id": self.sid})
        self.assertIn("outside", preview["retains"])
        self.assertTrue(self.directory.exists())
        with self.assertRaises(ValueError):
            self.core.request("delete", {"session_id": self.sid, "confirm": "wrong"})
        self.core.request("delete", dict(session_id=self.sid, confirm=self.sid))
        self.assertFalse(self.directory.exists())
        self.assertEqual(original.read_bytes(), b"original")
        self.assertEqual(self.core.request("sessions"), [])
        self.assertEqual(self.core.events(self.sid), [])
        self.assertEqual(self.core.db.execute("SELECT count(*) FROM commands").fetchone()[0], 0)
        self.core.close()
        self.core = SessionCore(self.tmp.name, executor=lambda *_: {})
        self.assertEqual(self.core.request("sessions"), [])

    def test_busy_sessions_and_running_jobs_cannot_be_deleted(self):
        for state in ACTIVE | {"scheduled"}:
            self.s["state"] = state
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.core.request("delete", dict(session_id=self.sid, confirm=self.sid))
        self.s["state"] = "failed"
        self.s["producer_connected"] = True
        with self.assertRaises(ValueError):
            self.core.request("delete.preview", dict(session_id=self.sid))
        self.s["producer_connected"] = False
        self.core.db.execute("INSERT INTO jobs(session,kind,payload,state) VALUES (?,?,?,?)",
                             (self.sid, "chunk", "{}", "running"))
        self.core.db.commit()
        with self.assertRaisesRegex(ValueError, "still running"):
            self.core.request("delete", dict(session_id=self.sid, confirm=self.sid))
        self.assertTrue(self.directory.exists())

    def test_file_failure_is_retryable_after_restart_and_cancels_queued_work(self):
        self.s["state"] = "failed"
        with self.core.changed:
            self.core._job(self.s, "chunk")
        with patch("shutil.rmtree", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                self.core.request("delete", dict(session_id=self.sid, confirm=self.sid))
        self.assertEqual(self.s["state"], "deleting")
        self.core.close()
        self.core = SessionCore(self.tmp.name, executor=lambda *_: self.fail("Deleted jobs must not execute"))
        self.assertEqual(self.core.request("get", dict(session_id=self.sid))["state"], "deleting")
        self.core.request("delete", dict(session_id=self.sid, confirm=self.sid))
        self.assertEqual(self.core.db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)

    def test_cli_preview_confirmation_and_old_service(self):
        client = MagicMock()
        client.resolve_session.return_value = self.s
        client.request.return_value = {"session_delete": True}
        with contextlib.redirect_stdout(io.StringIO()):
            execute(client, parser().parse_args(["delete", self.sid]))
            self.assertEqual(client.request.call_args.args[0], "delete.preview")
            execute(client, parser().parse_args(["delete", self.sid, "--confirm", self.sid]))
            self.assertEqual(client.request.call_args.args, ("delete", dict(session_id=self.sid, confirm=self.sid)))
        client.reset_mock()
        client.request.return_value = {}
        with self.assertRaisesRegex(RuntimeError, "restart"):
            execute(client, parser().parse_args(["delete", self.sid, "--confirm", self.sid]))
        client.resolve_session.assert_not_called()

    def test_database_failure_keeps_retryable_session(self):
        import sqlite3
        self.core.db.execute("CREATE TEMP TRIGGER block_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT, 'locked'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.core.request("delete", dict(session_id=self.sid, confirm=self.sid))
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.core.request("get", dict(session_id=self.sid))["state"], "deleting")
        self.core.db.execute("DROP TRIGGER block_delete")
        self.core.request("delete", dict(session_id=self.sid, confirm=self.sid))
        self.assertEqual(self.core.request("sessions"), [])

    def test_symlink_cannot_redirect_deletion(self):
        outside = Path(self.tmp.name) / "outside"
        self.directory.rename(outside)
        try:
            self.directory.symlink_to(outside, target_is_directory=True)
        except OSError:
            outside.rename(self.directory)
            self.skipTest("Directory symlinks unavailable on this platform")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.core.request("delete", dict(session_id=self.sid, confirm=self.sid))
        self.assertEqual((outside / "audio.wav").read_bytes(), b"audio")
