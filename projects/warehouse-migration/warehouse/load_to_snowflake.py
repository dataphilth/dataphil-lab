"""Step 2 -- Load: Parquet files -> Snowflake RAW schema.

Pattern: PUT (upload file to an internal stage) -> COPY INTO (bulk load).
This is the standard Snowflake bulk-load path; every ETL tool does a version
of it under the hood.

Idempotent: each table is TRUNCATEd before COPY, and PUT uses OVERWRITE, so a
rerun replaces the data instead of doubling it.

    python warehouse/load_to_snowflake.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EXPORT_DIR, SF_STAGE, TABLES, snowflake_connect  # noqa: E402


def main() -> None:
    conn = snowflake_connect()
    cur = conn.cursor()
    try:
        for table in TABLES:
            path = EXPORT_DIR / f"{table}.parquet"
            if not path.exists():
                sys.exit(f"Missing {path} -- run export_to_parquet.py first")

            # 1. upload. Parquet is already compressed, so skip gzip.
            cur.execute(
                f"PUT 'file://{path.as_posix()}' @{SF_STAGE}/{table}/ "
                "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
            )
            # 2. reload from scratch so reruns can't duplicate rows
            cur.execute(f"TRUNCATE TABLE IF EXISTS {table}")
            # 3. bulk load; Parquet columns map to table columns by name
            cur.execute(
                f"COPY INTO {table} FROM @{SF_STAGE}/{table}/ "
                "FILE_FORMAT = (TYPE = PARQUET) "
                "MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE "
                "ON_ERROR = ABORT_STATEMENT FORCE = TRUE"
            )
            loaded = sum(r[3] for r in cur.fetchall() if len(r) > 3 and isinstance(r[3], int))
            print(f"{table:<20} {loaded:>10,} rows loaded")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
