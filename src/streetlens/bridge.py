"""Earnings-call bridge for US Financials: grounded facts -> base-case driver changes, each logged with its evidence."""


from earningslens.config import q_index


def _latest(rows, metric):
    ok = [r for r in rows if r["metric"] == metric and r["status"] == "grounded"]
    return max(ok, key=lambda r: q_index(r["quarter"]), default=None)


def attribute(c, value_fn, old_base, new_base, log, *args) -> list[dict]:
    """Target bridge by sequential substitution, one driver at a time. Steps sum exactly to the change in unrounded value."""
    steps, d = [], dict(old_base)
    v = lambda dd: value_fn({**c, "scenarios": {**c["scenarios"], "base": dd}}, *args)["tp_raw"]
    prev = v(d)
    for ch in log:
        d[ch["driver"]] = ch["new"]
        now = v(d)
        steps.append({"step": f"{ch['driver']}: {ch['old']:.4f} -> {ch['new']:.4f}", "usd_per_share": now - prev, "evidence": ch["evidence"]})
        prev = now
    return steps


def apply(c: dict, reported: list[dict], guidance: list[dict]) -> tuple[dict, list[dict]]:
    base, log = dict(c["scenarios"]["base"]), []

    def change(key, new, rule, ev):
        if abs(new - base[key]) > 1e-9:
            log.append({"driver": key, "old": base[key], "new": round(new, 4), "rule": rule, "evidence": ev})
            base[key] = round(new, 4)

    if c["model"] == "bank":
        r = _latest(reported, "rotce")
        if r:
            change("rotce1", 0.5 * r["value_pct"] / 100 + 0.5 * base["rotce1"], "50/50 blend: latest reported RoTCE and prior", r["evidence"])
        g = _latest(guidance, "rotce")
        if g and g["low_pct"] is not None:
            target = (g["low_pct"] + (g["high_pct"] or g["low_pct"])) / 200
            change("rotce_sust", 0.5 * target + 0.5 * base["rotce_sust"], "50/50 blend: management RoTCE target and prior", g["evidence"])
    else:
        r = _latest(reported, "organic_base_fee_growth")
        target = c.get("eps_build", {}).get("organic_base_fee_growth", 0.05)
        if r:
            change("g1", base["g1"] + 0.5 * (r["value_pct"] / 100 - target),
                   f"year-1 growth moves by half the gap between reported organic growth and the {target:.0%} target", r["evidence"])
    return base, log
