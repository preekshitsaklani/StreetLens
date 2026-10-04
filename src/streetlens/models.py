"""Valuation models.

Banks (JPM, GS): residual income on tangible book value per share.
    value_0 = TBV_0 + sum_t RI_t / (1+Ke)^t + TV / (1+Ke)^5,  RI_t = (RoTCE_t - Ke) x TBV_{t-1}
    RoTCE: years 1-2 explicit, years 3-5 fade linearly to the sustainable level; terminal RI grows at g.
    Clean surplus: TBV_t = TBV_{t-1} + EPS_t x (1 - total payout), total payout = dividends + buybacks.
Asset manager (BLK): two-stage DCF on free cash flow to equity, FCFE = adjusted EPS (asset-light, ~100% conversion).
12-month target = value_0 x (1 + Ke) - dividend over the next year. Rating on total return = upside + dividend yield.
"""
import math

import numpy as np


def capm(rf, beta, erp):
    return rf + beta * erp


def adjusted_beta(raw):
    """Bloomberg-style adjusted beta: shrinks the raw regression beta one-third of the way toward 1."""
    return 0.67 * raw + 0.33


def r10(x):
    """Round to nearest whole dollar for share prices under $100, else nearest $5 (Excel: MROUND-style, halves up)."""
    step = 1 if x < 100 else 5
    return math.floor(x / step + 0.5) * step


def rotce_path(s):
    p = [s["rotce1"], s["rotce2"]]
    for k in (1, 2, 3):
        p.append(s["rotce2"] + (s["rotce_sust"] - s["rotce2"]) * k / 3)
    return p                                   # years 1..5


def bank_value(tbv0, dps1, ke, s):
    tbv, pv, rows = tbv0, 0.0, []
    for t, r in enumerate(rotce_path(s), start=1):
        eps = r * tbv
        ri = (r - ke) * tbv
        pv += ri / (1 + ke) ** t
        tbv_next = tbv + eps * (1 - s["total_payout"])
        rows.append({"year": t, "rotce": r, "tbv_open": tbv, "eps": eps, "ri": ri, "tbv_close": tbv_next})
        tbv = tbv_next
    tv = (s["rotce_sust"] - ke) * tbv / (ke - s["g"]) if ke > s["g"] else float("nan")
    v0 = tbv0 + pv + tv / (1 + ke) ** 5
    return {"value0": v0, "pv_ri": pv, "pv_tv": tv / (1 + ke) ** 5, "rows": rows, "tp_raw": v0 * (1 + ke) - dps1,
            "implied_ptbv": v0 / tbv0, "eps1": rows[0]["eps"], "eps2": rows[1]["eps"], "tbv1": rows[0]["tbv_close"]}


def am_value(eps0, ke, s):
    eps, pv, rows = eps0, 0.0, []
    for t in range(1, 6):
        eps = eps * (1 + s[f"g{t}"])
        pv += eps / (1 + ke) ** t
        rows.append({"year": t, "growth": s[f"g{t}"], "eps": eps})
    tv = eps * (1 + s["g"]) / (ke - s["g"]) if ke > s["g"] else float("nan")
    v0 = pv + tv / (1 + ke) ** 5
    dps1 = rows[0]["eps"] * s["div_payout"]
    return {"value0": v0, "pv_explicit": pv, "pv_tv": tv / (1 + ke) ** 5, "rows": rows, "dps1": dps1,
            "tp_raw": v0 * (1 + ke) - dps1, "eps1": rows[0]["eps"], "eps2": rows[1]["eps"],
            "implied_pe1": v0 / rows[0]["eps"]}


def rate(tp, price, dps1, buy, sell):
    up = tp / price - 1
    tr = up + dps1 / price
    return up, tr, "BUY" if tr >= buy else "SELL" if tr <= sell else "HOLD"


def value_company(c: dict, mkt: dict, macro: dict, val: dict, scenario: str = "base") -> dict:
    s = c["scenarios"][scenario]
    m = mkt["companies"][c["ticker"]]
    beta = adjusted_beta(m["beta"])
    ke = capm(macro["DGS10"]["value"], beta, val["erp"])
    if c["model"] == "bank":
        dps1 = c["latest"]["dps_run_rate"]
        res = bank_value(c["latest"]["tbvps"], dps1, ke, s)
    else:
        res = am_value(c["latest"]["adj_eps_quarter"] * 4, ke, s)
        dps1 = res["dps1"]
    tp = r10(res["tp_raw"])
    up, tr, rating = rate(tp, m["price"], dps1, val["buy"], val["sell"])
    return {**res, "ticker": c["ticker"], "scenario": scenario, "beta_raw": m["beta"], "beta_adj": beta, "ke": ke, "g": s["g"], "price": m["price"], "tp": tp,
            "upside": up, "total_return": tr, "dps1": dps1, "rating": rating}


def sensitivity(c, mkt, macro, val, kes=None, row_key=None, rows=None):
    """Target price grid. Banks: rows = sustainable RoTCE; asset manager: rows = terminal growth. Columns = Ke."""
    base = value_company(c, mkt, macro, val)
    kes = kes or [round(base["ke"] + d, 4) for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    s0 = dict(c["scenarios"]["base"])
    if c["model"] == "bank":
        row_key = "rotce_sust"
        rows = rows or [round(s0["rotce_sust"] + d, 4) for d in (-0.03, -0.015, 0, 0.015, 0.03)]
    else:
        row_key = "g"
        rows = rows or [round(s0["g"] + d, 4) for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    grid = np.full((len(rows), len(kes)), np.nan)
    for i, rv in enumerate(rows):
        for j, k in enumerate(kes):
            s = {**s0, row_key: rv}
            if c["model"] == "bank":
                r = bank_value(c["latest"]["tbvps"], c["latest"]["dps_run_rate"], k, s)
            else:
                r = am_value(c["latest"]["adj_eps_quarter"] * 4, k, s)
            grid[i, j] = r10(r["tp_raw"]) if not math.isnan(r["tp_raw"]) else np.nan
    return {"row_key": row_key, "rows": rows, "kes": kes, "grid": grid}


def implied(c, mkt, macro, val) -> dict:
    """Reverse valuation: what the current price implies, holding every other base assumption.
    Banks: the sustainable RoTCE that makes the 12-month value equal today's price. Asset manager: the terminal growth."""
    base = value_company(c, mkt, macro, val)
    price, ke, s0 = base["price"], base["ke"], dict(c["scenarios"]["base"])
    if c["model"] == "bank":
        key, lo, hi = "rotce_sust", s0["g"] + 0.001, 0.60
        f = lambda x: bank_value(c["latest"]["tbvps"], c["latest"]["dps_run_rate"], ke, {**s0, key: x})["tp_raw"] - price
    else:
        key, lo, hi = "g", -0.05, ke - 0.0005
        f = lambda x: am_value(c["latest"]["adj_eps_quarter"] * 4, ke, {**s0, key: x})["tp_raw"] - price
    if f(lo) * f(hi) > 0:
        return {"key": key, "value": None}
    for _ in range(80):                         # bisection: robust, monotone in both models
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(lo) * f(mid) > 0 else (lo, mid)
    return {"key": key, "value": (lo + hi) / 2}
