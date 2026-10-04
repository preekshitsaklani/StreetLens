"""SQLite research warehouse: raw tables loaded from pandas, analytical views defined in sql/views.sql."""
import sqlite3

import pandas as pd

from .paths import ROOT


def build(path, tables: dict[str, pd.DataFrame]) -> sqlite3.Connection:
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    for name, df in tables.items():
        df.to_sql(name, con, index=False)
    con.executescript((ROOT / "sql" / "views.sql").read_text())
    con.commit()
    return con


def query(con, sql: str, **params) -> pd.DataFrame:
    return pd.read_sql_query(sql, con, params=params)
