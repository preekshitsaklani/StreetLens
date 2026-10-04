"""FactSet Formula API adapter. Switches on when FACTSET_USERNAME_SERIAL and FACTSET_API_KEY are set in .env.

Authentication: HTTP basic auth with your FactSet username-serial and API key (developer.factset.com).
Formula codes live in companies/_data_fields.json; check them in the Formula API Request Builder.
"""
import json
import os

import requests

from .paths import COMPANIES

CFG = json.loads((COMPANIES / "_data_fields.json").read_text())["factset"]


def available() -> bool:
    return bool(os.getenv("FACTSET_USERNAME_SERIAL") and os.getenv("FACTSET_API_KEY"))


def _time_series(ids: list[str], formulas: list[str]) -> list[dict]:
    r = requests.get(f"{CFG['base_url']}/time-series", params={"ids": ",".join(ids), "formulas": ",".join(formulas), "flatten": "Y"},
                     auth=(os.environ["FACTSET_USERNAME_SERIAL"], os.environ["FACTSET_API_KEY"]), timeout=60)
    r.raise_for_status()
    return r.json().get("data", [])


def _value(row: dict, formula: str):
    """Flattened rows key results by formula text; match loosely in case FactSet normalises spacing or case."""
    norm = formula.replace(" ", "").upper()
    for k, v in row.items():
        if k.replace(" ", "").upper() == norm:
            return v
    return None


def fetch(tickers: list[str]) -> dict:
    from .market import beta_from_prices
    ids = {t: CFG["id"].format(ticker=t) for t in tickers}
    f = CFG["fields"]
    rows = {r.get("requestId"): r for r in _time_series(list(ids.values()), list(f.values()))}
    hist_rows = _time_series(list(ids.values()) + [CFG["index"]], [CFG["history"]])
    hist = {}
    for r in hist_rows:
        v = _value(r, CFG["history"])
        if v is not None:
            hist.setdefault(r.get("requestId"), []).append((r.get("date"), v))
    out = {"companies": {}}
    for t, i in ids.items():
        r = rows.get(i, {})
        g = lambda k, scale=1.0: (_value(r, f[k]) / scale) if _value(r, f[k]) is not None else None
        out["companies"][t] = {"price": g("price"), "mcap_bn": g("mcap_mn", 1000), "high52": g("high52"), "low52": g("low52"),
                               "consensus_tp": g("consensus_tp"), "consensus_eps": g("consensus_eps"),
                               "beta": beta_from_prices(hist.get(i, []), hist.get(CFG["index"], []))}
    return out
