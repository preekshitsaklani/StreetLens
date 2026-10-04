"""One-page earnings summary built ONLY from grounded facts. The LLM may phrase; it may not add numbers."""
import re
from collections import Counter

from .config import BANKS, METRICS
from .grounding import numbers_in

SYSTEM = ("You write a 3-sentence 'what changed this quarter' paragraph for an equity research analyst. "
          "Use ONLY the facts given. Do not add any number that is not in the facts. "
          'Return ONLY JSON: {"paragraph": "..."}')


def _fmt(v, unit="pct"):
    return f"{v:.2f}%" if unit == "pct" else f"{v:.0f} bps"


def facts(reported, guidance) -> list[str]:
    out = [f"{METRICS[r['metric']][0]}: {_fmt(r['value'], r['unit'])} ({r['period']})"
           for r in reported if r["status"] == "grounded"]
    for g in guidance:
        if g["status"] != "grounded":
            continue
        what = (f"{_fmt(g['low'], g['unit'])} to {_fmt(g['high'], g['unit'])}" if g["kind"] == "range" and g["high"] is not None
                else _fmt(g["low"], g["unit"]) if g["low"] is not None else (g["phrase"] or g["direction"] or ""))
        out.append(f"Guidance, {METRICS[g['metric']][0]}: {what} ({g['horizon'] or 'unspecified horizon'})")
    return out


def paragraph(fs: list[str], client=None) -> tuple[str, str]:
    """Return (text, source). LLM text is accepted only if every number in it appears in the facts."""
    allowed = {round(n, 2) for f in fs for n in numbers_in(f)}
    if client and fs:
        try:
            text = client.json(SYSTEM, "Facts:\n- " + "\n- ".join(fs)).get("paragraph", "")
            if text and {round(n, 2) for n in numbers_in(text)} <= allowed:
                return text, "llm"
        except Exception:
            pass
    return ("Key reported figures: " + "; ".join(fs[:4]) + ".") if fs else "No grounded figures extracted.", "template"


def build(bank, quarter, reported, guidance, qs, client=None) -> tuple[str, str]:
    fs = facts(reported, guidance)
    para, src = paragraph(fs, client)
    top = Counter(q["topic"] for q in qs).most_common(3)
    lines = [f"# {BANKS.get(bank, bank)}: {quarter} earnings call summary", "",
             f"**What changed** ({'AI-drafted, numbers verified' if src == 'llm' else 'template'}): {para}", "",
             "## Reported this quarter", "", "| Metric | Value | Evidence |", "| --- | --- | --- |"]
    for r in reported:
        if r["status"] == "grounded" and r["period"] == quarter:
            ev = re.sub(r"\s+", " ", r["evidence"])[:140].replace("|", "/")
            lines.append(f"| {METRICS[r['metric']][0]} | {_fmt(r['value'], r['unit'])} | \"{ev}\" |")
    lines += ["", "## Management guidance", ""]
    lines += [f"- {f.removeprefix('Guidance, ')}" for f in fs if f.startswith("Guidance")] or ["- None stated with figures."]
    lines += ["", "## What analysts asked about", ""]
    lines += [f"- {t.replace('_', ' ')}: {n} question(s)" for t, n in top] or ["- No analyst questions parsed."]
    n_bad = sum(r["status"] != "grounded" for r in reported) + sum(g["status"] != "grounded" for g in guidance)
    lines += ["", f"_Grounding: {len(fs)} facts verified against the transcript; {n_bad} extracted item(s) rejected._"]
    return "\n".join(lines) + "\n", src
