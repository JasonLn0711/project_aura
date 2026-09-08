"""Interactive and scriptable frontends for the shared AURA SDK."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time

from aura.sdk import AuraClient, local_connection
from aura.metadata import __version__
from aura.terminal import safe_text

CLI_BANNER = f"AURA v{__version__} · shared transcription workspace"


def parser():
    p = argparse.ArgumentParser(prog="aura", description="Record, transcribe, and control shared AURA sessions")
    p.add_argument("--version", action="version", version=f"AURA {__version__}")
    p.add_argument("--ssh", metavar="HOST")
    p.add_argument("--json", action="store_true")
    subs = p.add_subparsers(dest="command")
    subs.add_parser("gui")
    server = subs.add_parser("serve")
    server.add_argument("--port", type=int, default=0)
    subs.add_parser("connection-info").add_argument("--json", action="store_true")
    subs.add_parser("sessions")
    subs.add_parser("capabilities")
    for command in ("attach", "pause", "resume", "stop", "refine", "capture"):
        sub = subs.add_parser(command)
        sub.add_argument("session_id")
    for command in ("record", "transcribe", "schedule"):
        sub = subs.add_parser(command)
        if command == "transcribe":
            sub.add_argument("path")
        else:
            sub.add_argument("--source", choices=("microphone", "system", "system_microphone"), default="system_microphone")
            sub.add_argument("--capture-location", choices=("server", "client"), default="server")
            sub.add_argument("--consent", action="store_true", help=argparse.SUPPRESS)
        if command == "schedule":
            sub.add_argument("--start-at", required=True, help="ISO 8601 with timezone")
            sub.add_argument("--stop-at", required=True, help="ISO 8601 with timezone")
        sub.add_argument("--title", default="Meeting")
        sub.add_argument("--profile", choices=("off", "light", "medium", "far-speaker", "rescue-offline"), default=None)
        sub.add_argument("--language", choices=("zh", "en", "auto"), default=None)
        sub.add_argument("--hotwords-file", type=Path)
        sub.add_argument("--detach", action="store_true")
    export = subs.add_parser("export")
    export.add_argument("session_id")
    export.add_argument("--format", choices=("txt", "refined", "json", "wav", "m4a", "mp3"), default="txt")
    export.add_argument("--output", type=Path)
    return p


def start_client_capture(session_id, ssh=None):
    from aura.sdk import connection_file
    command = [sys.executable, "-m", "aura.cli"]
    if ssh:
        command += ["--ssh", ssh]
    command += ["capture", session_id]
    root = connection_file().parent
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / "capture.log").open("ab") as log:
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


def show(value, machine=False):
    if machine:
        print(json.dumps(value, ensure_ascii=False), flush=True)
    elif isinstance(value, list):
        for s in value:
            print(safe_text(f'{s["id"]}  {s["state"]:12} {s["title"]}'))
    elif isinstance(value, dict) and "id" in value:
        print(safe_text(f'{value["id"]}  {value["state"]}  {value["title"]}'), flush=True)
        if value.get("error"):
            print(value["error"], file=sys.stderr)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def attach(client, sid, machine=False):
    previous = ""
    try:
        while True:
            s = client.request("get", {"session_id": sid})
            if machine:
                show(s, True)
            elif s["transcript"] != previous:
                text = s["transcript"]
                print(safe_text(text[len(previous):] if text.startswith(previous) else text), end="", flush=True)
                previous = text
            if s["state"] in ("ready", "failed", "recoverable"):
                if s.get("error"):
                    print(s["error"], file=sys.stderr)
                return 1 if s["state"] != "ready" else 0
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Detached; session remains available.", file=sys.stderr)
        return 0


def execute(client, args, *, on_progress=None):
    command = args.command
    if command == "attach":
        return attach(client, args.session_id, args.json)
    if command == "export":
        path = args.output or Path(f"{args.session_id}.{args.format}")
        client.download(args.session_id, args.format, path, on_progress=on_progress)
        show({"export": str(path)}, args.json)
        return 0
    values = {}
    if hasattr(args, "session_id"):
        values["session_id"] = args.session_id
    if command in ("record", "transcribe", "schedule"):
        options = {}
        if args.profile is not None:
            options["profile"] = args.profile
        if args.language is not None:
            options["language"] = None if args.language == "auto" else args.language
        if args.hotwords_file:
            options["hotwords"] = " ".join(dict.fromkeys(args.hotwords_file.read_text(encoding="utf-8-sig").splitlines()))
        values.update(title=args.title, options=options)
        if command in ("record", "schedule"):
            values.update(source=args.source, capture_location=args.capture_location)
        else:
            values["path"] = client.upload(args.path, on_progress=on_progress)
    if command == "schedule":
        values.update(start_at=args.start_at, stop_at=args.stop_at)
    result = client.request(command, values)
    show(result, args.json)
    if command == "record" and args.capture_location == "client":
        start_client_capture(result["id"], args.ssh)
    if command in ("record", "transcribe") and not args.detach:
        return attach(client, result["id"], args.json)
    return result if command in ("record", "transcribe") else 0


def interactive(client, ssh=None):
    import queue
    import shutil
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.styles import Style
    from aura.terminal import TerminalStatus, safe_text
    commands = ["/record", "/schedule", "/sessions", "/attach", "/pause", "/resume", "/stop", "/refine", "/export", "/transcribe", "/status", "/graphs", "/detach", "/help", "/quit"]
    view = TerminalStatus()
    prompt = PromptSession(completer=WordCompleter(commands), complete_while_typing=False,
        bottom_toolbar=lambda: view.toolbar(shutil.get_terminal_size().columns), refresh_interval=.25,
        style=Style.from_dict({'accent': '#48c7b8', 'owl': '#e4b56b', 'muted': '#888888', 'error': '#ef7777'}))
    selected = {"id": None, "text": "", "state": ""}
    done = threading.Event()
    pending = queue.Queue(maxsize=8)
    def select(sid):
        selected.update(id=sid, text="", state="")
        view.session = None
        view.audio.clear()
        view.queue.clear()
    def follow():
        with AuraClient(connection=client.connection) as watcher:
            while not done.wait(.25):
                sid = selected['id']
                if not sid:
                    continue
                try:
                    s = watcher.request("get", {"session_id": sid})
                    if selected['id'] != sid:
                        continue
                    view.update(s)
                    if s['state'] != selected['state']:
                        print(safe_text(f'[{s["state"]}] {s["title"]} · {s["id"]}'))
                        selected['state'] = s['state']
                    if s['transcript'] != selected['text']:
                        text = s['transcript']
                        print(safe_text(text[len(selected['text']):] if text.startswith(selected['text']) else text))
                        selected['text'] = text
                except Exception as exc:
                    view.connected = False
                    view.error = str(exc)
                    break
    def operate():
        with AuraClient(connection=client.connection) as operator:
            while not done.is_set():
                try:
                    args = pending.get(timeout=.2)
                except queue.Empty:
                    continue
                try:
                    result = execute(operator, args, on_progress=view.progress)
                    if isinstance(result, dict) and 'id' in result:
                        select(result['id'])
                except Exception as exc:
                    print(safe_text(f'AURA: {exc}'))
                finally:
                    view.transfer = None
                    pending.task_done()
    print("  /\\_/\\    " + CLI_BANNER)
    print(" ( o.o )   Connected: " + safe_text(ssh or 'local service'))
    print("  > ^ <    /help for commands · /record to start")
    with patch_stdout():
        threads = [threading.Thread(target=f, daemon=True) for f in (follow, operate)]
        for thread in threads:
            thread.start()
        try:
            while True:
                try:
                    words = shlex.split(prompt.prompt("aura> ").strip())
                    if not words:
                        continue
                    command = words[0].lstrip('/')
                    if command in ('quit', 'exit'):
                        break
                    if command == 'help':
                        print(' '.join(commands))
                        print('/record --source microphone · /attach ID · /stop · /export ID --output meeting.txt')
                        continue
                    if command == 'graphs':
                        if len(words) != 2 or words[1] not in ('on', 'off'):
                            raise ValueError('Use /graphs on or /graphs off')
                        view.graphs = words[1] == 'on'
                        continue
                    if command == 'status':
                        print('\n'.join(text for _, text in view.lines(shutil.get_terminal_size().columns)))
                        continue
                    if command == 'detach':
                        select(None)
                        continue
                    if command == 'attach':
                        s = client.request('get', {'session_id': words[1]})
                        select(s['id'])
                        view.update(s)
                        continue
                    words[0] = command
                    if command in ('pause', 'resume', 'stop', 'refine', 'export') and len(words) == 1:
                        if not selected['id']:
                            raise ValueError('Attach a session first')
                        words.append(selected['id'])
                    if command in ('record', 'transcribe'):
                        words.append('--detach')
                    args = parser().parse_args(words)
                    if args.command not in ('record', 'transcribe', 'schedule', 'sessions', 'pause', 'resume', 'stop', 'refine', 'export', 'capabilities'):
                        raise ValueError('Use /help for workspace commands')
                    args.ssh = ssh
                    pending.put_nowait(args)
                except KeyboardInterrupt:
                    select(None)
                    print('Detached; recording remains controlled by /stop.')
                except EOFError:
                    break
                except SystemExit:
                    continue
                except queue.Full:
                    print('Command queue full; wait for the current operation.')
                except (ValueError, RuntimeError, OSError, IndexError) as exc:
                    print(safe_text(exc))
        finally:
            done.set()
            for thread in threads:
                thread.join(timeout=2)
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "serve":
            from aura.service import serve
            serve(port=args.port)
            return 0
        if args.command == "connection-info":
            print(json.dumps(local_connection()))
            return 0
        if args.command == "gui":
            from aura.app import main as gui
            return gui()
        if args.command == "capture":
            from aura.producer import capture
            capture(args.session_id, args.ssh)
            return 0
        if args.command is None and not args.json and not sys.stdin.isatty():
            parser().print_help()
            return 2
        with AuraClient(ssh=args.ssh) as client:
            if args.command is None and args.json:
                show(client.request("sessions"), True)
                return 0
            if args.command is None:
                if not sys.stdin.isatty():
                    parser().print_help()
                    return 2
                return interactive(client, args.ssh)
            result = execute(client, args)
            return result if isinstance(result, int) else 0
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"AURA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
