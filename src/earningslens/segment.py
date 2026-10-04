"""Split a transcript into speaker turns; tag role (management, analyst, moderator) and section (remarks, qa)."""
import re
from dataclasses import dataclass


@dataclass
class Turn:
    speaker: str
    role: str      # management | analyst | moderator
    section: str   # remarks | qa
    firm: str
    text: str


_SPEAKER = re.compile(
    r"^(?P<name>(?:(?:Mr|Ms|Mrs|Dr)\.?\s+)?[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,4})"
    r"(?:\s*[-\u2013\u2014,]\s*(?P<org>[A-Z][^:\n]{1,80}?))?\s*:\s*(?P<rest>.*)$")
_INTRO = re.compile(
    r"(?i:line of|question is from|question from)\s+(?:(?:Mr|Ms|Mrs)\.?\s+)?"
    r"(?P<name>[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})\s+(?i:from|of|with)\s+"
    r"(?P<firm>[A-Z][A-Za-z0-9&.' \-]+?)(?=[.,]|\s+(?i:please|you may)|$)")
_QA_START = re.compile(r"question[- ]and[- ]answer|first question|begin the q\s*&\s*a", re.I)
_MGMT_WORDS = re.compile(r"\b(chief|officer|director|cfo|ceo|md|president|head|chairman|managing|bank)\b", re.I)
_NOT_NAMES = {"note", "total", "source", "disclaimer", "agenda", "participants", "date", "time"}
MODERATOR = {"moderator", "operator"}


def _key(name: str) -> str:
    parts = re.sub(r"^(mr|ms|mrs|dr)\.?\s+", "", name.strip(), flags=re.I).lower().split()
    return f"{parts[0]} {parts[-1]}" if parts else ""


def segment(text: str) -> list[Turn]:
    raw = []
    for line in text.splitlines():
        s = line.strip()
        m = _SPEAKER.match(s)
        if m and m.group("name").split()[0].lower() not in _NOT_NAMES:
            raw.append({"speaker": " ".join(m.group("name").split()), "org": (m.group("org") or "").strip(),
                        "text": m.group("rest").strip()})
        elif raw and s:
            raw[-1]["text"] += " " + s
    turns, analysts, qa = [], {}, False
    for t in raw:
        if t["speaker"].lower() in MODERATOR:
            role = "moderator"
            for im in _INTRO.finditer(t["text"]):
                analysts[_key(im.group("name"))] = im.group("firm").strip()
            qa = qa or bool(_QA_START.search(t["text"]) or _INTRO.search(t["text"]))
        elif _key(t["speaker"]) in analysts or (t["org"] and not _MGMT_WORDS.search(t["org"])):
            role, qa = "analyst", True
        else:
            role = "management"
        firm = analysts.get(_key(t["speaker"]), t["org"]) if role == "analyst" else ""
        turns.append(Turn(t["speaker"], role, "qa" if qa else "remarks", firm, t["text"].strip()))
    if not any(t.role == "moderator" for t in turns):     # calls always have a moderator; filings never do
        return release_turns(text)
    return turns


def release_turns(text: str, size: int = 1500) -> list[Turn]:
    """Earnings releases and presentations have no speakers: treat the company's own words as management remarks."""
    out, buf = [], ""
    for line in text.splitlines():
        buf += line.strip() + " "
        if len(buf) >= size:
            out.append(Turn("Company filing", "management", "remarks", "", buf.strip()))
            buf = ""
    if buf.strip():
        out.append(Turn("Company filing", "management", "remarks", "", buf.strip()))
    return out
