"""One OpenAI-compatible chat client for Gemini, Ollama, Groq or any compatible endpoint.

Responses are cached on disk by a hash of (model, prompts), so re-runs cost nothing and are reproducible.
"""
import hashlib
import json
import os
import re
import time

import requests

from .config import CACHE

PRESETS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "ollama": "http://localhost:11434/v1",
    "groq": "https://api.groq.com/openai/v1",
}


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = "", temperature: float = 0.0, timeout: int = 120):
        if not model:
            raise LLMError("LLM_MODEL is not set. Add it to your .env file.")
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.temperature, self.timeout = temperature, timeout
        self.calls = 0

    @classmethod
    def from_env(cls) -> "LLMClient":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        base = os.getenv("LLM_BASE_URL") or PRESETS.get(provider)
        if not base:
            raise LLMError(f"Unknown LLM_PROVIDER {provider!r}; set LLM_BASE_URL for openai_compatible.")
        return cls(base, os.getenv("LLM_MODEL", ""), os.getenv("LLM_API_KEY", ""))

    def json(self, system: str, user: str) -> dict:
        key = hashlib.sha256(f"{self.model}\n{system}\n{user}".encode()).hexdigest()
        path = CACHE / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        body = {"model": self.model, "temperature": self.temperature,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last = None
        for attempt in range(4):
            try:
                r = requests.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
                if r.status_code in (429, 500, 502, 503):
                    raise LLMError(f"HTTP {r.status_code}")
                r.raise_for_status()
                text = r.json()["choices"][0]["message"]["content"]
                data = parse_json(text)
                self.calls += 1
                CACHE.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data))
                return data
            except (requests.RequestException, LLMError, ValueError, KeyError) as e:
                last = e
                time.sleep(2 ** attempt * 2)
        raise LLMError(f"LLM call failed after retries: {last}")


def parse_json(text: str) -> dict:
    """Accept raw JSON or JSON wrapped in markdown fences."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data
