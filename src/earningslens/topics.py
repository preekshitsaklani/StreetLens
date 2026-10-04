"""Tag each analyst question with a topic: what did the market worry about this quarter?"""
from .config import TOPICS

KEYWORDS = {
    "margins": ["margin", "nim", "yield", "spread", "repricing", "cost of funds"],
    "asset_quality": ["npa", "slippage", "credit cost", "provision", "stress", "delinquen", "write-off", "recover"],
    "loan_growth": ["loan growth", "advances", "disbursement", "credit growth", "book growth"],
    "deposits_funding": ["deposit", "casa", "funding", "liquidity", "lcr", "credit-deposit", "cd ratio"],
    "fees": ["fee", "commission", "cross-sell", "distribution"],
    "costs": ["opex", "operating expense", "employee", "branch", "cost-to-income", "cost to income"],
    "capital": ["capital", "cet", "tier", "dividend", "risk weight", "rwa"],
    "regulation": ["rbi", "regulat", "guideline", "ecl", "priority sector", "psl"],
    "subsidiaries": ["subsidiar", "insurance", "amc", "lombard", "prudential", "home finance"],
    "macro_rates": ["rate cut", "repo", "rate hike", "inflation", "gdp", "macro", "tariff"],
}

SYSTEM = (f"Label each analyst question from an Indian bank earnings call with exactly one topic from: {', '.join(TOPICS)}. "
          'Return ONLY JSON: {"labels": ["topic", ...]} with one label per question, in order.')


def keyword_topic(text: str) -> str:
    t = text.lower()
    scores = {k: sum(t.count(w) for w in ws) for k, ws in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "other"


def questions(turns) -> list[dict]:
    return [{"analyst": t.speaker, "firm": t.firm, "text": t.text}
            for t in turns if t.role == "analyst" and t.section == "qa" and len(t.text) >= 40]


def tag(qs: list[dict], client=None) -> list[dict]:
    labels = None
    if client and qs:
        user = "\n".join(f"{i + 1}. {q['text'][:600]}" for i, q in enumerate(qs))
        try:
            got = client.json(SYSTEM, user).get("labels", [])
            if len(got) == len(qs) and all(g in TOPICS for g in got):
                labels = got
        except Exception:
            labels = None
    for i, q in enumerate(qs):
        q["topic"] = labels[i] if labels else keyword_topic(q["text"])
        q["tagger"] = "llm" if labels else "keyword"
    return qs
