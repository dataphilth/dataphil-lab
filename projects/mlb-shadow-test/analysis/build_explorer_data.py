"""Emit the compact dataset the browser explorer loads.

The full shadow log is ~2.1MB of 20 columns; the explorer needs five. This writes
a minimal CSV so the page is fast on a phone. Regenerate whenever the log grows:
    python analysis/build_explorer_data.py
"""
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT.parents[1] / "docs" / "mlb-shadow-test" / "shadow.csv"

d = pd.read_csv(ROOT / "data" / "shadow_log.csv", parse_dates=["date_placed"])
s = d[d.result.isin(["win", "loss"])].copy()
s = s[s.p_market_devig.between(0.01, 0.99) & s.p_model.between(0.01, 0.99)]

epoch = s.date_placed.min()
out = pd.DataFrame({
    "d": (s.date_placed - epoch).dt.days,              # days since first prediction
    "pm": s.p_model.round(4),                          # model probability
    "pk": s.p_market_devig.round(4),                   # de-vigged market probability
    "o": s.american_odds_at_bet.astype(int),           # american odds at bet
    "w": (s.result == "win").astype(int),              # outcome
})
OUT.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(OUT, index=False)
print(f"{len(out):,} rows -> {OUT.relative_to(ROOT.parents[1])}  "
      f"({OUT.stat().st_size/1024:.0f} KB)  epoch={epoch.date()}")
