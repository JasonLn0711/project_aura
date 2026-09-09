"""Compact terminal presentation of real shared-session state."""
from collections import deque
import math
import re
import time

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)')


def safe_text(value):
    return ''.join(c for c in ANSI.sub('', str(value)) if c in '\n\t' or ord(c) >= 32 and ord(c) != 127)


def clip_line(line, width):
    from prompt_toolkit.utils import get_cwidth
    text, cells = '', 0
    for char in safe_text(line).replace('\n', ' ').replace('\t', ' '):
        size = get_cwidth(char)
        if cells + size > max(1, width - 1):
            break
        text += char
        cells += size
    return text


def bar(done, total, width=16):
    fraction = min(1, max(0, done / total)) if total else 0
    filled = round(width * fraction)
    return '[' + '=' * filled + ' ' * (width - filled) + f'] {fraction:.0%}'


def graph(values, width=24):
    values = list(values)[-width:]
    return ''.join('▁▂▃▄▅▆▇█'[min(7, max(0, round(v * 7)))] for v in values) or 'unavailable'


class TerminalStatus:
    def __init__(self):
        self.model_status = ""
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
            return [('class:muted', '(o.o) Ready · /model · /record · /sessions · /help')] + ([("class:muted", self.model_status)] if self.model_status else [])
        state = s['state']
        face = {'paused': '(-.-)', 'ready': '(^.^)', 'failed': '(!.!)', 'recoverable': '(!.!)'}.get(state, '(o.o)')
        active = state in ('starting', 'draining', 'importing', 'refining', 'exporting')
        pulse = '|/-\\'[int(time.monotonic() * 4) % 4] if active else '·'
        seconds = s.get('samples', 0) // 16000
        work = s.get('work')
        queued = f'{work["queued"]} pending · {work["running"]} processing' if work else 'queue unavailable'
        lines = [('class:owl', f'{face} {state} {pulse} Audio {seconds//60:02d}:{seconds%60:02d} · {queued}')]
        if self.model_status:
            lines.append(('class:muted', self.model_status))
        if state == 'draining' and work:
            total = sum(work.values())
            if total:
                lines.append(('class:accent', 'Transcription queue ' + bar(work['done'], total)))
        gaps = sum(i["status"] == "pending" for i in s.get("asr_issues", []))
        if gaps:
            lines.append(('class:error', f'{gaps} transcription gaps · audio preserved · /inspect · /recover after stop'))
        if s.get('error'):
            lines.append(('class:error', safe_text(s['error'])))
        if self.graphs and width >= 60:
            ceiling = max(1, max(self.queue, default=0))
            lines.append(('class:accent', 'Audio ' + graph(self.audio, 20) + '  Queue ' + graph([v / ceiling for v in self.queue], 20) + f' (0–{ceiling})'))
        lines.append(('class:muted', '/unpause · /stop · /inspect · /detach' if state == 'paused' else
                      '/pause · /stop · /inspect · /detach' if state == 'recording' else
                      '/inspect · /export · /recover · /resume · /detach' if state in ('ready', 'failed', 'recoverable') else
                      '/inspect · /detach · /graphs off'))
        return lines

    def toolbar(self, width):
        result = []
        for style, line in self.lines(width):
            if result:
                result.append(('', '\n'))
            result.append((style, clip_line(line, width)))
        return result


def pick_session(rows):
    """Search saved sessions in a bounded inline prompt, preserving scrollback."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings
    import shutil

    if not rows:
        print('No saved sessions. Use /record to start a session.')
        return None
    index = 0
    bindings = KeyBindings()
    prompt = None

    def matches():
        query = prompt.default_buffer.text.casefold()
        return [row for row in rows if query in (row['title'] + ' ' + row['id']).casefold()]

    @bindings.add('up')
    def previous(event):
        nonlocal index
        index = max(0, index - 1)

    @bindings.add('down')
    def following(event):
        nonlocal index
        index = min(max(0, len(matches()) - 1), index + 1)

    @bindings.add('enter')
    def choose(event):
        found = matches()
        if found:
            event.app.exit(result=found[min(index, len(found) - 1)]['id'])

    @bindings.add('escape')
    @bindings.add('c-c')
    @bindings.add('c-d')
    def cancel(event):
        event.app.exit(result=None)

    def changed(_):
        nonlocal index
        index = 0

    def toolbar():
        found = matches()
        start = index // 8 * 8
        lines = ['↑/↓ select · Enter reopen · Esc cancel · search title or ID']
        for i, row in enumerate(found[start:start + 8], start):
            lines.append(f'{">" if i == index else " "} {row["id"][:8]}  {row["state"]}  '
                         f'{clip_line(row["title"], 25)}  {row.get("updated_at", row.get("created_at", ""))}')
        lines.append(f'{len(found)} matching sessions')
        width = shutil.get_terminal_size().columns
        return '\n'.join(clip_line(line, width) for line in lines)

    prompt = PromptSession(key_bindings=bindings, bottom_toolbar=toolbar)
    prompt.app.ttimeoutlen = 0.05
    prompt.app.timeoutlen = 0.3
    prompt.default_buffer.on_text_changed += changed
    return prompt.prompt('Find session> ')
