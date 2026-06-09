from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from summary.field_schemas import BASE_MODEL_ID, OLLAMA_MODEL_TAG, OLLAMA_NUM_CTX


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
    max_output_tokens: int = 768
    timeout_sec: int = 180


class OllamaGemma4Client:
    def __init__(self, config: OllamaGemmaConfig | None = None) -> None:
        self.config = config or OllamaGemmaConfig()
        if self.config.model != OLLAMA_MODEL_TAG or self.config.base_model_id != BASE_MODEL_ID:
            raise OllamaGemmaError("No fallback model is allowed for meeting summary generation.")
        if not self.config.host.startswith("http://127.0.0.1:") and not self.config.host.startswith("http://localhost:"):
            raise OllamaGemmaError("Ollama host must be localhost.")

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
            "/api/generate",
            payload={
                "model": self.config.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": self.config.temperature,
                    "seed": self.config.seed,
                    "num_predict": self.config.max_output_tokens,
                    "num_ctx": self.config.num_ctx,
                },
            },
            timeout=self.config.timeout_sec,
        )
        return str(response.get("response") or "")
