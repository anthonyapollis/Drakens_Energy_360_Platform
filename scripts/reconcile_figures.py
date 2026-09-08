"""Check every published figure against the warehouse that produced it.

A number in prose is a claim, and prose does not get rebuilt when the data
does. This project has already published one figure -- "roughly 1,050 synthetic
service stations" -- that was true of a warehouse which no longer builds, in a
document describing a warehouse with 587. Nothing failed. The build was green,
the tests passed, and the sentence was wrong.

So the claims live here, next to the query that settles each one, and a
mismatch fails the run. Three kinds of check:

  figures    a number asserted in a document, against the warehouse
  scope      a claim about *what the data covers*, which is the failure mode
             a row count cannot catch -- a report can be arithmetically
             perfect about 36% of its own estate
  artifacts  the generated Power BI model, report and CSV extracts against
             the warehouse, so a stale artifact is visible rather than merely
             old

Usage:
    python scripts/reconcile_figures.py
    python scripts/reconcile_figures.py --warehouse data/drakens360_test_full.duckdb
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
PBI = REPO / "powerbi"


# --------------------------------------------------------------------------
# The canonical figures
# --------------------------------------------------------------------------
def facts(con: duckdb.DuckDBPyConnection) -> dict:
    """Everything the documents are allowed to assert, measured once."""
    one = lambda sql: con.execute(sql).fetchone()  # noqa: E731

    sites, za, countries = one("""
        select count(*),
               count(*) filter (where country_code = 'ZA'),
               count(distinct country_code) filter (where country_code <> 'ZZ')
        from main_gold.dim_site""")
    provinces = one("""
        select count(distinct province) from main_gold.dim_site
        where country_code = 'ZA' and province is not null""")[0]
    raw, cleansed, quarantined, tables = one("""
        select sum(raw_rows), sum(cleansed_rows), sum(quarantined_rows),
               count(*)
        from main_platform.obs_cleansing_summary""")
    litres, margin, revenue = one("""
        select round(sum(litres), 3), round(sum(gross_margin_zar), 2),
               round(sum(gross_sales_zar), 2)
        from main_gold.agg_site_daily_fuel""")
    controls, passing = one("""
        select count(*), count(*) filter (where is_passing)
        from main_platform.obs_reconciliation_controls""")
    _za_litres, za_margin = one("""
        select round(sum(a.litres), 3), round(sum(a.gross_margin_zar), 2)
        from main_gold.agg_site_daily_fuel a
        join main_gold.dim_site s on s.site_key = a.site_key
        where s.country_code = 'ZA'""")

    return {
        "sites": sites,
        "sites_za": za,
        "countries": countries,
        "provinces": provinces,
        "raw_rows": raw,
        "cleansed_rows": cleansed,
        "quarantined_rows": quarantined,
        "tables_monitored": tables,
        "quarantine_rate_pct": round(quarantined / raw * 100, 2),
        "litres": litres,
        "gross_margin_zar": margin,
        "revenue_zar": revenue,
        "controls": controls,
        "controls_passing": passing,
        "za_share_of_sites_pct": round(za / sites * 100, 1),
        "za_share_of_margin_pct": round(za_margin / margin * 100, 1),
    }


# --------------------------------------------------------------------------
# Claims made in prose
# --------------------------------------------------------------------------
# (file, regex capturing one number, fact key, how to render the fact)
#
# The regex has to match the sentence as written, so that a document which no
# longer says anything about a figure fails loudly as "claim not found" rather
# than passing by silently having dropped it.
CLAIMS = [
    ("README.md", r"([\d,]+)\s+synthetic service stations", "sites", "{:,}"),
    ("README.md", r"across\s+([\d,]+)\s+African markets", "countries", "{:,}"),
    ("scripts/build_report.py", r"([\d,]+)\s+synthetic service stations",
     "sites", "{:,}"),
    ("scripts/build_report.py", r"across\s+([\d,]+)\s+African markets",
     "countries", "{:,}"),
]


def check_claims(fact: dict) -> list[str]:
    problems = []
    for relpath, pattern, key, fmt in CLAIMS:
        path = REPO / relpath
        if not path.exists():
            problems.append(f"{relpath}: file is missing")
            continue
        text = path.read_text(encoding="utf-8")
        found = re.search(pattern, text)
        if not found:
            problems.append(
                f"{relpath}: no claim matching /{pattern}/ -- the sentence "
                f"was reworded or removed, so the figure is no longer checked")
            continue
        claimed = found.group(1)
        actual = fmt.format(fact[key])
        if claimed != actual:
            problems.append(
                f"{relpath}: claims {claimed} but the warehouse says {actual} "
                f"({key})")
    return problems


# --------------------------------------------------------------------------
# Scope: what the numbers actually cover
# --------------------------------------------------------------------------
def check_scope(fact: dict) -> list[str]:
    """Catch a report that is exactly right about part of its own estate.

    Province is null for every site outside South Africa, because those sites
    do not have one. Any artifact that groups by province is therefore a South
    African artifact, and it has to say so -- otherwise a chart covering 36% of
    the margin is captioned as the network.
    """
    problems = []
    if fact["za_share_of_sites_pct"] > 99:
        return problems  # a single-country estate; the framing is fine

    pack = REPO / "scripts" / "build_evidence_pack.py"
    if pack.exists():
        text = pack.read_text(encoding="utf-8")
        if "country_code = 'ZA'" in text and "South Africa" not in text:
            problems.append(
                "build_evidence_pack.py: filters to country_code='ZA' but "
                "never says South Africa in a caption -- "
                f"{100 - fact['za_share_of_sites_pct']:.0f}% of sites are "
                "outside it")

    report = REPO / "scripts" / "build_report.py"
    if report.exists():
        text = report.read_text(encoding="utf-8")
        if "coalesce(province, 'Unresolved')" in text:
            problems.append(
                "build_report.py: labels a null province 'Unresolved'. A site "
                "in Ghana has no South African province; calling that "
                "unresolved reports correct data as a data-quality failure")
    return problems


# --------------------------------------------------------------------------
# Generated artifacts against the warehouse
# --------------------------------------------------------------------------
def check_artifacts(con: duckdb.DuckDBPyConnection, fact: dict) -> list[str]:
    problems = []

    bim = PBI / "DrakensEnergy360.SemanticModel" / "model.bim"
    if not bim.exists():
        problems.append("powerbi: model.bim is missing; run "
                        "scripts/generate_powerbi_model.py")
    else:
        model = json.loads(bim.read_text(encoding="utf-8"))["model"]
        tables = {t["name"] for t in model["tables"]}
        data_dir = PBI / "data"
        for table in sorted(tables):
            csv = data_dir / f"{table}.csv"
            if not csv.exists():
                problems.append(
                    f"powerbi: the model reads {table}.csv, which is not in "
                    f"powerbi/data -- run scripts/export_powerbi_data.py")
                continue
            with csv.open(encoding="utf-8", newline="") as fh:
                rows = sum(1 for _ in fh) - 1
            if table == "obs_ml_performance":
                # Not a warehouse table. It is written straight from the
                # MLflow store by scripts/export_ml_results.py, so there is
                # nothing in DuckDB to reconcile it against.
                continue
            schema = ("main_platform" if table.startswith("obs_")
                      else "main_gold")
            try:
                truth = con.execute(
                    f"select count(*) from {schema}.{table}").fetchone()[0]
            except duckdb.Error:
                problems.append(f"powerbi: {table} is not in the warehouse")
                continue
            if rows != truth:
                problems.append(
                    f"powerbi: {table}.csv has {rows:,} rows, the warehouse "
                    f"has {truth:,} -- the extract is stale")

    # The rendered deliverables, not the scripts that write them. A figure
    # present in the source is not proof it reached the page: the ebook
    # hardcoded a partial warehouse, every query failed silently, and the
    # template's fallback literals rendered as measured numbers.
    for name in ("Drakens_Energy_360_Report.html",
                 "Drakens_Energy_360_Ebook.html"):
        doc = REPO / "docs" / name
        if not doc.exists():
            problems.append(f"docs: {name} has not been built")
            continue
        text = doc.read_text(encoding="utf-8", errors="ignore")
        if f"{fact['sites']:,}" not in text and str(fact["sites"]) not in text:
            problems.append(
                f"docs/{name}: does not mention the site count "
                f"({fact['sites']}) anywhere -- it was built against a "
                f"different warehouse, or not rebuilt")
        if "1,050" in text:
            problems.append(
                f"docs/{name}: still carries the figure 1,050, which no "
                f"warehouse in this repo produces")

    # The CSV-backed model points at an absolute folder, because Power Query
    # has no way to resolve a path relative to the project. That is fine
    # locally and useless to anyone who clones the repo, so it has to be
    # stated rather than discovered when every table fails to refresh.
    if bim.exists():
        text = bim.read_text(encoding="utf-8")
        found = re.search(r'([A-Za-z]:\\[^"]*?powerbi)', text)
        if found and "DataFolder" not in (REPO / "README.md").read_text(
                encoding="utf-8", errors="ignore"):
            problems.append(
                "powerbi: model.bim hardcodes an absolute data folder and the "
                "README does not tell a reader to change it -- every table "
                "will fail to refresh on any other machine")

    report = PBI / "DrakensEnergy360.Report" / "report.json"
    if report.exists():
        sections = json.loads(report.read_text(encoding="utf-8"))["sections"]
        visuals = sum(len(s["visualContainers"]) for s in sections)
        if visuals == 0:
            problems.append("powerbi: report.json contains no visuals")
    elif (PBI / "DrakensEnergy360.Report" / "definition").exists():
        problems.append(
            "powerbi: the report is in PBIR format, which renders as a single "
            "blank page unless the reader has the preview feature on -- "
            "regenerate with --format legacy")
    else:
        problems.append("powerbi: no report found")

    return problems


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
    try:
        con = duckdb.connect(str(path), read_only=True)
    except duckdb.IOException as exc:
        print(f"warehouse is locked: {str(exc)[:90]}")
        return 1

    try:
        fact = facts(con)
        print(f"canonical figures, from {path.name}\n")
        for key, value in fact.items():
            shown = f"{value:,}" if isinstance(value, (int, float)) else value
            print(f"  {key:26} {shown:>18}")

        groups = [
            ("figures asserted in prose", check_claims(fact)),
            ("scope of what is reported", check_scope(fact)),
            ("generated artifacts", check_artifacts(con, fact)),
        ]
    finally:
        con.close()

    total = sum(len(p) for _, p in groups)
    print()
    for title, problems in groups:
        mark = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"{title}: {mark}")
        for problem in problems:
            print(f"    {problem}")
    print()
    if total:
        print(f"{total} figure(s) do not reconcile")
        return 1
    print("every published figure reconciles against the warehouse")
    return 0


if __name__ == "__main__":
    sys.exit(main())
