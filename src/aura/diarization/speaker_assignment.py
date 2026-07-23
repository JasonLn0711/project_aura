from dataclasses import dataclass


UNKNOWN_SPEAKER = "SPEAKER_UNKNOWN"


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    asr_logprob: float | None = None


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


@dataclass(frozen=True)
class SpeakerLabeledSegment:
    transcript: TranscriptSegment
    speaker: str


def overlap_seconds(left_start: float, left_end: float, right_start: float, right_end: float) -> float:
    return max(0.0, min(left_end, right_end) - max(left_start, right_start))


def speaker_for_segment(segment: TranscriptSegment, speaker_turns: list[SpeakerTurn]) -> str:
    """Assign the speaker with the largest time overlap, then fall back to midpoint containment."""
    best_speaker = UNKNOWN_SPEAKER
    best_overlap = 0.0

    for turn in speaker_turns:
        score = overlap_seconds(segment.start, segment.end, turn.start, turn.end)
        if score > best_overlap:
            best_overlap = score
            best_speaker = turn.speaker

    if best_overlap > 0:
        return best_speaker

    midpoint = segment.start + max(0.0, segment.end - segment.start) / 2
    for turn in speaker_turns:
        if turn.start <= midpoint <= turn.end:
            return turn.speaker

    return UNKNOWN_SPEAKER


def assign_speakers(
    transcript_segments: list[TranscriptSegment],
    speaker_turns: list[SpeakerTurn],
) -> list[SpeakerLabeledSegment]:
    return [
        SpeakerLabeledSegment(segment, speaker_for_segment(segment, speaker_turns))
        for segment in transcript_segments
    ]
