"""US rates from FRED (no key needed): 10-year Treasury yield and effective Fed funds rate."""
import csv
import io
import json

import requests

from .paths import SNAP

SERIES = {"DGS10": "10-year Treasury yield", "DFF": "Effective federal funds rate"}


def fetch(refresh: bool = False) -> dict:
    path = SNAP / "fred.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    out = {}
    for sid in SERIES:
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=30)
        r.raise_for_status()
        rows = [x for x in csv.reader(io.StringIO(r.text))][1:]
        rows = [(d, float(v)) for d, v in rows if v not in ("", ".")]
        last = rows[-1]
        year_ago = next((v for d, v in reversed(rows) if d <= f"{int(last[0][:4]) - 1}{last[0][4:]}"), None)
        out[sid] = {"date": last[0], "value": last[1] / 100, "year_ago": year_ago / 100 if year_ago is not None else None}
    SNAP.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out


def history(series_id: str, refresh: bool = False):
    """Full daily history from FRED as a pandas Series (percent units), cached as CSV."""
    import pandas as pd
    path = SNAP / f"fred_{series_id}.csv"
    if refresh or not path.exists():
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=60)
        r.raise_for_status()
        SNAP.mkdir(parents=True, exist_ok=True)
        path.write_text(r.text)
    df = pd.read_csv(path)
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date")["value"]
