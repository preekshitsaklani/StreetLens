"""Quant layer tests on synthetic data with known answers: Q4 derivation, SQL views, HAC regression, ML leakage, clustering."""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from streetlens import ml, peers, qa, quarterly, stats       # noqa: E402


def _fx(rows):
    return [{"facts": {"us-gaap": {"Revenues": {"units": {"USD": rows}}}}}]


def test_q4_is_full_year_minus_three_quarters():
    fx = _fx([{"frame": f"CY2025Q{i}", "val": 10.0 * i} for i in (1, 2, 3)] + [{"frame": "CY2025", "val": 100.0}])
    data, derived = quarterly.series(fx, ["Revenues"])
    assert data["2025Q4"] == 40.0 and derived == {"2025Q4"}


def test_sql_views_compute_yoy_and_ttm():
    con = sqlite3.connect(":memory:")
    rows = [{"ticker": "X", "period": f"{y}Q{q}", "year": y, "quarter": q, "metric": m, "value": v, "q4_derived": 0}
            for y in (2024, 2025) for q in (1, 2, 3, 4)
            for m, v in (("revenue", 100.0 if y == 2024 else 110.0), ("net_income", 10.0))]
    pd.DataFrame(rows).to_sql("fundamentals_quarterly", con, index=False)
    con.executescript((ROOT / "sql" / "views.sql").read_text().split("-- Base-case")[0])
    r = pd.read_sql("SELECT * FROM v_quarterly_yoy WHERE period = '2025Q4'", con).iloc[0]
    assert abs(r["revenue_yoy"] - 0.10) < 1e-12 and r["net_income_ttm"] == 40.0 and r["ttm_quarters"] == 4


def test_hac_regression_recovers_known_betas():
    rng = np.random.default_rng(1)
    n = 400
    w = pd.DataFrame({"^GSPC": rng.normal(0, 0.02, n), "d10": rng.normal(0, 0.1, n), "dslope": rng.normal(0, 0.05, n)})
    w["X"] = 1.2 * w["^GSPC"] + 0.05 * w["d10"] + rng.normal(0, 0.002, n)
    r = stats.rate_sensitivity(w, ["X"])[0]
    assert abs(r["beta_market"] - 1.2) < 0.02 and abs(r["beta_10y"] - 0.05) < 0.005 and r["p_slope"] > 0.05


def test_ml_backtest_never_sees_the_future():
    rng = np.random.default_rng(2)
    periods = [f"{y}Q{q}" for y in range(2010, 2027) for q in (1, 2, 3, 4)][:66]
    d = pd.DataFrame({"ticker": "X", "period": periods, **{f: rng.normal(0, 0.1, len(periods)) for f in ml.FEATURES}})
    d["target"] = d["rev_yoy"].shift(-1)
    bt, audit = ml.backtest(d, start="2020Q1")
    assert audit and all(a["train_max_period"] < a["test_period"] for a in audit)
    assert np.allclose(bt["naive"], d.set_index("period").loc[bt["period"], "rev_yoy"].to_numpy())


def test_clustering_separates_two_return_blocks():
    rng = np.random.default_rng(3)
    a, b = rng.normal(0, 0.02, 120), rng.normal(0, 0.02, 120)
    rets = {f"A{i}": a + rng.normal(0, 0.004, 120) for i in range(4)} | {f"B{i}": b + rng.normal(0, 0.004, 120) for i in range(4)}
    px = pd.DataFrame({k: 100 * np.exp(np.cumsum(v)) for k, v in rets.items()}, index=pd.date_range("2024-01-05", periods=120, freq="W-FRI"))
    out = peers.run(px, ["A0"], k=2, weeks=110)
    c = out["map"].set_index("ticker")["cluster"]
    assert len({c[f"A{i}"] for i in range(4)}) == 1 and c["A0"] != c["B0"] and set(out["nearest"]["A0"]) <= {"A1", "A2", "A3"}


def test_qa_report_is_written(tmp_path):
    qa.write(tmp_path / "qa.md", [("check one", "PASS", "ok"), ("check two", "SKIP", "n/a")])
    assert "1 passed, 0 failed, 1 skipped" in (tmp_path / "qa.md").read_text()
