"""Step 4 -- Reconcile: prove Snowflake matches SQLite, number for number.

Runs the SAME checks against both systems and prints a side-by-side table:
  * row count and distinct primary-key count per table (RAW layer)
  * column totals for the numeric facts (RAW layer)
  * per-season hits / runs / RBI / H+R+RBI, where the Snowflake side comes
    from the dbt fact table (ANALYTICS layer) -- so this also proves the
    rebuilt `hrr` column matches the SQLite generated column

Writes reconciliation.md next to this script (that table goes in the writeup).

    python warehouse/reconcile.py              # SQLite vs Snowflake
    python warehouse/reconcile.py --source-only # SQLite side only (dry run)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import PRIMARY_KEYS, SQLITE_PATH, TABLES  # noqa: E402

# numeric columns whose totals must match exactly
SUM_COLUMNS = {
    "game_results": ["home_runs", "away_runs", "home_hits", "away_hits"],
    "batter_game_stats": ["plate_appearances", "at_bats", "hits", "runs", "rbis"],
}

SEASON_SQL_SQLITE = """
    SELECT g.season,
           COUNT(*), SUM(b.hits), SUM(b.runs), SUM(b.rbis), SUM(b.hrr)
    FROM batter_game_stats b LEFT JOIN games g ON g.game_pk = b.game_pk
    GROUP BY 1 ORDER BY 1
"""
SEASON_SQL_SNOWFLAKE = """
    SELECT season, COUNT(*), SUM(hits), SUM(runs), SUM(rbis), SUM(hrr)
    FROM MLB.ANALYTICS.FCT_BATTER_GAME GROUP BY 1 ORDER BY 1
"""


def table_checks(run) -> dict[tuple[str, str], int]:
    """run(sql) -> first row. Same SQL text works on both engines."""
    out = {}
    for table in TABLES:
        pk = PRIMARY_KEYS[table]
        out[(table, "row_count")] = run(f"SELECT COUNT(*) FROM {table}")[0]
        # distinct over a composite key, written portably
        pk_expr = " || '|' || ".join(f"CAST({c} AS VARCHAR)" for c in pk)
        out[(table, "distinct_pk")] = run(
            f"SELECT COUNT(DISTINCT {pk_expr}) FROM {table}"
        )[0]
        for col in SUM_COLUMNS.get(table, []):
            v = run(f"SELECT COALESCE(SUM({col}), 0) FROM {table}")[0]
            out[(table, f"sum({col})")] = int(v)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-only", action="store_true")
    args = ap.parse_args()

    src = sqlite3.connect(f"file:{SQLITE_PATH.as_posix()}?mode=ro", uri=True)
    src_run = lambda sql: src.execute(sql).fetchone()  # noqa: E731
    src_checks = table_checks(src_run)
    src_seasons = src.execute(SEASON_SQL_SQLITE).fetchall()
    src.close()

    if args.source_only:
        tgt_checks, tgt_seasons = {}, []
    else:
        from config import snowflake_connect

        conn = snowflake_connect()
        cur = conn.cursor()
        tgt_run = lambda sql: cur.execute(sql).fetchone()  # noqa: E731
        tgt_checks = table_checks(tgt_run)
        tgt_seasons = cur.execute(SEASON_SQL_SNOWFLAKE).fetchall()
        conn.close()

    lines = [
        "# Reconciliation: SQLite -> Snowflake",
        "",
        f"Run {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## Table checks (RAW layer)",
        "",
        "| Table | Check | SQLite | Snowflake | Result |",
        "|---|---|---:|---:|---|",
    ]
    fails = 0
    for (table, check), s_val in src_checks.items():
        t_val = tgt_checks.get((table, check))
        ok = t_val is not None and int(t_val) == int(s_val)
        fails += 0 if ok or args.source_only else 1
        res = "-" if args.source_only else ("PASS" if ok else "FAIL")
        t_txt = "-" if t_val is None else f"{int(t_val):,}"
        lines.append(f"| {table} | {check} | {s_val:,} | {t_txt} | {res} |")

    lines += [
        "",
        "## Per-season batting totals (SQLite source vs dbt fact table)",
        "",
        "| Season | Rows | Hits | Runs | RBI | H+R+RBI | Result |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    tgt_by_season = {int(r[0]): r for r in tgt_seasons}
    for r in src_seasons:
        t = tgt_by_season.get(int(r[0]))
        ok = t is not None and all(int(a) == int(b) for a, b in zip(r[1:], t[1:]))
        fails += 0 if ok or args.source_only else 1
        res = "-" if args.source_only else ("PASS" if ok else "FAIL")
        lines.append(
            f"| {r[0]} | {r[1]:,} | {r[2]:,} | {r[3]:,} | {r[4]:,} | {r[5]:,} | {res} |"
        )

    if not args.source_only:
        lines += ["", f"**{'ALL CHECKS PASS' if fails == 0 else f'{fails} CHECK(S) FAILED'}**"]

    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parent / "reconciliation.md").write_text(report)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
