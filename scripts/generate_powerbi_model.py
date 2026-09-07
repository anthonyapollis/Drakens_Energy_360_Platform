"""Generate the Power BI semantic model as TMDL.

TMDL is Power BI's model-as-code format: the same definition Desktop reads and
the XMLA endpoint deploys, but as plain text that reviews in a pull request.
Building it here rather than clicking it together in Desktop means the model is
version-controlled, diffable, and reproducible on a machine that has never had
the .pbix open.

Table and column definitions are read from the gold schema in the warehouse, so
the model cannot claim a column the warehouse does not have. Measures,
relationships, roles and the aggregation mapping are curated below, because
those are design decisions and not derivable from a schema.

Usage:
    python scripts/generate_powerbi_model.py
    python scripts/generate_powerbi_model.py --warehouse data/drakens360.duckdb
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
PROJECT = "DrakensEnergy360"
PBI = REPO / "powerbi"
MODEL_DIR = PBI / f"{PROJECT}.SemanticModel"
DEFN = MODEL_DIR / "definition"
REPORT_DIR = PBI / f"{PROJECT}.Report"
OUT = DEFN

# Tables the semantic model exposes, and how each is stored.
#
# Storage mode is a deliberate choice per table, not a global setting:
# dimensions and aggregates are small and become Import so slicers and card
# visuals are instant; the transaction fact stays DirectQuery because importing
# 37 million rows into a .pbix is how a model becomes unmaintainable.
# `schema` is the warehouse schema each table lives in. It defaults to gold
# because that is where everything a report should read lives -- but the
# observability tables are in `platform`, and leaving them out meant the
# semantic model could not express the data-quality page at all. A report that
# cannot show its own rejection rate is a report asking to be trusted.
TABLES = {
    "dim_date":                     dict(mode="import", kind="dimension"),
    "dim_site":                     dict(mode="import", kind="dimension"),
    "dim_product":                  dict(mode="import", kind="dimension"),
    "dim_customer":                 dict(mode="import", kind="dimension"),
    "fct_retail_fuel_sales":        dict(mode="directQuery", kind="fact"),
    "agg_site_daily_fuel":          dict(mode="import", kind="aggregate"),
    "agg_executive_daily_kpi":      dict(mode="import", kind="aggregate"),
    "network_investment_scorecard": dict(mode="import", kind="aggregate"),
    "fct_deliveries":               dict(mode="import", kind="fact"),
    "fct_commercial_orders":        dict(mode="import", kind="fact"),
    "fct_maintenance_work_orders":  dict(mode="import", kind="fact"),
    # Not a reporting table. It exists because the row-level security role
    # reads the user's scope from it, and a role referencing a table the model
    # does not contain fails to load with an error naming the role rather than
    # the table.
    "bridge_security_user_scope":   dict(mode="import", kind="security"),
    "obs_cleansing_summary":        dict(mode="import", kind="observability",
                                         schema="platform"),
    "obs_quarantine_reasons":       dict(mode="import", kind="observability",
                                         schema="platform"),
    "obs_reconciliation_controls":  dict(mode="import", kind="observability",
                                         schema="platform"),
    "obs_table_freshness":          dict(mode="import", kind="observability",
                                         schema="platform"),
}

# DuckDB / Databricks types to TMDL data types.
TYPE_MAP = {
    "BIGINT": "int64", "INTEGER": "int64", "SMALLINT": "int64",
    "HUGEINT": "int64", "UBIGINT": "int64",
    "DOUBLE": "double", "FLOAT": "double", "REAL": "double",
    "BOOLEAN": "boolean",
    "DATE": "dateTime", "TIMESTAMP": "dateTime",
    "TIMESTAMP WITH TIME ZONE": "dateTime",
    "VARCHAR": "string", "TEXT": "string",
}

# Columns that must never be summed. A surrogate key with a default
# summarisation of Sum is the single most common cause of a Power BI model
# that silently reports nonsense, because the aggregation is invisible in the
# field list and only wrong in the visual.
NEVER_SUMMARISE = re.compile(
    r"(_key|_id|_code|latitude|longitude|_pct|_year|_number|_days|_ratio)$")

# Columns hidden from the report view. Keys and audit columns are needed by
# the model and are noise to a report author.
HIDDEN = re.compile(r"(_key$|^_|^dw_|^scd_|^record_source$|^ingested_at$)")

DATA_CATEGORY = {
    "latitude": "Latitude",
    "longitude": "Longitude",
    "province": "StateOrProvince",
    "city": "City",
    "country_code": "Country",
}


def tmdl_type(sql_type: str) -> str:
    base = sql_type.split("(")[0].strip().upper()
    if base.startswith("DECIMAL") or base.startswith("NUMERIC"):
        return "decimal"
    return TYPE_MAP.get(base, "string")


def friendly(name: str) -> str:
    """dim_site.urban_class -> Urban Class.

    Report authors see these names, and snake_case in a field list reads as
    unfinished. The physical name is kept in sourceColumn so the mapping stays
    explicit rather than relying on a naming convention.
    """
    words = name.replace("_", " ").split()
    keep = {"id": "ID", "zar": "(R)", "kwh": "kWh", "pct": "%", "ev": "EV",
            "co2": "CO2", "kg": "kg", "km": "km", "otif": "OTIF",
            "gl": "GL", "hsseq": "HSSEQ", "lpg": "LPG", "qsr": "QSR",
            "sla": "SLA", "dso": "DSO", "za": "ZA", "ts": "Timestamp"}
    return " ".join(keep.get(w.lower(), w.capitalize()) for w in words)


def resolve_dax(expression: str, columns: dict[str, set[str]]) -> str:
    """Rewrite physical column references in DAX to the model's column names.

    The measures and roles below are written against the warehouse's physical
    names -- `agg_site_daily_fuel[gross_sales_zar]` -- because that is what the
    SQL and the dbt models call them, and writing them any other way would mean
    holding two vocabularies in your head while editing this file.

    The model renames columns for report authors, so the same column is
    `[Gross Sales (R)]` by the time DAX is evaluated. Left unresolved, every
    measure touching a renamed column fails at load with "cannot find column",
    and the ones that happen to survive are the columns whose friendly name
    differs only in case.

    Rewriting here rather than by hand means the two can never drift: the
    mapping is derived from the same schema that produced the columns.
    """
    def replace(match: re.Match) -> str:
        table, column = match.group(1), match.group(2)
        if table in columns and column in columns[table]:
            return f"{table}[{friendly(column)}]"
        return match.group(0)

    return re.sub(r"(\w+)\[([a-z0-9_]+)\]", replace, expression)


# --------------------------------------------------------------------------
# Curated design
# --------------------------------------------------------------------------
RELATIONSHIPS = [
    # (name, fromTable, fromColumn, toTable, toColumn, crossFilter)
    ("rel_retail_date", "fct_retail_fuel_sales", "date_key",
     "dim_date", "date_key", "singleDirection"),
    ("rel_retail_site", "fct_retail_fuel_sales", "site_key",
     "dim_site", "site_key", "singleDirection"),
    ("rel_retail_product", "fct_retail_fuel_sales", "product_key",
     "dim_product", "product_key", "singleDirection"),
    ("rel_aggsite_date", "agg_site_daily_fuel", "date_key",
     "dim_date", "date_key", "singleDirection"),
    ("rel_aggsite_site", "agg_site_daily_fuel", "site_key",
     "dim_site", "site_key", "singleDirection"),
    ("rel_exec_date", "agg_executive_daily_kpi", "date_key",
     "dim_date", "date_key", "singleDirection"),
    ("rel_deliveries_date", "fct_deliveries", "date_key",
     "dim_date", "date_key", "singleDirection"),
    ("rel_deliveries_site", "fct_deliveries", "destination_site_key",
     "dim_site", "site_key", "singleDirection"),
    ("rel_orders_date", "fct_commercial_orders", "date_key",
     "dim_date", "date_key", "singleDirection"),
    ("rel_orders_customer", "fct_commercial_orders", "customer_key",
     "dim_customer", "customer_key", "singleDirection"),
    ("rel_wo_date", "fct_maintenance_work_orders", "date_key",
     "dim_date", "date_key", "singleDirection"),
    ("rel_wo_site", "fct_maintenance_work_orders", "site_key",
     "dim_site", "site_key", "singleDirection"),
    ("rel_scorecard_site", "network_investment_scorecard", "site_key",
     "dim_site", "site_key", "singleDirection"),
]

# Every relationship is single-direction on purpose. Bidirectional filtering
# is convenient once and ambiguous forever: with more than one path between
# two tables the engine picks one and the answer depends on which. Where a
# report genuinely needs reverse filtering, CROSSFILTER in the measure makes
# it visible at the point of use.

MEASURES: dict[str, list[tuple[str, str, str, str]]] = {
    # table: [(name, expression, formatString, displayFolder)]
    "agg_site_daily_fuel": [
        ("Fuel Volume (L)", "SUM ( agg_site_daily_fuel[litres] )",
         "#,0", "Volume"),
        ("Volume per Site (L)",
         "DIVIDE ( [Fuel Volume (L)], [Trading Sites] )", "#,0", "Volume"),
        ("Trading Sites",
         "DISTINCTCOUNT ( agg_site_daily_fuel[site_key] )", "#,0", "Volume"),
        ("Fuel Revenue",
         "SUM ( agg_site_daily_fuel[gross_sales_zar] )",
         '"R"#,0', "Value"),
        ("Gross Margin",
         "SUM ( agg_site_daily_fuel[gross_margin_zar] )",
         '"R"#,0', "Value"),
        ("Gross Margin %",
         "DIVIDE ( [Gross Margin], [Fuel Revenue] )", "0.0%", "Value"),
        ("Margin per Litre (c)",
         "DIVIDE ( [Gross Margin], [Fuel Volume (L)] ) * 100",
         "#,0.0", "Value"),
        ("Transaction Count",
         "SUM ( agg_site_daily_fuel[transaction_count] )", "#,0", "Volume"),
        ("Average Transaction Value",
         "DIVIDE ( [Fuel Revenue], [Transaction Count] )",
         '"R"#,0.00', "Value"),
        # Time intelligence. All of it goes through dim_date, which is marked
        # as the date table -- without that mark these return blank in some
        # filter contexts and nobody can see why.
        ("Fuel Volume LY",
         "CALCULATE ( [Fuel Volume (L)], "
         "SAMEPERIODLASTYEAR ( dim_date[full_date] ) )", "#,0", "Time"),
        ("Fuel Volume YoY %",
         "DIVIDE ( [Fuel Volume (L)] - [Fuel Volume LY], [Fuel Volume LY] )",
         "0.0%", "Time"),
        ("Gross Margin YTD",
         "TOTALYTD ( [Gross Margin], dim_date[full_date] )",
         '"R"#,0', "Time"),
        ("Fuel Volume 7D Average",
         "AVERAGEX ( DATESINPERIOD ( dim_date[full_date], "
         "MAX ( dim_date[full_date] ), -7, DAY ), [Fuel Volume (L)] )",
         "#,0", "Time"),
        # The map's headline ratio. The denominator counts the *filtered*
        # dim_site, so a regional analyst under row-level security sees their
        # own provinces' figure rather than a filtered numerator divided by a
        # network-wide denominator.
        ("Margin per Site",
         "DIVIDE ( [Gross Margin], DISTINCTCOUNT ( dim_site[site_key] ) )",
         '"R"#,0', "Network"),
    ],
    "fct_deliveries": [
        ("Deliveries", "COUNTROWS ( fct_deliveries )", "#,0", "Supply"),
        ("OTIF Deliveries",
         "CALCULATE ( [Deliveries], fct_deliveries[is_otif] = TRUE () )",
         "#,0", "Supply"),
        ("OTIF %", "DIVIDE ( [OTIF Deliveries], [Deliveries] )",
         "0.0%", "Supply"),
        ("Average Delay (min)",
         "AVERAGE ( fct_deliveries[delay_minutes] )", "#,0", "Supply"),
    ],
    "fct_maintenance_work_orders": [
        ("Work Orders",
         "COUNTROWS ( fct_maintenance_work_orders )", "#,0", "Assets"),
        ("Breakdown Rate %",
         "DIVIDE ( CALCULATE ( [Work Orders], "
         "fct_maintenance_work_orders[is_breakdown] = TRUE () ), "
         "[Work Orders] )", "0.0%", "Assets"),
        ("Maintenance Cost",
         "SUM ( fct_maintenance_work_orders[total_cost_zar] )",
         '"R"#,0', "Assets"),
    ],
    "network_investment_scorecard": [
        ("Sites Scored",
         "COUNTROWS ( network_investment_scorecard )", "#,0", "Network"),
        ("Average Investment Score",
         "AVERAGE ( network_investment_scorecard[investment_score] )",
         "#,0.0", "Network"),
        ("Divest Candidates",
         "CALCULATE ( [Sites Scored], "
         "CONTAINSSTRING ( network_investment_scorecard"
         "[investment_recommendation], \"Divest\" ) )", "#,0", "Network"),
        ("Margin at Risk",
         "CALCULATE ( SUM ( network_investment_scorecard[total_margin_zar] ), "
         "CONTAINSSTRING ( network_investment_scorecard"
         "[investment_recommendation], \"Divest\" ) )",
         '"R"#,0', "Network"),
        ("Downtime Hours",
         "SUM ( network_investment_scorecard[downtime_hours] )",
         "#,0", "Assets"),
        ("Corridor Sites",
         "CALCULATE ( DISTINCTCOUNT ( dim_site[site_key] ), "
         "dim_site[on_national_route] = TRUE () )", "#,0", "Network"),
    ],
    "obs_cleansing_summary": [
        ("Rows Landed", "SUM ( obs_cleansing_summary[raw_rows] )",
         "#,0", "Data quality"),
        ("Rows Cleansed", "SUM ( obs_cleansing_summary[cleansed_rows] )",
         "#,0", "Data quality"),
        ("Rows Quarantined",
         "SUM ( obs_cleansing_summary[quarantined_rows] )",
         "#,0", "Data quality"),
        # Recomputed from the totals rather than averaged from the per-table
        # rates. An average of rates weights a 40-row dimension the same as a
        # five-million-row fact, which is how a healthy network reports a
        # frightening number and an unhealthy one reports a calm one.
        ("Quarantine Rate %",
         "DIVIDE ( [Rows Quarantined], [Rows Landed] )",
         "0.00%", "Data quality"),
        ("Duplicate Rate %",
         "DIVIDE ( SUM ( obs_cleansing_summary[duplicates_removed] ), "
         "[Rows Landed] )", "0.00%", "Data quality"),
        ("Tables Monitored",
         "DISTINCTCOUNT ( obs_cleansing_summary[table_name] )",
         "#,0", "Data quality"),
        ("Tables Not Reconciling",
         "CALCULATE ( [Tables Monitored], "
         "obs_cleansing_summary[row_count_reconciles] = FALSE () )",
         "#,0", "Data quality"),
    ],
    "obs_reconciliation_controls": [
        ("Controls", "COUNTROWS ( obs_reconciliation_controls )",
         "#,0", "Data quality"),
        ("Controls Passing",
         "CALCULATE ( [Controls], "
         "obs_reconciliation_controls[is_passing] = TRUE () )",
         "#,0", "Data quality"),
        ("Control Pass Rate %",
         "DIVIDE ( [Controls Passing], [Controls] )", "0.0%", "Data quality"),
        ("Worst Control Variance %",
         "MAX ( obs_reconciliation_controls[variance_pct] )",
         "0.000%", "Data quality"),
    ],
    "obs_quarantine_reasons": [
        ("Rows Rejected", "SUM ( obs_quarantine_reasons[failure_count] )",
         "#,0", "Data quality"),
        ("Distinct Rules Firing",
         "DISTINCTCOUNT ( obs_quarantine_reasons[failed_rule] )",
         "#,0", "Data quality"),
    ],
    "fct_commercial_orders": [
        ("Commercial Revenue",
         "SUM ( fct_commercial_orders[revenue_zar] )", '"R"#,0', "Commercial"),
        ("Commercial Margin",
         "SUM ( fct_commercial_orders[gross_margin_zar] )",
         '"R"#,0', "Commercial"),
        # Referential drift made visible. A model that cannot say how much of
        # its revenue sits on an unmatched customer will eventually be asked,
        # and "I don't know" is the wrong answer to have to give.
        ("Unmatched Customer Revenue %",
         "DIVIDE ( CALCULATE ( [Commercial Revenue], "
         "fct_commercial_orders[customer_key] = -1 ), [Commercial Revenue] )",
         "0.00%", "Data quality"),
    ],
}

ROLES = [
    (
        "Regional Analyst",
        "dim_site",
        # The scope comes from a table, not from group names: adding a province
        # to someone's remit is a data change, not a deployment.
        "VAR UserScope = "
        "CALCULATETABLE ( VALUES ( bridge_security_user_scope[scope_value] ), "
        "bridge_security_user_scope[user_principal] = USERPRINCIPALNAME () ) "
        "RETURN dim_site[province] IN UserScope "
        "|| \"all\" IN CALCULATETABLE ( "
        "VALUES ( bridge_security_user_scope[scope_type] ), "
        "bridge_security_user_scope[user_principal] = USERPRINCIPALNAME () )",
    ),
    (
        "Executive",
        "dim_site",
        # Executives see every province. Object-level security, configured at
        # deployment, is what hides the transaction detail from them -- they
        # need the aggregate, not the customer list.
        "TRUE ()",
    ),
]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def render_column(name: str, sql_type: str, table: str) -> str:
    dtype = tmdl_type(sql_type)
    lines = [f"\tcolumn '{friendly(name)}'",
             f"\t\tdataType: {dtype}",
             f"\t\tsourceColumn: {name}"]

    if dtype in ("int64", "double", "decimal"):
        if NEVER_SUMMARISE.search(name):
            lines.append("\t\tsummarizeBy: none")
        else:
            lines.append("\t\tsummarizeBy: sum")
    else:
        lines.append("\t\tsummarizeBy: none")

    # Marking a date table needs both the table's dataCategory and isKey on
    # its date column. With only the first, Power BI does not accept it as a
    # date table and every time-intelligence measure returns blank -- silently,
    # which is the worst way for this to fail.
    if table == "dim_date" and name == "full_date":
        lines.append("		isKey")
    if name in DATA_CATEGORY:
        lines.append(f"\t\tdataCategory: {DATA_CATEGORY[name]}")
    if HIDDEN.search(name):
        lines.append("\t\tisHidden")
    if name.endswith("_zar"):
        lines.append('\t\tformatString: "R"#,0.00')
    elif name.endswith("_pct"):
        lines.append("\t\tformatString: 0.0%")
    elif dtype == "dateTime":
        lines.append("\t\tformatString: yyyy-mm-dd")

    lines.append('\t\tannotation SummarizationSetBy = "Automatic"')
    return "\n".join(lines)


def render_table(table: str, columns: list[tuple[str, str]], cfg: dict,
                 colmap: dict[str, set[str]]) -> str:
    parts = [f"table {table}", ""]
    if table == "dim_date":
        parts += ["\tdataCategory: Time", ""]

    for name, sql_type in columns:
        parts.append(render_column(name, sql_type, table))
        parts.append("")

    for mname, expr, fmt, folder in MEASURES.get(table, []):
        parts.append(f"\tmeasure '{mname}' = {resolve_dax(expr, colmap)}")
        parts.append(f"\t\tformatString: {fmt}")
        parts.append(f"\t\tdisplayFolder: {folder}")
        parts.append("")

    mode = "import" if cfg["mode"] == "import" else "directQuery"
    parts += [
        f"\tpartition {table} = m",
        f"\t\tmode: {mode}",
        "\t\tsource =",
        "\t\t\t\tlet",
        "\t\t\t\t    Source = Databricks.Catalogs("
        "ServerHostname, HttpPath, null),",
        "\t\t\t\t    Catalog = Source{[Name=CatalogName]}[Data],",
        f'\t\t\t\t    Schema  = Catalog{{[Name='
        f'"{cfg.get("schema", "gold")}"]}}[Data],',
        f'\t\t\t\t    Table   = Schema{{[Name="{table}"]}}[Data]',
        "\t\t\t\tin",
        "\t\t\t\t    Table",
        "",
    ]
    return "\n".join(parts)


def render_relationships(relationships) -> str:
    out = []
    for name, ft, fc, tt, tc, cf in relationships:
        out += [
            f"relationship {name}",
            f"\tfromColumn: {ft}.'{friendly(fc)}'",
            f"\ttoColumn: {tt}.'{friendly(tc)}'",
            f"\tcrossFilteringBehavior: {cf}",
            "",
        ]
    return "\n".join(out)


def render_role(name: str, table: str, expr: str,
                colmap: dict[str, set[str]]) -> str:
    return "\n".join([
        f"role '{name}'",
        "\tmodelPermission: read",
        "",
        f"\ttablePermission {table} = {resolve_dax(expr, colmap)}",
        "",
    ])


def render_model(tables: list[str], roles: list[str]) -> str:
    refs = [f"ref table {t}" for t in tables]
    refs += [f"ref role '{n}'" for n in roles]
    return "\n".join([
        "model Model",
        "\tculture: en-ZA",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "",
        "\t/// Drakens Energy 360 semantic model.",
        "\t/// Independent synthetic portfolio project. Generated data;",
        "\t/// no data from any real company.",
        "",
        "\tannotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        "\t/// Auto date/time is off. It creates a hidden date table per date",
        "\t/// column, none of which is the conformed dim_date, and the model",
        "\t/// then disagrees with itself about what a fiscal year is.",
        "",
        *refs,
        "",
    ])


def write_project_files() -> None:
    """Emit the .pbip wrapper so the model opens in Power BI Desktop.

    TMDL on its own is a definition, not a project. Desktop opens a `.pbip`
    that points at a SemanticModel folder and a Report folder, each carrying a
    small descriptor. Without these three files the model is only readable by
    a tool that already knows what it is looking at.
    """
    (PBI / f"{PROJECT}.pbip").write_text(json.dumps({
        "version": "1.0",
        "artifacts": [
            {"report": {"path": f"{PROJECT}.Report"}},
        ],
        "settings": {"enableAutoRecovery": True},
    }, indent=2), encoding="utf-8")

    (MODEL_DIR / "definition.pbism").write_text(json.dumps({
        "version": "4.2",
        "settings": {},
    }, indent=2), encoding="utf-8")

    (MODEL_DIR / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId":
                   "00000000-0000-0000-0000-000000000001"},
    }, indent=2), encoding="utf-8")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "definition.pbir").write_text(json.dumps({
        "version": "4.0",
        "datasetReference": {
            "byPath": {"path": f"../{PROJECT}.SemanticModel"},
            "byConnection": None,
        },
    }, indent=2), encoding="utf-8")

    # A minimal report. The pages a report author would build are described in
    # powerbi/semantic_model.md; shipping a stub rather than a fabricated
    # dashboard keeps the repository honest about what was actually built.
    (REPORT_DIR / "report.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/"
                   "report/definition/report/1.0.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU02"}},
        "layoutOptimization": "None",
        "resourcePackages": [],
        "sections": [{
            "name": "ReportSection_Network",
            "displayName": "Network",
            "displayOption": "FitToPage",
            "height": 720.0,
            "width": 1280.0,
            "visualContainers": [],
        }],
    }, indent=2), encoding="utf-8")

    (REPORT_DIR / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId":
                   "00000000-0000-0000-0000-000000000002"},
    }, indent=2), encoding="utf-8")


def render_expressions() -> str:
    return "\n".join([
        "/// Connection parameters, so the same model deploys to dev, test",
        "/// and prod by changing three values rather than editing queries.",
        "expression ServerHostname = "
        '"adb-0000000000000000.0.azuredatabricks.net" meta '
        '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        "",
        "expression HttpPath = "
        '"/sql/1.0/warehouses/0000000000000000" meta '
        '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        "",
        "expression CatalogName = "
        '"drakens_prod" meta '
        '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        "",
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", default=os.environ.get(
        "DRAKENS_DUCKDB_PATH", str(REPO / "data" / "drakens360.duckdb")))
    args = ap.parse_args()

    wh = Path(args.warehouse)
    if not wh.exists():
        print(f"no warehouse at {wh}; build it first")
        return 1
    try:
        con = duckdb.connect(str(wh), read_only=True)
    except duckdb.IOException as exc:
        print(f"warehouse is locked: {str(exc)[:100]}")
        return 1

    for path in (MODEL_DIR, REPORT_DIR):
        if path.exists():
            shutil.rmtree(path)
    (DEFN / "tables").mkdir(parents=True)

    # Two passes. Every schema is collected before any DAX is rendered,
    # because a measure on the first table may reference a column on the last.
    schemas: dict[str, list[tuple[str, str]]] = {}
    missing: list[str] = []
    for table in TABLES:
        db_schema = f"main_{TABLES[table].get('schema', 'gold')}"
        try:
            schema = con.execute(f"describe {db_schema}.{table}").df()
        except duckdb.Error:
            missing.append(table)
            continue
        schemas[table] = list(
            zip(schema.column_name, schema.column_type, strict=False))
    con.close()

    colmap = {t: {c for c, _ in cols} for t, cols in schemas.items()}
    written: list[str] = []
    for table, cols in schemas.items():
        (DEFN / "tables" / f"{table}.tmdl").write_text(
            render_table(table, cols, TABLES[table], colmap), encoding="utf-8")
        written.append(table)

    if not written:
        print("no gold tables found; build the warehouse first")
        return 1

    # Only relationships whose endpoints both exist are emitted. A dangling
    # relationship makes the whole model fail to load, with an error that
    # names the relationship rather than the missing table.
    kept = [r for r in RELATIONSHIPS if r[1] in written and r[3] in written]
    dropped = len(RELATIONSHIPS) - len(kept)

    # A role is only emitted when every table its expression reads is in the
    # model. Emitting one that references a missing table does not fail
    # loudly -- the whole model refuses to load, and the error names the role
    # rather than the table it could not find.
    (DEFN / "roles").mkdir(exist_ok=True)
    skipped_roles: list[tuple[str, list[str]]] = []
    emitted_roles: list[str] = []
    for name, table, expr in ROLES:
        needed = set(re.findall(r"(\w+)\[", expr)) | {table}
        absent = sorted(t for t in needed if t in TABLES and t not in written)
        if table not in written or absent:
            skipped_roles.append((name, absent or [table]))
            continue
        (DEFN / "roles" / f"{name}.tmdl").write_text(
            render_role(name, table, expr, colmap), encoding="utf-8")
        emitted_roles.append(name)

    (DEFN / "database.tmdl").write_text(
        "database\n\tcompatibilityLevel: 1567\n", encoding="utf-8")
    (DEFN / "model.tmdl").write_text(
        render_model(written, emitted_roles), encoding="utf-8")
    (DEFN / "relationships.tmdl").write_text(
        render_relationships(kept), encoding="utf-8")
    (DEFN / "expressions.tmdl").write_text(
        render_expressions(), encoding="utf-8")

    write_project_files()

    n_measures = sum(len(v) for k, v in MEASURES.items() if k in written)
    print(f"wrote {PROJECT}.pbip")
    print(f"  {len(written)} tables, {len(kept)} relationships, "
          f"{n_measures} measures, {len(emitted_roles)} roles")
    if missing:
        print(f"  not in this warehouse, skipped: {', '.join(missing)}")
    if dropped:
        print(f"  {dropped} relationships dropped: an endpoint is missing")
    for name, absent in skipped_roles:
        print(f"  role {name!r} skipped: needs {', '.join(absent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
