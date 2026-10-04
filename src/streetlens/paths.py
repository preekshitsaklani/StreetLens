from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES, SNAP, OUTPUT = ROOT / "companies", ROOT / "snapshots", ROOT / "output"
