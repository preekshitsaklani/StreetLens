"""Statistics: how each stock trades against rates, and how net interest income responds to the Fed.

OLS with Newey-West (HAC) standard errors, because weekly and quarterly financial series are autocorrelated
and heteroskedastic; ordinary standard errors would overstate significance.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm


def weekly_frame(prices: pd.DataFrame, d10: pd.Series, d2: pd.Series, years: int = 5) -> pd.DataFrame:
    rates = pd.concat({"y10": d10, "y2": d2}, axis=1).resample("W-FRI").last()
    px = prices.copy()
    px.index = px.index.to_period("W-FRI").to_timestamp("W-FRI")
    df = px.join(rates, how="inner").dropna()
    df = df[df.index >= df.index.max() - pd.DateOffset(years=years)]
    out = np.log(df.drop(columns=["y10", "y2"])).diff()
    out["d10"] = df["y10"].diff()                          # percentage points per week
    out["dslope"] = (df["y10"] - df["y2"]).diff()
    return out.dropna()


def rate_sensitivity(w: pd.DataFrame, tickers: list[str], market: str = "^GSPC", lags: int = 4) -> list[dict]:
    rows = []
    for t in tickers:
        X = sm.add_constant(w[[market, "d10", "dslope"]])
        fit = sm.OLS(w[t], X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
        rows.append({"ticker": t, "n_weeks": int(fit.nobs), "r2": fit.rsquared,
                     "beta_market": fit.params[market], "beta_10y": fit.params["d10"], "t_10y": fit.tvalues["d10"],
                     "p_10y": fit.pvalues["d10"], "beta_slope": fit.params["dslope"], "t_slope": fit.tvalues["dslope"],
                     "p_slope": fit.pvalues["dslope"]})
    return rows


def rolling_rate_beta(w: pd.DataFrame, tickers: list[str], market: str = "^GSPC", window: int = 52) -> pd.DataFrame:
    out = []
    for t in tickers:
        for end in range(window, len(w) + 1):
            s = w.iloc[end - window:end]
            X = np.column_stack([np.ones(window), s[market], s["d10"]])
            b = np.linalg.lstsq(X, s[t].to_numpy(), rcond=None)[0]
            out.append({"ticker": t, "date": s.index[-1].date().isoformat(), "beta_10y": b[2]})
    return pd.DataFrame(out)


def nii_sensitivity(q: pd.DataFrame, fed_funds: pd.Series, lags: int = 4) -> list[dict]:
    """Quarterly NII growth (YoY) regressed on the YoY change in the average Fed funds rate (pp)."""
    ff = fed_funds.resample("QE").mean()
    ff.index = [f"{d.year}Q{d.quarter}" for d in ff.index]
    ffd = (ff - ff.shift(4)).rename("d_ff")
    rows = []
    for t, g in q.dropna(subset=["nii_yoy"]).groupby("ticker"):
        d = g.set_index("period").join(ffd, how="inner").dropna(subset=["nii_yoy", "d_ff"])
        d = d[np.abs(d["nii_yoy"]) < 1.0]                  # drop distorted quarters (accounting breaks)
        if len(d) < 20:
            continue
        fit = sm.OLS(d["nii_yoy"], sm.add_constant(d[["d_ff"]])).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
        rows.append({"ticker": t, "n_quarters": int(fit.nobs), "r2": fit.rsquared, "nii_growth_per_1pp": fit.params["d_ff"],
                     "t": fit.tvalues["d_ff"], "p": fit.pvalues["d_ff"]})
    return rows
