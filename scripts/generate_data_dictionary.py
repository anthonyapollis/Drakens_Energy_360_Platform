"""Generate the data dictionary and bus matrix from the build manifest.

A hand-maintained data dictionary is wrong within a month. This one is derived
from `_manifest.json`, so it describes the model that actually exists rather
than the one someone documented once.

Usage:
    python scripts/generate_data_dictionary.py
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "data" / "lake" / "_manifest.json"
DICT_OUT = REPO / "docs" / "data_dictionary.md"
BUS_OUT = REPO / "docs" / "bus_matrix.md"

DISCLAIMER = (
    "> **Independent synthetic portfolio project.** Drakens Energy is a "
    "fictional company; no real company's data is used. Every value described "
    "here is generated.\n"
)

# Which business domain each fact belongs to, by name prefix. Ordered, so the
# first match wins.
DOMAINS = [
    ("Retail and forecourt", ("fact_retail", "fact_shop", "fact_forecourt",
                              "fact_pump", "fact_tank", "fact_price",
                              "fact_promotions", "fact_site_daily")),
    ("Commercial and B2B", ("fact_commercial", "fact_contract",
                            "fact_customer")),
    ("Supply and storage", ("fact_procurement", "fact_import", "fact_terminal",
                            "fact_inventory", "fact_stock", "fact_replenish")),
    ("Logistics and fleet", ("fact_deliveries", "fact_delivery", "fact_vehicle_trips",
                             "fact_route", "fact_fleet")),
    ("LPG", ("fact_lpg",)),
    ("Lubricants", ("fact_lubricant",)),
    ("Aviation", ("fact_aviation", "fact_aircraft")),
    ("Marine", ("fact_marine", "fact_bunker")),
    ("Loyalty and digital", ("fact_loyalty", "fact_digital", "fact_mobile",
                             "fact_campaign")),
    ("New energy", ("fact_ev", "fact_solar", "fact_site_energy", "fact_grid",
                    "fact_energy")),
    ("Assets and maintenance", ("fact_maintenance", "fact_asset", "fact_spare")),
    ("HSSEQ", ("fact_hsseq", "fact_near", "fact_environmental", "fact_safety",
               "fact_training", "fact_permit", "fact_vehicle_safety")),
    ("Finance and planning", ("fact_finance", "fact_general_ledger",
                              "fact_accounts", "fact_capex", "fact_opex",
                              "fact_budget", "fact_forecast", "fact_cashflow",
                              "fact_working", "fact_daily_executive")),
]

# Conformed dimensions tracked in the bus matrix, in the order they appear.
BUS_DIMENSIONS = [
    ("Date", ("date_key",)),
    ("Site", ("site_id",)),
    ("Product", ("product_id",)),
    ("Customer", ("customer_id",)),
    ("Supplier", ("supplier_id",)),
    ("Terminal", ("terminal_id",)),
    ("Vehicle", ("vehicle_id",)),
    ("Asset", ("asset_id",)),
    ("Employee", ("employee_id",)),
    ("Contract", ("contract_id",)),
]

TYPE_LABEL = {
    "code": "code",
    "text": "text",
    "integer": "integer",
    "decimal": "decimal",
    "timestamp": "timestamp",
    "boolean": "boolean",
}


def domain_for(table: str) -> str:
    for domain, prefixes in DOMAINS:
        if any(table.startswith(p) for p in prefixes):
            return domain
    return "Other"


def describe_column(col: str, logical: str) -> str:
    """A short, honest description derived from the naming convention."""
    if col == "date_key":
        return "Integer yyyymmdd key joining dim_date."
    if col == "time_key":
        return "Minute-of-day key joining dim_time."
    if col.startswith("_dq_"):
        return "Data-quality rule outcome."
    if col == "source_system_code":
        return "Originating source system, joins dim_data_source."
    if col == "ingested_at":
        return "When the record landed in bronze."
    if col.endswith("_id"):
        return "Business key."
    if col.endswith("_key"):
        return "Surrogate key."
    if col.endswith("_zar"):
        return "Amount in South African rand."
    if col.endswith("_usd"):
        return "Amount in US dollars."
    if col.endswith("_pct"):
        return "Percentage. Non-additive: recompute from its components."
    if col.endswith("_litres"):
        return "Volume in litres."
    if col.endswith("_kg"):
        return "Mass in kilograms."
    if col.endswith("_kwh"):
        return "Energy in kilowatt hours."
    if col.endswith("_km"):
        return "Distance in kilometres."
    if col.endswith("_ts"):
        return "Event timestamp."
    if col.endswith("_date"):
        return "Calendar date."
    if col.endswith("_flag") or col.startswith("is_") or col.startswith("has_"):
        return "Boolean indicator."
    if col.endswith("_count"):
        return "Count."
    if col.endswith("_hours"):
        return "Duration in hours."
    if col.endswith("_minutes"):
        return "Duration in minutes."
    return {"code": "Coded value.", "text": "Descriptive attribute.",
            "integer": "Whole number.", "decimal": "Numeric measure.",
            "timestamp": "Timestamp.", "boolean": "Boolean indicator."
            }.get(logical, "Attribute.")


def render_dictionary(manifest: dict) -> str:
    tables = manifest["tables"]
    dims = sorted(t for t in tables if t.startswith("dim_"))
    bridges = sorted(t for t in tables if t.startswith("bridge_"))
    facts = sorted(t for t in tables if t.startswith("fact_"))

    lines = [
        "# Data dictionary",
        "",
        DISCLAIMER,
        f"Generated from `data/lake/_manifest.json` "
        f"(profile `{manifest.get('profile', 'unknown')}`). "
        "Regenerate with `python scripts/generate_data_dictionary.py` after "
        "changing the model; do not edit by hand.",
        "",
        "## Summary",
        "",
        "| | |",
        "|---|---:|",
        f"| Conformed dimensions | {len(dims)} |",
        f"| Bridge tables | {len(bridges)} |",
        f"| Fact tables | {len(facts)} |",
        f"| Fact rows | {manifest['fact_rows']:,} |",
        f"| Dimension rows | {manifest['dimension_rows']:,} |",
        f"| Total columns | {sum(len(t['columns']) for t in tables.values()):,} |",
        "",
    ]

    # Facts by domain, largest first inside each domain.
    by_domain: dict[str, list[str]] = defaultdict(list)
    for f in facts:
        by_domain[domain_for(f)].append(f)

    lines += ["## Fact tables by domain", ""]
    for domain, _ in [*DOMAINS, ("Other", ())]:
        members = sorted(by_domain.get(domain, []),
                         key=lambda t: -tables[t]["rows"])
        if not members:
            continue
        total = sum(tables[t]["rows"] for t in members)
        lines += [f"### {domain}", "",
                  f"{len(members)} tables, {total:,} rows.", "",
                  "| Table | Rows | Columns |", "|---|---:|---:|"]
        for t in members:
            lines.append(f"| `{t}` | {tables[t]['rows']:,} | "
                         f"{len(tables[t]['columns'])} |")
        lines.append("")

    lines += ["## Dimensions", "",
              "| Dimension | Rows | Columns |", "|---|---:|---:|"]
    for d in dims:
        lines.append(f"| `{d}` | {tables[d]['rows']:,} | "
                     f"{len(tables[d]['columns'])} |")
    lines += ["", "## Bridge tables", "",
              "| Bridge | Rows | Columns |", "|---|---:|---:|"]
    for b in bridges:
        lines.append(f"| `{b}` | {tables[b]['rows']:,} | "
                     f"{len(tables[b]['columns'])} |")

    # Full column detail for the tables anyone will actually look up.
    detailed = [
        "dim_site", "dim_customer", "dim_product", "dim_date", "dim_asset",
        "fact_retail_fuel_sales", "fact_commercial_orders", "fact_deliveries",
        "fact_inventory_snapshot", "fact_maintenance_work_orders",
        "fact_ev_charging_sessions", "fact_solar_generation",
        "fact_general_ledger", "fact_hsseq_incidents",
    ]
    lines += ["", "## Column detail", "",
              "Full column listings for the most-used tables. Every other "
              "table follows the same naming conventions.", ""]
    for t in detailed:
        if t not in tables:
            continue
        info = tables[t]
        types = info.get("intended_types", {})
        lines += [f"### `{t}`", "",
                  f"{info['rows']:,} rows, {len(info['columns'])} columns.", "",
                  "| Column | Type | Description |", "|---|---|---|"]
        for col in info["columns"]:
            logical = types.get(col, "text")
            lines.append(f"| `{col}` | {TYPE_LABEL.get(logical, logical)} | "
                         f"{describe_column(col, logical)} |")
        lines.append("")

    lines += [
        "## Conventions",
        "",
        "| Suffix | Meaning |",
        "|---|---|",
        "| `_id` | Business key from the source system |",
        "| `_key` | Surrogate key generated by the warehouse |",
        "| `_zar` | Amount in South African rand |",
        "| `_pct` | Percentage. Non-additive: recompute from components, "
        "never average |",
        "| `_ts` | Event timestamp |",
        "| `_flag`, `is_`, `has_` | Boolean |",
        "",
        "Two conventions matter more than the rest:",
        "",
        "1. **Percentages are never additive.** A column ending `_pct` exists "
        "for inspection of a single row. Aggregate by recomputing from the "
        "numerator and denominator, never by averaging the column.",
        "2. **Snapshot measures are semi-additive.** Stock on hand may be "
        "summed across locations but never across time. Summing a month of "
        "daily snapshots reports the stock as though it existed "
        "simultaneously.",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_bus_matrix(manifest: dict) -> str:
    tables = manifest["tables"]
    facts = sorted(t for t in tables if t.startswith("fact_"))

    lines = [
        "# Kimball bus matrix",
        "",
        DISCLAIMER,
        "Which conformed dimensions each business process uses. Generated from "
        "the actual model, so it cannot drift from the tables that exist.",
        "",
        "A dimension is marked where the fact table carries its key. The value "
        "of the matrix is the columns: `dim_site` appearing across retail, "
        "supply, maintenance and safety is what makes it possible to ask one "
        "question of all four.",
        "",
    ]

    header = "| Business process | " + " | ".join(
        d for d, _ in BUS_DIMENSIONS) + " |"
    sep = "|---|" + "|".join([":-:"] * len(BUS_DIMENSIONS)) + "|"

    by_domain: dict[str, list[str]] = defaultdict(list)
    for f in facts:
        by_domain[domain_for(f)].append(f)

    for domain, _ in [*DOMAINS, ("Other", ())]:
        members = sorted(by_domain.get(domain, []))
        if not members:
            continue
        lines += [f"## {domain}", "", header, sep]
        for t in members:
            cols = set(tables[t]["columns"])
            marks = []
            for _, keys in BUS_DIMENSIONS:
                marks.append("x" if any(k in cols for k in keys) else "")
            label = t.replace("fact_", "").replace("_", " ")
            lines.append(f"| {label} | " + " | ".join(marks) + " |")
        lines.append("")

    counts = []
    for name, keys in BUS_DIMENSIONS:
        n = sum(1 for t in facts
                if any(k in set(tables[t]["columns"]) for k in keys))
        counts.append((name, n))
    counts.sort(key=lambda x: -x[1])

    lines += ["## Dimension reach", "",
              "How many fact tables each conformed dimension joins. The "
              "high-reach dimensions are the ones worth investing in: an "
              "error in `dim_site` is wrong in dozens of places at once.",
              "",
              "| Dimension | Fact tables |", "|---|---:|"]
    for name, n in counts:
        lines.append(f"| {name} | {n} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    args = ap.parse_args(argv)

    if not args.manifest.exists():
        raise SystemExit(f"no manifest at {args.manifest}; run the generator first")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    DICT_OUT.write_text(render_dictionary(manifest), encoding="utf-8")
    print(f"wrote {DICT_OUT.relative_to(REPO)}")

    BUS_OUT.write_text(render_bus_matrix(manifest), encoding="utf-8")
    print(f"wrote {BUS_OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
