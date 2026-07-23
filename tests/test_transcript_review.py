import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import aura.review as review_module
from aura.asr.threads import FileTranscriberThread
from aura.review import (
    CONFIRMED,
    FINAL,
    ReviewSegment,
    TranscriptReview,
    export_segments,
    parse_transcript_lines,
)


class TranscriptReviewTests(unittest.TestCase):
    def test_parse_transcript_lines_creates_stable_timed_segments(self):
        lines = [
            "[00:00:01] SPEAKER_00: 第一段",
            "[00:00:04] 第二段",
        ]

        first = parse_transcript_lines(lines)
        second = parse_transcript_lines(lines)

        self.assertEqual(
            [(item.start_ms, item.end_ms, item.speaker, item.text) for item in first],
            [
                (1000, 4000, "SPEAKER_00", "第一段"),
                (4000, 4000, "SPEAKER_UNKNOWN", "第二段"),
            ],
        )
        self.assertEqual([item.segment_id for item in first], [item.segment_id for item in second])
        self.assertTrue(all(item.state == FINAL for item in first))

    def test_parse_transcript_lines_preserves_explicit_segment_id(self):
        segments = parse_transcript_lines(
            ["[00:00:01] [seg-source-001] SPEAKER_00: 有來源的內容"]
        )

        self.assertEqual(segments[0].segment_id, "seg-source-001")
        self.assertEqual(segments[0].speaker, "SPEAKER_00")
        self.assertEqual(segments[0].text, "有來源的內容")

    def test_review_edit_preserves_segment_id_and_records_revision(self):
        review = TranscriptReview(
            [
                ReviewSegment(
                    segment_id="seg-1",
                    start_ms=1000,
                    end_ms=2500,
                    text="原始文字",
                    speaker="SPEAKER_UNKNOWN",
                    state=FINAL,
                )
            ]
        )

        edited = review.edit("seg-1", text="校訂文字", speaker="王小明")
        confirmed = review.confirm("seg-1")

        self.assertEqual(edited.segment_id, "seg-1")
        self.assertEqual(confirmed.revision, 2)
        self.assertEqual(confirmed.state, CONFIRMED)
        self.assertEqual(len(review.events), 2)
        self.assertEqual(review.events[0]["changes"]["text"], {"from": "原始文字", "to": "校訂文字"})

    def test_speaker_rename_updates_every_matching_segment_in_session(self):
        review = TranscriptReview(
            [
                ReviewSegment("seg-1", 0, 1000, "一", speaker="SPEAKER_00", state=FINAL),
                ReviewSegment("seg-2", 1000, 2000, "二", speaker="SPEAKER_01", state=FINAL),
                ReviewSegment("seg-3", 2000, 3000, "三", speaker="SPEAKER_00", state=FINAL),
            ]
        )

        changed = review.rename_speaker("SPEAKER_00", "王小明")

        self.assertEqual(changed, 2)
        self.assertEqual(
            [segment.speaker for segment in review.segments],
            ["王小明", "SPEAKER_01", "王小明"],
        )
        self.assertEqual([review.segments[0].revision, review.segments[2].revision], [1, 1])

    def test_save_and_load_keeps_segments_and_append_only_review_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            review = TranscriptReview(
                [
                    ReviewSegment(
                        segment_id="seg-1",
                        start_ms=0,
                        end_ms=1500,
                        text="待確認",
                        state=FINAL,
                    )
                ]
            )
            review.confirm("seg-1")
            base_path = Path(tmpdir) / "meeting"

            paths = review.save(base_path, meeting_id="meeting-123", audio_path="meeting.wav")
            loaded = TranscriptReview.load(base_path)

            self.assertEqual(loaded.segments, review.segments)
            payload = json.loads(paths["segments"].read_text(encoding="utf-8"))
            self.assertEqual(payload["meeting_id"], "meeting-123")
            self.assertEqual(payload["audio_path"], "meeting.wav")
            event_lines = paths["review_events"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(event_lines), 1)
            self.assertEqual(json.loads(event_lines[0])["segment_id"], "seg-1")

    def test_existing_session_directory_uses_canonical_artifact_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "session"
            session_dir.mkdir()
            review = TranscriptReview(
                [ReviewSegment("seg-1", 0, 1000, "內容", state=FINAL)]
            )

            paths = review.save(session_dir, meeting_id="meeting-123")

            self.assertEqual(paths["segments"], session_dir / "segments.json")
            self.assertEqual(paths["review_events"], session_dir / "review_events.jsonl")
            self.assertEqual(TranscriptReview.load(session_dir).segments, review.segments)

    def test_editing_saved_transcript_invalidates_existing_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "meeting_session"
            session_dir.mkdir()
            (session_dir / "session.json").write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-123",
                        "status": "ready",
                        "summary_status": "valid",
                    }
                ),
                encoding="utf-8",
            )
            (session_dir / "summary.json").write_text("{}", encoding="utf-8")
            review = TranscriptReview(
                [ReviewSegment("seg-1", 0, 1000, "原文", state=CONFIRMED)]
            )
            review.save(session_dir, meeting_id="meeting-123")

            review.edit("seg-1", text="修正文")
            review.save(session_dir, meeting_id="meeting-123")

            manifest = json.loads(
                (session_dir / "session.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["summary_status"], "invalidated")
            self.assertEqual(manifest["summary_invalidation_reason"], "segment.edited")

    def test_event_write_failure_leaves_edited_segments_with_invalidated_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "meeting_session"
            session_dir.mkdir()
            manifest_path = session_dir / "session.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-123",
                        "status": "ready",
                        "summary_status": "valid",
                    }
                ),
                encoding="utf-8",
            )
            (session_dir / "summary.json").write_text("{}", encoding="utf-8")
            review = TranscriptReview(
                [ReviewSegment("seg-1", 0, 1000, "原文", state=CONFIRMED)]
            )
            review.save(session_dir, meeting_id="meeting-123")
            review.edit("seg-1", text="修正文")
            atomic_write = review_module._atomic_write

            def fail_review_event(path, text):
                if Path(path).name == "review_events.jsonl":
                    raise OSError("disk full")
                return atomic_write(path, text)

            with patch(
                "aura.review._atomic_write",
                side_effect=fail_review_event,
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    review.save(session_dir, meeting_id="meeting-123")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            segments = json.loads(
                (session_dir / "segments.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["summary_status"], "invalidated")
            self.assertEqual(segments["segments"][0]["text"], "修正文")

    def test_invalidation_write_failure_preserves_old_segments_and_valid_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "meeting_session"
            session_dir.mkdir()
            manifest_path = session_dir / "session.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "meeting_id": "meeting-123",
                        "status": "ready",
                        "summary_status": "valid",
                    }
                ),
                encoding="utf-8",
            )
            (session_dir / "summary.json").write_text("{}", encoding="utf-8")
            review = TranscriptReview(
                [ReviewSegment("seg-1", 0, 1000, "原文", state=CONFIRMED)]
            )
            review.save(session_dir, meeting_id="meeting-123")
            review.edit("seg-1", text="修正文")

            with patch(
                "aura.review.write_session_manifest",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    review.save(session_dir, meeting_id="meeting-123")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            segments = json.loads(
                (session_dir / "segments.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["summary_status"], "valid")
            self.assertEqual(segments["segments"][0]["text"], "原文")

    def test_exports_json_markdown_srt_and_vtt_from_same_segments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            segment = ReviewSegment(
                segment_id="seg-1",
                start_ms=1000,
                end_ms=2500,
                text="確認內容",
                speaker="王小明",
                state=CONFIRMED,
            )

            paths = export_segments([segment], Path(tmpdir) / "meeting")

            self.assertIn('"segment_id": "seg-1"', paths["json"].read_text(encoding="utf-8"))
            self.assertIn("王小明：確認內容", paths["markdown"].read_text(encoding="utf-8"))
            self.assertIn("00:00:01,000 --> 00:00:02,500", paths["srt"].read_text(encoding="utf-8"))
            self.assertIn("WEBVTT", paths["vtt"].read_text(encoding="utf-8"))

    def test_dotted_export_base_keeps_full_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = export_segments(
                [ReviewSegment("seg-1", 0, 1000, "內容", state=FINAL)],
                Path(tmpdir) / "meeting.v1_review",
            )

            self.assertEqual(
                paths["json"],
                Path(tmpdir) / "meeting.v1_review.json",
            )

    def test_file_transcriber_thread_exposes_structured_segments(self):
        segment = ReviewSegment(
            segment_id="seg-1",
            start_ms=1000,
            end_ms=2500,
            text="內容",
            state=FINAL,
        )
        thread = FileTranscriberThread(model=object(), file_path="meeting.wav")

        with patch(
            "aura.asr.threads.transcribe_file",
            return_value=SimpleNamespace(lines=["[00:00:01] 內容"], segments=[segment]),
        ):
            thread.run()

        self.assertEqual(thread.result_segments, [segment])


if __name__ == "__main__":
    unittest.main()
