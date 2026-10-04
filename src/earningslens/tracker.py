"""Guidance vs delivery: did management deliver what it guided in later quarters?"""
import re

from .config import AMOUNT_TOL_REL, METRICS, TOLERANCE_PP, q_index, q_label


def target_quarters(guided_q: str, horizon: str) -> list[str]:
    """Quarters in which a guidance statement can be checked, strictly after the call."""
    i = q_index(guided_q)
    h = (horizon or "").upper().replace(" ", "")
    m = re.search(r"Q([1-4])FY(\d{2})", h)
    if m:
        t = q_index(f"Q{m.group(1)}FY{m.group(2)}")
        return [q_label(t)] if t > i else []
    m = re.search(r"FY(\d{2})", h)
    if m:
        fy = int(m.group(1))
        return [q_label(fy * 4 + k) for k in range(4) if fy * 4 + k > i]
    if "NEXTQUARTER" in h:
        return [q_label(i + 1)]
    return [q_label(i + k) for k in range(1, 5)]   # default: next four quarters


def evaluate(reported: list[dict], guidance: list[dict]) -> list[dict]:
    """reported: grounded rows with bank, quarter (call), metric, value_pct. guidance: grounded rows."""
    actual = {}
    for r in reported:
        if r["period"] == r["quarter"]:                       # quarter's own results only
            actual[(r["bank"], r["metric"], r["period"])] = r["value_pct"]
    rows = []
    for g in guidance:
        fam = METRICS[g["metric"]][1]
        tol = TOLERANCE_PP[fam]
        targets = target_quarters(g["quarter"], g["horizon"])
        seen = [(q, actual[(g["bank"], g["metric"], q)]) for q in targets if (g["bank"], g["metric"], q) in actual]
        status, observed, obs_q = "pending", None, ""
        if seen:
            obs_q, observed = seen[-1]
            if g["low_pct"] is not None:
                lo, hi = g["low_pct"], g["high_pct"] if g["high_pct"] is not None else g["low_pct"]
                if fam == "amount":
                    tol = AMOUNT_TOL_REL * abs(hi)
                status = "delivered" if lo - tol <= observed <= hi + tol else "missed"
            elif g["direction"]:
                base = actual.get((g["bank"], g["metric"], g["quarter"]))
                if base is None:
                    status = "no_baseline"
                else:
                    d = observed - base
                    got = "up" if d > tol else "down" if d < -tol else "stable"
                    status = "delivered" if got == g["direction"] else "missed"
        rows.append({**{k: g[k] for k in ("bank", "quarter", "metric", "kind", "low_pct", "high_pct", "direction", "horizon", "evidence")},
                     "checked_in": obs_q, "observed_pct": observed, "status": status})
    return rows


def scorecard(rows: list[dict]) -> list[dict]:
    out = {}
    for r in rows:
        s = out.setdefault(r["bank"], {"bank": r["bank"], "guided": 0, "resolved": 0, "delivered": 0})
        s["guided"] += 1
        if r["status"] in ("delivered", "missed"):
            s["resolved"] += 1
            s["delivered"] += r["status"] == "delivered"
    for s in out.values():
        s["delivery_rate"] = round(s["delivered"] / s["resolved"], 3) if s["resolved"] else None
    return sorted(out.values(), key=lambda s: s["bank"])
