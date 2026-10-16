# I moved part of my baseball warehouse to Snowflake. The tests found what SQLite had been letting through.

**Summary.** I took seven tables from the SQLite warehouse behind my MLB model, moved them into
Snowflake, rebuilt them as a star schema with dbt, and then checked every table against the
original before trusting any of it. **177,812 rows, 26 reconciliation checks, 26 passes**: row
counts, distinct keys, column totals, and hits, runs and RBI season by season. The dbt tests
that replaced the database's constraints also flagged **three things the old database had
never checked**: a franchise rename the team table can't represent, All-Star rosters mixed in
with regular-season batting lines, and what look like exhibition games against Japanese,
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
| `game_results` | 5,101 | final scores, joined onto games |
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

## 4. The tests found what SQLite had been letting through

Snowflake accepts `PRIMARY KEY` and `FOREIGN KEY` syntax but only enforces `NOT NULL`, so in
the new warehouse dbt tests do the job constraints used to do. The relationship tests were set
to warn rather than fail, and three came back with results. None were migration errors. They
were already true in the source. SQLite never checked these columns because none of them had a
foreign key.

| Warning | Rows | What it turned out to be |
|---|---:|---|
| Game's home team not in the team table | 86 games | `OAK`, `AL`, `NL`, `YOM`, `HAN`, `MEM`, `MTY` |
| Batting line's team not in the team table | 276 lines | team IDs 159 and 160, plus 105, 235, 241, 341, 343, 459, 562, 5434 |
| Batting line's player not in the player table | 281 lines, 147 players | consistent with the same rows |

Three different things are going on:

- **A rename the dimension can't represent.** The A's became `ATH` for the 2025 season. The
  team table stores each team's current abbreviation only, so every 2024 Oakland home game
  points at a code that no longer exists. This is a textbook *slowly changing dimension*. The
  fix is to keep the history, with each name valid for a date range.
- **All-Star rosters.** `AL` and `NL`, team IDs 159 and 160.
- **Exhibition games.** `YOM` and `HAN` line up with the Yomiuri Giants and Hanshin Tigers,
  `MEM` with Memphis (Triple-A), `MTY` with Monterrey. The other unfamiliar team IDs sit
  outside the range MLB uses for its 30 clubs. The 147 players missing from the player table
  are very likely these rosters. Foreign and minor-league players were never in an MLB player
  table.

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

**Constraints become tests.** That's not a workaround. It's where every finding in section 4
came from.

**A service user with a key pair, not a password.** Snowflake is retiring password-only
sign-ins for scripts. The scripts and dbt log in as a `TYPE = SERVICE` user that has no
password at all.

**One bug caught before it shipped.** The first version of the export let pandas infer column
types from the data. Testing showed a column that is entirely NULL in the extract came out as
text, which would have broken the load into a numeric column. The export now takes every type
from SQLite's declared schema and fails loudly if a value doesn't fit.

## 6. What this isn't

- **Small.** 177,812 rows across three seasons, done by one person in an afternoon. A
  production migration has live users, downstream reports to re-point, and a cutover window.
  This had none of those.
- **A full reload, not incremental.** Truncate-and-load is right for a one-time move. Keeping
  Snowflake in sync with the nightly pipeline would mean incremental models and merges.
- **Exhibition labels are inferred.** I identified those games from abbreviations and team ID
  ranges, not from an official game-type field, which this table doesn't have.
- **2,731 games have no result row.** The left join keeps them in `dim_game` with an empty
  score. I haven't traced why yet. Postponements and unplayed games are the likely answer.
- **Cost is provisional.** Snowflake reported about 0.1 credits for the whole job, which is
  under a dollar of compute, but its usage figures can lag up to 24 hours.

## What comes next

- Keep team-name history in `dim_team`, valid-from and valid-to, so `OAK` and `ATH` resolve to
  one franchise
- Add a game-type field upstream and filter the fact table to regular season by default
- Load the 7.8M-pitch Statcast archive as a volume test, and compare compute sizes
- Check whether any of the 276 non-regular-season lines reached the model's predictions

## Reproduce

The code is in [`warehouse/`](warehouse/): export, load, the dbt project and the reconcile
script. Every step is safe to rerun. The source data is the model's private warehouse, so
the reconciliation output is published instead of the rows.
