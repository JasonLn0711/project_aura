from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from aura.llm.ollama_runtime import OllamaRuntimeError, validate_localhost_host
from summary.field_schemas import (
    BASE_MODEL_ID,
    OLLAMA_MAX_OUTPUT_TOKENS,
    OLLAMA_MODEL_TAG,
    OLLAMA_NUM_CTX,
    OLLAMA_REASONING_ENABLED,
)


class OllamaGemmaError(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaGemmaConfig:
    host: str = "http://localhost:11434"
    model: str = OLLAMA_MODEL_TAG
    base_model_id: str = BASE_MODEL_ID
    num_ctx: int = OLLAMA_NUM_CTX
    temperature: float = 0.0
    seed: int = 20260604
    max_output_tokens: int = OLLAMA_MAX_OUTPUT_TOKENS
    timeout_sec: int = 180
    reasoning_enabled: bool = OLLAMA_REASONING_ENABLED


class OllamaGemma4Client:
    def __init__(self, config: OllamaGemmaConfig | None = None) -> None:
        self.config = config or OllamaGemmaConfig()
        if self.config.model != OLLAMA_MODEL_TAG or self.config.base_model_id != BASE_MODEL_ID:
            raise OllamaGemmaError("No fallback model is allowed for meeting summary generation.")
        if self.config.reasoning_enabled is not True:
            raise OllamaGemmaError("Gemma 4 E4B reasoning must remain enabled.")
        if self.config.max_output_tokens != OLLAMA_MAX_OUTPUT_TOKENS:
            raise OllamaGemmaError(
                f"Gemma 4 E4B max output tokens must be {OLLAMA_MAX_OUTPUT_TOKENS}."
            )
        try:
            validate_localhost_host(self.config.host)
        except OllamaRuntimeError as exc:
            raise OllamaGemmaError(str(exc)) from exc

    def _request(self, endpoint: str, payload: dict[str, Any] | None = None, timeout: int | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.host.rstrip('/')}{endpoint}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.config.timeout_sec) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise OllamaGemmaError(f"Ollama local runner unavailable: {exc}") from exc

    def check_model_available(self) -> None:
        tags = self._request("/api/tags", timeout=5)
        models = tags.get("models") or []
        names = {str(model.get("name") or "") for model in models if isinstance(model, dict)}
        if self.config.model not in names:
            raise OllamaGemmaError(f"Gemma 4 E4B local Ollama model tag not found: {self.config.model}")

    def generate_json(self, prompt: str) -> str:
        self.check_model_available()
        response = self._request(
            "/api/chat",
            payload={
                "model": self.config.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Return valid JSON only. Use only the supplied transcript.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "think": self.config.reasoning_enabled,
                "options": {
                    "temperature": self.config.temperature,
                    "seed": self.config.seed,
                    "num_predict": self.config.max_output_tokens,
                    "num_ctx": self.config.num_ctx,
                },
            },
            timeout=self.config.timeout_sec,
        )
        done_reason = str(response.get("done_reason") or "unknown")
        if response.get("done") is not True:
            raise OllamaGemmaError(f"Ollama generation did not complete (done_reason={done_reason}).")
        message = response.get("message") if isinstance(response.get("message"), dict) else {}
        content = str(message.get("content") or "").strip()
        if not content:
            raise OllamaGemmaError(
                f"Gemma 4 E4B returned no final JSON content (done_reason={done_reason})."
            )
        return content
