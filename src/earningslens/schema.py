"""Typed records for extracted facts. Invalid LLM output is dropped and counted, never patched."""
from typing import Literal, Optional

from pydantic import BaseModel, ValidationError, field_validator

from .config import METRICS


def _known(v: str) -> str:
    if v not in METRICS:
        raise ValueError(f"unknown metric {v}")
    return v


class Reported(BaseModel):
    metric: str
    value: float
    unit: Literal["pct", "bps", "usd_bn", "usd_tn", "usd"] = "pct"
    period: str
    evidence: str

    @field_validator("metric")
    @classmethod
    def check_metric(cls, v):
        return _known(v)

    def pct(self) -> float:
        """Value in the metric's own scale: percent for ratios, the stated amount for dollars."""
        return self.value / 100 if self.unit == "bps" else self.value


class Guidance(BaseModel):
    metric: str
    kind: Literal["range", "point", "direction"]
    low: Optional[float] = None
    high: Optional[float] = None
    direction: Optional[Literal["up", "down", "stable"]] = None
    phrase: Optional[str] = None
    unit: Literal["pct", "bps", "usd_bn", "usd_tn", "usd"] = "pct"
    horizon: str = ""
    evidence: str

    @field_validator("metric")
    @classmethod
    def check_metric(cls, v):
        return _known(v)

    def band_pct(self):
        f = 0.01 if self.unit == "bps" else 1.0
        lo = self.low * f if self.low is not None else None
        hi = self.high * f if self.high is not None else lo
        return lo, hi


class Extraction(BaseModel):
    reported: list[Reported] = []
    guidance: list[Guidance] = []
    dropped: int = 0

    @classmethod
    def parse_lenient(cls, raw: dict, default_period: str) -> "Extraction":
        out = cls()
        for item in (raw or {}).get("reported") or []:
            try:
                out.reported.append(Reported(**{**item, "period": item.get("period") or default_period}))
            except (ValidationError, TypeError, AttributeError):
                out.dropped += 1
        for item in (raw or {}).get("guidance") or []:
            try:
                out.guidance.append(Guidance(**item))
            except (ValidationError, TypeError):
                out.dropped += 1
        return out

    def merge(self, other: "Extraction") -> None:
        self.reported += other.reported
        self.guidance += other.guidance
        self.dropped += other.dropped

    def dedup(self) -> "Extraction":
        seen, rep, gui = set(), [], []
        for r in self.reported:
            k = ("r", r.metric, r.period, round(r.pct(), 3))
            if k not in seen:
                seen.add(k); rep.append(r)
        for g in self.guidance:
            k = ("g", g.metric, g.kind, g.low, g.high, g.direction, g.horizon.lower())
            if k not in seen:
                seen.add(k); gui.append(g)
        return Extraction(reported=rep, guidance=gui, dropped=self.dropped)
