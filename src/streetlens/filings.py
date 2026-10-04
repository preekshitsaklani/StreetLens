"""Fetch earnings releases straight from SEC EDGAR: every 8-K under Item 2.02 (results of operations), its Exhibit 99.x
documents converted to plain text, and a manifest row per quarter. No manual downloads."""
import csv
import html
import json
import re
import time
from pathlib import Path

import requests

from .edgar import UA
from .paths import ROOT

RAW = ROOT / "data" / "raw"


def _get(url):
    for attempt in range(3):
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        if r.status_code == 200:
            return r
        time.sleep(1 + attempt)                     # SEC fair-access: back off politely
    r.raise_for_status()


def html_to_text(raw: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in s.splitlines()]
    return "\n".join(l for l in lines if l)


def quarter_label(event_date: str) -> str:
    """Earnings are reported in the month after quarter-end: Jul-2026 release -> Q2FY26 (calendar = fiscal year)."""
    y, m = int(event_date[:4]), int(event_date[5:7])
    q = (m - 1) // 3                                # Jan-Mar -> 0 (Q4 of prior year)
    return f"Q4FY{(y - 1) % 100:02d}" if q == 0 else f"Q{q}FY{y % 100:02d}"


def earnings_8ks(cik: str, n: int = 4) -> list[dict]:
    sub = _get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()["filings"]["recent"]
    rows = [{k: sub[k][i] for k in ("form", "filingDate", "reportDate", "accessionNumber", "items", "primaryDocument")} for i in range(len(sub["form"]))]
    dates = [r["filingDate"] for r in rows if r["form"] == "8-K" and "2.02" in r["items"]][:n]
    # results (2.02) plus same-day presentation filings (7.01), which often carry the outlook slides
    return [r for r in rows if r["form"] == "8-K" and r["filingDate"] in dates and ("2.02" in r["items"] or "7.01" in r["items"])]


def fetch(ticker: str, cik: str, n: int = 4, manifest=ROOT / "data" / "manifest.csv") -> list[Path]:
    RAW.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in earnings_8ks(cik, n):
        q = quarter_label(f["filingDate"])
        acc = f["accessionNumber"].replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}"
        names = [x["name"] for x in _get(f"{base}/index.json").json()["directory"]["item"]]
        # every document except the 8-K cover page and EDGAR's own rendering/index files
        exhibits = [x for x in names if x.lower().endswith((".htm", ".html")) and x != f["primaryDocument"]
                    and not re.match(r"(R\d+|FilingSummary)\.htm|.*-index", x, re.I)]
        parts = []
        for x in sorted(exhibits):
            parts.append(html_to_text(_get(f"{base}/{x}").text))
            time.sleep(0.15)
        if not parts:
            continue
        path = RAW / f"{ticker}_{q}_{acc[-6:]}.txt"
        path.write_text(f"SOURCE: {base}/ ({', '.join(sorted(exhibits))})\n\n" + "\n\n".join(parts), encoding="utf-8")
        saved.append((ticker, q, f["filingDate"], f"{base}/", path))
    _merge_manifest(saved, manifest)
    return [s[-1] for s in saved]


def _merge_manifest(saved, manifest: Path):
    rows = []
    if manifest.exists():
        rows = [r for r in csv.DictReader(open(manifest, encoding="utf-8")) if r.get("local_file")]
    have = {r["local_file"] for r in rows}
    for t, q, d, url, p in saved:
        rel = str(p.relative_to(ROOT))
        if rel not in have:
            rows.append({"bank": t, "quarter": q, "call_date": d, "source_url": url, "local_file": rel})
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["bank", "quarter", "call_date", "source_url", "local_file"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["bank"], r["quarter"], r["local_file"])))
