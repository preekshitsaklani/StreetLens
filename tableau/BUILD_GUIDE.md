# Tableau Public dashboard: StreetLens

Every file below is in `output/tableau/` after `python -m streetlens all`. Install Tableau Public Desktop (free), connect each CSV as a text-file data source, then build four sheets and one dashboard. Budget about an hour.

| Sheet | Data source | Build |
| --- | --- | --- |
| 1. Valuation league table | `valuations.csv` | Filter `scenario = base`. Rows: `ticker`; columns: `total_return` as bars; colour: `rating` (BUY green, HOLD grey, SELL red); label: `target`. Add `scenario` as a filter shown as a single-value toggle so viewers can flip to bear or bull. |
| 2. Rate sensitivity | `rate_betas.csv` + `rolling_betas.csv` | Bar: `beta_10y` by `ticker`, with `significant` (p < 0.05) as colour. Second view: line of `beta_10y` over `date` from `rolling_betas.csv`, colour by `ticker`. Title: "Who wins when the 10-year yield rises?" |
| 3. Earnings trends | `quarterly.csv` | Columns: `period` (continuous); rows: `revenue_yoy`; colour: `ticker`. Add a `metric` parameter to switch between `revenue_yoy` and `nii_yoy`. Mark `q4_derived = 1` points with a shape so derived quarters are visible. |
| 4. Peer map | `peers_map.csv` | Scatter: `x` vs `y`; colour: `cluster`; label: `ticker`; size larger where `is_focus` is true. Caption: "Closer = more correlated weekly returns (2 years)." |
| 5. Forecast backtest (optional) | `ml_backtest.csv` | Lines for `actual`, `naive`, `ridge`, `gbm` over `period`, filtered by `ticker`. Caption with the mean absolute errors from `ml_summary.csv`. |

**Dashboard:** sheet 1 top-left, sheet 2 top-right, sheet 3 bottom-left, sheet 4 bottom-right. Add a `ticker` action filter from sheet 1 to sheets 2 and 3. Add a text box: "Data: SEC EDGAR, FRED, Yahoo Finance (or Bloomberg/FactSet where licensed). Student research project, not investment advice."

**Publish:** File > Save to Tableau Public. Only publish free-source data: if Bloomberg or FactSet supplied any field, check `snapshots/market.json` (`field_sources`) and rerun with `DATA_SOURCE=yahoo` before publishing.
