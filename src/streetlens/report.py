"""Initiation notes (one per company) and a sector note, generated from the same numbers as the Excel workbook."""
from datetime import date

EDGAR_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={}&type=10-K"


def p(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def usd(x, d=0):
    return f"${x:,.{d}f}"


def company_note(c, res, scen, sens, imp, hist, mkt, competitors=None, quant=None) -> str:
    m = mkt["companies"][c["ticker"]]
    bank = c["model"] == "bank"
    lo, hi = scen["bear"]["tp"], scen["bull"]["tp"]
    L = [f"# {c['name']} ({c['ticker']}): Initiation", "",
         f"_{date.today():%d %b %Y} · prices as of {mkt['as_of']} · student research project, not investment advice_", "",
         f"**{res['rating']}, 12-month target {usd(res['tp'])}: {p(abs(res['upside']))} price {'upside' if res['upside'] >= 0 else 'downside'}, "
         f"{p(res['total_return'])} expected total return including dividends.**", "",
         "| Key data | Value |", "| --- | --- |",
         f"| Price | {usd(res['price'], 2)} |", f"| 12-month target | {usd(res['tp'])} |",
         f"| Bear to bull target | {usd(lo)} to {usd(hi)} |", f"| 52-week range | {usd(m['low52'])} to {usd(m['high52'])} |",
         f"| Market cap | {usd(m['mcap_bn'])} bn |",
         f"| Beta: raw / adjusted | {res['beta_raw']:.2f} / {res['beta_adj']:.2f} |", f"| Cost of equity | {p(res['ke'], 2)} |",
         f"| Method | {'Residual income on tangible book value' if bank else 'Two-stage DCF on free cash flow to equity'} |",
         f"| Market data source | {', '.join(mkt.get('sources_used', ['snapshot']))} |", "",
         "## Investment thesis", ""] + [f"{i}. {t}" for i, t in enumerate(c["thesis"], 1)]
    if imp["value"] is not None:
        what = "sustainable RoTCE" if bank else "terminal growth"
        ours = c["scenarios"]["base"]["rotce_sust" if bank else "g"]
        L += ["", f"**What the price implies:** holding our other assumptions, today's price implies a {what} of {p(imp['value'])}, "
                  f"against {p(ours)} in our base case."]
        if bank:
            avg = [h["rotce"] for h in hist if h.get("rotce") is not None]
            if avg:
                L[-1] += f" RoTCE averaged {p(sum(avg) / len(avg))} over FY{hist[0]['year']} to FY{hist[-1]['year']} (computed from SEC filings)."
    if m.get("consensus_tp"):
        gap = res["tp"] / m["consensus_tp"] - 1
        src = mkt.get("field_sources", {}).get(c["ticker"], {}).get("consensus_tp", "data provider")
        L += ["", f"**Versus consensus:** the average analyst target is {usd(m['consensus_tp'])} ({src}); ours is {p(abs(gap))} "
                  f"{'above' if gap >= 0 else 'below'} it."]
    L += ["", f"## Latest quarter ({c['latest']['as_of']})", ""] + [f"- {n}" for n in c["latest"]["notes"]] + \
         ["", f"Source: [{c['latest']['source']}]({c['latest']['url']})", "", "## Five-year history (SEC XBRL filings)", "",
          "| USD bn unless stated | " + " | ".join(f"FY{h['year']}" for h in hist) + " |", "| --- |" + " --- |" * len(hist)]
    rows = [("Net revenue", "revenue", 1e9, "{:,.1f}"), ("Net income to common", "ni_common", 1e9, "{:,.1f}"),
            ("Diluted EPS (USD)", "eps", 1, "{:.2f}"), ("Dividends per share (USD)", "dps", 1, "{:.2f}"), ("ROE", "roe", None, None)]
    if bank:
        rows.append(("RoTCE", "rotce", None, None))
    for lab, k, sc, fmt in rows:
        cells = [(p(h.get(k)) if sc is None else (fmt.format(h[k] / sc) if h.get(k) is not None else "n/a")) for h in hist]
        L.append(f"| {lab} | " + " | ".join(cells) + " |")
    if quant:
        r, n, nearest, fc = quant.get("rate"), quant.get("nii"), quant.get("nearest"), quant.get("forecast")
        L += ["", "## Quant view", ""]
        if r:
            L.append(f"- **Rates:** a 1 point rise in the 10-year yield has coincided with a {r['beta_10y'] * 100:+.1f}% move relative to the market "
                     f"(t = {r['t_10y']:.1f}, {'significant' if r['p_10y'] < 0.05 else 'not significant'} at 5%; {r['n_weeks']} weeks, Newey-West errors).")
        if n:
            L.append(f"- **Fed funds:** each 1 point year-on-year rise has gone with {n['nii_growth_per_1pp'] * 100:+.1f} points of net interest income growth "
                     f"(t = {n['t']:.1f}, R squared {n['r2']:.2f}, {n['n_quarters']} quarters).")
        if nearest:
            L.append("- **Trades with:** " + ", ".join(f"{k} ({v:.2f})" for k, v in nearest.items()) + " (2-year weekly return correlation).")
        if fc is not None:
            L.append(f"- **Next-quarter revenue growth (YoY):** naive {fc['naive'] * 100:.1f}%, ridge {fc['ridge'] * 100:.1f}%, gradient boosting {fc['gbm'] * 100:.1f}%. "
                     "In backtests the naive estimate was the most accurate, so treat the model figures as context only.")
    L += ["", "## Valuation", ""]
    s = c["scenarios"]["base"]
    if bank:
        L += [f"Residual income: value = tangible book per share ({usd(c['latest']['tbvps'], 2)} at {c['latest']['as_of']}) plus the present value of "
              f"returns above the {p(res['ke'], 2)} cost of equity. RoTCE runs {p(s['rotce1'])} and {p(s['rotce2'])} in years 1 and 2, "
              f"fades to a sustainable {p(s['rotce_sust'])} by year 5, then grows at {p(s['g'])}. {c.get('sust_note', '')}", "",
              "| Base case | Y1 | Y2 | Y3 | Y4 | Y5 |", "| --- | --- | --- | --- | --- | --- |",
              "| RoTCE | " + " | ".join(p(r["rotce"]) for r in res["rows"]) + " |",
              "| EPS (USD) | " + " | ".join(f"{r['eps']:.2f}" for r in res["rows"]) + " |",
              "| Residual income (USD) | " + " | ".join(f"{r['ri']:.2f}" for r in res["rows"]) + " |", "",
              f"Value today {usd(res['value0'], 2)} = tangible book {usd(c['latest']['tbvps'], 2)} + PV of years 1-5 residual income "
              f"{usd(res['pv_ri'], 2)} + PV of terminal value {usd(res['pv_tv'], 2)}: an implied {res['implied_ptbv']:.2f}x tangible book. "
              f"Rolled forward one year at Ke, less the {usd(res['dps1'], 2)} dividend, this gives the {usd(res['tp'])} target."]
    else:
        L += [f"Two-stage DCF: free cash flow to equity equals adjusted EPS, starting from a {usd(c['latest']['adj_eps_quarter'] * 4, 2)} run-rate "
              f"(2Q26 adjusted EPS x 4). {c['eps_build']['note']}. Growth fades to {p(s['g5'])} by year 5, then {p(s['g'])} into perpetuity.", "",
              "| Base case | Y1 | Y2 | Y3 | Y4 | Y5 |", "| --- | --- | --- | --- | --- | --- |",
              "| EPS growth | " + " | ".join(p(r["growth"]) for r in res["rows"]) + " |",
              "| EPS (USD) | " + " | ".join(f"{r['eps']:.2f}" for r in res["rows"]) + " |", "",
              f"Value today {usd(res['value0'], 2)} = PV of years 1-5 {usd(res['pv_explicit'], 2)} + PV of terminal value {usd(res['pv_tv'], 2)}: "
              f"{res['implied_pe1']:.1f}x year-1 EPS. Rolled forward one year, less the {usd(res['dps1'], 2)} dividend, this gives {usd(res['tp'])}. "
              "Caveat: 2Q26 included higher performance fees, which flatters the run-rate."]
    rk = "Sustainable RoTCE" if bank else "Terminal growth"
    L += ["", f"**Sensitivity: target (USD) to {rk.lower()} (rows) and Ke (columns)**", "",
          f"| {rk} \\ Ke | " + " | ".join(p(k) for k in sens["kes"]) + " |", "| --- |" + " --- |" * len(sens["kes"])]
    L += [f"| {p(rv)} | " + " | ".join(usd(x) for x in row) + " |" for rv, row in zip(sens["rows"], sens["grid"])]
    L += ["", "## Scenarios", "", "| Scenario | Target | Total return | Rating |", "| --- | --- | --- | --- |"]
    L += [f"| {k.title()} | {usd(v['tp'])} | {p(v['total_return'])} | {v['rating']} |" for k, v in scen.items()]
    L += ["", "## Peers", "", "| Ticker | P/B | Forward P/E | ROE |", "| --- | --- | --- | --- |"]
    for t in c["peers"]:
        x = mkt["companies"].get(t, {})
        L.append(f"| {t} | {x.get('pb') or 0:.2f}x | {x.get('fwd_pe') or 0:.1f}x | {p(x.get('roe'))} |")
    for comp in competitors or []:
        L += ["", f"## Competitive landscape: {comp['name']}", "",
              "| | " + c["ticker"] + f" | {comp['name']} |", "| --- | --- | --- |",
              f"| Assets under management | ${c['latest'].get('aum_tn', 0):.1f}tn | about ${comp['aum_tn']:.0f}tn |",
              f"| Listed | Yes | {'Yes' if comp['listed'] else 'No'} |",
              f"| Average fund expense ratio | n/a | {comp['avg_expense_ratio'] * 100:.2f}% |", ""]
        L += [f"- {n}" for n in comp["notes"]] + ["", f"**Why it matters:** {comp['implication']}", "",
              f"Sources: {comp['aum_source']}; {comp['fee_source']}."]
    L += ["", "## Key risks", ""] + [f"- {r}" for r in c["risks"]]
    L += ["", "## Sources", "", f"- SEC EDGAR XBRL company facts, CIK {', '.join(c['ciks'])}: {EDGAR_URL.format(c['ciks'][0])}",
          f"- {c['latest']['source']}: {c['latest']['url']}", "- FRED: 10-year Treasury (DGS10), effective Fed funds (DFF)",
          f"- Yahoo Finance via yfinance: prices, 2-year weekly beta, peer multiples ({mkt['as_of']})"]
    return "\n".join(L) + "\n"


def sector_note(companies, results, macro, mkt, insights=None) -> str:
    d, f = macro["DGS10"], macro["DFF"]
    L = ["# US Financials: rates backdrop and relative value", "",
         f"_{date.today():%d %b %Y} · student research project, not investment advice_", "",
         f"The 10-year Treasury yield is {p(d['value'], 2)} ({d['date']}), up from {p(d['year_ago'], 2)} a year ago, while the effective Fed funds rate "
         f"is {p(f['value'], 2)}, down from {p(f['year_ago'], 2)}. A steeper curve helps bank net interest income, but a higher risk-free rate "
         "raises every cost of equity, and therefore lowers the multiple any given return deserves.", "",
         "| Company | Model | Price | Target | Total return | Rating | Ke |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for t, r in results.items():
        L.append(f"| {companies[t]['name']} | {'Residual income' if companies[t]['model'] == 'bank' else 'DCF'} | {usd(r['price'], 2)} | "
                 f"{usd(r['tp'])} | {p(r['total_return'])} | {r['rating']} | {p(r['ke'], 2)} |")
    L += ["", "**Common thread:** the market is pricing today's strong capital-markets cycle as durable. Goldman Sachs is the clearest case, "
              "since its earnings are the most cyclical of the three; JPMorgan's diversified mix makes its high returns easier to sustain, "
              "and BlackRock's fee base grows with markets and flows rather than with deal activity.", ""]
    if insights:
        L += ["## Quantitative findings", ""] + [f"- {i}" for i in insights] + [""]
    return "\n".join(L) + "\n"


def update_note(c, quarter_docs, extractor, rep, before, after, log, steps) -> str:
    good = [r for r in rep if r["status"] == "grounded"]
    bad = [r for r in rep if r["status"] != "grounded"]
    L = [f"# {c['name']} ({c['ticker']}): earnings update", "",
         f"_{date.today():%d %b %Y} · extractor: {extractor} · student research project, not investment advice_", "",
         f"**{after['rating']}, target {usd(after['tp'])} (was {usd(before['tp'])}, {before['rating']}); "
         f"{p(after['total_return'])} expected total return.**", "", "## Documents read (SEC EDGAR)", ""]
    L += [f"- {d}" for d in quarter_docs]
    L += ["", f"## Verified figures ({len(good)} accepted, {len(bad)} rejected by the grounding check)", "",
          "| Quarter | Metric | Value | Quote from the filing |", "| --- | --- | --- | --- |"]
    seen = set()
    for r in sorted(good, key=lambda r: (r["quarter"], r["metric"])):
        if (r["quarter"], r["metric"], r["value"]) in seen:          # same figure in release and presentation
            continue
        seen.add((r["quarter"], r["metric"], r["value"]))
        ev = " ".join(r["evidence"].split())
        i = max(ev.find(f"{r['value']:g}"), 0)
        q = ev[max(0, i - 70): i + 40].replace("|", "/")             # centre the quote on the figure
        L.append(f"| {r['quarter']} | {r['metric']} | {r['value']:g} | \"{q}\" |")
    L += ["", "## Model changes", "", "| Driver | Before | After | Rule |", "| --- | --- | --- | --- |"]
    L += [f"| {x['driver']} | {p(x['old'])} | {p(x['new'])} | {x['rule']} |" for x in log] or ["| none | | | no verified figure moved a driver |"]
    L += ["", "## Target price bridge (USD per share, before rounding)", "", "| Step | Change |", "| --- | --- |"]
    L += [f"| {s['step']} | {s['usd_per_share']:+.2f} |" for s in steps]
    L += [f"| **Total** | **{after['tp_raw'] - before['tp_raw']:+.2f}** |", ""]
    return "\n".join(L) + "\n"
