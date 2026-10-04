"""Offline tests: synthetic Example Bank transcripts + recorded LLM responses (no API key)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from earningslens.config import q_index, q_label                     # noqa: E402
from earningslens.evaluate import score                             # noqa: E402
from earningslens.extract import RegexExtractor, chunks             # noqa: E402
from earningslens.grounding import norm, numbers_in                 # noqa: E402
from earningslens.ingest import load_manifest                       # noqa: E402
from earningslens.pipeline import aggregate, process, save          # noqa: E402
from earningslens.extract import LLMExtractor                       # noqa: E402
from earningslens.replay import ReplayClient                        # noqa: E402
from earningslens.segment import segment                            # noqa: E402
from earningslens.summarize import paragraph                        # noqa: E402
from earningslens.tracker import target_quarters                    # noqa: E402

FX = ROOT / "tests" / "fixtures"


def transcripts():
    return {t.quarter: t for t in load_manifest(FX / "manifest.csv")}


def run_all(tmp_path):
    client = ReplayClient(FX / "replay.json")
    for t in transcripts().values():
        save(process(t, LLMExtractor(client), client), tmp_path)
    return aggregate(tmp_path), {p.stem: json.loads(p.read_text()) for p in (tmp_path / "processed").glob("*.json")}


def test_quarters_roundtrip():
    assert q_label(q_index("Q1FY27")) == "Q1FY27"
    assert target_quarters("Q4FY26", "FY27") == ["Q1FY27", "Q2FY27", "Q3FY27", "Q4FY27"]
    assert target_quarters("Q2FY27", "FY27") == ["Q3FY27", "Q4FY27"]


def test_segment_roles_and_firms():
    turns = segment(transcripts()["Q4FY26"].text)
    analysts = {(t.speaker, t.firm) for t in turns if t.role == "analyst"}
    assert analysts == {("Rohan Mehta", "Alpha Securities"), ("Priya Nair", "Beta Capital")}
    assert all(t.section == "remarks" for t in turns[:2]) and turns[-1].section == "qa"


def test_chunks_skip_moderator():
    text = "".join(c for _, c in chunks(segment(transcripts()["Q4FY26"].text)))
    assert "Moderator" not in text and "[analyst]" in text


def test_grounding_rejects_planted_errors(tmp_path):
    _, res = run_all(tmp_path)
    q4 = res["EXBANK_Q4FY26"]
    bad = {(i["metric"], i["status"]) for i in q4["reported"] + q4["guidance"] if i["status"] != "grounded"}
    assert bad == {("fee_growth_yoy", "number_not_in_quote"), ("nim", "not_management"), ("roe", "quote_not_found")}
    assert q4["run"]["dropped_invalid"] == 1          # unknown metric key rejected by the schema


def test_guidance_tracker(tmp_path):
    agg, _ = run_all(tmp_path)
    status = {(r["quarter"], r["metric"]): r["status"] for r in agg["tracker"]}
    assert status[("Q4FY26", "loan_growth_yoy")] == "delivered"     # mid-teens vs 15.6%
    assert status[("Q4FY26", "nim")] == "delivered"                 # range-bound: 4.10% -> 4.05%
    assert status[("Q4FY26", "credit_cost")] == "missed"            # ~50 bps vs 0.62%
    assert status[("Q1FY27", "credit_cost")] == "pending"
    assert agg["scorecard"][0]["delivery_rate"] == 0.75


def test_regex_baseline_and_scoring():
    t = transcripts()["Q4FY26"]
    ext = RegexExtractor().run(t.bank, t.quarter, segment(t.text))
    rows = [{"bank": t.bank, "quarter": t.quarter, "metric": r.metric, "value_pct": r.pct(), "status": "grounded"} for r in ext.reported]
    gold = [{"bank": "EXBANK", "quarter": "Q4FY26", "metric": m, "value": v} for m, v in
            [("nim", 4.10), ("loan_growth_yoy", 15.0), ("deposit_growth_yoy", 12.5), ("casa_ratio", 39.5), ("gnpa_ratio", 1.80),
             ("nnpa_ratio", 0.45), ("credit_cost", 0.48), ("cet1_ratio", 15.8), ("roe", 16.2)]]
    s = score(rows, gold)
    assert s["precision"] == 1.0 and s["recall"] == round(8 / 9, 3)   # regex has no credit-cost pattern


def test_summary_rejects_invented_numbers():
    class Liar:
        def json(self, system, user):
            return {"paragraph": "NIM rose to 4.9% and loans grew 22%."}
    text, src = paragraph(["Net interest margin: 4.05% (Q1FY27)"], Liar())
    assert src == "template" and "4.9" not in text


def test_norm_and_numbers():
    assert norm("13 per cent \u2013 14\u2019s") == "13 % - 14's"
    assert numbers_in("INR 24,384 crore and 4.36%") == [24384.0, 4.36]
