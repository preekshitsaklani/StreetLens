"""Market data with automatic source selection: Bloomberg Terminal -> FactSet API -> Yahoo Finance -> dated snapshot.

Premium sources override free ones field by field; every field records where it came from.
Force a source with DATA_SOURCE=bloomberg | factset | yahoo in .env.
"""
import json
import os
from datetime import date

import numpy as np

from .paths import SNAP


def beta_from_prices(stock: list, index: list) -> float | None:
    """Raw beta from weekly closes: cov(log returns) / var(index log returns), dates aligned."""
    a, b = dict(stock), dict(index)
    common = sorted(set(a) & set(b))
    if len(common) < 30:
        return None
    s, m = np.diff(np.log([a[d] for d in common])), np.diff(np.log([b[d] for d in common]))
    return round(float(np.cov(s, m)[0, 1] / np.var(m, ddof=1)), 2)


def yahoo(tickers: list[str]) -> dict:
    import yfinance as yf
    px = yf.download(tickers + ["^GSPC"], period="2y", interval="1wk", auto_adjust=True, progress=False)["Close"]
    series = {c: [(str(d.date()), float(v)) for d, v in px[c].dropna().items()] for c in px.columns}
    out = {"companies": {}}
    for t in tickers:
        i = yf.Ticker(t).info
        out["companies"][t] = {"price": i.get("currentPrice") or i.get("regularMarketPrice"), "beta": beta_from_prices(series[t], series["^GSPC"]),
                               "pb": i.get("priceToBook"), "roe": i.get("returnOnEquity"), "fwd_pe": i.get("forwardPE"),
                               "mcap_bn": (i.get("marketCap") or 0) / 1e9, "low52": i.get("fiftyTwoWeekLow"), "high52": i.get("fiftyTwoWeekHigh"),
                               "div_yield": i.get("dividendYield"), "consensus_tp": i.get("targetMeanPrice"), "consensus_eps": i.get("forwardEps")}
    return out


def _merge(base: dict, premium: dict, name: str, sources: dict) -> None:
    for t, fields in premium.get("companies", {}).items():
        for k, v in fields.items():
            if v is not None:
                base["companies"].setdefault(t, {})[k] = v
                sources.setdefault(t, {})[k] = name


def fetch(tickers: list[str], refresh: bool = False) -> dict:
    path = SNAP / "market.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    from . import bloomberg, factset
    want = os.getenv("DATA_SOURCE", "auto").lower()
    out, sources = {"companies": {}}, {}
    if want in ("auto", "yahoo"):
        try:
            _merge(out, yahoo(tickers), "yahoo", sources)
        except Exception as e:
            out["yahoo_error"] = type(e).__name__
    for name, mod in (("factset", factset), ("bloomberg", bloomberg)):        # Bloomberg last: it wins ties
        if want in ("auto", name) and mod.available():
            try:
                _merge(out, mod.fetch(tickers), name, sources)
            except Exception as e:
                out[f"{name}_error"] = f"{type(e).__name__}: {e}"[:200]
    if not out["companies"] and path.exists():
        return {**json.loads(path.read_text()), "note": "all live sources failed; using last snapshot"}
    used = sorted({s for d in sources.values() for s in d.values()})
    out.update({"as_of": f"latest close, fetched {date.today()}", "sources_used": used, "field_sources": sources})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out
