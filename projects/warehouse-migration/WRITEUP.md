# I moved part of my baseball warehouse to Snowflake. The checks found a missing season.

**Summary.** I took seven tables from the SQLite warehouse behind my MLB model, moved them into
Snowflake, rebuilt them as a star schema with dbt, and then checked every table against the
original before trusting any of it. **180,542 rows, 26 reconciliation checks, 26 passes**: row
counts, distinct keys, column totals, and hits, runs and RBI season by season.

Getting there turned up four things the old database had never checked. The biggest: **an entire
season of game results, 2,730 completed games, had never been pulled.** I backfilled it and re-ran
everything. The other three are a franchise rename the team table can't represent, All-Star
rosters mixed in with regular-season batting lines, and spring exhibitions against Japanese,
Mexican and minor-league clubs.

I did this to learn Snowflake and dbt properly, on data I know well enough to notice when a
number is wrong.

---

## 1. What was moved

The MLB model runs on a 21-table SQLite warehouse (about 1.2 GB) fed by a nightly pipeline.
I took the seven tables that form a clean star: one batting line per batter per game, pointing
at the player, team, game, park and season.

| Table | Rows | Role |
|---|---:|---|
| `batter_game_stats` | 157,853 | fact: one batting line per batter per game |
| `games` | 7,832 | game dimension: schedule, park, weather |
| `game_results` | 7,831 | final scores, joined onto games |
| `players` | 6,919 | player dimension |
| `parks` | 65 | park dimension |
| `teams` | 30 | team dimension |
| `seasons` | 12 | season dimension, with rule-change flags |

The batting lines cover **2024 through 2026**. The 7.8M-pitch Statcast archive the model trains
on is not part of this migration.

## 2. The pipeline

```
SQLite  ->  Parquet  ->  Snowflake stage  ->  RAW  ->  dbt staging  ->  dbt marts
   1. export_to_parquet.py   2. load_to_snowflake.py      3. dbt build
                    4. reconcile.py: same checks on both ends
```

1. **Extract.** One Parquet file per table, read from SQLite in read-only mode so the export
   can't touch the source.
2. **Load.** `PUT` each file to a Snowflake internal stage, `TRUNCATE`, then `COPY INTO`. The
   truncate makes a rerun replace data instead of doubling it.
3. **Transform and test.** dbt builds seven staging views (renames, real `DATE` types, rebuilt
   derived columns) and six mart tables: `dim_player`, `dim_team`, `dim_park`, `dim_season`,
   `dim_game` and `fct_batter_game`. Then it runs 29 data tests. The whole build takes about
   10 seconds.
4. **Reconcile.** Run identical checks against SQLite and Snowflake and compare.

## 3. Every number ties out

| Check | Count | Result |
|---|---:|---|
| Row count, every table | 7 | all match |
| Distinct primary keys, every table | 7 | all match |
| Column totals: runs, hits, plate appearances, at-bats, RBI | 9 | all match |
| Per-season hits, runs, RBI and H+R+RBI (from the dbt fact table) | 3 | all match |

| Season | Batting lines | Hits | Runs | RBI | H+R+RBI |
|---|---:|---:|---:|---:|---:|
| 2024 | 48,595 | 39,543 | 20,933 | 20,213 | 80,689 |
| 2025 | 65,549 | 48,988 | 26,551 | 25,645 | 101,184 |
| 2026 | 43,709 | 35,136 | 19,017 | 18,342 | 72,495 |

The season check is the one I care about most. Its Snowflake side reads from the finished dbt
fact table, not the raw copy, so it checks the transformation as well as the load. H+R+RBI
was a generated column in SQLite that I deliberately didn't copy. dbt rebuilds it, and it
lands on the same totals.

**Does the check have teeth?** Before the real run I tested the reconcile script against a
mock built from the same table definitions and deleted one row out of 720. Seven checks failed
at once: row count, distinct keys, four column totals, and that season's line. A single
dropped row can't hide.

Full output: [`reconciliation.md`](reconciliation.md).

## 4. What the checks found

Snowflake accepts `PRIMARY KEY` and `FOREIGN KEY` syntax but only enforces `NOT NULL`, so in
the new warehouse dbt tests do the job constraints used to do. Between those tests and a
follow-up query, four problems surfaced. None were migration errors. All four were already true
in the source, and SQLite never checked any of them.

### A missing season of results

