# Reconciliation: SQLite -> Snowflake

Run 2026-10-16 18:39 (after backfilling 2025 game results)

## Table checks (RAW layer)

| Table | Check | SQLite | Snowflake | Result |
|---|---|---:|---:|---|
| players | row_count | 6,919 | 6,919 | PASS |
| players | distinct_pk | 6,919 | 6,919 | PASS |
| teams | row_count | 30 | 30 | PASS |
| teams | distinct_pk | 30 | 30 | PASS |
| parks | row_count | 65 | 65 | PASS |
| parks | distinct_pk | 65 | 65 | PASS |
| seasons | row_count | 12 | 12 | PASS |
| seasons | distinct_pk | 12 | 12 | PASS |
| games | row_count | 7,832 | 7,832 | PASS |
| games | distinct_pk | 7,832 | 7,832 | PASS |
| game_results | row_count | 7,831 | 7,831 | PASS |
| game_results | distinct_pk | 7,831 | 7,831 | PASS |
| game_results | sum(home_runs) | 35,191 | 35,191 | PASS |
| game_results | sum(away_runs) | 34,670 | 34,670 | PASS |
| game_results | sum(home_hits) | 63,543 | 63,543 | PASS |
| game_results | sum(away_hits) | 65,079 | 65,079 | PASS |
| batter_game_stats | row_count | 157,853 | 157,853 | PASS |
| batter_game_stats | distinct_pk | 157,853 | 157,853 | PASS |
| batter_game_stats | sum(plate_appearances) | 566,012 | 566,012 | PASS |
| batter_game_stats | sum(at_bats) | 505,089 | 505,089 | PASS |
| batter_game_stats | sum(hits) | 123,667 | 123,667 | PASS |
| batter_game_stats | sum(runs) | 66,501 | 66,501 | PASS |
| batter_game_stats | sum(rbis) | 64,200 | 64,200 | PASS |

## Per-season batting totals (SQLite source vs dbt fact table)

| Season | Rows | Hits | Runs | RBI | H+R+RBI | Result |
|---|---:|---:|---:|---:|---:|---|
| 2024 | 48,595 | 39,543 | 20,933 | 20,213 | 80,689 | PASS |
| 2025 | 65,549 | 48,988 | 26,551 | 25,645 | 101,184 | PASS |
| 2026 | 43,709 | 35,136 | 19,017 | 18,342 | 72,495 | PASS |

**ALL CHECKS PASS**
