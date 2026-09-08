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


def parser():
    p = argparse.ArgumentParser(prog="aura", description="Record, transcribe, and control shared AURA sessions")
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
            sub.add_argument("--consent", action="store_true", help="Confirm permission to record the selected sources")
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
            print(f'{s["id"]}  {s["state"]:12} {s["title"]}')
    elif isinstance(value, dict) and "id" in value:
        print(f'{value["id"]}  {value["state"]}  {value["title"]}', flush=True)
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
                print(text[len(previous):] if text.startswith(previous) else text, end="", flush=True)
                previous = text
            if s["state"] in ("ready", "failed", "recoverable"):
                if s.get("error"):
                    print(s["error"], file=sys.stderr)
                return 1 if s["state"] != "ready" else 0
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Detached; session remains available.", file=sys.stderr)
        return 0


def execute(client, args):
    command = args.command
    if command == "attach":
        return attach(client, args.session_id, args.json)
    if command == "export":
        path = args.output or Path(f"{args.session_id}.{args.format}")
        client.download(args.session_id, args.format, path)
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
            values.update(source=args.source, capture_location=args.capture_location, consent=args.consent)
        else:
            values["path"] = client.upload(args.path)
    if command == "schedule":
        values.update(start_at=args.start_at, stop_at=args.stop_at)
    result = client.request(command, values)
    show(result, args.json)
    if command == "record" and args.capture_location == "client":
        start_client_capture(result["id"], args.ssh)
    if command in ("record", "transcribe") and not args.detach:
        return attach(client, result["id"], args.json)
    return 0


def interactive(client, ssh=None):
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.patch_stdout import patch_stdout
    commands = ["/record", "/schedule", "/sessions", "/attach", "/pause", "/resume", "/stop", "/refine", "/export", "/transcribe", "/detach", "/help", "/quit"]
    prompt = PromptSession(completer=WordCompleter(commands), complete_while_typing=False)
    selected = {"id": None, "text": "", "state": ""}
    done = threading.Event()
    def follow():
        try:
            with AuraClient(connection=client.connection) as watcher:
                while not done.wait(0.3):
                    if not selected["id"]:
                        continue
                    s = watcher.request("get", {"session_id": selected["id"]})
                    if s["state"] != selected["state"]:
                        print(f'[{s["state"]}] {s["title"]} — {s["id"]}')
                        selected["state"] = s["state"]
                    if s["transcript"] != selected["text"]:
                        text = s["transcript"]
                        print(text[len(selected["text"]):] if text.startswith(selected["text"]) else text)
                        selected["text"] = text
        except Exception as exc:
            print(f"Connection: {exc}")
    print("AURA · shared transcription workspace\n/help for commands · /record --consent to start")
    with patch_stdout():
        thread = threading.Thread(target=follow, daemon=True)
        thread.start()
        try:
            while True:
                try:
                    line = prompt.prompt("aura> ").strip()
                    words = shlex.split(line)
                    if not words:
                        continue
                    command = words[0].lstrip("/")
                    if command in ("quit", "exit"):
                        break
                    if command == "help":
                        print(" ".join(commands))
                        print("/record --source microphone --consent · /attach ID · /pause · /resume · /stop\n/export ID --format txt --output meeting.txt")
                        continue
                    if command == "detach":
                        selected.update(id=None, text="", state="")
                        continue
                    if command == "attach":
                        sid = words[1]
                        client.request("get", {"session_id": sid})
                        selected.update(id=sid, text="", state="")
                        continue
                    words[0] = command
                    if command in ("pause", "resume", "stop", "refine", "export") and len(words) == 1:
                        if not selected["id"]:
                            raise ValueError("Attach a session first")
                        words.append(selected["id"])
                    if command in ("record", "transcribe"):
                        words.append("--detach")
                    args = parser().parse_args(words)
                    args.ssh = ssh
                    execute(client, args)
                    if command in ("record", "transcribe"):
                        s = client.request("sessions")[0]
                        selected.update(id=s["id"], text="", state="")
                except KeyboardInterrupt:
                    selected.update(id=None, text="", state="")
                    print("Detached.")
                except EOFError:
                    break
                except SystemExit:
                    continue
                except (ValueError, RuntimeError, OSError, IndexError) as exc:
                    print(str(exc))
        finally:
            done.set()
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
        with AuraClient(ssh=args.ssh) as client:
            if args.command is None:
                if not sys.stdin.isatty():
                    parser().print_help()
                    return 2
                return interactive(client, args.ssh)
            return execute(client, args)
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"AURA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
