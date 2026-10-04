"""Formula-driven Excel workbook: one sheet per company, shared macro inputs, scenario selector, comps, history.
Mirrors models.py formula for formula; tests recalculate it and compare with the Python engine."""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

BLUE, BLACK, GREEN = "0000FF", "000000", "008000"
HEAD, SUBF, YEL = PatternFill("solid", fgColor="1F3864"), PatternFill("solid", fgColor="D9E1F2"), PatternFill("solid", fgColor="FFFF00")
USD, PCT, MULT = '$#,##0.00;($#,##0.00);"-"', '0.00%;(0.00%);"-"', '0.00"x"'
SEL = "Cover!$B$5"
COLS = "BCDEF"


def w(ws, ref, v, color=BLACK, bold=False, fmt=None, fill=None, italic=False):
    c = ws[ref]
    c.value = v
    c.font = Font(name="Arial", size=10, color=color, bold=bold, italic=italic)
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    return c


def head(ws, row, labels):
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=1 + i, value=lab)
        c.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        c.fill = HEAD
        c.alignment = Alignment(horizontal="left" if i == 0 else "center")


def sec(ws, row, text, n=6):
    for i in range(n):
        ws.cell(row=row, column=1 + i).fill = SUBF
    w(ws, f"A{row}", text, bold=True, fill=SUBF)


def common(ws, c, mkt):
    """Rows 1-10: title, price, beta, CAPM. Identical rows on every company sheet."""
    m = mkt["companies"][c["ticker"]]
    w(ws, "A1", f"{c['name']} ({c['ticker']}): {'residual income on tangible book' if c['model'] == 'bank' else 'two-stage DCF on FCFE'}", bold=True)
    w(ws, "A2", "Blue = input, black = formula, green = link. Scenario selector on Cover.", italic=True)
    sec(ws, 4, "Market data and cost of equity")
    w(ws, "A5", f"Share price (USD), {mkt['as_of']}"); w(ws, "B5", m["price"], BLUE, fmt=USD)
    w(ws, "A6", "Raw beta vs S&P 500 (2-year weekly)"); w(ws, "B6", m["beta"], BLUE, fmt="0.00")
    w(ws, "A7", "Adjusted beta (0.67 x raw + 0.33)"); w(ws, "B7", "=0.67*B6+0.33", fmt="0.00")
    w(ws, "A8", "Risk-free rate (10Y Treasury)"); w(ws, "B8", "=Macro!$B$4", GREEN, fmt=PCT)
    w(ws, "A9", "Equity risk premium"); w(ws, "B9", "=Macro!$B$6", GREEN, fmt=PCT)
    w(ws, "A10", "Cost of equity (Ke)", bold=True); w(ws, "B10", "=B8+B7*B9", bold=True, fmt=PCT)


def drivers(ws, c, rows, start=14):
    sec(ws, start - 1, "Scenario drivers")
    head(ws, start, ["Driver", "Bear", "Base", "Bull", "Active"])
    out = {}
    for i, (key, label, fmt) in enumerate(rows):
        r = start + 1 + i
        w(ws, f"A{r}", label)
        for col, scen in zip("BCD", ("bear", "base", "bull")):
            w(ws, f"{col}{r}", c["scenarios"][scen][key], BLUE, fmt=fmt)
        w(ws, f"E{r}", f"=CHOOSE({SEL},B{r},C{r},D{r})", bold=True, fmt=fmt)
        out[key] = f"$E${r}"
    return out


