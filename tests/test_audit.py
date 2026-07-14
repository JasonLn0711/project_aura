import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

from aura.audit import (
    AuditRecorder,
    analyze_audit_events,
    read_audit_events,
    verify_audit_integrity,
    write_audit_report,
)


class AuditTests(unittest.TestCase):
    def test_recorder_redacts_sensitive_details_and_builds_valid_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AuditRecorder(tmpdir, session_id="session-1", retention_days=0)
            recorder.record(
                "recording.started",
                category="workflow.recording",
                actor="user",
                workflow="recording",
                details={
                    "capture_source": "microphone",
                    "transcript": "private meeting text",
                    "source_path": "/home/jason/private.wav",
                },
            )
            recorder.record(
                "recording.artifact_saved",
                category="workflow.recording",
                workflow="recording",
                details={"duration_ms": 1234},
            )

            events, issues = read_audit_events([tmpdir])

            self.assertEqual(issues, [])
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["details"]["capture_source"], "microphone")
            self.assertEqual(events[0]["details"]["transcript"], "[REDACTED]")
            self.assertEqual(events[0]["details"]["source_path"], "[REDACTED]")
            self.assertEqual(events[0]["sequence"], 1)
            self.assertEqual(events[1]["integrity"]["previous_event_hash"], events[0]["integrity"]["event_hash"])
            self.assertEqual(verify_audit_integrity(events), [])
            self.assertEqual(Path(events[0]["_source_path"]).stat().st_mode & 0o777, 0o600)

    def test_integrity_verifier_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AuditRecorder(tmpdir, session_id="session-1", retention_days=0)
            recorder.record("app.session_started", category="app.lifecycle", workflow="app")
            events, _ = read_audit_events([tmpdir])
            events[0]["outcome"] = "error"

            issues = verify_audit_integrity(events)

            self.assertIn("event_hash_mismatch", {issue["kind"] for issue in issues})

    def test_analysis_flags_error_burst_repeated_action_and_incomplete_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AuditRecorder(tmpdir, session_id="session-1", retention_days=0)
            start = dt.datetime(2026, 7, 14, 18, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))
            recorder.record("app.session_started", category="app.lifecycle", occurred_at=start)
            recorder.record(
                "recording.started",
                category="workflow.recording",
                actor="user",
                workflow="recording",
                occurred_at=start + dt.timedelta(seconds=1),
            )
            for index in range(5):
                recorder.record(
                    "ui.settings_toggled",
                    category="ui.interaction",
                    actor="user",
                    occurred_at=start + dt.timedelta(seconds=10 + index),
                )
            for index in range(3):
                recorder.record(
                    "model.load_failed",
                    category="system.runtime",
                    workflow="diagnostics",
                    outcome="error",
                    severity="error",
                    occurred_at=start + dt.timedelta(seconds=30 + index),
                )
            recorder.record(
                "app.session_ended",
                category="app.lifecycle",
                occurred_at=start + dt.timedelta(seconds=60),
            )
            events, read_issues = read_audit_events([tmpdir])

            report = analyze_audit_events(events, read_issues)
            anomaly_kinds = {anomaly["kind"] for anomaly in report["anomalies"]}

            self.assertTrue(report["kpis"]["audit_integrity_pass"])
            self.assertIn("error_burst", anomaly_kinds)
            self.assertIn("repeated_action", anomaly_kinds)
            self.assertIn("incomplete_workflow", anomaly_kinds)

    def test_reader_keeps_malformed_line_as_audit_issue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit-2026-07-14.jsonl"
            path.write_text('{"schema_version":"1.0"}\nnot-json\n', encoding="utf-8")

            events, issues = read_audit_events([tmpdir])

            self.assertEqual(len(events), 1)
            self.assertEqual(issues[0]["kind"], "parse_failure")
            self.assertEqual(issues[0]["line"], 2)

    def test_retention_prunes_expired_daily_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = Path(tmpdir) / "audit-2020-01-01.jsonl"
            old_path.write_text("{}\n", encoding="utf-8")
            old_timestamp = (dt.datetime.now() - dt.timedelta(days=10)).timestamp()
            os.utime(old_path, (old_timestamp, old_timestamp))

            AuditRecorder(tmpdir, retention_days=1)

            self.assertFalse(old_path.exists())

    def test_report_writer_creates_human_readable_local_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AuditRecorder(tmpdir, session_id="session-1", retention_days=0)
            recorder.record("app.session_started", category="app.lifecycle")
            output = Path(tmpdir) / "report.md"

            path, report = write_audit_report(tmpdir, output)

            self.assertEqual(path, output)
            self.assertEqual(report["event_count"], 1)
            text = output.read_text(encoding="utf-8")
            self.assertIn("Project AURA 本機稽核摘要", text)
            self.assertIn("Integrity：`PASS`", text)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_active_session_is_not_flagged_as_uncontrolled_termination(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AuditRecorder(tmpdir, session_id="active-session", retention_days=0)
            recorder.record("app.session_started", category="app.lifecycle")
            events, read_issues = read_audit_events([tmpdir])

            active_report = analyze_audit_events(
                events,
                read_issues,
                active_session_id=recorder.session_id,
            )
            closed_report = analyze_audit_events(events, read_issues)

            self.assertNotIn(
                "uncontrolled_termination_candidate",
                {anomaly["kind"] for anomaly in active_report["anomalies"]},
            )
            self.assertIn(
                "uncontrolled_termination_candidate",
                {anomaly["kind"] for anomaly in closed_report["anomalies"]},
            )


if __name__ == "__main__":
    unittest.main()
