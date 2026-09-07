"""Generate entity-relationship diagrams from the build manifest.

A single ERD covering 70 dimensions and 85 facts is unreadable, and an ERD
maintained by hand stops matching the model almost immediately. This produces
Mermaid diagrams derived from the manifest:

  erd_conformed.md   the conformed dimensions and how far each one reaches
  erd_<domain>.md    one star schema per business domain

Mermaid renders natively on GitHub, so the diagrams are readable in the
repository without any build step or image checked into git.

Usage:
    python scripts/generate_erd.py
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "data" / "lake" / "_manifest.json"
OUT = REPO / "docs" / "erd"

DISCLAIMER = (
    "> **Independent synthetic portfolio project.** Drakens Energy is a "
    "fictional company; no real company's data is used.\n"
)

# Foreign-key column -> the dimension it points at.
FK_TO_DIM = {
    "date_key": "dim_date",
    "time_key": "dim_time",
    "site_id": "dim_site",
    "destination_site_id": "dim_site",
    "product_id": "dim_product",
    "customer_id": "dim_customer",
    "supplier_id": "dim_supplier",
    "terminal_id": "dim_terminal",
    "origin_terminal_id": "dim_terminal",
    "depot_id": "dim_depot",
    "warehouse_id": "dim_warehouse",
    "vehicle_id": "dim_vehicle",
    "driver_id": "dim_driver",
    "carrier_id": "dim_carrier",
    "route_id": "dim_route",
    "asset_id": "dim_asset",
    "tank_id": "dim_tank",
    "pump_id": "dim_pump",
    "employee_id": "dim_employee",
    "contract_id": "dim_contract",
    "loyalty_member_id": "dim_loyalty_member",
    "digital_user_id": "dim_digital_user",
    "ev_charger_id": "dim_ev_charger",
    "solar_asset_id": "dim_solar_asset",
    "campaign_id": "dim_campaign",
    "promotion_id": "dim_promotion",
    "airport_code": "dim_airport",
    "airline_code": "dim_airline",
    "port_code": "dim_port",
    "vessel_imo": "dim_vessel",
    "gl_account_code": "dim_gl_account",
    "cost_centre_code": "dim_cost_centre",
    "profit_centre_code": "dim_profit_centre",
    "legal_entity_code": "dim_legal_entity",
    "business_unit_code": "dim_business_unit",
    "country_code": "dim_country",
    "data_source_code": "dim_data_source",
    "source_system_code": "dim_data_source",
}

DOMAINS = [
    ("retail", "Retail and forecourt",
     ("fact_retail", "fact_shop", "fact_forecourt", "fact_pump", "fact_tank",
      "fact_price", "fact_promotions", "fact_site_daily")),
    ("commercial", "Commercial and B2B",
     ("fact_commercial", "fact_contract", "fact_customer")),
    ("supply", "Supply and storage",
     ("fact_procurement", "fact_import", "fact_terminal", "fact_inventory",
      "fact_stock", "fact_replenish")),
    ("logistics", "Logistics and fleet",
     ("fact_deliveries", "fact_delivery", "fact_vehicle_trips",
      "fact_route", "fact_fleet")),
    ("products", "LPG, lubricants, aviation and marine",
     ("fact_lpg", "fact_lubricant", "fact_aviation", "fact_aircraft",
      "fact_marine", "fact_bunker")),
    ("digital", "Loyalty and digital",
     ("fact_loyalty", "fact_digital", "fact_mobile", "fact_campaign")),
    ("energy", "New energy",
     ("fact_ev", "fact_solar", "fact_site_energy", "fact_grid", "fact_energy")),
    ("assets", "Assets and maintenance",
     ("fact_maintenance", "fact_asset", "fact_spare")),
    ("hsseq", "HSSEQ",
     ("fact_hsseq", "fact_near", "fact_environmental", "fact_safety",
      "fact_training", "fact_permit", "fact_vehicle_safety")),
    ("finance", "Finance and planning",
     ("fact_finance", "fact_general_ledger", "fact_accounts", "fact_capex",
      "fact_opex", "fact_budget", "fact_forecast", "fact_cashflow",
      "fact_working", "fact_daily_executive")),
]


def domain_of(table: str) -> str | None:
    for slug, _, prefixes in DOMAINS:
        if any(table.startswith(p) for p in prefixes):
            return slug
    return None


def fks_of(columns: list[str]) -> list[str]:
    """The dimensions a fact table joins, deduplicated and ordered."""
    seen: list[str] = []
    for col in columns:
        dim = FK_TO_DIM.get(col)
        if dim and dim not in seen:
            seen.append(dim)
    return seen


def measures_of(columns: list[str], types: dict) -> list[str]:
    """The additive measures, which are what a star schema is actually for."""
    out = []
    for col in columns:
        if types.get(col) != "decimal":
            continue
        if col.endswith("_pct") or col.endswith("_key"):
            continue
        out.append(col)
    return out[:6]


def render_domain(slug: str, title: str, facts: list[str],
                  tables: dict) -> str:
    lines = [
        f"# ERD — {title}",
        "",
        DISCLAIMER,
        "Generated from the build manifest by `scripts/generate_erd.py`.",
        "",
        "```mermaid",
        "erDiagram",
    ]

    used_dims: set[str] = set()
    for fact in facts:
        cols = tables[fact]["columns"]
        for dim in fks_of(cols):
            used_dims.add(dim)
            lines.append(f"    {dim.upper()} ||--o{{ {fact.upper()} : \"\"")

    # Attributes: keys and a few measures, enough to show the grain without
    # rendering 20 columns per box.
    for fact in facts:
        info = tables[fact]
        types = info.get("intended_types", {})
        lines.append(f"    {fact.upper()} {{")
        for col in fks_of(info["columns"]):
            key_col = next(c for c in info["columns"]
                           if FK_TO_DIM.get(c) == col)
            lines.append(f"        string {key_col} FK")
        for m in measures_of(info["columns"], types):
            lines.append(f"        decimal {m}")
        lines.append("    }")

    for dim in sorted(used_dims):
        if dim not in tables:
            continue
        lines.append(f"    {dim.upper()} {{")
        lines.append(f"        string {dim.replace('dim_', '')}_id PK")
        lines.append("    }")

    lines += ["```", "", "## Tables in this domain", "",
              "| Fact | Grain | Rows | Dimensions |", "|---|---|---:|---:|"]
    for fact in facts:
        info = tables[fact]
        grain = fact.replace("fact_", "").replace("_", " ")
        lines.append(f"| `{fact}` | one row per {grain} | "
                     f"{info['rows']:,} | {len(fks_of(info['columns']))} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_conformed(tables: dict) -> str:
    facts = sorted(t for t in tables if t.startswith("fact_"))
    reach: dict[str, list[str]] = defaultdict(list)
    for fact in facts:
        for dim in fks_of(tables[fact]["columns"]):
            reach[dim].append(fact)

    ranked = sorted(reach.items(), key=lambda kv: -len(kv[1]))

    lines = [
        "# ERD — conformed dimensions",
        "",
        DISCLAIMER,
        "Generated from the build manifest by `scripts/generate_erd.py`.",
        "",
        "The value of a conformed dimension is its **reach**: `dim_site` joins "
        "retail, supply, maintenance and safety, which is what makes it "
        "possible to ask one question of all four. It is also why an error in "
        "a high-reach dimension is wrong in dozens of places at once.",
        "",
        "```mermaid",
        "erDiagram",
    ]

    # Only the dimensions with real reach, or the diagram is unreadable.
    for dim, facts_using in ranked[:10]:
        lines.append(f"    {dim.upper()} {{")
        lines.append(f"        string {dim.replace('dim_', '')}_id PK")
        lines.append(f"        int joins_{len(facts_using)}_fact_tables")
        lines.append("    }")

    for slug, _title, _ in DOMAINS:
        lines.append(f"    {slug.upper()}_FACTS {{")
        n = sum(1 for f in facts if domain_of(f) == slug)
        lines.append(f"        int {n}_tables")
        lines.append("    }")

    for dim, facts_using in ranked[:10]:
        domains = {domain_of(f) for f in facts_using} - {None}
        for d in sorted(domains):
            lines.append(f"    {dim.upper()} ||--o{{ {d.upper()}_FACTS : \"\"")

    lines += ["```", "", "## Dimension reach", "",
              "| Conformed dimension | Fact tables | Domains |",
              "|---|---:|---:|"]
    for dim, facts_using in ranked:
        domains = {domain_of(f) for f in facts_using} - {None}
        lines.append(f"| `{dim}` | {len(facts_using)} | {len(domains)} |")

    lines += ["", "## Domain diagrams", ""]
    for slug, title, _ in DOMAINS:
        lines.append(f"- [{title}](erd_{slug}.md)")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    args = ap.parse_args(argv)

    if not args.manifest.exists():
        raise SystemExit(f"no manifest at {args.manifest}; run the generator first")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    tables = manifest["tables"]
    OUT.mkdir(parents=True, exist_ok=True)

    (OUT / "README.md").write_text(render_conformed(tables), encoding="utf-8")
    print(f"wrote {(OUT / 'README.md').relative_to(REPO)}")

    all_facts = sorted(t for t in tables if t.startswith("fact_"))
    for slug, title, _ in DOMAINS:
        facts = [f for f in all_facts if domain_of(f) == slug]
        if not facts:
            continue
        path = OUT / f"erd_{slug}.md"
        path.write_text(render_domain(slug, title, facts, tables),
                        encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)} ({len(facts)} facts)")

    unassigned = [f for f in all_facts if domain_of(f) is None]
    if unassigned:
        print(f"note: {len(unassigned)} facts not assigned to a domain: "
              f"{unassigned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
