-- StreetLens analytical views (SQLite 3.25+ for window functions)

-- One row per company-quarter, metrics as columns
DROP VIEW IF EXISTS v_quarterly_wide;
CREATE VIEW v_quarterly_wide AS
SELECT ticker, period, year, quarter,
       MAX(CASE WHEN metric = 'revenue'    THEN value END) AS revenue,
       MAX(CASE WHEN metric = 'nii'        THEN value END) AS nii,
       MAX(CASE WHEN metric = 'net_income' THEN value END) AS net_income,
       MAX(q4_derived) AS q4_derived
FROM fundamentals_quarterly
GROUP BY ticker, period, year, quarter;

-- Year-on-year growth and trailing-twelve-month profit, computed with window functions
DROP VIEW IF EXISTS v_quarterly_yoy;
CREATE VIEW v_quarterly_yoy AS
SELECT w.*,
       revenue / LAG(revenue, 4) OVER win - 1           AS revenue_yoy,
       nii / LAG(nii, 4) OVER win - 1                   AS nii_yoy,
       SUM(net_income) OVER (PARTITION BY ticker ORDER BY period ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS net_income_ttm,
       COUNT(*) OVER (PARTITION BY ticker ORDER BY period ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)      AS ttm_quarters
FROM v_quarterly_wide w
WINDOW win AS (PARTITION BY ticker ORDER BY period);

-- Base-case valuation league table
DROP VIEW IF EXISTS v_valuation_summary;
CREATE VIEW v_valuation_summary AS
SELECT v.ticker, c.name, c.model, v.price, v.target, v.total_return, v.rating, v.ke,
       RANK() OVER (ORDER BY v.total_return DESC) AS return_rank
FROM valuations v JOIN companies c USING (ticker)
WHERE v.scenario = 'base';

-- Which stock is the strongest rates play
DROP VIEW IF EXISTS v_rate_exposure;
CREATE VIEW v_rate_exposure AS
SELECT ticker, beta_10y, t_10y, beta_slope, t_slope, r2,
       RANK() OVER (ORDER BY beta_10y DESC) AS rate_sensitivity_rank
FROM rate_sensitivity;
