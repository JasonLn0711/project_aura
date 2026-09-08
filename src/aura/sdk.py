"""AURA's shared, Qt/CUDA-independent client API."""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid


def connection_file():
    root = Path(os.environ.get("AURA_DATA_DIR", Path.home() / ".local/share/project-aura")).expanduser()
    return root / "connection.json"


def local_connection(ensure=True):
    path = connection_file()
    def read():
        data = json.loads(path.read_text())
        os.kill(data["pid"], 0)
        return data
    try:
        return read()
    except (OSError, ValueError, KeyError):
        if not ensure:
            raise RuntimeError("AURA service is not running; start aura serve")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (path.parent / "service.log").open("ab") as log:
        subprocess.Popen([sys.executable, "-m", "aura.cli", "serve"], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    for _ in range(100):
        try:
            return read()
        except (OSError, ValueError, KeyError):
            time.sleep(0.1)
    raise RuntimeError(f"Service did not start; see {path.parent / 'service.log'}")


class AuraClient:
    def __init__(self, connection=None, *, ssh=None):
        self.tunnel = None
        self.ssh = ssh
        if ssh:
            if not isinstance(ssh, str) or ssh.startswith("-") or any(c.isspace() for c in ssh):
                raise ValueError("Use an SSH host alias or user@host")
            info = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", ssh, "aura connection-info --json"], check=True, capture_output=True, text=True, timeout=20)
            connection = json.loads(info.stdout)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            from urllib.parse import urlsplit
            remote_port = urlsplit(connection["url"]).port
            self.tunnel = subprocess.Popen(["ssh", "-N", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=10",
                "-o", "ServerAliveCountMax=2", "-L", f"127.0.0.1:{port}:127.0.0.1:{remote_port}", ssh])
            connection["url"] = f"ws://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if self.tunnel.poll() is not None:
                        raise RuntimeError("SSH tunnel failed")
                    time.sleep(0.1)
            else:
                self.tunnel.terminate()
                self.tunnel.wait(timeout=10)
                raise RuntimeError("SSH forwarding did not become ready")
        self.connection = connection or local_connection()
        self.lock = threading.Lock()
        self.socket = None
        self.audio_socket = None
        self.audio_session = None
        self.closed = False

    def _connect(self):
        from websockets.sync.client import connect
        ws = connect(self.connection["url"], additional_headers={"Authorization": "Bearer " + self.connection["token"]},
                     max_size=16 * 1024 * 1024, open_timeout=10, proxy=None)
        return ws

    @staticmethod
    def _result(ws):
        result = json.loads(ws.recv(timeout=30))
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["result"]

    def request(self, command, args=None, *, request_id=None):
        message = dict(version=1, id=request_id or str(uuid.uuid4()), command=command, args=args or {})
        with self.lock:
            if self.closed:
                raise RuntimeError("Client is closed")
            if self.socket is None:
                self.socket = self._connect()
            try:
                self.socket.send(json.dumps(message))
                return self._result(self.socket)
            except (TimeoutError, OSError):
                self.socket.close()
                self.socket = None
                raise

    def subscribe(self, session_id=None, after=0):
        with self._connect() as ws:
            ws.send(json.dumps(dict(version=1, id=str(uuid.uuid4()), command="subscribe",
                args={"session_id": session_id, "after": after})))
            while not self.closed:
                try:
                    value = json.loads(ws.recv(timeout=1))
                except TimeoutError:
                    continue
                if "error" in value:
                    raise RuntimeError(value["error"])
                yield value

    def open_audio(self, session_id, tracks):
        self.audio_socket = self._connect()
        self.audio_socket.send(json.dumps(dict(version=1, id=str(uuid.uuid4()), command="audio.open",
            args={"session_id": session_id, "tracks": tracks})))
        result = self._result(self.audio_socket)
        self.audio_session = session_id
        return result

    def send_audio(self, session_id, sequence, pcm):
        if self.audio_socket is None or session_id != self.audio_session:
            raise RuntimeError("Open an audio stream first")
        self.audio_socket.send(struct.pack("<Q", sequence) + pcm)
        return self._result(self.audio_socket)

    def upload(self, path):
        path = Path(path)
        with self._connect() as ws, path.open("rb") as f:
            ws.send(json.dumps(dict(version=1, id=str(uuid.uuid4()), command="upload",
                args={"name": path.name, "size": path.stat().st_size})))
            self._result(ws)
            while block := f.read(1024 * 1024):
                ws.send(block)
            ws.send("end")
            return self._result(ws)["path"]

    def download(self, session_id, fmt, destination):
        destination = Path(destination)
        if destination.exists():
            raise ValueError("Export destination already exists")
        temp = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".part")
        try:
            with self._connect() as ws, temp.open("xb") as f:
                ws.send(json.dumps(dict(version=1, id=str(uuid.uuid4()), command="download",
                    args={"session_id": session_id, "format": fmt})))
                while True:
                    block = ws.recv(timeout=30)
                    if isinstance(block, str):
                        result = json.loads(block)
                        if "error" in result:
                            raise RuntimeError(result["error"])
                        break
                    f.write(block)
                f.flush()
                os.fsync(f.fileno())
            # Exclusive destination creation also protects a concurrent export.
            os.link(temp, destination)
        finally:
            temp.unlink(missing_ok=True)
        return destination

    def close(self):
        self.closed = True
        for ws in (self.socket, self.audio_socket):
            if ws:
                ws.close()
        if self.tunnel:
            self.tunnel.terminate()
            self.tunnel.wait()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
