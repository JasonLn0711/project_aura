#!/usr/bin/env python3
"""Render the actual CLI presentation with synthetic state; no service or ASR.

Uses Pillow when installed (as in the local GUI environment). Images are review
artifacts, not evidence of device capture or model inference.
"""
import argparse
from pathlib import Path
from unittest.mock import patch

from aura.cli import CLI_BANNER, model_status_text
from aura.metadata import __version__
from aura.asr.models import PARAKEET
from aura.terminal import TerminalStatus, welcome, prompt_message, picker_rows, terminal_style, PALETTES


def toolbar_style(parts):
    return [('class:bottom-toolbar class:bottom-toolbar.text ' + token, text) for token, text in parts]


def snapshots(at=12):
    report = {'service_version': __version__, 'version_status': 'matched'}
    model = model_status_text({'default': PARAKEET, 'asr_model': PARAKEET, 'state': 'loaded'}, compact=True)
    session = dict(id='preview-001', title='Design review', state='recording', samples=2144000,
                   work={'queued': 2, 'running': 1, 'done': 4, 'failed': 0})
    with patch('aura.terminal.unicode_terminal', return_value=True), patch('aura.terminal.time.monotonic', return_value=at):
        idle = TerminalStatus()
        idle.model_status = model_status_text({'default': PARAKEET, 'state': 'unloaded'}, compact=True)
        result = [('Welcome', welcome(CLI_BANNER, 'local service', report, idle.model_status, (80, 32))
                   + prompt_message(80) + [('', '\n')] + toolbar_style(idle.toolbar(80, 32)))]
        for state in ('recording', 'paused', 'ready', 'disconnected'):
            view = TerminalStatus()
            view.model_status = model
            view.update({**session, 'state': 'recording' if state == 'disconnected' else state,
                         'work': {'queued': 0, 'running': 0, 'done': 7, 'failed': 0} if state == 'ready' else session['work']})
            view.audio.extend([.1, .2, .6, .4, .1, .3, .8, .2])
            view.queue.extend([0, 0, 1, 2, 1, 1])
            if state == 'disconnected':
                view.connected, view.error = False, 'Connection lost; session state unknown'
            result.append((state.title(), [('class:heading', CLI_BANNER + '\n\n'),
                           ('class:muted', 'Design review · preview-001\n\n'),
                           ('', 'Let us confirm the scope for this release.\n\n')]
                           + prompt_message(80) + [('', '\n')] + toolbar_style(view.toolbar(80, 24))))
        rows = [dict(id='a81f23c0-preview', title='Design review', state='ready', updated_at='2026-09-10'),
                dict(id='b92f34d1-preview', title='Research notes', state='paused', updated_at='2026-09-09')]
        result.append(('Sessions', [('class:accent', 'Reopen a session\n\n'), ('', 'Find session> \n')]
                       + toolbar_style(picker_rows(rows, '', 0, 80, 24))))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/cli-garden-preview'))
    parser.add_argument('--font', default='DejaVuSansMono.ttf')
    parser.add_argument('--palette', choices=PALETTES, default='slate')
    parser.add_argument('--background', choices=('light', 'dark'), default='light')
    args = parser.parse_args()
    from PIL import Image, ImageDraw, ImageFont
    from prompt_toolkit.utils import get_cwidth
    from prompt_toolkit.styles import default_ui_style, merge_styles
    font = ImageFont.truetype(args.font, 14)
    cell, line = font.getlength('M'), 21
    width = int(cell * 80) + 40
    style = merge_styles([default_ui_style(), terminal_style(args.palette)])
    background, foreground = ('#EEF0F4', '#414750') if args.background == 'light' else ('#151b1c', '#dddddd')

    def panel(title, fragments):
        height = line * (sum(text.count('\n') for _, text in fragments) + 1) + 70
        canvas = Image.new('RGB', (width, height), background)
        draw = ImageDraw.Draw(canvas)
        draw.text((20, 12), f'{title} · {args.palette} / {args.background} · synthetic UI', font=font, fill=foreground)
        x, y = 20, 48
        for token, text in fragments:
            attrs = style.get_attrs_for_style_str(token)
            fg = '#' + attrs.color if attrs.color not in ('', 'default') else foreground
            bg = '#' + attrs.bgcolor if attrs.bgcolor not in ('', 'default') else background
            if attrs.reverse:
                fg, bg = bg, fg
            for char in text:
                if char == '\n':
                    x, y = 20, y + line
                else:
                    if bg != background and get_cwidth(char):
                        draw.rectangle((x, y, x + cell * get_cwidth(char) - 1, y + line - 1), fill=bg)
                    draw.text((x, y), char, font=font, fill=fg)
                    x += cell * get_cwidth(char)
        return canvas

    args.output.mkdir(parents=True, exist_ok=True)
    screens = snapshots()
    panels = [panel(title, fragments) for title, fragments in screens]
    heights = [max(panels[i].height, panels[i + 1].height) for i in range(0, len(panels), 2)]
    sheet = Image.new('RGB', (width * 2, sum(heights)), background)
    for i, canvas in enumerate(panels):
        sheet.paste(canvas, ((i % 2) * width, sum(heights[:i // 2])))
    sheet.save(args.output / 'preview.png')
    frames = [panel(*snapshots(12 + i / 4)[1]) for i in range(8)]
    frames[0].save(args.output / 'recording.gif', save_all=True, append_images=frames[1:], duration=250, loop=0)
    (args.output / 'preview.txt').write_text('Synthetic UI states; no capture or inference.\n\n' + '\n\n'.join(
        title + '\n' + ''.join(text for _, text in fragments) for title, fragments in screens) + '\n', encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