def outputs(ws, first, value_ref, tp_raw_formula, dps_ref, implied_label, implied_formula):
    """Rows first..first+8: value, target, upside, total return, rating, implied multiple. Same rows on every sheet."""
    r = first
    w(ws, f"A{r}", "Equity value per share today (USD)", bold=True); w(ws, f"B{r}", value_ref, bold=True, fmt=USD)
    w(ws, f"A{r+1}", "12-month value: value x (1 + Ke) - next-year dividend"); w(ws, f"B{r+1}", tp_raw_formula, fmt=USD)
    w(ws, f"A{r+2}", "12-month target price (USD; $5 steps above $100)", bold=True)
    w(ws, f"B{r+2}", f"=IF(B{r+1}<100,ROUND(B{r+1},0),FLOOR(B{r+1}/5+0.5,1)*5)", bold=True, fmt='$#,##0', fill=YEL)
    w(ws, f"A{r+3}", "Price upside"); w(ws, f"B{r+3}", f"=B{r+2}/B5-1", fmt=PCT)
    w(ws, f"A{r+4}", "Total return (upside + dividend yield)", bold=True); w(ws, f"B{r+4}", f"=B{r+3}+{dps_ref}/B5", bold=True, fmt=PCT)
    w(ws, f"A{r+5}", "Rating", bold=True)
    w(ws, f"B{r+5}", f'=IF(B{r+4}>=Macro!$B$7,"BUY",IF(B{r+4}<=Macro!$B$8,"SELL","HOLD"))', bold=True)
    w(ws, f"A{r+6}", implied_label); w(ws, f"B{r+6}", implied_formula, fmt=MULT)
    return {"tp": f"$B${r+2}", "tr": f"$B${r+4}", "rating": f"$B${r+5}"}


def bank_sheet(wb, c, mkt):
    ws = wb.create_sheet(c["ticker"])
    common(ws, c, mkt)
    w(ws, "A11", f"Tangible book value per share, {c['latest']['as_of']} (USD)"); w(ws, "B11", c["latest"]["tbvps"], BLUE, fmt=USD)
    w(ws, "A12", "Dividend per share, next 12 months (USD)"); w(ws, "B12", c["latest"]["dps_run_rate"], BLUE, fmt=USD)
    d = drivers(ws, c, [("rotce1", "RoTCE, year 1", PCT), ("rotce2", "RoTCE, year 2", PCT), ("rotce_sust", "Sustainable RoTCE (year 5 and terminal)", PCT),
                        ("g", "Long-term growth (g)", PCT), ("total_payout", "Total payout (dividends + buybacks)", PCT)])
    sec(ws, 21, "Residual income: RI = (RoTCE - Ke) x opening TBV; RoTCE fades linearly from year 2 to sustainable by year 5")
    head(ws, 22, ["Year", "Y1", "Y2", "Y3", "Y4", "Y5"])
    labels = ["t", "RoTCE", "TBV per share, opening", "EPS", "Residual income", "TBV per share, closing", "PV of residual income"]
    for i, lab in enumerate(labels):
        w(ws, f"A{23 + i}", lab)
    for j, col in enumerate(COLS):
        t = j + 1
        w(ws, f"{col}23", t)
        rot = {1: f"={d['rotce1']}", 2: f"={d['rotce2']}"}.get(t, f"=$C$24+({d['rotce_sust']}-$C$24)*{t - 2}/3")
        w(ws, f"{col}24", rot, fmt=PCT)
        w(ws, f"{col}25", "=B11" if t == 1 else f"={COLS[j - 1]}28", fmt=USD)
        w(ws, f"{col}26", f"={col}24*{col}25", fmt=USD)
        w(ws, f"{col}27", f"=({col}24-$B$10)*{col}25", fmt=USD)
        w(ws, f"{col}28", f"={col}25+{col}26*(1-{d['total_payout']})", fmt=USD)
        w(ws, f"{col}29", f"={col}27/(1+$B$10)^{col}23", fmt=USD)
    w(ws, "A31", "Terminal value of RI at year 5"); w(ws, "B31", f"=({d['rotce_sust']}-B10)*F28/(B10-{d['g']})", fmt=USD)
    w(ws, "A32", "PV of terminal value"); w(ws, "B32", "=B31/(1+B10)^5", fmt=USD)
    return ws, outputs(ws, 34, "=B11+SUM(B29:F29)+B32", "=B34*(1+B10)-B12", "B12", "Implied price / TBV (x)", "=B34/B11")


