"""Compact terminal presentation of real shared-session state."""
from collections import deque
import math
import os
import re
import shutil
import sys
import time

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)')

PALETTES = {
    'slate': ('#BCC1C7', '#939BA5', '#697583', '#485361', '#A2988D'),
    'sage': ('#C5C1BA', '#A29B90', '#80796E', '#5F655E', '#829084'),
}

GARDEN = """     ·        ░░░░                          ▄██
         ░░░░░░░░░░                        ▐██
                                   ·        ▀▀

     ▄     ▄               ·            ▄▄
    ███▄▄▄███                          ████
    █ o v o █  )))           ▄          ▀█▀
    ▀███████▀               ▀█▀       ▄ │
      ▀   ▀                  │        ▀█│
▁▁▂▁▁▁▂▁▁▁▂▃▅▃▂▁▁▂▁▁▁▂▁▁▂▁▁▁▂▁▁▁▂▁▁▁▂▁▁▂▃▅▃▂▁▂▁"""


def unicode_terminal():
    try:
        '▁█❯·'.encode(sys.stdout.encoding or 'ascii')
        return os.environ.get('TERM') != 'dumb'
    except UnicodeEncodeError:
        return False


def decoration(text):
    if unicode_terminal():
        return text
    return text.translate(str.maketrans({'·': '|', '─': '-', '❯': '>', '↑': '^', '↓': 'v',
                                        '–': '-', **{c: '#' for c in '▁▂▃▄▅▆▇█'}})).encode('ascii', 'backslashreplace').decode()


def terminal_style(palette='slate'):
    from prompt_toolkit.styles import Style
    cloud, scenery, body, shadow, flower = PALETTES[palette]
    selection = '#DCE2E8' if palette == 'slate' else '#E2E4DF'
    return Style.from_dict({
        '': 'fg:default bg:default', 'heading': 'fg:default bold',
        'accent': 'fg:default', 'muted': 'fg:default', 'error': 'fg:default bold',
        'cloud': cloud, 'scenery': scenery, 'owl': body, 'shadow': shadow,
        'flower': flower, 'terrain': body,
        'bottom-toolbar': 'fg:default bg:default noreverse',
        'completion-menu.completion': 'fg:#414750 bg:#EEF0F4 noreverse',
        'completion-menu.completion.current': f'fg:#414750 bg:{selection} noreverse bold',
        'completion-menu.meta.completion': 'fg:#414750 bg:#EEF0F4 noreverse',
        'completion-menu.meta.completion.current': f'fg:#414750 bg:{selection} noreverse',
        'completion-menu.scrollbar.background': 'bg:#EEF0F4',
        'completion-menu.scrollbar.button': f'bg:{selection}',
    })


def terminal_color_depth():
    from prompt_toolkit.output import ColorDepth
    return ColorDepth.DEPTH_1_BIT if 'NO_COLOR' in os.environ else None


def owl(eyes='o', wings=False, celebrate=False):
    return ['▀▄ ▄     ▄ ▄▀' if celebrate else '   ▄     ▄   ', '  ███▄▄▄███  ',
            f' {"▄" if wings else " "}█ {eyes} v {eyes} █{"▄" if wings else " "} ',
            '  ▀███████▀  ', '    ▀   ▀    ']


def owl_fragments(line, row):
    return [('class:accent' if c in 'ov-^!' else 'class:shadow' if row == 3 else 'class:owl', c) for c in line]


def garden_rows():
    # ponytail: fixed scene coordinates; update these ranges when the artwork moves.
    rows = []
    for row, line in enumerate(GARDEN.splitlines()):
        parts = []
        for col, char in enumerate(line):
            role = 'scenery'
            if row == 9:
                role = 'terrain'
            elif char == '░':
                role = 'cloud'
            elif row < 3 and col >= 40:
                role = 'flower'
            elif 4 <= row <= 8 and 4 <= col < 13:
                parts.extend(owl_fragments(char, row - 4))
                continue
            elif row >= 4 and col >= 23 and char in '█▀▄':
                role = 'flower'
            parts.append(('class:' + role, char))
        rows.append(parts)
    return rows


def clip_fragments(parts, width):
    from prompt_toolkit.utils import get_cwidth
    result = []
    for style, text in parts:
        if width <= 1:
            break
        text = clip_line(decoration(text), width)
        result.append((style, text))
        width -= get_cwidth(text)
    return result


