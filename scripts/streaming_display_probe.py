#!/usr/bin/env python3
"""Observe real CLI/Qt rendering without saving transcript text in timing traces."""
import argparse
import json
import sys
import time
from pathlib import Path

from aura.sdk import AuraClient


class DisplayReceipt:
    def __init__(self, path):
        self.output = path.open('x')
        self.seen = set()

    def displayed(self, session):
        ranges = []
        for segment in session.get('segments', []):
            span = (segment['start_ms'], segment['end_ms'])
            if segment.get('text', '').strip() and span not in self.seen:
                self.seen.add(span)
                ranges.append(span)
        if ranges:
            self.output.write(json.dumps(dict(event='text_displayed', monotonic=time.monotonic(), ranges=ranges)) + '\n')
            self.output.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--view', choices=('cli', 'gui'), required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = DisplayReceipt(args.output)
    if args.view == 'cli':
        from aura.cli import attach
        class Client(AuraClient):
            def request(self, *args, **kwargs):
                self.last = super().request(*args, **kwargs)
                return self.last
        class Sink:
            def write(self, text):
                if text: receipt.displayed(client.last)
                return len(text)
            def flush(self): pass
        import contextlib
        with Client() as client, contextlib.redirect_stdout(Sink()):
            return attach(client, args.session)
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from aura.ui.transcription_tab import TranscriptionTab
    app = QApplication([])
    class Tab(TranscriptionTab):
        def render(self, session):
            super().render(session)
            if self.text_area.toPlainText() == session['transcript']:
                receipt.displayed(session)
            if session['state'] in ('ready', 'failed', 'recoverable'):
                QTimer.singleShot(0, app.quit)
    tab = Tab()
    with AuraClient() as client:
        tab.current = client.request('get', {'session_id': args.session})
    tab.show()
    # ServiceWorker performs the production polling and receive/render path.
    QTimer.singleShot(0, lambda: tab.render(tab.current))
    try:
        app.exec()
    finally:
        tab.stop_threads()
        receipt.output.close()
    return 0 if tab.current['state'] == 'ready' else 1


if __name__ == '__main__':
    raise SystemExit(main())
