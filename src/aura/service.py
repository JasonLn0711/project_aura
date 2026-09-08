"""Authenticated loopback transport; remote access uses OpenSSH."""
import hmac
import json
import os
from pathlib import Path
import secrets
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid

from aura.session_core import SessionCore, default_root


def serve(root=None, port=0, core=None):
    from websockets.sync.server import serve as websocket_serve
    root = Path(root or default_root())
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    # A held lock prevents two GUIs racing to launch two model owners.
    lockfile = (root / "service.lock").open("a+")
    if sys.platform != "win32":
        import fcntl
        try:
            fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lockfile.close()
            return
    else:
        import msvcrt
        lockfile.write("0")
        lockfile.flush()
        lockfile.seek(0)
        try:
            msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            lockfile.close()
            return
    token = secrets.token_urlsafe(32)
    core = core or SessionCore(root)
    stop = threading.Event()
    connection = None

    def auth(conn, request):
        supplied = request.headers.get("Authorization", "")
        if request.headers.get("Origin") or not hmac.compare_digest(supplied, "Bearer " + token):
            return conn.respond(401, "Authentication required\n")

    def producer(s):
        with (root / "capture.log").open("ab") as log:
            subprocess.Popen([sys.executable, "-m", "aura.cli", "capture", s["id"]],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                env={**os.environ, "AURA_DATA_DIR": str(root)})

    def handler(ws):
        sid = None
        tracks = None
        try:
            for message in ws:
                request_id = None
                try:
                    if isinstance(message, bytes):
                        if sid is None or len(message) < 8:
                            raise ValueError("Open an audio stream before sending PCM")
                        result = core.ingest(sid, struct.unpack("<Q", message[:8])[0], message[8:], tracks)
                    else:
                        req = json.loads(message)
                        if not isinstance(req, dict) or req.get("version") != 1:
                            raise ValueError("Unsupported protocol version")
                        request_id = req.get("id")
                        if not isinstance(request_id, str) or len(request_id) > 100:
                            raise ValueError("A bounded request ID is required")
                        command, args = req["command"], req.get("args", {})
                        if not isinstance(command, str) or not isinstance(args, dict):
                            raise ValueError("Command must be a string and arguments an object")
                        if command == "subscribe":
                            from websockets.protocol import State
                            after = int(args.get("after", 0))
                            while not stop.is_set() and ws.state is State.OPEN:
                                events = core.events(args.get("session_id"), after)
                                for event in events:
                                    ws.send(json.dumps(event))
                                    after = event["seq"]
                                if not events:
                                    time.sleep(0.1)
                            return
                        if command == "upload":
                            name, size = args["name"], args["size"]
                            from aura.config import SUPPORTED_IMPORT_EXTENSIONS
                            if not isinstance(name, str) or Path(name).suffix.lower().lstrip(".") not in SUPPORTED_IMPORT_EXTENSIONS:
                                raise ValueError("Unsupported media extension")
                            if type(size) is not int or not 0 < size <= 8 * 1024**3:
                                raise ValueError("Uploads must be between 1 byte and 8 GiB")
                            directory = root / "uploads"
                            directory.mkdir(mode=0o700, exist_ok=True)
                            path = directory / (uuid.uuid4().hex + Path(name).suffix)
                            ws.send(json.dumps({"result": "ready"}))
                            count = 0
                            try:
                                with path.open("xb") as f:
                                    for block in ws:
                                        if block == "end":
                                            break
                                        if not isinstance(block, bytes) or count + len(block) > size:
                                            raise ValueError("Upload size mismatch")
                                        f.write(block)
                                        count += len(block)
                                    f.flush()
                                    os.fsync(f.fileno())
                                if count != size:
                                    raise ValueError("Upload was interrupted")
                            except BaseException:
                                path.unlink(missing_ok=True)
                                raise
                            result = {"path": str(path)}
                        elif command == "download":
                            result = core.request("export", args)
                            if "text" in result:
                                ws.send(result["text"].encode("utf-8"))
                            else:
                                with open(result["path"], "rb") as f:
                                    while block := f.read(1024 * 1024):
                                        ws.send(block)
                            result = {"complete": True}
                        elif command == "audio.open":
                            tracks = args["tracks"]
                            if not isinstance(tracks, list) or not tracks or any(t not in ("mixed", "microphone", "system") for t in tracks) or len(set(tracks)) != len(tracks) or "mixed" not in tracks:
                                raise ValueError("Invalid audio tracks")
                            if sid is not None:
                                raise ValueError("This connection already owns a producer")
                            result = core.request("producer.open", {"session_id": args["session_id"]})
                            sid = args["session_id"]
                        else:
                            if command.startswith("producer.") and command not in ("producer.paused", "producer.stopped"):
                                raise ValueError("Producer control requires an audio connection")
                            result = core.request(command, args, request_id=request_id)
                    ws.send(json.dumps({"id": request_id, "result": result}))
                except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
                    ws.send(json.dumps({"id": request_id, "error": str(exc)}))
        finally:
            if sid:
                core.disconnected(sid)

    with websocket_serve(handler, "127.0.0.1", port, process_request=auth, max_size=16 * 1024 * 1024, max_queue=2) as server:
        connection = dict(url=f"ws://127.0.0.1:{server.socket.getsockname()[1]}", token=token, pid=os.getpid(), protocol=1)
        path = root / "connection.json"
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
            os.chmod(tmp, 0o600)
            json.dump(connection, f)
        os.replace(tmp, path)
        launched = set()
        def launch_captures():
            while not stop.wait(0.1):
                for s in core.request("sessions"):
                    if s["state"] == "recording" and s["capture_location"] == "server" and not s["producer_connected"] and s["id"] not in launched:
                        launched.add(s["id"])
                        producer(s)
                    if s["state"] == "paused" and not s["producer_connected"]:
                        launched.discard(s["id"])
        threading.Thread(target=launch_captures, daemon=True).start()
        def shutdown(*_):
            stop.set()
            server.shutdown()
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, shutdown)
            signal.signal(signal.SIGINT, shutdown)
        try:
            server.serve_forever()
        finally:
            stop.set()
            core.close()
            path.unlink(missing_ok=True)
            lockfile.close()
