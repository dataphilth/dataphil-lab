# dataphil lab

The forecasting work behind [dataphil.com](https://dataphil.com), published with the raw data
and the code to recompute every number.

**Live at [lab.dataphil.com](https://lab.dataphil.com)**

---

## Projects

### [Moving the warehouse](https://lab.dataphil.com/warehouse-migration/) · reconciled

Seven tables of the MLB model's SQLite warehouse, **180,542 rows**, moved into Snowflake and
rebuilt as a star schema with dbt. Reconciled on both ends before trusting any of it:
**26 of 26 checks pass** (row counts, distinct keys, column totals, per-season batting lines).
The checks found a full 2025 season of game results (2,730 completed games) that had never been
pulled; it was backfilled and everything re-run. The dbt tests also caught a franchise rename the
team table can't represent, and All-Star and exhibition games in the regular-season batting lines.

**[Writeup](https://lab.dataphil.com/warehouse-migration/)** ·
**[Reconciliation output](projects/warehouse-migration/reconciliation.md)** ·
**[Code](projects/warehouse-migration/warehouse/)**

### [The MLB shadow test](https://lab.dataphil.com/mlb-shadow-test/) · not deployed

A Monte Carlo simulator that prices MLB hitter props from 7.8M pitches of Statcast data. I
wrote a pass/fail gate into the methodology document two days before the first prediction,
then ran it against live sportsbook prices for **87 days and 10,928 out-of-sample
predictions** without betting a dollar.

It failed the gate. The model forecast well (predicted 62.3%, observed 59.6%, Brier 0.2392)
and bet badly — its most confident decile predicted 64.7% and delivered 54.0%.

A head-to-head regression against the market price shows why:

| term | β | SE | z |
|---|---|---|---|
| model forecast | **+0.231** | 0.105 | **+2.20** |
| market price | +0.820 | 0.103 | +7.98 |

The model carries genuine independent information beyond the closing line — at about **22%**
of the weight `edge = p_model − p_market` implicitly gave it. Levered ~2.3× past its true
strength, it lost in proportion to its own conviction. The decision rule was wrong, not the
model, and neither was good enough to ship.

**[Writeup](https://lab.dataphil.com/mlb-shadow-test/)** ·
**[Interactive explorer](https://lab.dataphil.com/mlb-shadow-test/explorer.html)** ·
**[Run it in Colab](https://colab.research.google.com/github/dataphilth/dataphil-lab/blob/main/projects/mlb-shadow-test/notebook.ipynb)**

---

## Reproduce

```bash
pip install pandas numpy matplotlib
cd projects/mlb-shadow-test
python analysis/reproduce.py      # every figure + results.json
python analysis/verify.py         # independent recheck of all 52 published figures
```

| path | what it is |
|---|---|
| `projects/mlb-shadow-test/data/shadow_log.csv` | the append-only prediction log — every leg, model probability and book price recorded pre-game |
| `projects/mlb-shadow-test/data/shadow_log_totals.csv` | same, for the game-totals sub-model |
| `projects/mlb-shadow-test/analysis/reproduce.py` | regenerates every number and figure, regression included (Newton–Raphson by hand, no sklearn) |
| `projects/mlb-shadow-test/analysis/verify.py` | independent recomputation sharing no code with `reproduce.py` |
| `projects/mlb-shadow-test/analysis/verify_explorer.py` | reference values the browser explorer must reproduce |
| `projects/mlb-shadow-test/notebook.ipynb` | the Colab walkthrough |
| `projects/mlb-shadow-test/WRITEUP.md` | the long-form version |
| `docs/` | the published site (GitHub Pages root) |

## What's not here

The model source — simulator, feature builders, the Statcast pipeline, the methodology
document — is in a separate private repo. This repo is the **evidence**, which is the part
worth checking.

## Why publish a failure

Because the failure is the result. Anyone can show you a backtest. The rarer thing is a
forward test with the bar set in advance, an audit trail you can recompute yourself, and a
decision not to ship.
