"""Which product lines the platform can actually report on, and why not.

A blank bar on a product chart has at least three different causes, and they
call for three different fixes:

* **No gold fact at all.** Nothing anywhere sells this line. The pipeline is
  the gap.
* **A gold fact exists but carries no product key.** The data is there and
  the mapping is missing. EV charging was this case until the key was derived
  from `connector_type`: R1.67m of revenue and 232,029 kWh sat in
  `fct_ev_charging_sessions` unable to join `dim_product`, so the Energy line
  read as zero on every product chart while the money was in the warehouse
  all along.
* **Both exist but the table is not in the semantic model.** The warehouse can
  answer the question and the report cannot ask it.

Reading a blank visual and concluding "no data" collapses all three into the
wrong one. This derives the distinction from the warehouse and the semantic
model rather than asserting it, so the answer stays true after the next build.

It also refuses to add kWh to litres. They are different quantities and a
"total volume" spanning both is a number with no unit.

Usage:
    python scripts/build_product_coverage.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
MODEL_BIM = REPO / "powerbi" / "DrakensEnergy360.SemanticModel" / "model.bim"
OUT = REPO / "powerbi" / "data" / "obs_product_coverage.csv"

# Facts that serve a reporting line without carrying product_key. Listed
# explicitly, with the column that stands in for the mapping, because guessing
# this from column names is how a line gets silently attributed to the wrong
# fact.
# Energy used to live here: fct_ev_charging_sessions held R1.67m of revenue
# with no product_key, so it could not join dim_product. The key is derived
# from connector_type now and the line resolves like any other, which is why
# this map is empty rather than deleted -- the next fact that arrives without
# a mapping belongs in it.
UNMAPPED_FACTS: dict[str, tuple[str, str]] = {}


def gold_facts_with_product(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute("""
        select table_name from information_schema.columns
        where table_schema = 'main_gold' and column_name = 'product_key'
          and table_name not like '%__dbt_backup'
        group by 1 order by 1
    """).fetchall()
    return [r[0] for r in rows]


def revenue_column(con: duckdb.DuckDBPyConnection, table: str) -> str | None:
    cols = {r[0] for r in con.execute(
        f"select column_name from information_schema.columns "
        f"where table_schema='main_gold' and table_name='{table}'").fetchall()}
    for candidate in ("revenue_zar", "gross_sales_zar"):
        if candidate in cols:
            return candidate
    return None


def model_tables() -> set[str]:
    if not MODEL_BIM.exists():
        return set()
    model = json.loads(MODEL_BIM.read_text(encoding="utf-8"))["model"]
    return {t["name"] for t in model["tables"]}


def build(con: duckdb.DuckDBPyConnection) -> list[dict]:
    exposed = model_tables()
    facts = gold_facts_with_product(con)

    lines = [r[0] for r in con.execute("""
        select distinct reporting_line from main_gold.dim_product
        where reporting_line is not null order by 1
    """).fetchall()]

    rows = []
    for line in lines:
        n_products = con.execute("""
            select count(*) from main_gold.dim_product
            where reporting_line = ?""", [line]).fetchone()[0]

        serving, revenue = [], 0.0
        for fact in facts:
            rev_col = revenue_column(con, fact)
            if rev_col is None:
                continue
            got = con.execute(f"""
                select count(*), coalesce(sum(f.{rev_col}), 0)
                from main_gold.{fact} f
                join main_gold.dim_product p on p.product_key = f.product_key
                where p.reporting_line = ?""", [line]).fetchone()
            if got[0]:
                serving.append(fact)
                revenue += float(got[1])

        unmapped_fact, unmapped_note = UNMAPPED_FACTS.get(line, (None, None))

        if serving:
            exposure = [f for f in serving if f in exposed]
            status = ("Reportable" if exposure
                      else "In gold, not in the semantic model")
        elif unmapped_fact:
            status = "Gold fact exists, no product mapping"
        else:
            status = "No gold fact"

        rows.append({
            "reporting_line": line,
            "products_in_dimension": n_products,
            "gold_facts": ", ".join(serving) or (unmapped_fact or ""),
            "has_product_key": bool(serving),
            "in_semantic_model": bool(serving) and any(
                f in exposed for f in serving),
            "revenue_zar": round(revenue, 2),
            "status": status,
            "note": unmapped_note or "",
            "disclaimer": "Synthetic data. Drakens Energy is a fictional "
                          "company.",
        })
    return sorted(rows, key=lambda r: (-r["revenue_zar"], r["reporting_line"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", default=os.environ.get(
        "DRAKENS_DUCKDB_PATH",
        str(REPO / "data" / "drakens360_test_full.duckdb")))
    args = ap.parse_args()

    path = Path(args.warehouse)
    if not path.exists():
        print(f"no warehouse at {path}")
        return 1
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = build(con)
    finally:
        con.close()

    import csv
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} reporting lines to {OUT.relative_to(REPO)}\n")
    print(f"  {'line':16} {'products':>8} {'revenue':>18}  status")
    for r in rows:
        print(f"  {r['reporting_line']:16} {r['products_in_dimension']:>8} "
              f"{r['revenue_zar']:>18,.0f}  {r['status']}")
        if r["note"]:
            print(f"  {'':16} {'':>8} {'':>18}  ({r['note']})")

    gaps = [r for r in rows if r["status"] != "Reportable"]
    print(f"\n{len(rows) - len(gaps)} of {len(rows)} lines are reportable; "
          f"{len(gaps)} are not:")
    for r in gaps:
        print(f"  {r['reporting_line']:16} {r['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
