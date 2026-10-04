"""Turn statistical results into plain-English, actionable findings. Deterministic; an optional LLM may rephrase
but any paragraph with a number not present in the findings is discarded (same guard as EarningsLens)."""
NAMES = {"JPM": "JPMorgan", "GS": "Goldman Sachs", "BLK": "BlackRock", "STT": "State Street"}


def build(rate: list, nii: list, ml_eval: dict, nearest: dict, clusters: dict, vals: dict) -> list[str]:
    out = []
    sig = sorted([r for r in rate if r["p_10y"] < 0.05], key=lambda r: -r["beta_10y"])
    if sig:
        top = sig[0]
        out.append(f"Rates: {NAMES[top['ticker']]} is the clearest rates play. Over {top['n_weeks']} weeks, a 1 percentage point rise in the "
                   f"10-year Treasury yield coincided with a {top['beta_10y'] * 100:+.1f}% move relative to the market (t = {top['t_10y']:.1f}). "
                   + "; ".join(f"{NAMES[r['ticker']]} {r['beta_10y'] * 100:+.1f}% (t = {r['t_10y']:.1f})" for r in sig[1:])
                   + (". " if len(sig) > 1 else "") + "No other name shows a statistically significant link at the 5% level.")
    for r in sorted(nii, key=lambda r: r["p"]):
        verdict = "a reliable deposit-bank pattern" if r["p"] < 0.05 else "no reliable link, consistent with trading-driven net interest income"
        out.append(f"Fed sensitivity: for {NAMES[r['ticker']]}, each 1 point year-on-year rise in the Fed funds rate has gone with "
                   f"{r['nii_growth_per_1pp'] * 100:+.1f} points of net interest income growth over {r['n_quarters']} quarters "
                   f"(R squared {r['r2']:.2f}): {verdict}.")
    m = ml_eval["mae"]
    if ml_eval["best"] == "naive":
        out.append(f"Forecasting: across {ml_eval['n_forecasts']} walk-forward forecasts ({ml_eval['first']} to {ml_eval['last']}), the naive baseline "
                   f"(mean absolute error {m['naive'] * 100:.1f} points) beat ridge regression ({m['ridge'] * 100:.1f}) and gradient boosting "
                   f"({m['gbm'] * 100:.1f}). Revenue growth is mostly momentum; the models are reported, not used for estimates.")
    else:
        out.append(f"Forecasting: {ml_eval['best']} cut mean absolute error by {ml_eval['improvement_vs_naive'] * 100:.0f}% versus the naive baseline "
                   f"over {ml_eval['n_forecasts']} walk-forward forecasts.")
    for t, peers in nearest.items():
        p = ", ".join(f"{k} ({v:.2f})" for k, v in peers.items())
        out.append(f"Peers: {NAMES[t]} trades most closely with {p} (weekly return correlation, 2 years); cluster: {', '.join(clusters[t])}.")
    best = max(vals.items(), key=lambda kv: kv[1]["total_return"])
    out.append(f"Valuation: {NAMES[best[0]]} offers the highest base-case 12-month total return ({best[1]['total_return'] * 100:+.1f}%, {best[1]['rating']}).")
    return out
