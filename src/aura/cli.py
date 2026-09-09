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
    subs.add_parser("doctor")
    models = subs.add_parser("models", help="Manage server-local ASR weights")
    downloads = models.add_subparsers(dest="model_command", required=True)
    from aura.asr.models import PARAKEET, MODEL_KEYS
    downloads.add_parser("download").add_argument("model", choices=(PARAKEET,))
    subs.add_parser("model", help="Show, preload, switch or unload ASR").add_argument("selection", nargs="?", default="status", choices=(*MODEL_KEYS, "status", "load", "unload"))
    resume = subs.add_parser("resume", help="Reopen a saved workspace; audio capture stays unchanged",
                             description="Reopen saved transcripts and controls. Use unpause to restart paused audio capture.")
    resume.add_argument("session_id", nargs="?")
    resume.add_argument("--all", action="store_true", help="Show all sessions on the selected service")
    resume.add_argument("--last", action="store_true", help="Reopen the most recently updated session")
    for command in ("attach", "inspect", "pause", "unpause", "stop", "refine", "recover", "capture"):
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
        sub.add_argument("--model", choices=MODEL_KEYS, default=None)
        sub.add_argument("--language", choices=("zh", "en", "auto"), default=None)
        sub.add_argument("--hotwords-file", type=Path)
        sub.add_argument("--detach", action="store_true")
    export = subs.add_parser("export")
    export.add_argument("session_id")
    export.add_argument("--format", choices=("txt", "refined", "recovered", "json", "wav", "m4a", "mp3"), default="txt")
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
            print(safe_text(f'{s["id"]}  {s["state"]:12} {s.get("updated_at", s.get("created_at", ""))}  {s["title"]}'))
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


def inspect_session(session, machine=False):
    if machine:
        show(session, True)
    else:
        fields = ("id", "title", "state", "created_at", "updated_at", "source", "capture_location",
                  "error", "capture_error", "asr_issues", "work", "artifacts")
        print(safe_text(json.dumps({k: session[k] for k in fields if k in session}, ensure_ascii=False, indent=2)))


def diagnostics(client, host=None):
    capabilities = client.request("capabilities")
    service_version = capabilities.get("service_version")
    return dict(client_version=__version__, service_version=service_version or "unknown",
                connection="connected", host=host or client.ssh or "local service",
                version_status="unknown" if not service_version else "matched" if service_version == __version__ else "mismatch",
                capabilities={k: capabilities[k] for k in ("model_control", "recover", "asr_models", "protocol", "ffmpeg", "profiles", "capture_format", "single_owner", "deepfilternet", "clearvoice") if k in capabilities},
                diagnostics=capabilities.get("diagnostics", {}),
                guidance="Finish active recordings and jobs before restarting an older service. Device capture requires its own check.")


def resume_selection(client, args, *, terminal):
    if args.session_id or args.last:
        return client.resolve_session(args.session_id, last=args.last)
    rows = client.session_summaries()
    if not terminal or args.json:
        show(rows, args.json)
        return None
    from aura.terminal import pick_session
    sid = pick_session(rows)
    return client.resolve_session(sid) if sid else None


def model_status_text(result):
    state = result["state"]
    text = f'ASR: {result.get("asr_model") or result["default"]} · {state} · default: {result["default"]}'
    if state == "unloaded":
        text += " · loads on /record or /transcribe; /model load preloads"
    if result.get("error"):
        text += " · " + str(result["error"])
    return safe_text(text)


def execute(client, args, *, on_progress=None):
    command = args.command
    if command == "model":
        if not client.request("capabilities").get("model_control"):
            raise RuntimeError("This service does not have /model controls. Finish active work, then restart the service and CLI.")
        action = args.selection
        result = client.request("model." + (action if action in ("status", "unload") else "load"),
                                {} if action in ("status", "load", "unload") else {"asr_model": action})
        if args.json:
            show(result, True)
        else:
            print(model_status_text(result), flush=True)
        return result
    if command == "recover" and not client.request("capabilities").get("recover"):
        raise RuntimeError("This service has no recovery controls; finish active work, then restart the service and CLI.")
    if command == "sessions":
        show(client.session_summaries(), args.json)
        return 0
    if command == "doctor":
        result = diagnostics(client, args.ssh)
        if args.json:
            show(result, True)
        else:
            print(safe_text(json.dumps(result, ensure_ascii=False, indent=2)))
        return 0
    if command in ("inspect", "unpause", "attach", "recover"):
        session = client.resolve_session(args.session_id)
        args.session_id = session["id"]
        if command == "inspect":
            inspect_session(session, args.json)
            return 0
        if command == "unpause":
            command = "resume"
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
        if args.model is not None:
            options["asr_model"] = args.model
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


