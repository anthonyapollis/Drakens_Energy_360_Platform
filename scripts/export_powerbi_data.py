"""Export the tables the Power BI project reads, as CSV.

The semantic model has two shapes. The deployed one reads Unity Catalog
directly; the portable one reads these extracts. The portable shape exists
because a portfolio model nobody can open is a model nobody can assess, and
the Databricks version shows an authentication prompt before it shows a
number.

The extracts are not committed. They are derived data the warehouse
reproduces exactly, and 117 MB of it -- the same call as not committing the
DuckDB file. This script is what makes that safe: the files can always be
rebuilt, so losing them costs a minute rather than a rebuild.

Usage:
    python scripts/export_powerbi_data.py
    python scripts/export_powerbi_data.py --warehouse data/drakens360.duckdb
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "powerbi" / "data"

# Kept in step with TABLES in scripts/generate_powerbi_model.py: the model
# names a schema per table, and an extract that is missing or in the wrong
# schema fails at refresh rather than at generation.
TABLES = {
    "gold": [
        "dim_date", "dim_site", "dim_product", "dim_customer",
        "fct_retail_fuel_sales", "agg_site_daily_fuel",
        "agg_executive_daily_kpi", "network_investment_scorecard",
        "fct_deliveries", "fct_commercial_orders",
        "fct_maintenance_work_orders", "bridge_security_user_scope",
    ],
    "platform": [
        "obs_cleansing_summary", "obs_quarantine_reasons",
        "obs_reconciliation_controls", "obs_table_freshness",
    ],
}


def select_list(con: duckdb.DuckDBPyConnection, schema: str,
                table: str) -> str:
    """The column list to export, with timezone-aware timestamps flattened.

    A TIMESTAMPTZ lands in CSV as `2026-09-07 20:42:37.29855+02`, and Power
    Query cannot read that as a datetime: the offset is not part of the format
    it parses, so every row of the table fails conversion. The load still
    reports success and the rows still arrive -- they just arrive as errors,
    which is how a table can show 128 rows and 128 errors at once.

    Casting to a plain TIMESTAMP under a pinned UTC session removes the offset
    and the ambiguity together. Sub-millisecond precision is kept: Power Query
    stores 100-nanosecond ticks, so the six fractional digits DuckDB writes
    survive the round trip untouched.
    """
    rows = con.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema = ? and table_name = ? order by ordinal_position",
        [schema, table]).fetchall()
    if not rows:
        raise duckdb.CatalogException(f"{schema}.{table} not found")
    parts = []
    for name, dtype in rows:
        if "TIME ZONE" in dtype.upper():
            parts.append(f'cast("{name}" as timestamp) as "{name}"')
        else:
            parts.append(f'"{name}"')
    return ", ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", default=os.environ.get(
        "DRAKENS_DUCKDB_PATH", str(REPO / "data" / "drakens360.duckdb")))
    args = ap.parse_args()

    warehouse = Path(args.warehouse)
    if not warehouse.exists():
        print(f"no warehouse at {warehouse}; run dbt build first")
        return 1
    try:
        con = duckdb.connect(str(warehouse), read_only=True)
    except duckdb.IOException as exc:
        print(f"warehouse is locked: {str(exc)[:100]}")
        return 1

    # Every timestamp in the extracts is UTC, and says so by carrying no
    # offset at all. DuckDB casts TIMESTAMPTZ to TIMESTAMP through whatever
    # TimeZone the session happens to have, so pinning it here is what makes
    # a rebuild on another machine produce byte-identical files.
    con.execute("set TimeZone='UTC'")

    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    missing: list[str] = []
    try:
        for schema, tables in TABLES.items():
            for table in tables:
                target = OUT / f"{table}.csv"
                try:
                    columns = select_list(con, f"main_{schema}", table)
                    con.execute(
                        f"copy (select {columns} from main_{schema}.{table}) "
                        f"to '{target.as_posix()}' (header, delimiter ',')")
                except duckdb.Error:
                    missing.append(f"{schema}.{table}")
                    continue
                size = target.stat().st_size
                total += size
                print(f"  {table:32} {size / 1e6:>8.2f} MB")
    finally:
        con.close()

    n = sum(len(v) for v in TABLES.values()) - len(missing)
    print(f"wrote {n} extracts, {total / 1e6:,.0f} MB total, to "
          f"{OUT.relative_to(REPO)}")
    if missing:
        # Reported rather than raised: a partially built warehouse should
        # still produce the extracts it can, and say which it could not.
        print(f"  not in this warehouse: {', '.join(missing)}")
        print("  the model will fail to refresh the tables backed by those")
    return 0


if __name__ == "__main__":
    sys.exit(main())