def welcome(banner, host, report, model_status='', size=None):
    """One scrollback header; the garden is decorative, never an audio meter."""
    width, height = size or shutil.get_terminal_size()
    rows = [[('class:heading', banner)], [('', '')]]
    if unicode_terminal() and width >= 80 and height >= 30:
        rows.extend(garden_rows())
    elif unicode_terminal() and height >= 20:
        rows.extend(owl_fragments(line, row) for row, line in enumerate(owl()))
    else:
        rows.append([('class:accent', '(o v o)')])
    rows += [[(style, text)] for style, text in [('', ''), ('class:muted', '/record   Start recording'),
             ('class:muted', '/resume   Reopen a session'), ('class:muted', '/model    Choose an ASR model'),
             ('class:muted', '/help     Explore commands'),
             ('', ''), ('class:muted', 'Connected: ' + safe_text(host)),
             ('class:muted', f'Service version: {report["service_version"]} · {report["version_status"]}')]]
    if model_status:
        rows.append([('class:muted', model_status)])
    return [part for row in rows for part in [*clip_fragments(row, width), ('', '\n')]]


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
        self.animations = True
        self.ready_since = None
        self.audio = deque(maxlen=60)
        self.queue = deque(maxlen=60)
        self.transfer = None
        self.last_sample = None

    def update(self, session):
        if not self.session or (session['id'], session['state']) != (self.session['id'], self.session['state']):
            self.ready_since = time.monotonic() if session['state'] == 'ready' else None
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

    def has_warning(self):
        s = self.session or {}
        return bool(not self.connected or s.get('error') or s.get('state') in ('failed', 'recoverable') or any(
            issue['status'] == 'pending' for issue in s.get('asr_issues', [])))

    def lines(self, width=80):
        if not self.connected:
            return [('class:error', '(!.!) Disconnected · ' + safe_text(self.error))]
        if self.transfer and not self.has_warning():
            done, total = self.transfer
            return [('class:accent', 'Transfer ' + (bar(done, total) if total else f'{done:,} bytes transferred'))]
        s = self.session
        if not s:
            return [('class:muted', '(o.o) Ready · /model · /record · /sessions · /help')] + ([("class:muted", self.model_status)] if self.model_status else [])
        state = s['state']
        face = '(!.!)' if self.has_warning() else {'paused': '(-.-)', 'ready': '(^.^)'}.get(state, '(o.o)')
        active = state in ('starting', 'draining', 'importing', 'refining', 'exporting')
        pulse = '|/-\\'[int(time.monotonic() * 4) % 4] if active and self.animations and os.environ.get('TERM') != 'dumb' else '·'
        seconds = s.get('samples', 0) // 16000
        work = s.get('work')
        queued = f'{work["queued"]} pending · {work["running"]} processing' if work else 'queue unavailable'
        lines = [('class:heading', f'{face} {state} {pulse} Audio {seconds//60:02d}:{seconds%60:02d}'),
                 ('class:muted', queued)]
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
            count = max(3, min(20, (width - 30) // 2))
            lines.append(('class:accent', 'Audio ' + graph(self.audio, count) + '  Queue ' + graph([v / ceiling for v in self.queue], count) + f' (0–{ceiling})'))
        lines.append(('class:muted', '/unpause · /stop · /inspect · /detach' if state == 'paused' else
                      '/pause · /stop · /inspect · /detach' if state == 'recording' else
                      '/inspect · /export · /recover · /resume · /detach' if state in ('ready', 'failed', 'recoverable') else
                      '/inspect · /detach · /graphs off'))
        return lines

    def toolbar(self, width, height=24):
        wide = unicode_terminal() and width >= 60 and height >= 20
        rows = self.lines(width - (14 if wide else 0))
        s = self.session or {}
        warning = self.has_warning()
        now = time.monotonic()
        animated = self.animations and os.environ.get('TERM') != 'dumb'
        eyes = '!' if warning else '-' if s.get('state') == 'paused' else '^' if s.get('state') == 'ready' else (
            '-' if animated and now % 5 < .25 else 'o')
        wings = animated and not warning and s.get('state') == 'recording' and int(now * 2) % 2 == 1
        celebrate = animated and not warning and s.get('state') == 'ready' and self.ready_since is not None and now - self.ready_since < 1
        mascot = owl(eyes, wings, celebrate) if wide else []
        result = [('class:scenery', decoration('─' * max(1, width - 1)))]
        if not wide:
            # Keep warnings ahead of optional model and graph detail on short terminals.
            rows = [row for row in rows if row[0] == 'class:error'] + [row for row in rows if row[0] != 'class:error']
            rows = rows[:max(1, min(3, height - 5))]
        for index in range(max(len(rows), len(mascot))):
            result.append(('', '\n'))
            if wide:
                result.extend(owl_fragments(mascot[index], index) if index < len(mascot) else [('', ' ' * 13)])
                result.append(('', ' '))
            if index < len(rows):
                style, line = rows[index]
                if wide:
                    line = re.sub(r'^\([!o^.-]+\) ', '', line)
                result.append((style, clip_line(decoration(line), width - (14 if wide else 0))))
        return result


def prompt_message(width):
    return [('class:scenery', decoration('─' * max(1, width - 1)) + '\n'), ('class:accent', decoration('❯ '))]


def picker_rows(rows, query, index, width, height):
    found = [row for row in rows if query.casefold() in (row['title'] + ' ' + row['id']).casefold()]
    count = max(1, min(8, height - 7))
    start = index // count * count
    lines = [('class:muted', '↑/↓ select · Enter reopen · Esc cancel · search title or ID')]
    for i, row in enumerate(found[start:start + count], start):
        lines.append(('class:accent' if i == index else 'class:muted',
                      f'{">" if i == index else " "} {row["id"][:8]}  {row["state"]}  '
                      f'{clip_line(row["title"], 25)}  {row.get("updated_at", row.get("created_at", ""))}'))
    lines.append(('class:muted', f'{len(found)} matching sessions'))
    result = []
    for style, line in lines:
        if result:
            result.append(('', '\n'))
        result.append((style, clip_line(decoration(line), width)))
    return result


def pick_session(rows, palette='slate'):
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
        return picker_rows(rows, prompt.default_buffer.text, index, *shutil.get_terminal_size())

    prompt = PromptSession(key_bindings=bindings, bottom_toolbar=toolbar,
                           style=terminal_style(palette), color_depth=terminal_color_depth())
    prompt.app.ttimeoutlen = 0.05
    prompt.app.timeoutlen = 0.3
    prompt.default_buffer.on_text_changed += changed
    return prompt.prompt('Find session> ')
