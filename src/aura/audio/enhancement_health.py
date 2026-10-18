"""Source-aligned signal checks; no raw audio is admitted to ASR by this guard."""
from collections import deque
import math


class EnhancementHealth:
    """Detect sustained speech erasure, with one reset per suppression episode.

    Counts are source samples, independent of inference or transport speed.
    A three-second window must contain at least one second of audible source
    speech. Quiet output alone is normal and never triggers a reset.
    """
    window_samples = 48000
    speech_samples = 16000

    def __init__(self):
        self.frames = deque()
        self.position = 0
        self.length = self.source_power = self.output_power = 0
        self.source_voice = self.output_voice = 0
        self.episode = self.unresolved = False

    def observe(self, count, source_rms, output_rms, source_speech, output_speech):
        if count <= 0 or not all(math.isfinite(v) and v >= 0 for v in (source_rms, output_rms)):
            raise ValueError('Health checks require positive sample counts and finite RMS')
        frame = (self.position, count, source_rms ** 2 * count,
                 output_rms ** 2 * count, count if source_speech and source_rms >= 80 else 0,
                 count if output_speech and output_rms >= 80 else 0)
        self.position += count
        self.frames.append(frame)
        self.length += count
        self.source_power += frame[2]
        self.output_power += frame[3]
        self.source_voice += frame[4]
        self.output_voice += frame[5]
        while self.frames and self.length - self.frames[0][1] >= self.window_samples:
            old = self.frames.popleft()
            self.length -= old[1]
            self.source_power -= old[2]
            self.output_power -= old[3]
            self.source_voice -= old[4]
            self.output_voice -= old[5]
        if self.episode and self.output_voice >= self.speech_samples:
            self.episode = self.unresolved = False
            return dict(event='restored', end_sample=self.position)
        if self.length < self.window_samples or self.source_voice < self.speech_samples:
            return None
        source = math.sqrt(max(0, self.source_power) / self.length)
        output = math.sqrt(max(0, self.output_power) / self.length)
        if source < 80 or output >= 8 or output >= source * .01:
            return None
        if not self.episode:
            self.episode = True
            event = dict(event='suppression', start_sample=self.frames[0][0], end_sample=self.position,
                         source_rms=source, output_rms=output)
            self.frames.clear()
            self.length = self.source_power = self.output_power = 0
            self.source_voice = self.output_voice = 0
            return event
        if not self.unresolved:
            self.unresolved = True
            return dict(event='unresolved', end_sample=self.position)
        return None


def pending_gaps(session):
    return [gap for gap in session.get('enhancement', {}).get('gaps', []) if gap['status'] == 'pending']


def gap_warning(session):
    state = session.get('enhancement', {})
    status = state.get('health', {}).get('status')
    count = len(pending_gaps(session))
    if any(g.get('live_repair') in ('waiting', 'queued', 'running')
           for g in state.get('gaps', [])) and session.get('state') == 'recording':
        return f'RE-USE {status}: bounded live repair pending · original audio retained'
    review = sum(bool(g.get('review_required_ranges')) for g in pending_gaps(session))
    if review:
        message = f'{review} submitted intervals need review'
        if count > review:
            message += f' · {count - review} enhancement gaps'
        message += ' · original audio retained · /inspect'
        return message + (' · /recover after stop' if count > review else '')
    if status in ('recovering', 'blocked'):
        return f'RE-USE {status}: source speech was suppressed. Original audio retained; /recover after stop.'
    if count:
        return f'{count} enhancement gaps · original audio retained · /recover after stop'
    return ''
