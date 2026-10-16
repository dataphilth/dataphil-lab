# warehouse/ -- SQLite -> Snowflake migration (dbt)

Migrates a slice of the mlb-model-v2 warehouse (players, teams, parks, seasons,
games, game_results, batter_game_stats) into Snowflake, rebuilds it as a star
schema with dbt, and reconciles every table back to the source.

| Step | Command | What it does |
|---|---|---|
| 0 | `python warehouse/make_keypair.py` | RSA key pair for the service user |
| 0 | run `snowflake_setup.sql` in Snowsight | warehouse, role, user, DB, stage, RAW tables |
| 1 | `python warehouse/export_to_parquet.py` | Extract: SQLite -> Parquet (read-only on source) |
| 2 | `python warehouse/load_to_snowflake.py` | Load: PUT + COPY INTO Snowflake RAW |
| 3 | `cd warehouse/dbt_mlb; dbt deps; dbt build` | Transform + test: staging views, dim/fct tables |
| 4 | `python warehouse/reconcile.py` | Prove source and target match; writes reconciliation.md |

Pipeline: SQLite -> Parquet -> Snowflake stage -> RAW -> dbt staging -> dbt marts.

Env vars: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_PRIVATE_KEY_PATH` (plus the usual `DB_PATH`).
Every step is safe to rerun.
