"""Shared config for the SQLite -> Snowflake migration.

The slice we migrate: four reference dimensions, the game dimension, and the
batter-game fact table. Generated (virtual) columns are deliberately NOT
exported -- derived values get rebuilt in the warehouse (dbt), then reconciled
against the source. That is the point of the exercise.
"""

from __future__ import annotations

import os
from pathlib import Path

# Source warehouse. Same env var the rest of mlb-model-v2 uses.
SQLITE_PATH = Path(
    os.environ.get(
        "DB_PATH",
        Path(os.environ.get("LOCALAPPDATA", ".")) / "mlb-model-v2" / "mlb_v2.sqlite",
    )
)

# Where the Parquet extracts land before upload (outside OneDrive).
EXPORT_DIR = Path(
    os.environ.get(
        "EXPORT_DIR",
        Path(os.environ.get("LOCALAPPDATA", ".")) / "mlb-model-v2" / "export",
    )
)

# table -> columns to export (explicit, so generated columns stay out)
TABLES: dict[str, list[str]] = {
    "players": [
        "mlbam_id", "full_name", "primary_position", "bats", "throws",
        "debut_date", "birth_date", "last_updated",
    ],
    "teams": [
        "team_id", "abbr", "full_name", "league", "division",
        "current_park_id", "last_updated",
    ],
    "parks": [
        "park_id", "name", "city", "state", "lat", "lon", "altitude_ft",
        "surface", "roof", "lf_dist_ft", "cf_dist_ft", "rf_dist_ft",
        "run_factor", "hr_factor_lhb", "hr_factor_rhb", "last_updated",
    ],
    "seasons": [
        "season", "start_date", "end_date", "shift_ban", "universal_dh",
        "pitch_clock", "bigger_bases", "ball_era_label", "notes",
    ],
    "games": [
        "game_pk", "game_date", "season", "home_team", "away_team", "park_id",
        "home_pitcher_id", "away_pitcher_id", "ump_id", "weather_temp_f",
        "weather_wind_mph", "weather_wind_dir", "weather_humidity",
        "game_status", "first_pitch_ts", "last_updated",
    ],
    # total_runs is GENERATED in SQLite -> rebuilt in dbt
    "game_results": [
        "game_pk", "home_runs", "away_runs", "home_hits", "away_hits",
        "home_errors", "away_errors", "innings_played", "decided_at",
    ],
    # hrr is GENERATED in SQLite -> rebuilt in dbt
    "batter_game_stats": [
        "game_pk", "batter_id", "game_date", "team_id", "batting_order_slot",
        "plate_appearances", "at_bats", "hits", "runs", "rbis",
        "source", "ingested_at_utc",
    ],
}

# Primary keys (Snowflake does not enforce these -- dbt tests do)
PRIMARY_KEYS: dict[str, list[str]] = {
    "players": ["mlbam_id"],
    "teams": ["team_id"],
    "parks": ["park_id"],
    "seasons": ["season"],
    "games": ["game_pk"],
    "game_results": ["game_pk"],
    "batter_game_stats": ["game_pk", "batter_id"],
}

# Snowflake target
SF_DATABASE = os.environ.get("SNOWFLAKE_DATABASE", "MLB")
SF_RAW_SCHEMA = "RAW"
SF_WAREHOUSE = os.environ.get("SNOWFLAKE_WAREHOUSE", "MIGRATION_WH")
SF_ROLE = os.environ.get("SNOWFLAKE_ROLE", "MIGRATION_ROLE")
SF_STAGE = "MLB_PARQUET_STAGE"


def snowflake_connect():
    """Key-pair connection. Snowflake is retiring password-only logins."""
    import snowflake.connector  # imported lazily so export.py has no dependency

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ.get("SNOWFLAKE_USER", "MIGRATION_SVC"),
        private_key_file=os.environ.get(
            "SNOWFLAKE_PRIVATE_KEY_PATH",
            str(Path.home() / ".snowflake" / "rsa_key.p8"),
        ),
        role=SF_ROLE,
        warehouse=SF_WAREHOUSE,
        database=SF_DATABASE,
        schema=SF_RAW_SCHEMA,
    )
