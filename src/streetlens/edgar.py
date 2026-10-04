"""SEC EDGAR XBRL company facts: audited annual history and latest balance-sheet values. Cached as dated snapshots."""
import json
import os

import requests

from .paths import SNAP

UA = os.getenv("SEC_USER_AGENT", "StreetLens research project contact@example.com")  # SEC asks for a contact


def facts(cik: str, refresh: bool = False) -> dict:
    path = SNAP / f"edgar_{cik}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    data = r.json()
    keep = {"entityName": data["entityName"], "facts": {"us-gaap": data["facts"].get("us-gaap", {}),
                                                         "dei": data["facts"].get("dei", {})}}
    SNAP.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keep))
    return keep


def _rows(fx: list[dict], concept: str, unit: str, ns: str = "us-gaap") -> list[dict]:
    out = []
    for f in fx:
        out += f["facts"].get(ns, {}).get(concept, {}).get("units", {}).get(unit, [])
    return out


def annual(fx, concept, unit="USD", instant=False) -> dict[int, float]:
    """Calendar-year values: full-year durations (frame CY2025) or year-end instants (CY2025Q4I). Newer CIK wins."""
    out = {}
    for x in reversed(_rows(fx, concept, unit)):
        fr = x.get("frame", "")
        if (instant and len(fr) == 9 and fr.endswith("Q4I")) or (not instant and len(fr) == 6 and fr.startswith("CY")):
            out.setdefault(int(fr[2:6]), float(x["val"]))
    return dict(sorted(out.items()))


def latest_instant(fx, concept, unit="USD") -> tuple[str, float] | None:
    rows = [x for x in _rows(fx, concept, unit) if x.get("frame", "").endswith("I")]
    if not rows:
        return None
    x = max(rows, key=lambda r: r["end"])
    return x["end"], float(x["val"])


def shares_outstanding(fx) -> tuple[str, float] | None:
    rows = _rows(fx, "EntityCommonStockSharesOutstanding", "shares", ns="dei")
    if not rows:
        return None
    x = max(rows, key=lambda r: r["end"])
    return x["end"], float(x["val"])


def history(fx, c: dict, years=5) -> list[dict]:
    """Five-year table: revenue, net income to common, EPS, DPS, common equity, TCE, ROE, RoTCE (average-equity basis)."""
    s = lambda k, **kw: annual(fx, c[k], **kw) if c.get(k) else {}
    rev, ni, eps = s("revenue"), s("ni_common"), annual(fx, c["eps"], "USD/shares")
    dps = annual(fx, c["dps"], "USD/shares")
    eq, pref, gw = s("equity", instant=True), s("preferred", instant=True), s("goodwill", instant=True)
    intang = {}
    for k in c.get("intangibles", []):
        for y, v in annual(fx, k, instant=True).items():
            intang[y] = intang.get(y, 0.0) + v
    opi = s("operating_income")
    yrs = sorted(y for y in ni if y in eq)[-(years + 1):]
    out = []
    for i, y in enumerate(yrs):
        ce = eq[y] - pref.get(y, 0.0)
        tce = ce - gw.get(y, 0.0) - intang.get(y, 0.0)
        row = {"year": y, "revenue": rev.get(y), "ni_common": ni[y], "eps": eps.get(y), "dps": dps.get(y),
               "common_equity": ce, "tce": tce, "operating_income": opi.get(y)}
        if i:
            p = out[-1]
            row["roe"] = ni[y] / ((p["common_equity"] + ce) / 2)
            row["rotce"] = ni[y] / ((p["tce"] + tce) / 2)
        out.append(row)
    return out[1:] if len(out) > years else out


def tbvps_latest(fx, c: dict) -> float | None:
    """Tangible book value per share at the latest balance sheet: (equity - preferred - goodwill - intangibles) / shares."""
    try:
        eq = latest_instant(fx, c["equity"])[1]
        pref = (latest_instant(fx, c["preferred"]) or ("", 0.0))[1] if c.get("preferred") else 0.0
        gw = latest_instant(fx, "Goodwill")[1]
        intang = sum((latest_instant(fx, k) or ("", 0.0))[1] for k in c.get("intangibles", []))
        return (eq - pref - gw - intang) / shares_outstanding(fx)[1]
    except (TypeError, IndexError):
        return None
