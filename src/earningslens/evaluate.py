"""Score extraction against a hand-labelled gold file: precision, recall, F1 and grounding rate."""
import csv


def load_gold(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh)]


def score(extracted: list[dict], gold: list[dict], tol: float = 0.01) -> dict:
    """extracted: grounded reported rows (bank, quarter, metric, value_pct). gold: bank, quarter, metric, value."""
    gold_keys = [(g["bank"], g["quarter"], g["metric"], float(g["value"])) for g in gold]
    ext = [(e["bank"], e["quarter"], e["metric"], e["value_pct"]) for e in extracted if e["status"] == "grounded"]
    banks_q = {(g[0], g[1]) for g in gold_keys}
    ext = [e for e in ext if (e[0], e[1]) in banks_q]                 # score only labelled calls
    tp_e = sum(any(e[:3] == g[:3] and abs(e[3] - g[3]) <= tol for g in gold_keys) for e in ext)
    tp_g = sum(any(e[:3] == g[:3] and abs(e[3] - g[3]) <= tol for e in ext) for g in gold_keys)
    p = tp_e / len(ext) if ext else 0.0
    r = tp_g / len(gold_keys) if gold_keys else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"extracted": len(ext), "gold": len(gold_keys), "precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}


def grounding_rate(rows: list[dict]) -> float:
    return round(sum(r["status"] == "grounded" for r in rows) / len(rows), 3) if rows else 0.0