def interactive(client, ssh=None, initial=None):
    import queue
    import shutil
    from prompt_toolkit import PromptSession
    from aura.completion import WorkspaceCompleter
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.styles import Style
    from aura.terminal import TerminalStatus, safe_text
    commands = ["/recover", "/model", "/record", "/schedule", "/sessions", "/attach", "/pause", "/resume", "/unpause", "/inspect", "/doctor", "/stop", "/refine", "/export", "/transcribe", "/status", "/graphs", "/detach", "/help", "/quit"]
    view = TerminalStatus()
    prompt = PromptSession(completer=WorkspaceCompleter(parser(), commands), complete_while_typing=False,
        bottom_toolbar=lambda: view.toolbar(shutil.get_terminal_size().columns), refresh_interval=.25,
        style=Style.from_dict({'accent': '#48c7b8', 'owl': '#e4b56b', 'muted': '#888888', 'error': '#ef7777'}))
    selected = {"id": None, "text": "", "state": "", "error": ""}
    done = threading.Event()
    pending = queue.Queue(maxsize=8)
    def select(sid):
        selected.update(id=sid, text="", state="", error="")
        view.session = None
        view.audio.clear()
        view.queue.clear()
    if initial:
        select(initial['id'])
        view.update(initial)
    def follow():
        last_model = None
        last_model_poll = 0.0
        with AuraClient(connection=client.connection) as watcher:
            while not done.wait(.25):
                sid = selected['id']
                try:
                    if report["capabilities"].get("model_control") and time.monotonic() - last_model_poll >= 1:
                        last_model_poll = time.monotonic()
                        state = watcher.request("model.status")
                        model_line = model_status_text(state)
                        view.model_status = model_line
                        if model_line != last_model:
                            print(model_line)
                            last_model = model_line
                    if not sid:
                        continue
                    s = watcher.request("get", {"session_id": sid})
                    if selected['id'] != sid:
                        continue
                    view.update(s)
                    if s['state'] != selected['state']:
                        print(safe_text(f'[{s["state"]}] {s["title"]} · {s["id"]}'))
                        selected['state'] = s['state']
                    if s.get('error') and s['error'] != selected['error']:
                        print(safe_text(f'AURA: {s["error"]}'))
                    selected['error'] = s.get('error') or ''
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
    report = diagnostics(client)
    print("  /\\_/\\    " + CLI_BANNER)
    print(" ( o.o )   Connected: " + safe_text(ssh or 'local service'))
    print("  > ^ <    /help · /model · /record · /resume --all")
    print(safe_text(f'Service version: {report["service_version"]} · {report["version_status"]}'))
    if not report['capabilities'].get('model_control'):
        print('ASR controls are unavailable in this running service. Finish active work, then restart the service and CLI.')
    if report['version_status'] != 'matched':
        print(report['guidance'])
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
                        print('/recover [ID] retries saved gaps once; /export ID --format recovered exports recovered text')
                        print('Tab completes commands, options, model names and local paths; press Tab again to cycle choices.')
                        print('/model shows ASR status · /model breeze or /model parakeet-tdt-0.6b-v2 selects and preloads')
                        print('/model load preloads the default · /model unload releases GPU memory · finish active work before switching')
                        print('/record --model MODEL and /transcribe FILE --model MODEL override one new session')
                        print('/resume [ID|--last|--all] reopens history · /unpause [ID] restarts paused capture')
                        print('/record --source microphone · /inspect [ID] · /doctor · /stop · /export ID --output meeting.txt')
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
                    if command == 'resume':
                        args = parser().parse_args(['resume', *words[1:]])
                        s = resume_selection(client, args, terminal=True)
                        if s:
                            select(s['id'])
                            view.update(s)
                        continue
                    if command == 'attach':
                        if len(words) != 2:
                            raise ValueError('Use /attach SESSION_ID')
                        s = client.resolve_session(words[1])
                        select(s['id'])
                        view.update(s)
                        continue
                    words[0] = command
                    if command in ('pause', 'unpause', 'inspect', 'stop', 'refine', 'recover', 'export') and len(words) == 1:
                        if not selected['id']:
                            raise ValueError('Attach a session first')
                        words.append(selected['id'])
                    if command in ('record', 'transcribe'):
                        words.append('--detach')
                    args = parser().parse_args(words)
                    if args.command not in ('model', 'record', 'transcribe', 'schedule', 'sessions', 'pause', 'unpause', 'inspect', 'doctor', 'stop', 'refine', 'recover', 'export', 'capabilities'):
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
        if args.command == "models":
            if args.ssh:
                raise ValueError("Run model downloads locally on the inference server.")
            from aura.asr.models import download_model
            show({"model": args.model, "checkpoint": download_model(args.model)}, args.json)
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
            if args.command == "resume":
                terminal = sys.stdin.isatty() and sys.stdout.isatty()
                session = resume_selection(client, args, terminal=terminal)
                if session:
                    if terminal and not args.json:
                        return interactive(client, args.ssh, initial=session)
                    inspect_session(session, args.json)
                return 0
            result = execute(client, args)
            return result if isinstance(result, int) else 0
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"AURA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
