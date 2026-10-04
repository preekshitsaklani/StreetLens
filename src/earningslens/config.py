"""Project configuration: banks, metric taxonomy, tolerances, paths."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW, PROCESSED, CACHE = DATA / "raw", DATA / "processed", DATA / "cache"
OUTPUT = ROOT / "output"

BANKS = {
    "ICICIBANK": "ICICI Bank",
    "HDFCBANK": "HDFC Bank",
    "AXISBANK": "Axis Bank",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "SBIN": "State Bank of India",
}

# metric key -> (label, family). Values are stored in percent: 4.36 means 4.36%.
METRICS = {
    "loan_growth_yoy": ("Loan growth, YoY", "growth"),
    "deposit_growth_yoy": ("Deposit growth, YoY", "growth"),
    "nim": ("Net interest margin", "rate"),
    "credit_cost": ("Credit cost, annualised", "rate"),
    "gnpa_ratio": ("Gross NPA ratio", "rate"),
    "nnpa_ratio": ("Net NPA ratio", "rate"),
    "casa_ratio": ("CASA ratio", "share"),
    "cost_to_income": ("Cost-to-income", "share"),
    "roa": ("Return on assets", "rate"),
    "roe": ("Return on equity", "share"),
    "pat_growth_yoy": ("PAT growth, YoY", "growth"),
    "fee_growth_yoy": ("Fee income growth, YoY", "growth"),
    "cet1_ratio": ("CET-1 ratio", "share"),
    # US Financials
    "rotce": ("Return on tangible common equity (RoTCE, also reported as ROTE)", "share"),
    "nii_amount": ("Net interest income, full year (USD bn)", "amount"),
    "expense_amount": ("Adjusted expense, full year (USD bn)", "amount"),
    "card_nco_rate": ("Card net charge-off rate", "rate"),
    "tbvps": ("Tangible book value per share (USD)", "amount"),
    "organic_base_fee_growth": ("Organic base fee growth", "growth"),
    "adj_operating_margin": ("Operating margin, as adjusted", "share"),
    "aum_tn": ("Assets under management (USD tn)", "amount"),
}

# How far an actual may sit outside a guided band and still count as delivered (percentage points).
TOLERANCE_PP = {"growth": 1.0, "rate": 0.10, "share": 0.5, "amount": 0.0}
AMOUNT_TOL_REL = 0.02   # amounts (USD bn) count as delivered within 2%

TOPICS = ["margins", "asset_quality", "loan_growth", "deposits_funding", "fees", "costs",
          "capital", "regulation", "subsidiaries", "macro_rates", "other"]

CHUNK_CHARS = 9000
CHUNK_OVERLAP = 600

_Q = re.compile(r"^Q([1-4])FY(\d{2})$")


def q_index(q: str) -> int:
    """Q1FY27 -> sortable integer. Raises on a malformed label."""
    m = _Q.match(q)
    if not m:
        raise ValueError(f"Quarter must look like Q1FY27, got {q!r}")
    return int(m.group(2)) * 4 + int(m.group(1)) - 1


def q_label(i: int) -> str:
    fy, q = divmod(i, 4)
    return f"Q{q + 1}FY{fy:02d}"
