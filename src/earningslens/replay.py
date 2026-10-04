"""Replay client: serves recorded LLM responses so the pipeline runs without an API key (demo and tests)."""
import json
import re


class ReplayClient:
    def __init__(self, path):
        self.responses = json.loads(open(path, encoding="utf-8").read())
        self.calls = 0
        self._served = set()

    def json(self, system: str, user: str) -> dict:
        self.calls += 1
        m = re.search(r"Quarter of this call: (Q[1-4]FY\d{2})", user)
        if m and "Excerpt" in user and m.group(1) not in self._served:
            self._served.add(m.group(1))          # one recorded response per call, served to the first chunk
            return self.responses.get(m.group(1), {})
        return {}   # topics and summary fall back to their deterministic paths
