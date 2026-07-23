from __future__ import annotations

import datetime
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from aura.audio.recording_session import write_session_manifest


PROVISIONAL = "provisional"
FINAL = "final"
CONFIRMED = "confirmed"
SEGMENT_STATES = {PROVISIONAL, FINAL, CONFIRMED}
UNKNOWN_SPEAKER = "SPEAKER_UNKNOWN"
UNKNOWN_SPEAKER_FLAG = "unknown_speaker"
SPEAKER_OVERLAP_FLAG = "speaker_overlap"
LOW_CONFIDENCE_FLAG = "low_confidence"
LOW_CONFIDENCE_LOGPROB = -1.0
_LINE_PATTERN = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s*(.*)$")
_SEGMENT_ID_PATTERN = re.compile(r"^\[(seg-[\w.-]+)\]\s*(.*)$")
_SPEAKER_PATTERN = re.compile(r"^([\w\u3400-\u9fff.-]{1,40}):\s*(.*)$")


@dataclass(frozen=True)
class ReviewSegment:
    segment_id: str
    start_ms: int
    end_ms: int
    text: str
    speaker: str = UNKNOWN_SPEAKER
    state: str = PROVISIONAL
    revision: int = 0
    asr_logprob: float | None = None
    review_flags: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.segment_id.strip():
            raise ValueError("segment_id is required")
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise ValueError("segment timestamps must be non-negative and ordered")
        if self.state not in SEGMENT_STATES:
            raise ValueError(f"unsupported segment state: {self.state}")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")

    @classmethod
    def from_dict(cls, payload: dict) -> "ReviewSegment":
        return cls(
            segment_id=str(payload["segment_id"]),
            start_ms=int(payload["start_ms"]),
            end_ms=int(payload["end_ms"]),
            text=str(payload.get("text", "")),
            speaker=str(payload.get("speaker") or UNKNOWN_SPEAKER),
            state=str(payload.get("state") or PROVISIONAL),
            revision=int(payload.get("revision", 0)),
            asr_logprob=(
                float(payload["asr_logprob"])
                if payload.get("asr_logprob") is not None
                else None
            ),
            review_flags=tuple(str(item) for item in payload.get("review_flags", [])),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def stable_segment_id(index: int, start_ms: int) -> str:
    value = uuid.uuid5(uuid.NAMESPACE_URL, f"project-aura:segment:{index}:{start_ms}")
    return f"seg-{value.hex[:16]}"


def _timestamp_ms(hours: str, minutes: str, seconds: str) -> int:
    return (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000


def parse_transcript_lines(
    lines: Iterable[str],
    *,
    state: str = FINAL,
) -> list[ReviewSegment]:
    parsed: list[tuple[int, str | None, str, str]] = []
    for raw_line in lines:
        line = str(raw_line).strip()
        if not line:
            continue
        match = _LINE_PATTERN.match(line)
        if match:
            start_ms = _timestamp_ms(match.group(1), match.group(2), match.group(3))
            content = match.group(4).strip()
        else:
            start_ms = parsed[-1][0] if parsed else 0
            content = line
        segment_id_match = _SEGMENT_ID_PATTERN.match(content)
        if segment_id_match:
            explicit_segment_id, content = segment_id_match.groups()
        else:
            explicit_segment_id = None
        speaker_match = _SPEAKER_PATTERN.match(content)
        if speaker_match:
            speaker, text = speaker_match.groups()
        else:
            speaker, text = UNKNOWN_SPEAKER, content
        parsed.append((start_ms, explicit_segment_id, speaker, text.strip()))

    segments = []
    for index, (start_ms, explicit_segment_id, speaker, text) in enumerate(parsed):
        end_ms = parsed[index + 1][0] if index + 1 < len(parsed) else start_ms
        segments.append(
            ReviewSegment(
                segment_id=explicit_segment_id or stable_segment_id(index, start_ms),
                start_ms=start_ms,
                end_ms=max(start_ms, end_ms),
                text=text,
                speaker=speaker,
                state=state,
                review_flags=(
                    (UNKNOWN_SPEAKER_FLAG,)
                    if speaker == UNKNOWN_SPEAKER
                    else ()
                ),
            )
        )
    return segments


def segment_artifact_paths(base_path: str | Path) -> dict[str, Path]:
    path = Path(base_path)
    if path.is_dir():
        return {
            "segments": path / "segments.json",
            "review_events": path / "review_events.jsonl",
        }
    return {
        "segments": path.with_name(f"{path.name}_segments.json"),
        "review_events": path.with_name(f"{path.name}_review_events.jsonl"),
    }


def _atomic_write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp_path.open("w", encoding="utf-8") as target:
        target.write(text)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temp_path, path)
    return path


class TranscriptReview:
    def __init__(self, segments: Iterable[ReviewSegment] = (), events: Iterable[dict] = ()):
        self.segments = list(segments)
        self.events = list(events)
        self._saved_event_count = len(self.events)

    def _index(self, segment_id: str) -> int:
        for index, segment in enumerate(self.segments):
            if segment.segment_id == segment_id:
                return index
        raise KeyError(segment_id)

    def edit(self, segment_id: str, *, text: str | None = None, speaker: str | None = None) -> ReviewSegment:
        index = self._index(segment_id)
        current = self.segments[index]
        changes = {}
        values = {}
        if text is not None and text != current.text:
            values["text"] = str(text)
            changes["text"] = {"from": current.text, "to": str(text)}
        if speaker is not None and speaker != current.speaker:
            values["speaker"] = str(speaker) or UNKNOWN_SPEAKER
            changes["speaker"] = {"from": current.speaker, "to": values["speaker"]}
            flags = set(current.review_flags)
            if values["speaker"] == UNKNOWN_SPEAKER:
                flags.add(UNKNOWN_SPEAKER_FLAG)
            else:
                flags.discard(UNKNOWN_SPEAKER_FLAG)
            values["review_flags"] = tuple(sorted(flags))
        if not changes:
            return current
        updated = replace(current, revision=current.revision + 1, **values)
        self.segments[index] = updated
        self._record("segment.edited", updated, changes)
        return updated

    def confirm(self, segment_id: str) -> ReviewSegment:
        index = self._index(segment_id)
        current = self.segments[index]
        if current.state == CONFIRMED:
            return current
        updated = replace(current, state=CONFIRMED, revision=current.revision + 1)
        self.segments[index] = updated
        self._record(
            "segment.confirmed",
            updated,
            {"state": {"from": current.state, "to": CONFIRMED}},
        )
        return updated

    def rename_speaker(self, current_name: str, new_name: str) -> int:
        replacement = str(new_name).strip()
        if not replacement:
            raise ValueError("new speaker name is required")
        matching_ids = [
            segment.segment_id
            for segment in self.segments
            if segment.speaker == current_name
        ]
        for segment_id in matching_ids:
            self.edit(segment_id, speaker=replacement)
        return len(matching_ids)

    def _record(self, event_type: str, segment: ReviewSegment, changes: dict) -> None:
        self.events.append(
            {
                "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "event": event_type,
                "segment_id": segment.segment_id,
                "revision": segment.revision,
                "changes": changes,
            }
        )

    def save(
        self,
        base_path: str | Path,
        *,
        meeting_id: str,
        audio_path: str | Path | None = None,
    ) -> dict[str, Path]:
        paths = segment_artifact_paths(base_path)
        new_events = self.events[self._saved_event_count :]
        manifest_path = paths["segments"].parent / "session.json"
        if (
            any(event.get("event") == "segment.edited" for event in new_events)
            and manifest_path.exists()
            and (manifest_path.parent / "summary.json").exists()
        ):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["summary_status"] = "invalidated"
            manifest["summary_invalidation_reason"] = "segment.edited"
            manifest["summary_invalidated_at"] = (
                datetime.datetime.now().astimezone().isoformat(timespec="seconds")
            )
            write_session_manifest(manifest_path, manifest)
        payload = {
            "schema_version": 1,
            "meeting_id": str(meeting_id),
            "audio_path": str(audio_path) if audio_path else None,
            "segments": [segment.to_dict() for segment in self.segments],
        }
        _atomic_write(
            paths["segments"],
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        if new_events:
            existing_events = (
                paths["review_events"].read_text(encoding="utf-8")
                if paths["review_events"].exists()
                else ""
            )
            _atomic_write(
                paths["review_events"],
                existing_events
                + "".join(
                    json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
                    for event in new_events
                ),
            )
            self._saved_event_count = len(self.events)
        else:
            paths["review_events"].touch(exist_ok=True)
        return paths

    @classmethod
    def load(cls, base_path: str | Path) -> "TranscriptReview":
        paths = segment_artifact_paths(base_path)
        payload = json.loads(paths["segments"].read_text(encoding="utf-8"))
        events = []
        if paths["review_events"].exists():
            events = [
                json.loads(line)
                for line in paths["review_events"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        return cls(
            (ReviewSegment.from_dict(item) for item in payload.get("segments", [])),
            events,
        )


def _subtitle_timestamp(milliseconds: int, separator: str) -> str:
    hours, remainder = divmod(max(0, int(milliseconds)), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def export_segments(segments: Iterable[ReviewSegment], base_path: str | Path) -> dict[str, Path]:
    items = list(segments)
    base = Path(base_path)
    paths = {
        "json": base.with_name(f"{base.name}.json"),
        "markdown": base.with_name(f"{base.name}.md"),
        "srt": base.with_name(f"{base.name}.srt"),
        "vtt": base.with_name(f"{base.name}.vtt"),
    }
    _atomic_write(
        paths["json"],
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write(
        paths["markdown"],
        "\n".join(
            f"- [{_subtitle_timestamp(item.start_ms, '.')[:-4]}] {item.speaker}：{item.text}"
            for item in items
        )
        + ("\n" if items else ""),
    )
    srt_blocks = []
    vtt_blocks = ["WEBVTT", ""]
    for index, item in enumerate(items, 1):
        end_ms = max(item.end_ms, item.start_ms + 1)
        label = f"{item.speaker}: {item.text}" if item.speaker != UNKNOWN_SPEAKER else item.text
        start_srt = _subtitle_timestamp(item.start_ms, ",")
        end_srt = _subtitle_timestamp(end_ms, ",")
        srt_blocks.append(f"{index}\n{start_srt} --> {end_srt}\n{label}")
        vtt_blocks.append(
            f"{_subtitle_timestamp(item.start_ms, '.')} --> {_subtitle_timestamp(end_ms, '.')}\n{label}\n"
        )
    _atomic_write(paths["srt"], "\n\n".join(srt_blocks) + ("\n" if srt_blocks else ""))
    _atomic_write(paths["vtt"], "\n".join(vtt_blocks))
    return paths
