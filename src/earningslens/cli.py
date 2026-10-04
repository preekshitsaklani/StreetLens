"""EarningsLens command line.

  python -m earningslens demo                     # synthetic bank, no API key needed
  python -m earningslens run --extractor llm      # every call listed in data/manifest.csv
  python -m earningslens run --extractor regex    # baseline, no API key
  python -m earningslens evaluate --gold data/gold.csv
"""
import argparse
import csv
import json
from pathlib import Path

from .config import OUTPUT, ROOT
from .evaluate import grounding_rate, load_gold, score
from .extract import LLMExtractor, RegexExtractor
from .ingest import load_manifest
from .pipeline import aggregate, process, save


def _run(transcripts, extractor, client, out_dir: Path):
    for t in transcripts:
        res = process(t, extractor, client)
        save(res, out_dir)
        r = res["run"]
        print(f"{t.bank} {t.quarter}: {r['n_grounded']} grounded, {r['n_rejected']} rejected, "
              f"{r['llm_calls']} LLM calls, {r['seconds_total']}s")
    agg = aggregate(out_dir)
    print(f"\n{agg['calls']} calls processed -> {out_dir / 'csv'}")
    for s in agg["scorecard"]:
        print(f"  {s['bank']}: guided {s['guided']}, resolved {s['resolved']}, delivered {s['delivered']}, rate {s['delivery_rate']}")
    return agg


def main(argv=None):
    ap = argparse.ArgumentParser(prog="earningslens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run on the synthetic fixture bank with recorded LLM responses")
    d.add_argument("--out", default=str(OUTPUT / "demo"))
    r = sub.add_parser("run", help="run on transcripts listed in the manifest")
    r.add_argument("--manifest", default=str(ROOT / "data" / "manifest.csv"))
    r.add_argument("--bank"); r.add_argument("--quarter")
    r.add_argument("--extractor", choices=["llm", "regex"], default="llm")
    r.add_argument("--out")
    e = sub.add_parser("evaluate", help="score extraction against hand-labelled gold.csv")
    e.add_argument("--gold", default=str(ROOT / "data" / "gold.csv"))
    e.add_argument("--out", default=str(OUTPUT))
    a = ap.parse_args(argv)

    if a.cmd == "demo":
        from .replay import ReplayClient
        fx = ROOT / "tests" / "fixtures"
        client = ReplayClient(fx / "replay.json")
        _run(load_manifest(fx / "manifest.csv"), LLMExtractor(client), client, Path(a.out))
    elif a.cmd == "run":
        if a.extractor == "llm":
            from .llm import LLMClient
            client = LLMClient.from_env(); ex = LLMExtractor(client)
        else:
            client, ex = None, RegexExtractor()
        _run(load_manifest(a.manifest, a.bank, a.quarter), ex, client, Path(a.out or OUTPUT / a.extractor))
    elif a.cmd == "evaluate":
        gold = load_gold(a.gold)
        for name in ("llm", "regex"):
            path = Path(a.out) / name / "csv" / "kpis.csv"
            if not path.exists():
                continue
            rows = list(csv.DictReader(open(path, encoding="utf-8")))
            for x in rows:
                x["value_pct"] = float(x["value_pct"])
            print(name, json.dumps({**score(rows, gold), "grounding_rate": grounding_rate(rows)}))


if __name__ == "__main__":
    main()
