"""Step 1 -- Extract: SQLite warehouse -> one Parquet file per table.

Read-only against the source. Safe to rerun (overwrites the extract files,
never touches mlb_v2.sqlite).

    python warehouse/export_to_parquet.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EXPORT_DIR, SQLITE_PATH, TABLES  # noqa: E402

# SQLite declared type -> Parquet type. Taken from the schema rather than
# inferred from the data, because inference gets it wrong: a column that is
# all NULL in the extract would otherwise come out as text.
TYPE_MAP = {"INTEGER": pa.int64(), "REAL": pa.float64(), "TEXT": pa.string()}


def arrow_schema(conn: sqlite3.Connection, table: str, cols: list[str]) -> pa.Schema:
    declared = {
        row[1]: (row[2] or "TEXT").upper()
        for row in conn.execute(f"PRAGMA table_info({table})")
    }
    return pa.schema([(c, TYPE_MAP.get(declared[c], pa.string())) for c in cols])


def main() -> None:
    if not SQLITE_PATH.exists():
        sys.exit(f"Source DB not found: {SQLITE_PATH}  (set DB_PATH)")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    # mode=ro: open the warehouse read-only so the export can never write to it
    uri = f"file:{SQLITE_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    manifest = {}
    for table, cols in TABLES.items():
        sql = f"SELECT {', '.join(cols)} FROM {table}"
        # pyarrow dtypes keep integer columns as integers even when they hold
        # NULLs (plain pandas would silently turn them into floats)
        # Note: an all-NULL column arrives as a null type; cast() fixes it.
        df = pd.read_sql_query(sql, conn, dtype_backend="pyarrow")
        arrow = pa.Table.from_pandas(df, preserve_index=False)
        arrow = arrow.cast(arrow_schema(conn, table, cols))  # fails loudly on bad data
        out = EXPORT_DIR / f"{table}.parquet"
        pq.write_table(arrow, out)
        manifest[table] = len(df)
        print(f"{table:<20} {len(df):>10,} rows -> {out.name}")

    conn.close()
    (EXPORT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote {len(manifest)} files to {EXPORT_DIR}")


if __name__ == "__main__":
    main()
