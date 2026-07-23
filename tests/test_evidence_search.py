import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from aura.evidence_search import EvidenceSearch, main, rebuild_evidence_index


def write_session(root: Path) -> Path:
    session_dir = root / "meeting-001_session"
    session_dir.mkdir()
    (session_dir / "audio").mkdir()
    (session_dir / "audio" / "mixed.wav").touch()
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "meeting_id": "meeting-001",
                "title": "AURA 產品會議",
                "status": "ready",
                "started_at": "2026-07-23T09:00:00+08:00",
                "audio_tracks": {"mixed": "audio/mixed.wav"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (session_dir / "segments.json").write_text(
        json.dumps(
            {
                "meeting_id": "meeting-001",
                "segments": [
                    {
                        "segment_id": "seg-001",
                        "start_ms": 1_250,
                        "end_ms": 4_500,
                        "text": "智德萬確認本機部署方案",
                        "speaker": "Jason",
                        "state": "confirmed",
                        "revision": 2,
                    },
                    {
                        "segment_id": "seg-002",
                        "start_ms": 4_500,
                        "end_ms": 8_000,
                        "text": "下一步整理驗收清單",
                        "speaker": "現場人員",
                        "state": "final",
                        "revision": 1,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (session_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "meeting_id": "meeting-001",
                "summary": {
                    "meeting_topic": "本機部署與驗收",
                    "action_items": [
                        {
                            "task": "整理驗收清單",
                            "owner": "Jason",
                            "deadline": "2026-07-30",
                        },
                        {"task": "直接寄出會議通知"},
                    ],
                },
                "claims": [
                    {
                        "claim_id": "action-001",
                        "field": "action_items",
                        "text": "整理驗收清單",
                        "source_segment_ids": ["seg-002"],
                        "support_status": "supported",
                        "review_status": "unreviewed",
                    },
                    {
                        "claim_id": "action-002",
                        "field": "action_items",
                        "text": "直接寄出會議通知",
                        "source_segment_ids": [],
                        "support_status": "unsupported",
                        "review_status": "rejected",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (session_dir / "review_events.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-07-23T09:30:00+08:00",
                "event": "claim.confirmed",
                "claim_id": "action-001",
                "changes": {
                    "review_status": {
                        "from": "unreviewed",
                        "to": "confirmed",
                    }
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return session_dir


class EvidenceSearchTests(unittest.TestCase):
    def test_rebuilt_index_finds_traditional_chinese_segment_with_source_coordinates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_session(root)
            index_path = root / "evidence.sqlite3"

            stats = rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                results = evidence.search_segments("智德萬")

        self.assertEqual(stats.segment_count, 2)
        self.assertEqual(
            results,
            [
                {
                    "meeting_id": "meeting-001",
                    "segment_id": "seg-001",
                    "start_ms": 1_250,
                    "end_ms": 4_500,
                    "text": "智德萬確認本機部署方案",
                    "speaker": "Jason",
                    "state": "confirmed",
                    "revision": 2,
                    "session_path": str((root / "meeting-001_session" / "session.json").resolve()),
                }
            ],
        )

    def test_search_meetings_finds_summary_content_and_returns_session_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            index_path = root / "evidence.sqlite3"
            rebuild_evidence_index(root, index_path)

            with EvidenceSearch(index_path) as evidence:
                results = evidence.search_meetings("本機部署")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["meeting_id"], "meeting-001")
        self.assertEqual(results[0]["title"], "AURA 產品會議")
        self.assertEqual(results[0]["status"], "ready")
        self.assertEqual(results[0]["session_path"], str((session_dir / "session.json").resolve()))
        self.assertIn("本機部署", results[0]["matched_text"])

    def test_open_audio_span_returns_read_only_track_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            index_path = root / "evidence.sqlite3"
            rebuild_evidence_index(root, index_path)

            with EvidenceSearch(index_path) as evidence:
                span = evidence.open_audio_span(
                    meeting_id="meeting-001",
                    start_ms=1_250,
                    end_ms=4_500,
                    track="mixed",
                )

        self.assertEqual(
            span,
            {
                "meeting_id": "meeting-001",
                "track": "mixed",
                "path": str((session_dir / "audio" / "mixed.wav").resolve()),
                "start_ms": 1_250,
                "end_ms": 4_500,
                "duration_ms": 3_250,
                "exists": True,
            },
        )

    def test_imported_source_audio_is_available_as_the_default_track(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            audio_path = root / "source.wav"
            audio_path.touch()
            session_dir = root / "import_session"
            session_dir.mkdir()
            (session_dir / "session.json").write_text(
                json.dumps(
                    {
                        "meeting_id": "import-001",
                        "status": "ready",
                        "workflow": "import",
                        "source_path": str(audio_path),
                        "started_at": "",
                        "ended_at": "",
                        "audio_tracks": {},
                    }
                ),
                encoding="utf-8",
            )
            (session_dir / "segments.json").write_text(
                json.dumps(
                    {
                        "meeting_id": "import-001",
                        "audio_path": str(audio_path),
                        "segments": [
                            {
                                "segment_id": "seg-1",
                                "start_ms": 0,
                                "end_ms": 1000,
                                "text": "內容",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            index_path = root / "evidence.sqlite3"

            rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                span = evidence.open_audio_span("import-001", 0, 1000)

        self.assertEqual(span["path"], str(audio_path.resolve()))
        self.assertTrue(span["exists"])

    def test_get_confirmed_actions_excludes_unreviewed_or_unsupported_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            index_path = root / "evidence.sqlite3"

            stats = rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                actions = evidence.get_confirmed_actions()

        self.assertEqual(stats.action_count, 2)
        self.assertEqual(
            actions,
            [
                {
                    "meeting_id": "meeting-001",
                    "action_id": "action-001",
                    "task": "整理驗收清單",
                    "owner": "Jason",
                    "deadline": "2026-07-30",
                    "source_segment_ids": ["seg-002"],
                    "support_status": "supported",
                    "review_status": "confirmed",
                    "summary_path": str((session_dir / "summary.json").resolve()),
                }
            ],
        )

    def test_summary_status_alone_cannot_create_a_confirmed_action(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            (session_dir / "review_events.jsonl").unlink()
            summary_path = session_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["claims"][0]["review_status"] = "confirmed"
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False), encoding="utf-8"
            )
            index_path = root / "evidence.sqlite3"

            rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                actions = evidence.get_confirmed_actions()

        self.assertEqual(actions, [])

    def test_confirmed_action_requires_a_canonical_source_segment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            summary_path = session_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["claims"][0]["source_segment_ids"] = ["seg-missing"]
            summary["claims"][0]["support_status"] = "supported"
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False),
                encoding="utf-8",
            )
            index_path = root / "evidence.sqlite3"

            rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                actions = evidence.get_confirmed_actions()

        self.assertEqual(actions, [])

    def test_edited_action_requires_human_reconfirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            with (session_dir / "review_events.jsonl").open(
                "a", encoding="utf-8"
            ) as target:
                target.write(
                    json.dumps(
                        {
                            "timestamp": "2026-07-23T10:00:00+08:00",
                            "event": "claim.edited",
                            "claim_id": "action-001",
                            "changes": {
                                "text": {
                                    "from": "整理驗收清單",
                                    "to": "整理並覆核驗收清單",
                                },
                                "review_status": {
                                    "from": "confirmed",
                                    "to": "edited",
                                },
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            index_path = root / "evidence.sqlite3"

            rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                actions = evidence.get_confirmed_actions()

        self.assertEqual(actions, [])

    def test_invalidated_summary_cannot_publish_previously_confirmed_actions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            manifest_path = session_dir / "session.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.pop("title")
            manifest["summary_status"] = "invalidated"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
            summary_path = session_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["summary"]["meeting_topic"] = "量子香蕉議程"
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False),
                encoding="utf-8",
            )
            index_path = root / "evidence.sqlite3"

            rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                actions = evidence.get_confirmed_actions()
                stale_summary_results = evidence.search_meetings("量子香蕉")
                current_transcript_results = evidence.search_meetings("智德萬")

        self.assertEqual(actions, [])
        self.assertEqual(stale_summary_results, [])
        self.assertEqual(
            [result["meeting_id"] for result in current_transcript_results],
            ["meeting-001"],
        )

    def test_summary_hash_must_match_the_current_transcript_before_indexing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            manifest_path = session_dir / "session.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["transcript_sha256"] = "current-transcript"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            summary_path = session_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["transcript_sha256"] = "stale-transcript"
            summary["summary"]["meeting_topic"] = "火星鳳梨議程"
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False),
                encoding="utf-8",
            )
            index_path = root / "evidence.sqlite3"

            rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                actions = evidence.get_confirmed_actions()
                stale_summary_results = evidence.search_meetings("火星鳳梨")
                current_transcript_results = evidence.search_meetings("智德萬")

        self.assertEqual(actions, [])
        self.assertEqual(stale_summary_results, [])
        self.assertEqual(len(current_transcript_results), 1)

    def test_duplicate_action_text_keeps_each_items_owner_and_deadline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            summary_path = session_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["summary"]["action_items"] = [
                {
                    "task": "發送通知",
                    "owner": "Jason",
                    "deadline": "2026-07-30",
                },
                {
                    "task": "發送通知",
                    "owner": "Ada",
                    "deadline": "2026-07-31",
                },
            ]
            summary["claims"] = [
                {
                    "claim_id": "action-001",
                    "field": "action_items",
                    "text": "發送通知",
                    "source_segment_ids": ["seg-001"],
                    "support_status": "supported",
                },
                {
                    "claim_id": "action-002",
                    "field": "action_items",
                    "text": "發送通知",
                    "source_segment_ids": ["seg-002"],
                    "support_status": "supported",
                },
            ]
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False),
                encoding="utf-8",
            )
            (session_dir / "review_events.jsonl").write_text(
                "\n".join(
                    json.dumps(
                        {
                            "event": "claim.confirmed",
                            "claim_id": claim_id,
                            "changes": {
                                "review_status": {
                                    "from": "unreviewed",
                                    "to": "confirmed",
                                }
                            },
                        },
                        ensure_ascii=False,
                    )
                    for claim_id in ("action-001", "action-002")
                )
                + "\n",
                encoding="utf-8",
            )
            index_path = root / "evidence.sqlite3"

            rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                actions = evidence.get_confirmed_actions()

        self.assertEqual(
            [
                (action["action_id"], action["owner"], action["deadline"])
                for action in actions
            ],
            [
                ("action-001", "Jason", "2026-07-30"),
                ("action-002", "Ada", "2026-07-31"),
            ],
        )

    def test_rebuild_refuses_to_overwrite_a_canonical_json_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            manifest_path = session_dir / "session.json"
            original = manifest_path.read_bytes()

            with self.assertRaisesRegex(ValueError, "SQLite"):
                rebuild_evidence_index(root, manifest_path)

            self.assertEqual(manifest_path.read_bytes(), original)

    def test_cli_search_segments_prints_json_from_read_only_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_session(root)
            index_path = root / "evidence.sqlite3"
            rebuild_evidence_index(root, index_path)
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main(["search-segments", str(index_path), "智德萬"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload[0]["segment_id"], "seg-001")

    def test_search_segments_supports_short_chinese_queries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_session(root)
            index_path = root / "evidence.sqlite3"
            rebuild_evidence_index(root, index_path)

            with EvidenceSearch(index_path) as evidence:
                results = evidence.search_segments("驗收")

        self.assertEqual([result["segment_id"] for result in results], ["seg-002"])

    def test_short_meeting_search_returns_a_bounded_matching_excerpt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_session(root)
            index_path = root / "evidence.sqlite3"
            rebuild_evidence_index(root, index_path)

            with EvidenceSearch(index_path) as evidence:
                matched_text = evidence.search_meetings("驗收")[0]["matched_text"]

        self.assertIn("驗收", matched_text)
        self.assertLessEqual(len(matched_text), 120)

    def test_claim_review_event_updates_confirmed_action_without_rewriting_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            summary_path = session_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["claims"][0]["review_status"] = "unreviewed"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
            (session_dir / "review_events.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": "2026-07-23T10:00:00+08:00",
                        "event": "claim.confirmed",
                        "claim_id": "action-001",
                        "revision": 1,
                        "changes": {
                            "text": {
                                "from": "整理驗收清單",
                                "to": "整理並覆核驗收清單",
                            },
                            "review_status": {
                                "from": "unreviewed",
                                "to": "confirmed",
                            }
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            index_path = root / "evidence.sqlite3"

            rebuild_evidence_index(root, index_path)
            with EvidenceSearch(index_path) as evidence:
                actions = evidence.get_confirmed_actions("meeting-001")

        self.assertEqual([action["action_id"] for action in actions], ["action-001"])
        self.assertEqual(actions[0]["task"], "整理並覆核驗收清單")

    def test_rebuild_rejects_audio_track_paths_outside_the_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            session_path = session_dir / "session.json"
            session = json.loads(session_path.read_text(encoding="utf-8"))
            session["audio_tracks"]["mixed"] = "../../outside.wav"
            session_path.write_text(json.dumps(session), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "escapes its session directory"):
                rebuild_evidence_index(root, root / "evidence.sqlite3")

    def test_rebuild_rejects_invalid_segment_time_ranges(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = write_session(root)
            segments_path = session_dir / "segments.json"
            segments = json.loads(segments_path.read_text(encoding="utf-8"))
            segments["segments"][0]["end_ms"] = 1_000
            segments_path.write_text(json.dumps(segments), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "invalid timestamp range"):
                rebuild_evidence_index(root, root / "evidence.sqlite3")


if __name__ == "__main__":
    unittest.main()
