import argparse
import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import TracebackType


@dataclass(frozen=True)
class IndexStats:
    meeting_count: int
    segment_count: int
    action_count: int


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot index {path}: {exc}") from exc


def _segments(payload) -> list[dict]:
    rows = payload.get("segments", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("segments.json must contain a list or a segments list")
    return [row for row in rows if isinstance(row, dict)]


def _text_values(value):
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            yield cleaned
    elif isinstance(value, dict):
        for item in value.values():
            yield from _text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _text_values(item)


def _fts_phrase(query: str) -> str:
    text = query.strip()
    if not text:
        raise ValueError("query must not be empty")
    return f'"{text.replace(chr(34), chr(34) * 2)}"'


def _literal_like(query: str) -> str:
    text = query.strip()
    if not text:
        raise ValueError("query must not be empty")
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _matched_excerpt(content: str, query: str, limit: int = 120) -> str:
    if len(content) <= limit:
        return content
    match_at = content.casefold().find(query.strip().casefold())
    start = max(0, match_at - limit // 3) if match_at >= 0 else 0
    end = min(len(content), start + limit)
    start = max(0, end - limit)
    excerpt = content[start:end]
    if start:
        excerpt = "…" + excerpt[1:]
    if end < len(content):
        excerpt = excerpt[:-1] + "…"
    return excerpt


def _audio_tracks(
    session: dict,
    session_dir: Path,
    segments_payload: dict | list | None = None,
) -> dict[str, str]:
    tracks = session.get("audio_tracks") or {}
    if not isinstance(tracks, dict):
        return {}
    session_root = session_dir.resolve()
    resolved = {}
    for name, value in tracks.items():
        path_value = value.get("path") if isinstance(value, dict) else value
        if not path_value:
            continue
        path = Path(str(path_value)).expanduser()
        if not path.is_absolute():
            path = session_dir / path
        path = path.resolve()
        try:
            path.relative_to(session_root)
        except ValueError as exc:
            raise ValueError(f"Audio track path escapes its session directory: {path_value}") from exc
        resolved[str(name)] = str(path)
    if session.get("workflow") == "import" and session.get("source_path"):
        source = Path(str(session["source_path"])).expanduser().resolve()
        recorded_source = (
            segments_payload.get("audio_path")
            if isinstance(segments_payload, dict)
            else None
        )
        if recorded_source and Path(str(recorded_source)).expanduser().resolve() != source:
            raise ValueError("Imported source_path does not match segments.json audio_path")
        resolved.setdefault("source", str(source))
        resolved.setdefault("mixed", str(source))
    return resolved


def _action_payloads(summary: dict) -> list[dict]:
    summary_fields = summary.get("summary") if isinstance(summary.get("summary"), dict) else summary
    detail_items = summary_fields.get("action_items", [])
    if not isinstance(detail_items, list):
        detail_items = []
    details = [item for item in detail_items if isinstance(item, dict)]
    claims = summary.get("claims", [])
    action_claims = (
        [
            claim
            for claim in claims
            if isinstance(claim, dict) and claim.get("field") == "action_items"
        ]
        if isinstance(claims, list)
        else []
    )
    if not action_claims:
        return [item if isinstance(item, dict) else {"task": str(item)} for item in detail_items]
    payloads = []
    for index, claim in enumerate(action_claims):
        text = str(claim.get("text") or "").strip()
        detail = details[index] if index < len(details) else {}
        if str(detail.get("task") or "").strip() != text:
            detail = {}
        payloads.append({**detail, **claim, "task": text})
    return payloads


def _claim_review_overrides(session_dir: Path) -> dict[str, dict[str, str]]:
    canonical = session_dir / "review_events.jsonl"
    paths = [canonical] if canonical.exists() else sorted(session_dir.glob("*_review_events.jsonl"))
    overrides = {}
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Cannot index {path}:{line_number}: {exc}") from exc
            event_type = str(event.get("event") or "")
            claim_id = str(event.get("claim_id") or "")
            if not claim_id or event_type not in {
                "claim.confirmed",
                "claim.rejected",
                "claim.edited",
            }:
                continue
            changes = event.get("changes", {})
            override = overrides.setdefault(claim_id, {})
            review_status = changes.get("review_status", {}).get("to")
            text = changes.get("text", {}).get("to")
            if review_status:
                override["review_status"] = str(review_status)
            elif event_type in {"claim.confirmed", "claim.rejected"}:
                override["review_status"] = event_type.removeprefix("claim.")
            if isinstance(text, str) and text.strip():
                override["text"] = text.strip()
    return overrides


def rebuild_evidence_index(artifact_root: str | Path, index_path: str | Path) -> IndexStats:
    root = Path(artifact_root).expanduser().resolve()
    target = Path(index_path).expanduser().resolve()
    if target.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
        raise ValueError("Evidence index target must be a SQLite database path")
    if target.exists():
        try:
            with sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True) as existing:
                version = existing.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in existing.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
        except sqlite3.Error as exc:
            raise ValueError("Existing evidence index target is not a valid SQLite database") from exc
        if version != 1 or not {"meetings", "segments", "actions"}.issubset(tables):
            raise ValueError("Existing SQLite target is not an AURA evidence index")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    meeting_count = 0
    segment_count = 0
    action_count = 0
    try:
        with sqlite3.connect(temporary) as connection:
            connection.executescript(
                """
                CREATE TABLE meetings (
                    meeting_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    session_path TEXT NOT NULL,
                    audio_tracks_json TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE meeting_fts USING fts5(
                    meeting_id UNINDEXED,
                    title,
                    content,
                    tokenize='trigram'
                );
                CREATE TABLE segments (
                    segment_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY (meeting_id, segment_id)
                );
                CREATE VIRTUAL TABLE segment_fts USING fts5(
                    segment_id UNINDEXED,
                    meeting_id UNINDEXED,
                    text,
                    speaker,
                    tokenize='trigram'
                );
                CREATE TABLE actions (
                    meeting_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    source_segment_ids_json TEXT NOT NULL,
                    support_status TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    summary_path TEXT NOT NULL,
                    PRIMARY KEY (meeting_id, action_id)
                );
                PRAGMA user_version = 1;
                """
            )
            for session_path in sorted(root.rglob("session.json")):
                session = _read_json(session_path)
                meeting_id = str(session.get("meeting_id") or "").strip()
                if not meeting_id:
                    raise ValueError(f"Cannot index {session_path}: meeting_id is required")
                summary_path = session_path.with_name("summary.json")
                summary = _read_json(summary_path) if summary_path.exists() else {}
                segments_path = session_path.with_name("segments.json")
                segments_payload = _read_json(segments_path) if segments_path.exists() else []
                segment_rows = _segments(segments_payload)
                summary_valid = (
                    bool(summary)
                    and session.get("summary_status") != "invalidated"
                    and str(summary.get("meeting_id") or "") == meeting_id
                    and str(summary.get("transcript_sha256") or "")
                    == str(session.get("transcript_sha256") or "")
                )
                searchable_summary = summary if summary_valid else {}
                summary_fields = (
                    searchable_summary.get("summary")
                    if isinstance(searchable_summary.get("summary"), dict)
                    else searchable_summary
                )
                title = str(
                    session.get("title")
                    or (summary_fields.get("meeting_topic") if isinstance(summary_fields, dict) else "")
                    or session_path.parent.name
                ).strip()
                searchable_text = " ".join(
                    [
                        *list(_text_values(searchable_summary)),
                        *(str(row.get("text") or "") for row in segment_rows),
                    ]
                )
                connection.execute(
                    """
                    INSERT INTO meetings (
                        meeting_id, title, status, started_at, ended_at, session_path,
                        audio_tracks_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        meeting_id,
                        title,
                        str(session.get("status") or ""),
                        str(session.get("started_at") or ""),
                        str(session.get("ended_at") or ""),
                        str(session_path.resolve()),
                        json.dumps(
                            _audio_tracks(
                                session,
                                session_path.parent,
                                segments_payload,
                            ),
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    ),
                )
                connection.execute(
                    "INSERT INTO meeting_fts (meeting_id, title, content) VALUES (?, ?, ?)",
                    (meeting_id, title, searchable_text),
                )
                meeting_count += 1
                indexed_segment_ids = set()
                for segment in segment_rows:
                    segment_id = str(segment.get("segment_id") or "").strip()
                    text = str(segment.get("text") or "").strip()
                    if not segment_id or not text:
                        continue
                    start_ms = int(segment.get("start_ms") or 0)
                    end_ms = int(segment.get("end_ms") or 0)
                    if start_ms < 0 or end_ms < start_ms:
                        raise ValueError(
                            f"Cannot index {segments_path}: invalid timestamp range for {segment_id}"
                        )
                    row = (
                        segment_id,
                        meeting_id,
                        start_ms,
                        end_ms,
                        text,
                        str(segment.get("speaker") or ""),
                        str(segment.get("state") or "final"),
                        int(segment.get("revision") or 1),
                    )
                    connection.execute(
                        """
                        INSERT INTO segments (
                            segment_id, meeting_id, start_ms, end_ms, text, speaker, state, revision
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        row,
                    )
                    connection.execute(
                        "INSERT INTO segment_fts (segment_id, meeting_id, text, speaker) VALUES (?, ?, ?, ?)",
                        (segment_id, meeting_id, text, row[5]),
                    )
                    indexed_segment_ids.add(segment_id)
                    segment_count += 1
                action_items = (
                    _action_payloads(summary) if summary_valid else []
                )
                review_overrides = _claim_review_overrides(session_path.parent)
                for index, payload in enumerate(action_items, start=1):
                    action_id = str(
                        payload.get("claim_id")
                        or payload.get("action_id")
                        or payload.get("id")
                        or f"action-{index:04d}"
                    )
                    override = review_overrides.get(action_id, {})
                    task = str(
                        override.get("text")
                        or payload.get("task")
                        or payload.get("text")
                        or ""
                    ).strip()
                    if not task:
                        continue
                    review_status = override.get(
                        "review_status",
                        "unreviewed",
                    )
                    source_segment_ids = payload.get("source_segment_ids") or []
                    if not isinstance(source_segment_ids, list):
                        source_segment_ids = []
                    source_segment_ids = [
                        str(segment_id)
                        for segment_id in source_segment_ids
                        if str(segment_id) in indexed_segment_ids
                    ]
                    support_status = str(
                        payload.get("support_status") or "unsupported"
                    )
                    if not source_segment_ids:
                        support_status = "unsupported"
                    connection.execute(
                        """
                        INSERT INTO actions (
                            meeting_id,
                            action_id,
                            task,
                            owner,
                            deadline,
                            source_segment_ids_json,
                            support_status,
                            review_status,
                            summary_path
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            meeting_id,
                            action_id,
                            task,
                            str(payload.get("owner") or ""),
                            str(payload.get("deadline") or ""),
                            json.dumps(source_segment_ids, ensure_ascii=False),
                            support_status,
                            review_status,
                            str(summary_path.resolve()),
                        ),
                    )
                    action_count += 1
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return IndexStats(
        meeting_count=meeting_count,
        segment_count=segment_count,
        action_count=action_count,
    )


class EvidenceSearch:
    def __init__(self, index_path: str | Path):
        path = Path(index_path).expanduser().resolve()
        uri = f"{path.as_uri()}?mode=ro"
        self._connection = sqlite3.connect(uri, uri=True)
        self._connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "EvidenceSearch":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def search_segments(self, query: str, limit: int = 20) -> list[dict]:
        columns = """
            SELECT
                segments.meeting_id,
                segments.segment_id,
                segments.start_ms,
                segments.end_ms,
                segments.text,
                segments.speaker,
                segments.state,
                segments.revision,
                meetings.session_path
            FROM segments
            JOIN meetings ON meetings.meeting_id = segments.meeting_id
        """
        bounded_limit = max(1, min(int(limit), 100))
        if len(query.strip()) < 3:
            pattern = _literal_like(query)
            rows = self._connection.execute(
                columns
                + """
                WHERE segments.text LIKE ? ESCAPE '\\'
                   OR segments.speaker LIKE ? ESCAPE '\\'
                ORDER BY segments.meeting_id, segments.start_ms
                LIMIT ?
                """,
                (pattern, pattern, bounded_limit),
            )
            return [dict(row) for row in rows]
        rows = self._connection.execute(
            """
            SELECT
                segments.meeting_id,
                segments.segment_id,
                segments.start_ms,
                segments.end_ms,
                segments.text,
                segments.speaker,
                segments.state,
                segments.revision,
                meetings.session_path
            FROM segment_fts
            JOIN segments
              ON segments.meeting_id = segment_fts.meeting_id
             AND segments.segment_id = segment_fts.segment_id
            JOIN meetings ON meetings.meeting_id = segments.meeting_id
            WHERE segment_fts MATCH ?
            ORDER BY bm25(segment_fts), segments.meeting_id, segments.start_ms
            LIMIT ?
            """,
            (_fts_phrase(query), bounded_limit),
        )
        return [dict(row) for row in rows]

    def search_meetings(self, query: str, limit: int = 20) -> list[dict]:
        bounded_limit = max(1, min(int(limit), 100))
        if len(query.strip()) < 3:
            pattern = _literal_like(query)
            rows = self._connection.execute(
                """
                SELECT
                    meetings.meeting_id,
                    meetings.title,
                    meetings.status,
                    meetings.started_at,
                    meetings.ended_at,
                    meetings.session_path,
                    meeting_fts.content AS matched_text
                FROM meeting_fts
                JOIN meetings ON meetings.meeting_id = meeting_fts.meeting_id
                WHERE meeting_fts.title LIKE ? ESCAPE '\\'
                   OR meeting_fts.content LIKE ? ESCAPE '\\'
                ORDER BY meetings.started_at DESC, meetings.meeting_id
                LIMIT ?
                """,
                (pattern, pattern, bounded_limit),
            )
            results = [dict(row) for row in rows]
            for result in results:
                result["matched_text"] = _matched_excerpt(result["matched_text"], query)
            return results
        rows = self._connection.execute(
            """
            SELECT
                meetings.meeting_id,
                meetings.title,
                meetings.status,
                meetings.started_at,
                meetings.ended_at,
                meetings.session_path,
                snippet(meeting_fts, 2, '', '', ' … ', 18) AS matched_text
            FROM meeting_fts
            JOIN meetings ON meetings.meeting_id = meeting_fts.meeting_id
            WHERE meeting_fts MATCH ?
            ORDER BY bm25(meeting_fts), meetings.started_at DESC, meetings.meeting_id
            LIMIT ?
            """,
            (_fts_phrase(query), bounded_limit),
        )
        return [dict(row) for row in rows]

    def open_audio_span(
        self,
        meeting_id: str,
        start_ms: int,
        end_ms: int,
        track: str = "mixed",
    ) -> dict:
        start = int(start_ms)
        end = int(end_ms)
        if start < 0 or end <= start:
            raise ValueError("audio span must satisfy 0 <= start_ms < end_ms")
        row = self._connection.execute(
            "SELECT audio_tracks_json FROM meetings WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"meeting not found: {meeting_id}")
        tracks = json.loads(row["audio_tracks_json"])
        if track not in tracks:
            raise KeyError(f"audio track not found: {track}")
        path = Path(tracks[track])
        return {
            "meeting_id": meeting_id,
            "track": track,
            "path": str(path),
            "start_ms": start,
            "end_ms": end,
            "duration_ms": end - start,
            "exists": path.is_file(),
        }

    def get_confirmed_actions(self, meeting_id: str | None = None) -> list[dict]:
        rows = self._connection.execute(
            """
            SELECT
                actions.meeting_id,
                actions.action_id,
                actions.task,
                actions.owner,
                actions.deadline,
                actions.source_segment_ids_json,
                actions.support_status,
                actions.review_status,
                actions.summary_path
            FROM actions
            JOIN meetings ON meetings.meeting_id = actions.meeting_id
            WHERE actions.review_status = 'confirmed'
              AND actions.support_status != 'unsupported'
              AND (? IS NULL OR actions.meeting_id = ?)
            ORDER BY meetings.started_at DESC, actions.meeting_id, actions.action_id
            """,
            (meeting_id, meeting_id),
        )
        actions = []
        for row in rows:
            action = dict(row)
            action["source_segment_ids"] = json.loads(action.pop("source_segment_ids_json"))
            actions.append(action)
        return actions


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and query Project AURA local evidence indexes.")
    commands = parser.add_subparsers(dest="command", required=True)

    rebuild = commands.add_parser("rebuild", help="Rebuild an index from canonical session artifacts.")
    rebuild.add_argument("artifact_root")
    rebuild.add_argument("index_path")

    for name in ("search-meetings", "search-segments"):
        search = commands.add_parser(name)
        search.add_argument("index_path")
        search.add_argument("query")
        search.add_argument("--limit", type=int, default=20)

    audio = commands.add_parser("open-audio-span")
    audio.add_argument("index_path")
    audio.add_argument("meeting_id")
    audio.add_argument("start_ms", type=int)
    audio.add_argument("end_ms", type=int)
    audio.add_argument("--track", default="mixed")

    actions = commands.add_parser("confirmed-actions")
    actions.add_argument("index_path")
    actions.add_argument("--meeting-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    if args.command == "rebuild":
        payload = asdict(rebuild_evidence_index(args.artifact_root, args.index_path))
    else:
        with EvidenceSearch(args.index_path) as evidence:
            if args.command == "search-meetings":
                payload = evidence.search_meetings(args.query, args.limit)
            elif args.command == "search-segments":
                payload = evidence.search_segments(args.query, args.limit)
            elif args.command == "open-audio-span":
                payload = evidence.open_audio_span(
                    args.meeting_id,
                    args.start_ms,
                    args.end_ms,
                    args.track,
                )
            else:
                payload = evidence.get_confirmed_actions(args.meeting_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
