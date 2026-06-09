from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from summary.field_schemas import OLLAMA_MODEL_TAG


DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_READY_TIMEOUT_SEC = 20


class OllamaRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaRuntimeStatus:
    server_running: bool
    model_available: bool
    ollama_command_available: bool
    model_tag: str
    host: str
    message: str


def validate_localhost_host(host: str) -> None:
    if not host.startswith("http://localhost:") and not host.startswith("http://127.0.0.1:"):
        raise OllamaRuntimeError("Ollama host must be localhost.")


def ollama_tags(host: str = DEFAULT_OLLAMA_HOST, timeout_sec: int = 5) -> dict:
    validate_localhost_host(host)
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/tags",
        headers={"Content-Type": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def check_ollama_server(host: str = DEFAULT_OLLAMA_HOST) -> bool:
    try:
        ollama_tags(host, timeout_sec=2)
        return True
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return False


def check_ollama_command() -> bool:
    return shutil.which("ollama") is not None


def start_ollama_server() -> subprocess.Popen | None:
    if not check_ollama_command():
        return None
    return subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def wait_for_ollama_ready(
    host: str = DEFAULT_OLLAMA_HOST,
    timeout_sec: int = DEFAULT_OLLAMA_READY_TIMEOUT_SEC,
    poll_interval_sec: float = 0.5,
) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if check_ollama_server(host):
            return True
        time.sleep(poll_interval_sec)
    return check_ollama_server(host)


def check_model_tag(model_tag: str = OLLAMA_MODEL_TAG, host: str = DEFAULT_OLLAMA_HOST) -> bool:
    try:
        tags = ollama_tags(host, timeout_sec=5)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return False
    models = tags.get("models") or []
    names = {str(model.get("name") or "") for model in models if isinstance(model, dict)}
    return model_tag in names


def pull_model(
    model_tag: str = OLLAMA_MODEL_TAG,
    progress_callback: Callable[[str], None] | None = None,
) -> bool:
    if not check_ollama_command():
        if progress_callback:
            progress_callback("Ollama command was not found.")
        return False

    process = subprocess.Popen(
        ["ollama", "pull", model_tag],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is not None:
        for line in process.stdout:
            if progress_callback:
                progress_callback(line.rstrip())
    return process.wait() == 0


def ensure_ollama_ready(
    auto_start: bool = True,
    host: str = DEFAULT_OLLAMA_HOST,
    model_tag: str = OLLAMA_MODEL_TAG,
    timeout_sec: int = DEFAULT_OLLAMA_READY_TIMEOUT_SEC,
) -> OllamaRuntimeStatus:
    validate_localhost_host(host)
    command_available = check_ollama_command()
    server_running = check_ollama_server(host)

    if not server_running and not auto_start:
        return OllamaRuntimeStatus(
            server_running=False,
            model_available=False,
            ollama_command_available=command_available,
            model_tag=model_tag,
            host=host,
            message="Ollama local runner unavailable.",
        )

    if not server_running:
        if not command_available:
            return OllamaRuntimeStatus(
                server_running=False,
                model_available=False,
                ollama_command_available=False,
                model_tag=model_tag,
                host=host,
                message="Ollama command was not found. Install Ollama and restart AURA, or add ollama to PATH.",
            )
        start_ollama_server()
        server_running = wait_for_ollama_ready(host=host, timeout_sec=timeout_sec)
        if not server_running:
            return OllamaRuntimeStatus(
                server_running=False,
                model_available=False,
                ollama_command_available=True,
                model_tag=model_tag,
                host=host,
                message=f"AURA started ollama serve, but localhost:11434 did not become ready within {timeout_sec} seconds.",
            )

    model_available = check_model_tag(model_tag=model_tag, host=host)
    if not model_available:
        return OllamaRuntimeStatus(
            server_running=True,
            model_available=False,
            ollama_command_available=command_available,
            model_tag=model_tag,
            host=host,
            message=f"Required local model tag not found: {model_tag}",
        )

    return OllamaRuntimeStatus(
        server_running=True,
        model_available=True,
        ollama_command_available=command_available,
        model_tag=model_tag,
        host=host,
        message=f"Local Ollama runtime ready with model {model_tag}.",
    )
