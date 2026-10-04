"""Quarterly series from SEC XBRL. 10-Ks rarely tag a standalone fourth quarter, so Q4 = full year - (Q1 + Q2 + Q3)."""
from .edgar import _rows

CONCEPTS = {
    "JPM": {"revenue": ["RevenuesNetOfInterestExpense", "Revenues"], "nii": ["InterestIncomeExpenseNet"], "net_income": ["NetIncomeLoss"]},
    "GS": {"revenue": ["RevenuesNetOfInterestExpense"], "nii": ["InterestIncomeExpenseNet"], "net_income": ["NetIncomeLoss"]},
    "BLK": {"revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"], "net_income": ["NetIncomeLoss"]},
    "STT": {"revenue": ["Revenues"], "nii": ["InterestIncomeExpenseNet"], "net_income": ["NetIncomeLoss"]},
}


def series(fx: list, concepts: list[str]) -> tuple[dict, set]:
    """Returns ({'2025Q4': value}, set of derived Q4 keys). Earlier concepts and newer filers take priority."""
    q, fy = {}, {}
    for c in concepts:
        for x in _rows(fx, c, "USD"):
            fr = x.get("frame", "")
            if len(fr) == 8 and fr[6] == "Q":
                q.setdefault(fr[2:], float(x["val"]))
            elif len(fr) == 6:
                fy.setdefault(int(fr[2:]), float(x["val"]))
    derived = set()
    for y, v in fy.items():
        k = f"{y}Q4"
        if k not in q and all(f"{y}Q{i}" in q for i in (1, 2, 3)):
            q[k] = v - sum(q[f"{y}Q{i}"] for i in (1, 2, 3))
            derived.add(k)
    return dict(sorted(q.items())), derived


def long_table(ticker: str, fx: list) -> list[dict]:
    rows = []
    for metric, concepts in CONCEPTS[ticker].items():
        data, derived = series(fx, concepts)
        rows += [{"ticker": ticker, "period": k, "year": int(k[:4]), "quarter": int(k[-1]), "metric": metric,
                  "value": v, "q4_derived": int(k in derived)} for k, v in data.items()]
    return rows