The first build showed 7,832 games but only 5,101 final scores. Broken down by season and
status, **2,730 of the gaps were 2025 games marked Final** with no result row. The batting lines
for those games existed, because a separate script had backfilled them. The step that writes
final scores had simply never been run for that season.

It didn't touch the hitter model, which scores against batting lines. It did mean anything
joining to final scores for 2025, mainly the game-totals backtest, was coming up empty.

The fix was one run of the pipeline's existing catch-up mode: 2,844 box scores pulled in about
56 minutes. Then I re-exported, reloaded, rebuilt and reconciled. Final scores now cover
**7,831 of 7,832 games**. The one left is a 2026 game that was never played.

### Three relationship warnings

| Warning | Rows | Values found | Dates |
|---|---:|---|---|
| Home team not in team table | 86 games | `OAK` | 77 A's home games, 2024 |
| | | `AL`, `NL` | 2024-07-16, 2025-07-15, 2026-07-14 |
| | | `YOM`, `HAN` | 2025-03-15 to 16 |
| | | `MEM`, `MTY` | 2025-03-24 |
| Batting team not in team table | 276 lines | team IDs 159, 160 + eight others | same games |
| Batter not in player table | 281 lines | 147 distinct players | same games |

- **A rename the dimension can't represent.** The A's became `ATH` for the 2025 season. The
  team table stores current abbreviations only, so every 2024 Oakland home game points at a
  code that no longer exists. This is a textbook *slowly changing dimension*. The fix is to
  keep the history, with each name valid for a date range.
- **All-Star Games.** `AL` and `NL` on the three All-Star dates, team IDs 159 and 160.
- **Spring exhibitions.** `YOM` and `HAN` are the Yomiuri Giants and Hanshin Tigers, played in
  Tokyo on March 15 and 16, 2025. `MEM` (Memphis, Triple-A) and `MTY` (Monterrey) are
  exhibitions on March 24, 2025. The 147 missing players are those rosters. Foreign and
  minor-league players were never in an MLB player table.

Altogether, 276 of 157,853 batting lines (0.17%) come from games that aren't regular season.
That's too few to move the model's backtest, but the table has no game-type field to filter
them on, and it should.

## 5. Four decisions

**Land raw, transform in the warehouse.** RAW keeps SQLite's shape exactly, dates still stored
as text. The staging models do the casting. If a cast goes wrong, the original value is still
sitting one layer down.

**Don't migrate derived values. Rebuild them, then check.** `total_runs` and `hrr` were
generated columns in SQLite. Copying them would only prove the copy worked. Rebuilding them in
dbt and reconciling against the source proves the logic matches too.

**Constraints become tests.** That's not a workaround. It's where the findings in section 4
came from.

**A service user with a key pair, not a password.** Snowflake is retiring password-only
sign-ins for scripts. The scripts and dbt log in as a `TYPE = SERVICE` user that has no
password at all.

**One bug caught before it shipped.** The first version of the export let pandas infer column
types from the data. Testing showed a column that is entirely NULL in the extract came out as
text, which would have broken the load into a numeric column. The export now takes every type
from SQLite's declared schema and fails loudly if a value doesn't fit.

## 6. What this isn't

- **Small.** 180,542 rows across three seasons, done by one person in a day. A
  production migration has live users, downstream reports to re-point, and a cutover window.
  This had none of those.
- **A full reload, not incremental.** Truncate-and-load is right for a one-time move. Keeping
  Snowflake in sync with the nightly pipeline would mean incremental models and merges.
- **Cost is provisional.** Snowflake reported about 0.1 credits for the whole job, which is
  under a dollar of compute, but its usage figures can lag up to 24 hours.

## What comes next

- Keep team-name history in `dim_team`, valid-from and valid-to, so `OAK` and `ATH` resolve to
  one franchise
- Add a game-type field upstream and filter the fact table to regular season by default
- Load the 7.8M-pitch Statcast archive as a volume test, and compare compute sizes
- Check whether any of the 276 non-regular-season lines reached the model's predictions
- Add a scheduled check that final scores exist for every Final game, so a gap like 2025 can't
  sit unnoticed again

## Reproduce

The code is in [`warehouse/`](warehouse/): export, load, the dbt project and the reconcile
script. Every step is safe to rerun. The source data is the model's private warehouse, so
the reconciliation output is published instead of the rows.
