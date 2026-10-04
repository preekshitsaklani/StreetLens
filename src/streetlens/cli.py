"""StreetLens command line.

  python -m streetlens build [--refresh]        # notes, Excel model, CSVs for JPM, GS, BLK (snapshots unless --refresh)
  python -m streetlens update --ticker JPM      # read new call/release documents (LLM), revise drivers, revalue
"""
import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import bridge, edgar, macro, market, report
from .excel import build as build_xlsx
from .models import implied, sensitivity, value_company
from .paths import COMPANIES, OUTPUT, ROOT

TICKERS = ("JPM", "GS", "BLK", "STT")


def load():
    return {t: json.loads((COMPANIES / f"{t}.json").read_text()) for t in TICKERS}, json.loads((COMPANIES / "_valuation.json").read_text())


def build(refresh=False, out=OUTPUT, quant=None) -> dict:
    t0 = time.perf_counter()
    cos, val = load()
    peers = sorted({p for c in cos.values() for p in c["peers"]})
    with ThreadPoolExecutor(max_workers=4) as pool:                       # network fetches in parallel
        fx_f = {t: [pool.submit(edgar.facts, k, refresh) for k in c["ciks"]] for t, c in cos.items()}
        mac_f, mkt_f = pool.submit(macro.fetch, refresh), pool.submit(market.fetch, peers, refresh)
        fx = {t: [f.result() for f in fs] for t, fs in fx_f.items()}
        mac, mkt = mac_f.result(), mkt_f.result()
    t1 = time.perf_counter()
    hist = {t: edgar.history(fx[t], c["concepts"]) for t, c in cos.items()}
    results, scen, notes = {}, {}, {}
    for t, c in cos.items():
        scen[t] = {s: value_company(c, mkt, mac, val, s) for s in ("bear", "base", "bull")}
        results[t] = scen[t]["base"]
        comps = json.loads((COMPANIES / "_competitors.json").read_text()).get(t)
        qv = None
        if quant:
            pick = lambda rows: next((r for r in rows if r["ticker"] == t), None)
            fc = quant["forecast"]
            qv = {"rate": pick(quant["rate"]), "nii": pick(quant["nii"]), "nearest": quant["nearest"].get(t),
                  "forecast": fc[fc["ticker"] == t].iloc[0] if (fc["ticker"] == t).any() else None}
        notes[t] = report.company_note(c, results[t], scen[t], sensitivity(c, mkt, mac, val), implied(c, mkt, mac, val), hist[t], mkt, comps, qv)
    out.mkdir(parents=True, exist_ok=True)
    for t, n in notes.items():
        (out / f"{t}_initiation.md").write_text(n)
    ins = None
    if quant:
        from .insights import build as build_insights
        clusters = quant["peer_map"].set_index("ticker")["cluster"]
        members = {t: sorted(clusters[clusters == clusters[t]].index.drop(t)) for t in cos if t in clusters}
        ins = build_insights(quant["rate"], quant["nii"], quant["ml_eval"], quant["nearest"], members, results)
    (out / "US_Financials_sector_note.md").write_text(report.sector_note(cos, results, mac, mkt, ins))
    table = {s: {t: scen[t][s] for t in cos} for s in ("bear", "base", "bull")}
    extra = None
    if quant:
        import pandas as pd
        extra = {"Rate_Sensitivity": pd.DataFrame(quant["rate"]), "NII_Sensitivity": pd.DataFrame(quant["nii"]),
                 "ML_Backtest": pd.DataFrame([{"model": k, "mae_pts": v * 100} for k, v in quant["ml_eval"]["mae"].items()]),
                 "Peers": quant["peer_map"][["ticker", "cluster", "is_focus"]]}
    build_xlsx(out / "US_Financials_Coverage_Model.xlsx", cos, mkt, mac, val, hist, 2, table, extra)
    from .terminal_workbook import build as build_terminal
    build_terminal(out / "Terminal_Formulas.xlsx", list(cos))
    with open(out / "valuations.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "scenario", "price", "target", "upside", "total_return", "rating", "ke", "beta_adj"])
        for s in ("bear", "base", "bull"):
            for t in cos:
                r = scen[t][s]
                w.writerow([t, s, r["price"], r["tp"], round(r["upside"], 4), round(r["total_return"], 4), r["rating"], round(r["ke"], 4), round(r["beta_adj"], 3)])
    with open(out / "history.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "year", "revenue_bn", "ni_common_bn", "eps", "dps", "roe", "rotce"])
        for t, h in hist.items():
            for x in h:
                w.writerow([t, x["year"], round((x["revenue"] or 0) / 1e9, 3), round(x["ni_common"] / 1e9, 3), x["eps"], x["dps"],
                            round(x.get("roe") or 0, 4), round(x.get("rotce") or 0, 4) if cos[t]["model"] == "bank" else ""])
    t2 = time.perf_counter()
    return {"results": results, "scen": scen, "hist": hist, "insights": ins, "mkt": mkt, "mac": mac,
            "seconds": {"data": round(t1 - t0, 2), "models_notes_excel": round(t2 - t1, 2)}}


def quant(refresh=False) -> dict:
    """Statistics, ML and peer analysis on real data. Quarterly growth is computed in SQL (window functions)."""
    import sqlite3
    import warnings
    import pandas as pd
    from . import ml, peers, prices, quarterly, stats
    warnings.filterwarnings("ignore")
    cos, _ = load()
    fq = pd.DataFrame([r for t, c in cos.items() for r in quarterly.long_table(t, [edgar.facts(k, refresh) for k in c["ciks"]])])
    mem = sqlite3.connect(":memory:")
    fq.to_sql("fundamentals_quarterly", mem, index=False)
    mem.executescript((ROOT / "sql" / "views.sql").read_text().split("-- Base-case")[0])
    q = pd.read_sql_query("SELECT * FROM v_quarterly_yoy", mem)
    d10, d2, ff = (macro.history(s, refresh) for s in ("DGS10", "DGS2", "DFF"))
    px = prices.weekly(prices.FOCUS + ["^GSPC"], "focus", refresh=refresh)
    w = stats.weekly_frame(px, d10, d2)
    data = ml.dataset(q, px["^GSPC"], ff, d10, d2)
    bt, audit = ml.backtest(data)
    fc, imp = ml.forecast_next(data)
    pr = peers.run(prices.weekly(prices.UNIVERSE, "universe", period="2y", refresh=refresh), prices.FOCUS)
    return {"fq": fq, "q": q, "rate": stats.rate_sensitivity(w, prices.FOCUS), "rolling": stats.rolling_rate_beta(w, prices.FOCUS),
            "nii": stats.nii_sensitivity(q, ff), "ml_data": data, "backtest": bt, "ml_audit": audit, "ml_eval": ml.evaluate(bt),
            "forecast": fc, "importance": imp, "peer_map": pr["map"], "nearest": pr["nearest"], "px": px,
            "macro_hist": {"DGS10": d10, "DGS2": d2, "DFF": ff}}


def run_all(refresh=False, out=OUTPUT) -> dict:
    """One command, everything: data, statistics, ML, valuations, notes, Excel, SQL warehouse, Tableau extracts, QA."""
    import pandas as pd
    from . import qa, warehouse
    t0 = time.perf_counter()
    qd = quant(refresh)
    t1 = time.perf_counter()
    b = build(refresh, out, qd)
    t2 = time.perf_counter()
    cos, _ = load()
    vals = pd.DataFrame([{"ticker": t, "scenario": s, "price": r["price"], "target": r["tp"], "upside": r["upside"],
                          "total_return": r["total_return"], "rating": r["rating"], "ke": r["ke"]}
                         for t, sc in b["scen"].items() for s, r in sc.items()])
    facts = [f for t in cos for f in (json.loads((out / f"{t}_facts.json").read_text()) if (out / f"{t}_facts.json").exists() else [])]
    weekly = qd["px"][qd["px"].index >= qd["px"].index.max() - pd.DateOffset(years=5)]
    tables = {
        "companies": pd.DataFrame([{"ticker": t, "name": c["name"], "model": c["model"], "cik": c["ciks"][0]} for t, c in cos.items()]),
        "fundamentals_annual": pd.DataFrame([{"ticker": t, **{k: v for k, v in h.items()}} for t, hs in b["hist"].items() for h in hs]),
        "fundamentals_quarterly": qd["fq"],
        "prices_weekly": weekly.reset_index().melt(id_vars=weekly.index.name or "index", var_name="ticker", value_name="close")
                               .rename(columns={weekly.index.name or "index": "date"}).dropna(),
        "macro_daily": pd.concat([s.rename("value").to_frame().assign(series=k) for k, s in qd["macro_hist"].items()]).reset_index(),
        "valuations": vals, "rate_sensitivity": pd.DataFrame(qd["rate"]), "nii_sensitivity": pd.DataFrame(qd["nii"]),
        "rolling_betas": qd["rolling"], "ml_backtest": qd["backtest"], "ml_forecast": qd["forecast"], "peers_map": qd["peer_map"],
        "extracted_facts": pd.DataFrame(facts) if facts else pd.DataFrame(columns=["bank", "quarter", "metric", "value", "status"]),
    }
    con = warehouse.build(out / "streetlens.db", tables)
    tab = out / "tableau"
    tab.mkdir(exist_ok=True)
    exports = {"valuations": "SELECT * FROM valuations", "quarterly": "SELECT * FROM v_quarterly_yoy",
               "rate_betas": "SELECT *, CASE WHEN p_10y < 0.05 THEN 'significant' ELSE 'not significant' END AS significant FROM rate_sensitivity",
               "rolling_betas": "SELECT * FROM rolling_betas", "nii_sensitivity": "SELECT * FROM nii_sensitivity",
               "ml_backtest": "SELECT * FROM ml_backtest", "ml_forecast": "SELECT * FROM ml_forecast", "peers_map": "SELECT * FROM peers_map",
               "facts": "SELECT * FROM extracted_facts"}
    for name, sql in exports.items():
        warehouse.query(con, sql).to_csv(tab / f"{name}.csv", index=False)
    pd.DataFrame([{"model": k, "mae": v} for k, v in qd["ml_eval"]["mae"].items()]).to_csv(tab / "ml_summary.csv", index=False)
    jpm = cos["JPM"]
    ctx = {"jpm_tbvps_sec": edgar.tbvps_latest([edgar.facts(k) for k in jpm["ciks"]], jpm["concepts"]),
           "coverage": {f"{t}/{m}": n for (t, m), n in qd["fq"].groupby(["ticker", "metric"]).size().items()},
           "ml_audit": qd["ml_audit"], "valuations": b["results"], "fred_date": b["mac"]["DGS10"]["date"],
           "facts": facts or None, "xlsx": out / "US_Financials_Coverage_Model.xlsx"}
    checks = qa.run(ctx)
    qa.write(out / "qa_report.md", checks)
    t3 = time.perf_counter()
    return {"results": b["results"], "insights": b["insights"], "qa": checks, "ml_eval": qd["ml_eval"],
            "seconds": {"quant": round(t1 - t0, 1), "valuation_notes_excel": round(t2 - t1, 1), "warehouse_tableau_qa": round(t3 - t2, 1)}}


def choose_extractor(kind="auto"):
    """LLM if configured (or forced); otherwise the regex baseline, so updates always run on real filings."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    if kind == "llm" or (kind == "auto" and os.getenv("LLM_MODEL")):
        from earningslens.extract import LLMExtractor
        from earningslens.llm import LLMClient
        client = LLMClient.from_env()
        return LLMExtractor(client), client, f"LLM ({os.getenv('LLM_PROVIDER', 'gemini')}: {os.getenv('LLM_MODEL')})"
    from earningslens.extract import RegexExtractor
    return RegexExtractor(), None, "regex baseline (no LLM configured)"


def update(ticker, quarters=2, kind="auto", out=OUTPUT, fetch_filings=True, client_override=None, manifest=None) -> dict:
    from earningslens.extract import LLMExtractor
    from earningslens.ingest import load_manifest
    from earningslens.pipeline import process
    from . import filings
    cos, val = load()
    c = cos[ticker]
    if fetch_filings:
        filings.fetch(ticker, c["ciks"][0], n=quarters)
    docs = [t for t in load_manifest(manifest or ROOT / "data" / "manifest.csv") if t.bank == ticker]
    docs = [t for t in docs if t.quarter in sorted({d.quarter for d in docs}, key=lambda q: (q[-2:], q[1]))[-quarters:]]
    if client_override:
        ex, client, label = LLMExtractor(client_override), client_override, "replay (recorded LLM responses)"
    else:
        ex, client, label = choose_extractor(kind)
    with ThreadPoolExecutor(max_workers=4) as pool:
        res = list(pool.map(lambda t: process(t, ex, client), docs))
    rep = [r for x in res for r in x["reported"]]
    gui = [g for x in res for g in x["guidance"]]
    mkt = market.fetch(sorted({p for cc in cos.values() for p in cc["peers"]}))
    mac = macro.fetch()
    new_base, log = bridge.apply(c, rep, gui)
    before = value_company(c, mkt, mac, val)
    c_new = {**c, "scenarios": {**c["scenarios"], "base": new_base}}
    after = value_company(c_new, mkt, mac, val)
    steps = bridge.attribute(c, value_company, c["scenarios"]["base"], new_base, log, mkt, mac, val)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{ticker}_update.md").write_text(report.update_note(c, sorted({f"{d.quarter}: {d.source_url}" for d in docs}), label, rep, before, after, log, steps))
    (out / f"{ticker}_revised_assumptions.json").write_text(json.dumps(c_new, indent=1))
    used = {x["evidence"] for x in log}
    (out / f"{ticker}_facts.json").write_text(json.dumps([{**{k: r.get(k) for k in ("bank", "quarter", "metric", "value", "unit", "status", "match", "evidence")},
                                                            "used": r["evidence"] in used} for r in rep], indent=1))
    return {"before": before, "after": after, "log": log, "steps": steps, "extractor": label, "n_docs": len(docs),
            "grounded": sum(r["status"] == "grounded" for r in rep), "rejected": sum(r["status"] != "grounded" for r in rep)}


def sources():
    """What will run on this machine: data vendors and the LLM."""
    import os
    from . import bloomberg, factset
    ex = choose_extractor()[2]
    print(f"Bloomberg Terminal API : {'available' if bloomberg.available() else 'not available (needs blpapi + logged-in Terminal)'}")
    print(f"FactSet Formula API    : {'credentials found' if factset.available() else 'not configured (FACTSET_USERNAME_SERIAL, FACTSET_API_KEY)'}")
    print("Yahoo Finance          : always tried; snapshot used if offline")
    print("SEC EDGAR / FRED       : free; SEC_USER_AGENT " + ("set" if os.getenv("SEC_USER_AGENT") else "not set (add your name and email)"))
    print(f"Extraction             : {ex}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="streetlens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--refresh", action="store_true"); b.add_argument("--out", default=str(OUTPUT))
    u = sub.add_parser("update"); u.add_argument("--ticker", required=True, choices=TICKERS)
    u.add_argument("--quarters", type=int, default=2); u.add_argument("--extractor", choices=["auto", "llm", "regex"], default="auto")
    u.add_argument("--out", default=str(OUTPUT))
    sub.add_parser("sources")
    al = sub.add_parser("all"); al.add_argument("--refresh", action="store_true"); al.add_argument("--out", default=str(OUTPUT))
    a = ap.parse_args(argv)
    if a.cmd == "build":
        res = build(a.refresh, Path(a.out))
        for t, r in res["results"].items():
            print(f"{t:4} {r['rating']:5} target ${r['tp']:,.0f}  price ${r['price']:,.2f}  total return {r['total_return']:+.1%}")
        print("timings:", res["seconds"], "->", a.out)
    elif a.cmd == "sources":
        sources()
    elif a.cmd == "all":
        r = run_all(a.refresh, Path(a.out))
        for t, v in r["results"].items():
            print(f"{t:4} {v['rating']:5} target ${v['tp']:,.0f}  price ${v['price']:,.2f}  total return {v['total_return']:+.1%}")
        print("\n".join("- " + i for i in r["insights"]))
        n = {k: sum(c[1] == k for c in r["qa"]) for k in ("PASS", "FAIL", "SKIP")}
        print(f"QA: {n['PASS']} passed, {n['FAIL']} failed, {n['SKIP']} skipped (output/qa_report.md); timings {r['seconds']}")
    else:
        r = update(a.ticker, a.quarters, a.extractor, Path(a.out))
        b, n = r["before"], r["after"]
        print(f"{a.ticker}: read {r['n_docs']} SEC filings with {r['extractor']}; {r['grounded']} figures verified, {r['rejected']} rejected")
        for x in r["log"]:
            print(f"  {x['driver']}: {x['old']:.4f} -> {x['new']:.4f}  [{x['rule']}]")
        print(f"  target ${b['tp']:,.0f} ({b['rating']}) -> ${n['tp']:,.0f} ({n['rating']}); note: {a.out}/{a.ticker}_update.md")
        print(f"  Review {a.ticker}_revised_assumptions.json, copy it over companies/{a.ticker}.json, then run build.")


if __name__ == "__main__":
    main()