def am_sheet(wb, c, mkt):
    ws = wb.create_sheet(c["ticker"])
    common(ws, c, mkt)
    w(ws, "A11", f"Adjusted EPS, latest quarter ({c['latest']['as_of']}, USD)"); w(ws, "B11", c["latest"]["adj_eps_quarter"], BLUE, fmt=USD)
    w(ws, "A12", "Adjusted EPS run-rate (quarter x 4)"); w(ws, "B12", "=B11*4", fmt=USD)
    d = drivers(ws, c, [("g1", "EPS growth, year 1", PCT), ("g2", "EPS growth, year 2", PCT), ("g3", "EPS growth, year 3", PCT),
                        ("g4", "EPS growth, year 4", PCT), ("g5", "EPS growth, year 5", PCT), ("g", "Terminal growth (g)", PCT),
                        ("div_payout", "Dividend payout", PCT)])
    sec(ws, 23, "Free cash flow to equity = adjusted EPS (asset-light model, ~100% cash conversion)")
    head(ws, 24, ["Year", "Y1", "Y2", "Y3", "Y4", "Y5"])
    for i, lab in enumerate(["t", "EPS growth", "EPS / FCFE per share", "PV of FCFE"]):
        w(ws, f"A{25 + i}", lab)
    for j, col in enumerate(COLS):
        t = j + 1
        w(ws, f"{col}25", t)
        w(ws, f"{col}26", f"={d['g' + str(t)]}", fmt=PCT)
        w(ws, f"{col}27", f"=B12*(1+B26)" if t == 1 else f"={COLS[j - 1]}27*(1+{col}26)", fmt=USD)
        w(ws, f"{col}28", f"={col}27/(1+$B$10)^{col}25", fmt=USD)
    w(ws, "A30", "Terminal value at year 5"); w(ws, "B30", f"=F27*(1+{d['g']})/(B10-{d['g']})", fmt=USD)
    w(ws, "A31", "PV of terminal value"); w(ws, "B31", "=B30/(1+B10)^5", fmt=USD)
    w(ws, "A32", "Dividend per share, year 1 (USD)"); w(ws, "B32", f"=B27*{d['div_payout']}", fmt=USD)
    return ws, outputs(ws, 34, "=SUM(B28:F28)+B31", "=B34*(1+B10)-B32", "B32", "Implied P/E on year-1 EPS (x)", "=B34/B27")


