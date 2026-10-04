"""Grounding check: every extracted figure must be traceable to the transcript, word for word.

An item is grounded only if (1) its evidence quote is found in the source, (2) the extracted number
or phrase is inside that quote, and (3) for guidance, the quote comes from a management speaker.
"""
import re
import unicodedata

from rapidfuzz import fuzz

# Management phrases -> numeric band (percent) or a direction. Mapping is deterministic and auditable.
PHRASES = {
    "mid-teens": (14.0, 16.0), "mid teens": (14.0, 16.0), "low teens": (11.0, 13.0), "high teens": (17.0, 19.0),
    "low twenties": (20.0, 22.0), "mid-twenties": (24.0, 26.0), "range-bound": "stable", "range bound": "stable",
    "broadly stable": "stable", "stable": "stable", "flattish": "stable", "improve": "up", "increase": "up",
    "moderate": "down", "decline": "down", "compress": "down", "mid-single-digit": (4.0, 6.0), "high-single-digit": (7.0, 9.0), "low-single-digit": (1.0, 3.0),
}
FUZZY_MIN = 92


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.translate(str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"}))
    s = re.sub(r"per\s?cent", "%", s)
    s = re.sub(r"\[(management|analyst)\]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def numbers_in(s: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d{2,3})*(?:\.\d+)?", s)]


def _has(nums, v, tol=0.005):
    return v is not None and any(abs(n - v) < tol for n in nums)


def locate(quote: str, source: str, turns_norm: list[tuple[str, str]]):
    """Return (match, score, role) for a quote: exact, fuzzy or none; role of the turn that contains it."""
    q = norm(quote)
    if not q:
        return "none", 0, ""
    if q in source:
        role = next((r for r, t in turns_norm if q in t), "")
        return "exact", 100, role
    al = fuzz.partial_ratio_alignment(q, source)
    if al.score >= FUZZY_MIN:
        # Fuzzy matching tolerates PDF artefacts, never changed figures: every number in the quote
        # must also appear in the matched passage of the source.
        window = source[al.dest_start:al.dest_end]
        if not all(_has(numbers_in(window), n) for n in numbers_in(q)):
            return "none", round(al.score), "figures_differ_from_source"
        best = max(turns_norm, key=lambda rt: fuzz.partial_ratio(q, rt[1]), default=("", ""))
        return "fuzzy", round(al.score), best[0]
    return "none", round(al.score), ""


def check_reported(item, source, turns_norm) -> dict:
    match, score, role = locate(item.evidence, source, turns_norm)
    number_ok = _has(numbers_in(norm(item.evidence)), item.value)
    status = "grounded" if match != "none" and number_ok else ("quote_not_found" if match == "none" else "number_not_in_quote")
    return {"status": status, "match": match, "score": score, "role": role}


def check_guidance(item, source, turns_norm) -> dict:
    match, score, role = locate(item.evidence, source, turns_norm)
    q = norm(item.evidence)
    nums = numbers_in(q)
    phrase = norm(item.phrase) if item.phrase else ""
    mapped = PHRASES.get(phrase)
    if phrase and phrase in q and mapped is not None:
        if isinstance(mapped, tuple):
            content_ok = item.low is None or (abs(item.low - mapped[0]) < 0.01 and abs((item.high or item.low) - mapped[1]) < 0.01)
        else:
            content_ok = item.direction in (None, mapped)
    elif item.kind in ("range", "point"):
        content_ok = _has(nums, item.low) and (item.high is None or _has(nums, item.high))
    else:
        content_ok = any(w in q for w, d in PHRASES.items() if d == item.direction)
    if match == "none":
        status = "quote_not_found"
    elif not content_ok:
        status = "figure_not_in_quote"
    elif role and role != "management":
        status = "not_management"
    else:
        status = "grounded"
    return {"status": status, "match": match, "score": score, "role": role}


def ground(extraction, transcript_text: str, turns) -> tuple[list[dict], list[dict]]:
    source = norm(transcript_text)
    turns_norm = [(t.role, norm(t.text)) for t in turns]
    rep = [{**r.model_dump(), **check_reported(r, source, turns_norm)} for r in extraction.reported]
    gui = []
    for g in extraction.guidance:
        lo, hi = g.band_pct()
        if g.phrase and isinstance(PHRASES.get(norm(g.phrase)), tuple) and lo is None:
            lo, hi = PHRASES[norm(g.phrase)]
        direction = g.direction or (PHRASES.get(norm(g.phrase or "")) if isinstance(PHRASES.get(norm(g.phrase or "")), str) else None)
        gui.append({**g.model_dump(), "low_pct": lo, "high_pct": hi, "direction": direction, **check_guidance(g, source, turns_norm)})
    return rep, gui
