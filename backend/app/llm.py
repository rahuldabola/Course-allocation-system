"""LLM provider clients for the AI assistant.

Two interchangeable backends behind one tiny interface:
  * GeminiClient — Google Gemini over its REST API (the hosted default);
  * OllamaClient — a local model served by Ollama (fully offline).

`get_llm()` returns the client selected by settings, or None when no LLM is
configured; the assistant then answers built-in report questions only.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

import httpx

from .config import settings

log = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class LLMError(RuntimeError):
    """The provider was unreachable, rate-limited, or returned something unusable."""


class LLMClient(Protocol):
    provider: str
    model: str

    def generate(
        self, prompt: str, *, system: str, json_mode: bool = False, timeout: float | None = None
    ) -> str: ...


class GeminiClient:
    provider = "gemini"

    def __init__(self, api_key: str, model: str, *, http: httpx.Client | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._http = http or httpx.Client(timeout=settings.llm_timeout_seconds)

    def generate(
        self, prompt: str, *, system: str, json_mode: bool = False, timeout: float | None = None
    ) -> str:
        generation_config: dict = {"temperature": 0}
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        try:
            resp = self._http.post(
                f"{GEMINI_BASE_URL}/models/{self.model}:generateContent",
                json=body,
                headers={"x-goog-api-key": self._api_key},
                timeout=timeout or settings.llm_timeout_seconds,
            )
        except httpx.HTTPError as e:
            raise LLMError(f"Gemini request failed: {e.__class__.__name__}") from e
        if resp.status_code == 429:
            raise LLMError("Gemini rate limit reached")
        if resp.status_code >= 400:
            raise LLMError(f"Gemini returned HTTP {resp.status_code}")
        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise LLMError("Gemini returned no content") from e
        # Skip "thought" parts that thinking models may include.
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise LLMError("Gemini returned an empty response")
        return text


class OllamaClient:
    provider = "ollama"

    def __init__(self, base_url: str, model: str, *, http: httpx.Client | None = None) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=max(settings.llm_timeout_seconds, 60))

    def generate(
        self, prompt: str, *, system: str, json_mode: bool = False, timeout: float | None = None
    ) -> str:
        body: dict = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0},
        }
        if json_mode:
            body["format"] = "json"
        try:
            resp = self._http.post(
                f"{self._base_url}/api/generate", json=body, timeout=timeout or 60.0
            )
            resp.raise_for_status()
            text = resp.json().get("response", "")
        except (httpx.HTTPError, ValueError) as e:
            raise LLMError(f"Ollama request failed: {e.__class__.__name__}") from e
        if not text.strip():
            raise LLMError("Ollama returned an empty response")
        return text


@lru_cache(maxsize=1)
def _configured_client() -> LLMClient | None:
    provider = settings.effective_llm_provider
    if provider == "gemini":
        if not settings.gemini_api_key:
            log.warning("LLM_PROVIDER=gemini but GEMINI_API_KEY is empty; assistant LLM disabled")
            return None
        return GeminiClient(settings.gemini_api_key, settings.gemini_model)
    if provider == "ollama":
        return OllamaClient(settings.ollama_url, settings.ollama_model)
    return None


def get_llm() -> LLMClient | None:
    """FastAPI dependency: the configured LLM client, or None."""
    return _configured_client()
