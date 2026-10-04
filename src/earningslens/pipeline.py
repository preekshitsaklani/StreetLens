"""Run one transcript end to end, then aggregate all processed calls into tracker, scorecard and CSVs."""
import json
import time
from collections import Counter
from pathlib import Path

from . import export, summarize, topics, tracker
from .grounding import ground
from .segment import segment


def process(t, extractor, client=None) -> dict:
    t0 = time.perf_counter()
    calls0 = getattr(client, "calls", 0)
    turns = segment(t.text)
    ext = extractor.run(t.bank, t.quarter, turns)
    t1 = time.perf_counter()
    rep, gui = ground(ext, t.text, turns)
    for r in rep:
        r.update(bank=t.bank, quarter=t.quarter, extractor=extractor.name,
                 value_pct=round(r["value"] / 100 if r["unit"] == "bps" else r["value"], 4))
    for g in gui:
        g.update(bank=t.bank, quarter=t.quarter)
    qs = topics.tag(topics.questions(turns), client)
    for q in qs:
        q.update(bank=t.bank, quarter=t.quarter)
    md, src = summarize.build(t.bank, t.quarter, rep, gui, qs, client)
    t2 = time.perf_counter()
    items = rep + gui
    run = {"bank": t.bank, "quarter": t.quarter, "extractor": extractor.name,
           "seconds_extract": round(t1 - t0, 2), "seconds_total": round(t2 - t0, 2),
           "llm_calls": getattr(client, "calls", 0) - calls0, "n_reported": len(rep), "n_guidance": len(gui),
           "n_grounded": sum(i["status"] == "grounded" for i in items),
           "n_rejected": sum(i["status"] != "grounded" for i in items), "dropped_invalid": ext.dropped}
    return {"bank": t.bank, "quarter": t.quarter, "source_url": t.source_url, "summary_source": src,
            "roles": dict(Counter(x.role for x in turns)), "reported": rep, "guidance": gui,
            "questions": qs, "summary_md": md, "run": run}


def save(result: dict, out_dir: Path) -> None:
    (out_dir / "processed").mkdir(parents=True, exist_ok=True)
    (out_dir / "summaries").mkdir(parents=True, exist_ok=True)
    stem = f"{result['bank']}_{result['quarter']}"
    (out_dir / "processed" / f"{stem}.json").write_text(json.dumps(result, indent=2))
    (out_dir / "summaries" / f"{stem}.md").write_text(result["summary_md"])


def aggregate(out_dir: Path) -> dict:
    files = sorted((out_dir / "processed").glob("*.json"))
    res = [json.loads(f.read_text()) for f in files]
    rep = [r for x in res for r in x["reported"]]
    gui = [g for x in res for g in x["guidance"]]
    track = tracker.evaluate([r for r in rep if r["status"] == "grounded"], [g for g in gui if g["status"] == "grounded"])
    card = tracker.scorecard(track)
    tables = {"kpis.csv": rep, "guidance.csv": gui, "guidance_tracker.csv": track, "guidance_scorecard.csv": card,
              "analyst_topics.csv": [q for x in res for q in x["questions"]], "runs.csv": [x["run"] for x in res]}
    for name, rows in tables.items():
        export.write_csv(out_dir / "csv" / name, rows, export.FIELDS[name])
    return {"calls": len(res), "reported": len(rep), "guidance": len(gui), "tracker": track, "scorecard": card}
