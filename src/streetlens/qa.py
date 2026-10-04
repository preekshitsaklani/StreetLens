"""Quality checks written to output/qa_report.md: every run proves its own numbers before anyone reads them."""
import math
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path


def run(ctx: dict) -> list[tuple[str, str, str]]:
    from .models import am_value, bank_value
    checks = []
    add = lambda name, ok, detail: checks.append((name, "PASS" if ok is True else "SKIP" if ok is None else "FAIL", detail))
    s = {"rotce1": 0.1, "rotce2": 0.1, "rotce_sust": 0.1, "g": 0.04, "total_payout": 0.6}
    add("Residual income identity (RoTCE = Ke gives value = book)", abs(bank_value(100, 3, 0.10, s)["value0"] - 100) < 1e-9, "value0 = 100.00")
    g = {f"g{i}": 0.04 for i in range(1, 6)} | {"g": 0.04, "div_payout": 0.4}
    add("DCF reduces to Gordon growth", abs(am_value(10, 0.10, g)["value0"] - 10 * 1.04 / 0.06) < 1e-6, "constant growth case")
    jpm_calc = ctx.get("jpm_tbvps_sec")
    add("JPM TBVPS from SEC filings within 2% of reported $113.35", jpm_calc and abs(jpm_calc / 113.35 - 1) < 0.02, f"computed ${jpm_calc:.2f}" if jpm_calc else "n/a")
    cov = ctx["coverage"]
    add("Quarterly coverage: 20+ quarters per company and metric", all(v >= 20 for v in cov.values()), ", ".join(f"{k} {v}" for k, v in cov.items()))
    add("No look-ahead in the ML backtest (train ends before every test quarter)", all(a["train_max_period"] < a["test_period"] for a in ctx["ml_audit"]),
        f"{len(ctx['ml_audit'])} folds")
    vals = ctx["valuations"]
    add("Valuations finite and ratings consistent with thresholds",
        all(math.isfinite(v["tp"]) and v["rating"] == ("BUY" if v["total_return"] >= 0.10 else "SELL" if v["total_return"] <= -0.10 else "HOLD") for v in vals.values()),
        ", ".join(f"{t} {v['rating']}" for t, v in vals.items()))
    fred = ctx["fred_date"]
    age = (date.today() - datetime.strptime(fred, "%Y-%m-%d").date()).days
    add("Rates data fresh (FRED within 10 days)", age <= 10, f"{fred}, {age} days old")
    facts = ctx.get("facts")
    add("Every extracted figure used is grounded in its filing", None if facts is None else all(f["status"] == "grounded" for f in facts if f.get("used")),
        "run `update` first" if facts is None else f"{sum(f['status'] == 'grounded' for f in facts)} grounded of {len(facts)}")
    recalc = Path("/mnt/skills/public/xlsx/scripts/recalc.py")
    xlsx = ctx["xlsx"]
    if recalc.exists() and shutil.which("soffice"):
        tmp = xlsx.with_name("_qa_recalc.xlsx")
        shutil.copy(xlsx, tmp)
        subprocess.run([sys.executable, str(recalc), str(tmp), "90"], capture_output=True)
        from openpyxl import load_workbook
        wb = load_workbook(tmp, data_only=True)
        ok = all(wb[t]["B36"].value == v["tp"] and wb[t]["B39"].value == v["rating"] for t, v in vals.items())
        tmp.unlink()
        add("Excel model recalculates to the Python targets and ratings", ok, "LibreOffice recalculation")
    else:
        add("Excel model recalculates to the Python targets and ratings", None, "open in Excel, run RunScenarios and compare with the Cover sheet")
    return checks


def write(path, checks) -> None:
    n = {k: sum(c[1] == k for c in checks) for k in ("PASS", "FAIL", "SKIP")}
    lines = [f"# QA report ({date.today()})", "", f"**{n['PASS']} passed, {n['FAIL']} failed, {n['SKIP']} skipped**", "",
             "| Check | Result | Detail |", "| --- | --- | --- |"] + [f"| {a} | {b} | {c} |" for a, b, c in checks]
    path.write_text("\n".join(lines) + "\n")
