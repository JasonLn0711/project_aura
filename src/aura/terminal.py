"""Compact terminal presentation of real shared-session state."""
from collections import deque
import math
import re
import time

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)')


def safe_text(value):
    return ''.join(c for c in ANSI.sub('', str(value)) if c in '\n\t' or ord(c) >= 32 and ord(c) != 127)


def bar(done, total, width=16):
    fraction = min(1, max(0, done / total)) if total else 0
    filled = round(width * fraction)
    return '[' + '=' * filled + ' ' * (width - filled) + f'] {fraction:.0%}'


def graph(values, width=24):
    values = list(values)[-width:]
    return ''.join('▁▂▃▄▅▆▇█'[min(7, max(0, round(v * 7)))] for v in values) or 'unavailable'


class TerminalStatus:
    def __init__(self):
        self.session = None
        self.connected = True
        self.error = ''
        self.graphs = True
        self.audio = deque(maxlen=60)
        self.queue = deque(maxlen=60)
        self.transfer = None
        self.last_sample = None

    def update(self, session):
        if not self.session or session['id'] != self.session['id']:
            self.audio.clear()
            self.queue.clear()
            self.last_sample = None
        self.session = session
        self.connected = True
        self.error = ''
        if session.get('samples') != self.last_sample and 'audio_level' in session:
            level = session['audio_level']
            self.audio.append(max(0, min(1, (20 * math.log10(max(1e-6, level)) + 60) / 60)))
        self.last_sample = session.get('samples')
        if 'work' in session:
            self.queue.append(session['work']['queued'])

    def progress(self, done, total):
        self.transfer = (done, total)

    def lines(self, width=80):
        if not self.connected:
            return [('class:error', '(!.!) Disconnected · ' + safe_text(self.error))]
        if self.transfer:
            done, total = self.transfer
            return [('class:accent', 'Transfer ' + (bar(done, total) if total else f'{done:,} bytes transferred'))]
        s = self.session
        if not s:
            return [('class:muted', '(o.o) Ready · /record · /sessions · /help')]
        state = s['state']
        face = {'paused': '(-.-)', 'ready': '(^.^)', 'failed': '(!.!)', 'recoverable': '(!.!)'}.get(state, '(o.o)')
        active = state in ('starting', 'draining', 'importing', 'refining', 'exporting')
        pulse = '|/-\\'[int(time.monotonic() * 4) % 4] if active else '·'
        seconds = s.get('samples', 0) // 16000
        work = s.get('work')
        queued = f'{work["queued"]} pending · {work["running"]} processing' if work else 'queue unavailable'
        lines = [('class:owl', f'{face} {state} {pulse} Audio {seconds//60:02d}:{seconds%60:02d} · {queued}')]
        if state == 'draining' and work:
            total = sum(work.values())
            if total:
                lines.append(('class:accent', 'Transcription queue ' + bar(work['done'], total)))
        if self.graphs and width >= 60:
            ceiling = max(1, max(self.queue, default=0))
            lines.append(('class:accent', 'Audio ' + graph(self.audio, 20) + '  Queue ' + graph([v / ceiling for v in self.queue], 20) + f' (0–{ceiling})'))
        lines.append(('class:muted', '/pause · /resume · /stop · /detach · /graphs off'))
        return lines

    def toolbar(self, width):
        from prompt_toolkit.utils import get_cwidth
        result = []
        for style, line in self.lines(width):
            # Cell-aware truncation keeps Chinese text inside narrow terminals.
            text, cells = '', 0
            for char in safe_text(line).replace('\n', ' '):
                size = get_cwidth(char)
                if cells + size > max(1, width - 1):
                    break
                text += char
                cells += size
            if result:
                result.append(('', '\n'))
            result.append((style, text))
        return result
