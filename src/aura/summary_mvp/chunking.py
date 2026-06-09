from __future__ import annotations

from aura.summary_mvp.schema import Transcript, TranscriptChunk


def parse_timestamp(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"Timestamp must use HH:MM:SS format: {value}")
    hours, minutes, seconds = (int(part) for part in parts)
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remainder = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remainder:02d}"


def build_time_chunks(transcript: Transcript, window_seconds: int = 90) -> list[TranscriptChunk]:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive.")

    chunks: list[TranscriptChunk] = []
    current_text: list[str] = []
    current_sources: list[str] = []
    chunk_start = transcript.asr_transcript[0].start
    chunk_end = transcript.asr_transcript[0].end
    chunk_start_seconds = parse_timestamp(chunk_start)

    def flush() -> None:
        if current_text:
            chunks.append(
                TranscriptChunk(
                    chunk_id=f"c{len(chunks) + 1:03d}",
                    start=chunk_start,
                    end=chunk_end,
                    text=" ".join(current_text).strip(),
                    source_segment_ids=list(current_sources),
                )
            )

    for index, segment in enumerate(transcript.asr_transcript, start=1):
        segment_end_seconds = parse_timestamp(segment.end)
        if current_text and segment_end_seconds - chunk_start_seconds > window_seconds:
            flush()
            current_text = []
            current_sources = []
            chunk_start = segment.start
            chunk_start_seconds = parse_timestamp(segment.start)

        current_text.append(segment.text)
        current_sources.append(f"s{index:03d}")
        chunk_end = segment.end

    flush()
    return chunks


def build_sliding_window_chunks(
    transcript: Transcript,
    max_chars: int = 900,
    overlap_chars: int = 180,
) -> list[TranscriptChunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive.")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars.")

    chunks: list[TranscriptChunk] = []
    window_text: list[str] = []
    window_sources: list[str] = []
    window_start = transcript.asr_transcript[0].start
    window_end = transcript.asr_transcript[0].end

    def trim_for_overlap(texts: list[str], sources: list[str]) -> tuple[list[str], list[str]]:
        retained_texts: list[str] = []
        retained_sources: list[str] = []
        retained_len = 0
        for text, source in reversed(list(zip(texts, sources))):
            if retained_len >= overlap_chars:
                break
            retained_texts.insert(0, text)
            retained_sources.insert(0, source)
            retained_len += len(text) + 1
        return retained_texts, retained_sources

    for index, segment in enumerate(transcript.asr_transcript, start=1):
        source_id = f"s{index:03d}"
        next_len = len(" ".join(window_text + [segment.text]))
        if window_text and next_len > max_chars:
            chunks.append(
                TranscriptChunk(
                    chunk_id=f"c{len(chunks) + 1:03d}",
                    start=window_start,
                    end=window_end,
                    text=" ".join(window_text).strip(),
                    source_segment_ids=list(window_sources),
                )
            )
            window_text, window_sources = trim_for_overlap(window_text, window_sources)
            window_start = segment.start if not window_text else window_start

        if not window_text:
            window_start = segment.start
        window_text.append(segment.text)
        window_sources.append(source_id)
        window_end = segment.end

    if window_text:
        chunks.append(
            TranscriptChunk(
                chunk_id=f"c{len(chunks) + 1:03d}",
                start=window_start,
                end=window_end,
                text=" ".join(window_text).strip(),
                source_segment_ids=list(window_sources),
            )
        )
    return chunks
