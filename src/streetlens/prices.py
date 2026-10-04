"""Weekly price history (Yahoo Finance), cached as CSV snapshots for reproducible offline runs."""
import pandas as pd

from .paths import SNAP

FOCUS = ["JPM", "GS", "BLK", "STT"]
UNIVERSE = ["JPM", "BAC", "WFC", "C", "GS", "MS", "SCHW", "BLK", "STT", "NTRS", "USB", "PNC", "TFC", "COF",
            "AXP", "BX", "KKR", "APO", "TROW", "BEN", "IVZ", "AMP", "SPGI", "MCO", "ICE", "CME", "NDAQ", "MSCI", "RJF"]


def weekly(tickers: list[str], name: str, period: str = "max", refresh: bool = False) -> pd.DataFrame:
    path = SNAP / f"prices_{name}.csv"
    if refresh or not path.exists():
        import yfinance as yf
        px = yf.download(tickers, period=period, interval="1wk", auto_adjust=True, progress=False)["Close"]
        SNAP.mkdir(parents=True, exist_ok=True)
        px.to_csv(path)
    return pd.read_csv(path, index_col=0, parse_dates=True)
