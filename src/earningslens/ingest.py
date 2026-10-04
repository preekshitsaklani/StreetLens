"""Load transcripts listed in data/manifest.csv (PDF or TXT) and clean the text."""
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .config import ROOT, q_index


@dataclass
class Transcript:
    bank: str
    quarter: str
    call_date: str
    source_url: str
    path: Path
    text: str


def read_pdf_pages(path: Path) -> list[str]:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return [(p.extract_text() or "") for p in pdf.pages]
    except ImportError:
        from pypdf import PdfReader
        return [(p.extract_text() or "") for p in PdfReader(str(path)).pages]


_PAGE_NO = re.compile(r"^\s*(page\s*\d+(\s*of\s*\d+)?|\d+\s*/\s*\d+|-?\s*\d{1,3}\s*-?)\s*$", re.I)


def clean_pages(pages: list[str]) -> str:
    """Drop page numbers and running headers/footers; re-join words hyphenated across lines."""
    counts = Counter(l.strip() for p in pages for l in set(p.splitlines()) if l.strip())
    repeated = {l for l, c in counts.items() if len(pages) >= 3 and c >= 0.5 * len(pages) and len(l) < 120}
    lines = [s for p in pages for s in (l.strip() for l in p.splitlines())
             if s and s not in repeated and not _PAGE_NO.match(s)]
    return re.sub(r"(\w)-\n(\w)", r"\1\2", "\n".join(lines))


def load_text(path) -> str:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return clean_pages(read_pdf_pages(path))
    return path.read_text(encoding="utf-8", errors="ignore")


def load_manifest(manifest=ROOT / "data" / "manifest.csv", bank=None, quarter=None) -> list[Transcript]:
    out = []
    with open(manifest, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not (r.get("local_file") or "").strip():
                continue
            if (bank and r["bank"] != bank) or (quarter and r["quarter"] != quarter):
                continue
            q_index(r["quarter"])
            p = Path(r["local_file"])
            p = p if p.is_absolute() else ROOT / p
            if not p.exists():
                raise FileNotFoundError(f"{p} is listed in the manifest but missing")
            out.append(Transcript(r["bank"], r["quarter"], r.get("call_date", ""), r.get("source_url", ""), p, load_text(p)))
    return out
