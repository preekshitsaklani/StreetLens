"""Extract reported KPIs and forward guidance. LLMExtractor is the main path; RegexExtractor is the baseline."""
import re

from .config import CHUNK_CHARS, CHUNK_OVERLAP, METRICS
from .schema import Extraction, Reported

SYSTEM = f"""You extract facts from a bank's or asset manager's earnings call transcript or earnings release for an equity research analyst.
Return ONLY a JSON object: {{"reported": [...], "guidance": [...]}}.
Allowed metric keys: {", ".join(METRICS)}.
Rules:
1. Extract only figures stated explicitly in the excerpt. Never calculate, infer or use outside knowledge.
2. "evidence" is copied verbatim from the excerpt (max 300 characters) and contains the figure or phrase.
3. Percent values as numbers: 4.36% -> 4.36. Basis points keep unit "bps": 38 basis points -> 38. Dollar amounts: "$105.5 billion" -> 105.5 with unit "usd_bn"; "$15.3 trillion" -> 15.3 with unit "usd_tn"; per-share dollars -> unit "usd".
4. "reported" = results for a past period. "period" is the call's quarter (e.g. Q1FY27) unless the text names another; full years as FY27.
5. "guidance" = forward-looking statements by MANAGEMENT only, never by analysts.
   kind: "range" (low and high), "point" (low only) or "direction" (direction = up, down or stable; low and high null).
   If management uses a phrase such as "mid-teens", "low teens" or "range-bound", copy it exactly into "phrase".
   "horizon" = the period covered, e.g. FY27, Q2FY27, "next few quarters".
6. Skip anything ambiguous. Empty lists are a valid answer.
Reported keys: metric, value, unit, period, evidence.
Guidance keys: metric, kind, low, high, direction, phrase, unit, horizon, evidence."""

USER = 'Bank: {bank}\nQuarter of this call: {quarter}\nSection: {section}\n\nExcerpt:\n"""\n{text}\n"""'


def chunks(turns, size=CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    """Group consecutive non-moderator turns into ~size-character windows within one section."""
    buf, section = "", None
    for t in turns:
        if t.role == "moderator":
            continue
        piece = f"{t.speaker} [{t.role}]: {t.text}\n"
        if buf and (t.section != section or len(buf) + len(piece) > size):
            yield section, buf
            buf = buf[-overlap:] if t.section == section else ""
        buf += piece
        section = t.section
    if buf:
        yield section, buf


class LLMExtractor:
    name = "llm"

    def __init__(self, client):
        self.client = client

    def run(self, bank, quarter, turns) -> Extraction:
        out = Extraction()
        for section, text in chunks(turns):
            raw = self.client.json(SYSTEM, USER.format(bank=bank, quarter=quarter, section=section, text=text))
            out.merge(Extraction.parse_lenient(raw, default_period=quarter))
        return out.dedup()


_NUM = r"(\d{1,2}(?:\.\d{1,2})?)\s?(?:%|per\s?cent)"
PATTERNS = {
    "nim": rf"net interest margin[^.%]{{0,45}}?{_NUM}",
    "gnpa_ratio": rf"gross NPA ratio[^.%]{{0,45}}?{_NUM}",
    "nnpa_ratio": rf"net NPA ratio[^.%]{{0,45}}?{_NUM}",
    "casa_ratio": rf"CASA ratio[^.%]{{0,45}}?{_NUM}",
    "roe": rf"(?:ROE|return on equity)[^.%]{{0,45}}?{_NUM}",
    "cet1_ratio": rf"CET[- ]?1(?: capital)? ratio[^.%]{{0,45}}?{_NUM}",
    "rotce": rf"ROTCE of {_NUM}",
    "organic_base_fee_growth": rf"{_NUM} organic base fee growth",
    "adj_operating_margin": rf"adjusted operating margin was {_NUM}",
    "loan_growth_yoy": rf"(?:advances|loan portfolio|loans)\s+(?:grew|increased)\s+by\s+{_NUM}\s+year[- ]on[- ]year",
    "deposit_growth_yoy": rf"deposits\s+(?:grew|increased)\s+by\s+{_NUM}\s+year[- ]on[- ]year",
}


class RegexExtractor:
    """Deterministic baseline: first matching statement per metric in management's prepared remarks."""
    name = "regex"

    def run(self, bank, quarter, turns) -> Extraction:
        text = " ".join(t.text for t in turns if t.role == "management" and t.section == "remarks")
        sentences = re.split(r"(?<=[.!?])\s+", text)
        out = Extraction()
        for metric, pat in PATTERNS.items():
            rx = re.compile(pat, re.I)
            for s in sentences:
                m = rx.search(s)
                if m:
                    ev = s[max(0, m.start() - 150): m.end() + 60]          # quote window centred on the figure
                    out.reported.append(Reported(metric=metric, value=float(m.group(1)), period=quarter, evidence=ev))
                    break
        return out
