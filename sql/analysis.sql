-- Example research queries against output/streetlens.db (sqlite3 output/streetlens.db < sql/analysis.sql)

-- 1. Latest four quarters of revenue growth per company
SELECT ticker, period, ROUND(revenue / 1e9, 2) AS revenue_bn, ROUND(revenue_yoy * 100, 1) AS revenue_yoy_pct
FROM v_quarterly_yoy
WHERE period >= (SELECT MAX(period) FROM v_quarterly_yoy) AND revenue_yoy IS NOT NULL
   OR period IN (SELECT DISTINCT period FROM v_quarterly_yoy ORDER BY period DESC LIMIT 4)
ORDER BY ticker, period;

-- 2. Best and worst year-on-year revenue quarter for each company since 2010
SELECT ticker, MIN(revenue_yoy) AS worst_yoy, MAX(revenue_yoy) AS best_yoy
FROM v_quarterly_yoy WHERE year >= 2010 GROUP BY ticker;

-- 3. Valuation league table with rate exposure
SELECT s.ticker, s.rating, ROUND(s.total_return * 100, 1) AS total_return_pct, r.rate_sensitivity_rank
FROM v_valuation_summary s LEFT JOIN v_rate_exposure r USING (ticker)
ORDER BY s.return_rank;