def build(path, companies: dict, mkt: dict, macro: dict, val: dict, histories: dict, selector=2, scenario_table=None, extra=None):
    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    mac = wb.create_sheet("Macro")
    w(mac, "A1", "Macro and valuation inputs", bold=True)
    rows = [("Risk-free rate: 10-year Treasury, FRED DGS10, " + macro["DGS10"]["date"], macro["DGS10"]["value"], PCT),
            ("Effective Fed funds rate, FRED DFF, " + macro["DFF"]["date"], macro["DFF"]["value"], PCT),
            ("Equity risk premium (analyst assumption)", val["erp"], PCT),
            ("BUY if 12-month total return at or above", val["buy"], PCT), ("SELL if 12-month total return at or below", val["sell"], PCT)]
    for i, (lab, v, fmt) in enumerate(rows):
        w(mac, f"A{4 + i}", lab); w(mac, f"B{4 + i}", v, BLUE, fmt=fmt)
    mac.column_dimensions["A"].width = 56
    refs = {}
    for t, c in companies.items():
        ws, refs[t] = (bank_sheet if c["model"] == "bank" else am_sheet)(wb, c, mkt)
        ws.column_dimensions["A"].width = 52
        for col in "BCDEF":
            ws.column_dimensions[col].width = 13
    # Cover
    w(cover, "A1", "US Financials coverage: JPMorgan Chase, Goldman Sachs, BlackRock", bold=True)
    w(cover, "A2", "Student research project. Not investment advice.", italic=True)
    w(cover, "A5", "Scenario (1 = Bear, 2 = Base, 3 = Bull)", bold=True); w(cover, "B5", selector, BLUE, bold=True, fill=YEL)
    dv = DataValidation(type="list", formula1='"1,2,3"'); cover.add_data_validation(dv); dv.add(cover["B5"])
    w(cover, "C5", '=CHOOSE(B5,"Bear","Base","Bull")', bold=True)
    head(cover, 7, ["Company", "Price (USD)", "Target (USD)", "Total return", "Rating", "Ke"])
    for i, t in enumerate(companies):
        r = 8 + i
        w(cover, f"A{r}", companies[t]["name"])
        w(cover, f"B{r}", f"='{t}'!B5", GREEN, fmt=USD); w(cover, f"C{r}", f"='{t}'!{refs[t]['tp']}", GREEN, fmt='$#,##0')
        w(cover, f"D{r}", f"='{t}'!{refs[t]['tr']}", GREEN, fmt=PCT); w(cover, f"E{r}", f"='{t}'!{refs[t]['rating']}", GREEN)
        w(cover, f"F{r}", f"='{t}'!B10", GREEN, fmt=PCT)
    w(cover, "A13", "Scenario results (written by the VBA macro RunScenarios)", bold=True)
    hdr = ["Scenario"] + [f"{t} {k}" for t in companies for k in ("target", "TR", "rating")]
    head(cover, 14, hdr)
    for i, scen in enumerate(("Bear", "Base", "Bull")):
        w(cover, f"A{15 + i}", scen, bold=True)
        if scenario_table:
            for j, t in enumerate(companies):
                x = scenario_table[scen.lower()][t]
                cover.cell(15 + i, 2 + 3 * j, x["tp"]).number_format = '$#,##0'
                cover.cell(15 + i, 3 + 3 * j, x["total_return"]).number_format = PCT
                cover.cell(15 + i, 4 + 3 * j, x["rating"])
    w(cover, "A19", "Pre-filled by the Python engine; run RunScenarios after importing ScenarioRunner.bas to refresh in Excel.", italic=True)
    cover.column_dimensions["A"].width = 34
    # History (SEC XBRL)
    hs = wb.create_sheet("History")
    w(hs, "A1", "Five-year history from SEC XBRL filings (USD bn unless stated; ratios on average equity)", bold=True)
    r = 3
    for t, h in histories.items():
        head(hs, r, [t] + [str(x["year"]) for x in h]); r += 1
        for key, lab, scale, fmt in (("revenue", "Net revenue", 1e9, "#,##0.0"), ("ni_common", "Net income to common", 1e9, "#,##0.0"),
                                     ("eps", "Diluted EPS (USD)", 1, "0.00"), ("dps", "Dividends per share (USD)", 1, "0.00"),
                                     ("roe", "ROE", 1, PCT), ("rotce", "RoTCE", 1, PCT)):
            if t == "BLK" and key == "rotce":
                continue
            w(hs, f"A{r}", lab)
            for j, x in enumerate(h):
                v = x.get(key)
                if v is not None:
                    hs.cell(r, 2 + j, v / scale).number_format = fmt
                    hs.cell(r, 2 + j).font = Font(name="Arial", size=10, color=BLUE)
            r += 1
        r += 1
    hs.column_dimensions["A"].width = 30
    # Comps
    cs = wb.create_sheet("Comps")
    w(cs, "A1", f"Peer multiples, Yahoo Finance, {mkt['as_of']} (trailing P/B and ROE, forward P/E as reported by the provider)", bold=True)
    head(cs, 3, ["Ticker", "Price (USD)", "P/B (x)", "Forward P/E (x)", "ROE", "Market cap (USD bn)"])
    peers = sorted({p for c in companies.values() for p in c["peers"]})
    for i, p in enumerate(peers):
        m = mkt["companies"].get(p, {})
        for j, (k, fmt) in enumerate((("price", USD), ("pb", MULT), ("fwd_pe", MULT), ("roe", PCT), ("mcap_bn", "#,##0"))):
            if m.get(k) is not None:
                cs.cell(4 + i, 2 + j, m[k]).number_format = fmt
        cs.cell(4 + i, 1, p)
    # Analysis results as value sheets (rate sensitivity, ML backtest summary, peers)
    for title, df in (extra or {}).items():
        ws = wb.create_sheet(title[:31])
        w(ws, "A1", title.replace("_", " "), bold=True)
        head(ws, 3, list(df.columns))
        for i, row in enumerate(df.itertuples(index=False)):
            for j, v in enumerate(row):
                cell = ws.cell(4 + i, 1 + j, v.item() if hasattr(v, "item") else v)
                if isinstance(cell.value, float):
                    cell.number_format = "0.000"
        ws.column_dimensions["A"].width = 14
    # Names for VBA
    names = {"ScenarioSelector": SEL, "ScenarioOut": "Cover!$A$14"}
    for t in companies:
        for k in ("tp", "tr", "rating"):
            names[f"{k.upper()}_{t}"] = f"'{t}'!{refs[t][k]}"
    for n, ref in names.items():
        wb.defined_names[n] = DefinedName(n, attr_text=ref)
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
    wb.save(path)
    return refs
