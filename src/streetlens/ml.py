"""Machine learning, honestly validated: can macro and momentum features forecast next quarter's revenue growth?

Walk-forward backtest: at every quarter the models are trained only on data that was known at that time, then
forecast the next quarter. Gradient boosting and ridge regression are compared with a naive baseline
(next quarter's growth = this quarter's growth). A model only earns a place if it beats the baseline.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ["rev_yoy", "rev_yoy_lag1", "d_ff_yoy", "spx_yoy", "d10_yoy", "slope"]


def _qkey(idx):
    return [f"{d.year}Q{d.quarter}" for d in idx]


def dataset(q: pd.DataFrame, spx: pd.Series, ff: pd.Series, y10: pd.Series, y2: pd.Series) -> pd.DataFrame:
    m = pd.DataFrame({"spx": spx.resample("QE").last(), "ff": ff.resample("QE").mean(),
                      "y10": y10.resample("QE").mean(), "y2": y2.resample("QE").mean()})
    m.index = _qkey(m.index)
    m["spx_yoy"] = np.log(m["spx"] / m["spx"].shift(4))
    m["d_ff_yoy"] = m["ff"] - m["ff"].shift(4)
    m["d10_yoy"] = m["y10"] - m["y10"].shift(4)
    m["slope"] = m["y10"] - m["y2"]
    out = []
    for t, g in q.groupby("ticker"):
        g = g.set_index("period").sort_index()[["revenue_yoy"]].rename(columns={"revenue_yoy": "rev_yoy"})
        g["rev_yoy_lag1"] = g["rev_yoy"].shift(1)
        g["target"] = g["rev_yoy"].shift(-1)                    # next quarter's YoY growth
        g = g.join(m[["spx_yoy", "d_ff_yoy", "d10_yoy", "slope"]], how="left")
        g["ticker"] = t
        out.append(g.reset_index().rename(columns={"index": "period"}))
    d = pd.concat(out, ignore_index=True)
    d = d[d["rev_yoy"].abs() < 1.0]                              # exclude accounting-break quarters (>100% swings)
    return d.dropna(subset=FEATURES)


def models():
    return {"ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
            "gbm": GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0)}


def backtest(d: pd.DataFrame, start: str = "2016Q1") -> tuple[pd.DataFrame, list[dict]]:
    known = d.dropna(subset=["target"])
    preds, audit = [], []
    for p in sorted(x for x in known["period"].unique() if x >= start):
        train, test = known[known["period"] < p], known[known["period"] == p]
        if len(train) < 40:
            continue
        audit.append({"test_period": p, "train_max_period": train["period"].max(), "n_train": len(train)})
        row = test[["ticker", "period", "target", "rev_yoy"]].rename(columns={"target": "actual", "rev_yoy": "naive"}).copy()
        for name, mdl in models().items():
            mdl.fit(train[FEATURES], train["target"])
            row[name] = mdl.predict(test[FEATURES])
        preds.append(row)
    return pd.concat(preds, ignore_index=True), audit


def evaluate(bt: pd.DataFrame) -> dict:
    mae = {m: float(np.mean(np.abs(bt[m] - bt["actual"]))) for m in ("naive", "ridge", "gbm")}
    best = min(mae, key=mae.get)
    return {"mae": mae, "best": best, "n_forecasts": len(bt), "first": bt["period"].min(), "last": bt["period"].max(),
            "improvement_vs_naive": 1 - mae[best] / mae["naive"] if best != "naive" else 0.0}


def forecast_next(d: pd.DataFrame) -> pd.DataFrame:
    """Fit on everything known, forecast the quarter after the latest one, per company."""
    known = d.dropna(subset=["target"])
    latest = d.sort_values("period").groupby("ticker").tail(1)
    out = latest[["ticker", "period", "rev_yoy"]].rename(columns={"rev_yoy": "naive"}).copy()
    for name, mdl in models().items():
        mdl.fit(known[FEATURES], known["target"])
        out[name] = mdl.predict(latest[FEATURES])
        if name == "gbm":
            imp = dict(zip(FEATURES, mdl.feature_importances_))
    return out, imp
