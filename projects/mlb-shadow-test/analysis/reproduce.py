"""
Reproduce every figure and headline number in the MLB shadow-test writeup.

Input : data/shadow_log.csv  (append-only prediction log, 2026-06-01 -> 2026-08-26)
Output: figures/*.png, results.json

Every number that appears in the writeup or on the dossier site is computed here.
Run:  python analysis/reproduce.py
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "shadow_log.csv"
FIGS = ROOT / "figures"
OUT = ROOT / "results.json"

# The shadow test's pre-registered cut: only legs placed on/after 2026-06-16 count
# toward the graduation gate. Reason: the free-tier odds capture and the settlement
# void-path were both still being hardened before that date, so earlier rows have
# known data-quality caveats. Fixed before the re-cut, not after.
GATE_START = "2026-06-16"
GATE_EDGE = 0.05  # the gate is defined on legs the model flagged at >= 5% edge


# ---------------------------------------------------------------- loading

def load() -> pd.DataFrame:
    d = pd.read_csv(LOG, parse_dates=["date_placed"])
    # edge_pct is stored as a fraction in some rows and percent in others across
    # the log's history; normalise to a fraction once, here.
    if d["edge_pct"].abs().max() > 1.5:
        d["edge_pct"] = d["edge_pct"] / 100.0
    return d


def settled(d: pd.DataFrame) -> pd.DataFrame:
    """Only win/loss rows. 'void' = player DNP or postponement; excluded, never
    silently counted as a loss."""
    s = d[d["result"].isin(["win", "loss"])].copy()
    s["won"] = (s["result"] == "win").astype(int)
    return s


def roi(g: pd.DataFrame) -> float:
    """Flat-stake ROI in percent. One unit risked per leg, American odds."""
    o = g["american_odds_at_bet"].to_numpy(float)
    profit = np.where(o > 0, o / 100.0, 100.0 / -o)
    pay = np.where(g["won"].to_numpy() == 1, profit, -1.0)
    return float(pay.mean() * 100)


def roi_se(g: pd.DataFrame) -> float:
    o = g["american_odds_at_bet"].to_numpy(float)
    profit = np.where(o > 0, o / 100.0, 100.0 / -o)
    pay = np.where(g["won"].to_numpy() == 1, profit, -1.0)
    return float(pay.std(ddof=1) / np.sqrt(len(pay)) * 100)


# ---------------------------------------------------------------- exhibits

def calibration(s: pd.DataFrame, nbins: int = 10) -> list[dict]:
    """Exhibit 1 - is the model a good forecaster? Reliability diagram."""
    edges = np.linspace(0.30, 0.90, nbins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        g = s[(s.p_model >= lo) & (s.p_model < hi)]
        if len(g) < 30:
            continue
        rows.append(
            dict(lo=round(lo, 3), hi=round(hi, 3), n=len(g),
                 predicted=round(float(g.p_model.mean()), 4),
                 observed=round(float(g.won.mean()), 4))
        )
    return rows


def edge_deciles(s: pd.DataFrame) -> list[dict]:
    """Exhibit 2 - is the model a good *bettor*? Sort by disagreement with the
    market. If the model has alpha, win rate rises left to right. It falls."""
    # Rank-based cut, stable tie-break on date, rather than pd.qcut: edge_pct has
    # heavy ties and qcut's boundary handling makes the middle deciles wobble by
    # ~0.002 depending on row order. Equal-sized buckets, deterministically.
    s = s.sort_values(["edge_pct", "date_placed"]).reset_index(drop=True)
    s["dec"] = (np.arange(len(s)) * 10 // len(s))
    rows = []
    for d, g in s.groupby("dec"):
        rows.append(
            dict(decile=int(d) + 1, n=len(g),
                 edge_mid=round(float(g.edge_pct.mean()), 4),
                 predicted=round(float(g.p_model.mean()), 4),
                 observed=round(float(g.won.mean()), 4),
                 roi=round(roi(g), 2), roi_se=round(roi_se(g), 2))
        )
    return rows


def horse_race(s: pd.DataFrame) -> dict:
    """Exhibit 3 - the diagnosis. Regress the realised outcome on BOTH forecasts
    in log-odds space:

        logit P(win) = a + b*logit(p_model) + c*logit(p_market)

    b is how much the model is worth *after* the market price is already known.
    Newton-Raphson, no sklearn, so the arithmetic is inspectable."""
    m = s[(s.p_market_devig.between(0.01, 0.99)) & (s.p_model.between(0.01, 0.99))]
    lg = lambda p: np.log(p / (1 - p))
    X = np.column_stack([np.ones(len(m)), lg(m.p_model.to_numpy()), lg(m.p_market_devig.to_numpy())])
    y = m.won.to_numpy(float)

    b = np.zeros(3)
    for _ in range(60):
        p = 1.0 / (1.0 + np.exp(-X @ b))
        W = np.clip(p * (1 - p), 1e-9, None)
        H = X.T @ (X * W[:, None])
        step = np.linalg.solve(H, X.T @ (y - p))
        b = b + step
        if np.max(np.abs(step)) < 1e-10:
            break
    se = np.sqrt(np.diag(np.linalg.inv(H)))

    brier = lambda p: float(((p - y) ** 2).mean())
    ll = lambda p: float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
    blend = 0.5 * m.p_model.to_numpy() + 0.5 * m.p_market_devig.to_numpy()

    return dict(
        n=int(len(m)),
        coefficients={
            "intercept": dict(beta=round(float(b[0]), 4), se=round(float(se[0]), 4), z=round(float(b[0] / se[0]), 2)),
            "logit_p_model": dict(beta=round(float(b[1]), 4), se=round(float(se[1]), 4), z=round(float(b[1] / se[1]), 2)),
            "logit_p_market": dict(beta=round(float(b[2]), 4), se=round(float(se[2]), 4), z=round(float(b[2] / se[2]), 2)),
        },
        implied_model_weight=round(float(b[1] / (b[1] + b[2])), 4),
        brier={"model": round(brier(m.p_model.to_numpy()), 4),
               "market": round(brier(m.p_market_devig.to_numpy()), 4),
               "naive_50_50_blend": round(brier(blend), 4)},
        log_loss={"model": round(ll(m.p_model.to_numpy()), 4),
                  "market": round(ll(m.p_market_devig.to_numpy()), 4)},
    )


def monthly_drift(s: pd.DataFrame) -> list[dict]:
    """Exhibit 4 - the gate cohort month by month. The early positive window did
    not survive sample growth."""
    g = s[(s.date_placed >= GATE_START) & (s.edge_pct >= GATE_EDGE)]
    rows = []
    for m, grp in g.groupby(g.date_placed.dt.to_period("M")):
        rows.append(dict(month=str(m), n=len(grp),
                         observed=round(float(grp.won.mean()), 4),
                         predicted=round(float(grp.p_model.mean()), 4),
                         roi=round(roi(grp), 2), roi_se=round(roi_se(grp), 2)))
    return rows


def clv(s: pd.DataFrame) -> dict:
    """Closing-line value. Rows before capture went live are structural zeros and
    are excluded - averaging them in would manufacture a number out of nothing."""
    c = s[s.clv_pct.fillna(0) != 0]
    hi = c[c.edge_pct >= GATE_EDGE]
    return dict(n_nonzero=int(len(c)), mean_pct=round(float(c.clv_pct.mean()), 4),
                n_high_edge=int(len(hi)),
                mean_pct_high_edge=round(float(hi.clv_pct.mean()), 4) if len(hi) else None)


# ---------------------------------------------------------------- figures

def make_figures(res: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGS.mkdir(exist_ok=True)
    ink, muted, accent, warn = "#1a1a1a", "#8a8a8a", "#2b6cb0", "#c53030"

    def style(ax):
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(muted)
        ax.tick_params(colors=muted, labelsize=9)
        ax.grid(axis="y", color="#e8e8e8", lw=0.8)
        ax.set_axisbelow(True)

    # 1 - reliability
    cal = res["calibration"]
    fig, ax = plt.subplots(figsize=(6, 5), dpi=160)
    ax.plot([0.35, 0.85], [0.35, 0.85], color=muted, ls="--", lw=1, label="perfect calibration")
    ax.plot([r["predicted"] for r in cal], [r["observed"] for r in cal],
            "o-", color=accent, lw=2, ms=6, label="model")
    style(ax)
    ax.set_xlabel("predicted probability"); ax.set_ylabel("observed frequency")
    ax.set_title("The model is a decent forecaster", color=ink, fontsize=12, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(FIGS / "01_calibration.png"); plt.close(fig)

    # 2 - edge deciles (the money chart)
    dec = res["edge_deciles"]
    fig, ax = plt.subplots(figsize=(7.5, 5), dpi=160)
    x = [r["decile"] for r in dec]
    ax.plot(x, [r["predicted"] for r in dec], "o--", color=muted, lw=1.5, ms=5, label="model predicted")
    ax.plot(x, [r["observed"] for r in dec], "o-", color=warn, lw=2.5, ms=7, label="actually happened")
    style(ax)
    ax.set_xticks(x)
    ax.set_xlabel("decile of model-vs-market disagreement  (1 = model most bearish  →  10 = model most bullish)")
    ax.set_ylabel("win rate")
    ax.set_title("...and a bad bettor: conviction runs backwards", color=ink, fontsize=12, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(FIGS / "02_edge_deciles.png"); plt.close(fig)

    # 3 - horse race coefficients
    hr = res["horse_race"]["coefficients"]
    fig, ax = plt.subplots(figsize=(6.5, 3.4), dpi=160)
    names = ["model forecast", "market price"]
    betas = [hr["logit_p_model"]["beta"], hr["logit_p_market"]["beta"]]
    ses = [hr["logit_p_model"]["se"], hr["logit_p_market"]["se"]]
    ax.barh(names, betas, xerr=[1.96 * s for s in ses], color=[accent, muted],
            height=0.5, error_kw=dict(ecolor=ink, lw=1.2, capsize=4))
    ax.axvline(0, color=ink, lw=1)
    style(ax); ax.grid(axis="y", visible=False); ax.grid(axis="x", color="#e8e8e8", lw=0.8)
    ax.set_xlabel("coefficient in log-odds space (95% CI)")
    ax.set_title("The model carries real, independent information — at ~1/4 the weight",
                 color=ink, fontsize=12, loc="left", pad=12)
    fig.tight_layout(); fig.savefig(FIGS / "03_horse_race.png"); plt.close(fig)

    # 4 - monthly drift
    mo = res["monthly_drift"]
    fig, ax = plt.subplots(figsize=(6.5, 4), dpi=160)
    labs = [r["month"] for r in mo]
    vals = [r["roi"] for r in mo]
    errs = [1.0 * r["roi_se"] for r in mo]
    ax.bar(labs, vals, yerr=errs, color=[accent if v > 0 else warn for v in vals],
           width=0.55, error_kw=dict(ecolor=ink, lw=1.2, capsize=4))
    ax.axhline(0, color=ink, lw=1)
    style(ax)
    ax.set_ylabel("flat-stake ROI %  (±1 SE)")
    ax.set_title("The one good month did not survive the sample growing",
                 color=ink, fontsize=12, loc="left", pad=12)
    for lab, v, r in zip(labs, vals, mo):
        ax.annotate(f"n={r['n']}", (lab, 0), textcoords="offset points",
                    xytext=(0, 6 if v < 0 else -14), ha="center", color=muted, fontsize=8)
    fig.tight_layout(); fig.savefig(FIGS / "04_monthly_drift.png"); plt.close(fig)


# ---------------------------------------------------------------- main

def main() -> None:
    d = load()
    s = settled(d)
    gate = s[(s.date_placed >= GATE_START) & (s.edge_pct >= GATE_EDGE)]

    res = {
        "window": {"start": str(d.date_placed.min().date()), "end": str(d.date_placed.max().date())},
        "counts": {
            "rows_logged": int(len(d)),
            "settled": int(len(s)),
            "void": int((d.result == "void").sum()),
            "unsettled": int(len(d) - len(s) - (d.result == "void").sum()),
            "prop_mix": {k: int(v) for k, v in s.prop_type.value_counts().items()},
        },
        "aggregate": {
            "predicted": round(float(s.p_model.mean()), 4),
            "observed": round(float(s.won.mean()), 4),
            "brier": round(float(((s.p_model - s.won) ** 2).mean()), 4),
        },
        "gate": {
            "definition": f"legs placed on/after {GATE_START} that the model flagged at >= {GATE_EDGE:.0%} edge",
            "target_n": 1200,
            "n": int(len(gate)),
            "observed": round(float(gate.won.mean()), 4),
            "predicted": round(float(gate.p_model.mean()), 4),
            "roi": round(roi(gate), 2),
            "roi_se": round(roi_se(gate), 2),
            "verdict": "FAILED",
        },
        "calibration": calibration(s),
        "edge_deciles": edge_deciles(s),
        "horse_race": horse_race(s),
        "monthly_drift": monthly_drift(s),
        "clv": clv(s),
    }

    OUT.write_text(json.dumps(res, indent=2))
    make_figures(res)

    print(f"window      {res['window']['start']} -> {res['window']['end']}")
    print(f"settled     {res['counts']['settled']:,}")
    print(f"aggregate   pred {res['aggregate']['predicted']:.3f}  obs {res['aggregate']['observed']:.3f}"
          f"  brier {res['aggregate']['brier']:.4f}")
    print(f"gate        n={res['gate']['n']:,}  roi {res['gate']['roi']:+.2f}% "
          f"+/-{res['gate']['roi_se']:.2f}  -> {res['gate']['verdict']}")
    hr = res["horse_race"]["coefficients"]
    print(f"horse race  model b={hr['logit_p_model']['beta']:+.3f} (z={hr['logit_p_model']['z']:+.2f})  "
          f"market b={hr['logit_p_market']['beta']:+.3f} (z={hr['logit_p_market']['z']:+.2f})")
    print(f"            implied model weight {res['horse_race']['implied_model_weight']:.1%}")
    print(f"wrote {OUT.name} and {len(list(FIGS.glob('*.png')))} figures")


if __name__ == "__main__":
    main()
