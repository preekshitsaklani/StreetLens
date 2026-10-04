"""Tidy CSVs for Tableau (one row per observation)."""
import csv
from pathlib import Path


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


FIELDS = {
    "kpis.csv": ["bank", "quarter", "metric", "period", "value", "unit", "value_pct", "status", "match", "role", "extractor", "evidence"],
    "guidance.csv": ["bank", "quarter", "metric", "kind", "low", "high", "unit", "low_pct", "high_pct", "direction", "phrase", "horizon", "status", "role", "evidence"],
    "guidance_tracker.csv": ["bank", "quarter", "metric", "kind", "low_pct", "high_pct", "direction", "horizon", "checked_in", "observed_pct", "status", "evidence"],
    "guidance_scorecard.csv": ["bank", "guided", "resolved", "delivered", "delivery_rate"],
    "analyst_topics.csv": ["bank", "quarter", "analyst", "firm", "topic", "tagger", "text"],
    "runs.csv": ["bank", "quarter", "extractor", "seconds_extract", "seconds_total", "llm_calls", "n_reported", "n_guidance", "n_grounded", "n_rejected", "dropped_invalid"],
}
