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

# Which shape the partitions take. `csv` reads the extracts in powerbi/data
# and opens anywhere; `databricks` is the deployed shape. Set by --source.
SOURCE = "csv"

# How the semantic model is serialised. `bim` is TMSL, the single JSON file
# every version of Desktop reads. `tmdl` is the newer text format, nicer to
# review and gated behind a preview feature that governs writing rather than
# reading -- Desktop 2.156 refuses a TMDL project with "Missing required
# artifact 'model.bim'" even with that feature switched on. Set by --format.
FORMAT = "bim"

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


def measure_names(table: str) -> set[str]:
    return {m for m, _, _, _ in MEASURES.get(table, [])}


def column_name(table: str, physical: str) -> str:
    """The name a column takes in the model, avoiding its own table's measures.

    A measure and a column cannot share a name within a table, and five pairs
    here did: agg_site_daily_fuel carries a per-row `gross_margin_pct` and also
    needs a `Gross Margin %` measure computed over the whole filter context.
    Desktop refuses the model outright -- "the measure cannot be created
    because a column with the same name already exists" -- naming one pair at a
    time, so the model opens five failures deep.

    The column is renamed rather than the measure. The measure is the object a
    report should bind to, because it recalculates in filter context and the
    pre-aggregated column does not; a report author who picks the column
    instead gets a number that is right for one row and wrong for any total.
    Suffixing and hiding the column makes that mistake unavailable while
    keeping the value in the model for anyone who genuinely wants the row.
    """
    name = friendly(physical)
    return f"{name} (row)" if name in measure_names(table) else name


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
            return f"{table}[{column_name(table, column)}]"
        return match.group(0)

    return re.sub(r"(\w+)\[([a-z0-9_]+)\]", replace, expression)


# --------------------------------------------------------------------------
# Curated design
# --------------------------------------------------------------------------
RELATIONSHIPS = [
    # (name, fromTable, fromColumn, toTable, toColumn, crossFilter)
    ("rel_retail_date", "fct_retail_fuel_sales", "date_key",
     "dim_date", "date_key", "oneDirection"),
    ("rel_retail_site", "fct_retail_fuel_sales", "site_key",
     "dim_site", "site_key", "oneDirection"),
    ("rel_retail_product", "fct_retail_fuel_sales", "product_key",
     "dim_product", "product_key", "oneDirection"),
    ("rel_aggsite_date", "agg_site_daily_fuel", "date_key",
     "dim_date", "date_key", "oneDirection"),
    ("rel_aggsite_site", "agg_site_daily_fuel", "site_key",
     "dim_site", "site_key", "oneDirection"),
    ("rel_exec_date", "agg_executive_daily_kpi", "date_key",
     "dim_date", "date_key", "oneDirection"),
    ("rel_deliveries_date", "fct_deliveries", "date_key",
     "dim_date", "date_key", "oneDirection"),
    ("rel_deliveries_site", "fct_deliveries", "destination_site_key",
     "dim_site", "site_key", "oneDirection"),
    ("rel_orders_date", "fct_commercial_orders", "date_key",
     "dim_date", "date_key", "oneDirection"),
    ("rel_orders_customer", "fct_commercial_orders", "customer_key",
     "dim_customer", "customer_key", "oneDirection"),
    ("rel_wo_date", "fct_maintenance_work_orders", "date_key",
     "dim_date", "date_key", "oneDirection"),
    ("rel_wo_site", "fct_maintenance_work_orders", "site_key",
     "dim_site", "site_key", "oneDirection"),
    ("rel_scorecard_site", "network_investment_scorecard", "site_key",
     "dim_site", "site_key", "oneDirection"),
]

# Every relationship filters in one direction on purpose. Bidirectional
# filtering is convenient once and ambiguous forever: with more than one path
# between two tables the engine picks one and the answer depends on which.
# Where a report genuinely needs reverse filtering, CROSSFILTER in the measure
# makes it visible at the point of use.
#
# The value is `oneDirection`. TMSL calls the same thing `singleDirection`,
# and TMDL rejects it -- one of several places where the JSON vocabulary and
# the text vocabulary differ by a word.

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
        # Growth, on the three measures a downstream business is actually run
        # on. Volume already had a year-on-year pair; revenue and margin did
        # not, so a page could show margin falling while only volume carried a
        # comparison -- and a reader assumes the arrow they can see applies to
        # the number next to it.
        ("Fuel Revenue LY",
         "CALCULATE ( [Fuel Revenue], "
         "SAMEPERIODLASTYEAR ( dim_date[full_date] ) )", '"R"#,0', "Time"),
        ("Fuel Revenue YoY %",
         "DIVIDE ( [Fuel Revenue] - [Fuel Revenue LY], [Fuel Revenue LY] )",
         "0.0%", "Time"),
        ("Gross Margin LY",
         "CALCULATE ( [Gross Margin], "
         "SAMEPERIODLASTYEAR ( dim_date[full_date] ) )", '"R"#,0', "Time"),
        ("Gross Margin YoY %",
         "DIVIDE ( [Gross Margin] - [Gross Margin LY], [Gross Margin LY] )",
         "0.0%", "Time"),
        ("Margin per Litre LY (c)",
         "CALCULATE ( [Margin per Litre (c)], "
         "SAMEPERIODLASTYEAR ( dim_date[full_date] ) )", "#,0.0", "Time"),

        # Period averages. AVERAGEX over the *visible* days rather than a
        # total divided by a constant: divide by 365 and a part-year filter
        # silently understates every average on the page.
        ("Average Daily Volume (L)",
         "AVERAGEX ( VALUES ( dim_date[full_date] ), [Fuel Volume (L)] )",
         "#,0", "Averages"),
        ("Average Weekly Volume (L)",
         "AVERAGEX ( SUMMARIZE ( dim_date, dim_date[calendar_year], "
         "dim_date[week_of_year] ), [Fuel Volume (L)] )",
         "#,0", "Averages"),
        ("Average Yearly Volume (L)",
         "AVERAGEX ( VALUES ( dim_date[calendar_year] ), "
         "[Fuel Volume (L)] )", "#,0", "Averages"),
        ("Average Monthly Volume (L)",
         "AVERAGEX ( VALUES ( dim_date[year_month] ), [Fuel Volume (L)] )",
         "#,0", "Averages"),
        ("Average Monthly Margin",
         "AVERAGEX ( VALUES ( dim_date[year_month] ), [Gross Margin] )",
         '"R"#,0', "Averages"),
        ("Average Daily Margin",
         "AVERAGEX ( VALUES ( dim_date[full_date] ), [Gross Margin] )",
         '"R"#,0', "Averages"),

        # A 30-day mean plotted beside the daily series, so a reader can see
        # the trend through the noise instead of being asked to imagine it.
        ("Fuel Volume 30D Average",
         "AVERAGEX ( DATESINPERIOD ( dim_date[full_date], "
         "MAX ( dim_date[full_date] ), -30, DAY ), [Fuel Volume (L)] )",
         "#,0", "Time"),
        ("Margin 30D Average",
         "AVERAGEX ( DATESINPERIOD ( dim_date[full_date], "
         "MAX ( dim_date[full_date] ), -30, DAY ), [Gross Margin] )",
         '"R"#,0', "Time"),
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
        ("Commercial Revenue LY",
         "CALCULATE ( [Commercial Revenue], "
         "SAMEPERIODLASTYEAR ( dim_date[full_date] ) )", '"R"#,0', "Time"),
        ("Commercial Revenue YoY %",
         "DIVIDE ( [Commercial Revenue] - [Commercial Revenue LY], "
         "[Commercial Revenue LY] )", "0.0%", "Time"),
        ("Average Monthly Commercial Revenue",
         "AVERAGEX ( VALUES ( dim_date[year_month] ), [Commercial Revenue] )",
         '"R"#,0', "Averages"),
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
    # No blank line between the declaration and its own properties: TMDL
    # treats that as the end of the object's body and rejects the property
    # that follows.
    parts = [f"table {table}"]
    if table == "dim_date":
        parts.append("\tdataCategory: Time")
    parts.append("")

    for name, sql_type in columns:
        parts.append(render_column(name, sql_type, table))
        parts.append("")

    for mname, expr, fmt, folder in MEASURES.get(table, []):
        parts.append(f"\tmeasure '{mname}' = {resolve_dax(expr, colmap)}")
        parts.append(f"\t\tformatString: {fmt}")
        parts.append(f"\t\tdisplayFolder: {folder}")
        parts.append("")

    # DirectQuery has no meaning over a CSV, so the csv shape imports
    # everything. The retail fact is DirectQuery in the deployed shape because
    # importing 37 million rows into a .pbix is how a model becomes
    # unmaintainable; at extract scale it fits in memory.
    mode = ("import" if (SOURCE == "csv" or cfg["mode"] == "import")
            else "directQuery")
    parts += [
        f"\tpartition {table} = m",
        f"\t\tmode: {mode}",
        "\t\tsource =",
        "\t\t\t\tlet",
        *[f"\t\t\t\t{line}" for line in source_query(table, cfg, columns)],
        "",
    ]
    return "\n".join(parts)


def source_query(table: str, cfg: dict,
                 columns: list[tuple[str, str]]) -> list[str]:
    """The M that loads one table, in whichever of the two shapes is wanted.

    `databricks` is the deployed shape: the same catalog the dbt models build
    into, parameterised so one model serves dev, test and prod.

    `csv` is the shape that lets the project be opened by someone who has
    neither a workspace nor a gateway, reading the extracts in `powerbi/data`.
    That matters more than it sounds: a portfolio model nobody can open is a
    model nobody can assess, and the Databricks version shows an authentication
    prompt before it shows a number.

    Columns are selected and typed in M rather than left to inference. Power
    Query guesses types from the first two hundred rows, and a column that is
    integer for two hundred rows and decimal afterwards fails the refresh at
    the row where it changes.
    """
    if SOURCE == "databricks":
        schema = cfg.get("schema", "gold")
        return [
            "    Source = Databricks.Catalogs("
            "ServerHostname, HttpPath, null),",
            "    Catalog = Source{[Name=CatalogName]}[Data],",
            f'    Schema  = Catalog{{[Name="{schema}"]}}[Data],',
            f'    Table   = Schema{{[Name="{table}"]}}[Data]',
            "in",
            "    Table",
        ]

    names = ", ".join(f'"{c}"' for c, _ in columns)
    types = ", ".join(f'{{"{c}", {m_type(t)}}}' for c, t in columns)
    return [
        f'    Path    = DataFolder & "{table}.csv",',
        "    Source  = Csv.Document(File.Contents(Path), "
        '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, "
        "[PromoteAllScalars=true]),",
        f"    Chosen  = Table.SelectColumns(Headers, {{{names}}}),",
        # The culture is pinned to en-US, matching how DuckDB writes the
        # extracts: a dot decimal separator and ISO timestamps.
        #
        # Without it Power Query types the columns in the model's culture,
        # which is en-ZA, where the decimal separator is a comma. Every
        # numeric cell then fails to parse and the table loads with as many
        # errors as it has rows -- 128 rows, 128 errors -- while still
        # reporting success. The measures come back blank and the model looks
        # empty rather than broken.
        f'    Typed   = Table.TransformColumnTypes(Chosen, {{{types}}}, '
        f'"en-US")',
        "in",
        "    Typed",
    ]


def m_type(sql_type: str) -> str:
    """The M type annotation matching the TMDL data type for a column."""
    return {
        "int64": "Int64.Type",
        "double": "type number",
        "decimal": "type number",
        "boolean": "type logical",
        "dateTime": "type datetime",
    }.get(tmdl_type(sql_type), "type text")


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
    """The model header, its refs, and nothing between them.

    TMDL is stricter than it looks, and both rules that matter here produce a
    parse error naming a line number rather than a cause:

      * `///` is a *description*, bound to the object declared on the next
        line. It is not a free-standing comment. A `///` block sitting in the
        middle of a body, or followed by a blank line, is a description of
        nothing and fails to parse.
      * A declaration and its properties cannot be separated by a blank line.

    So the commentary that would naturally sit inside the body is written as
    the model's own description, above the declaration, where it is both valid
    and visible in Desktop's model view.
    """
    refs = [f"ref table {t}" for t in tables]
    refs += [f"ref role '{n}'" for n in roles]
    return "\n".join([
        "/// Drakens Energy 360 semantic model.",
        "///",
        "/// Independent synthetic portfolio project. Generated data; no data",
        "/// from any real company.",
        "///",
        "/// Auto date/time is off. It creates a hidden date table per date",
        "/// column, none of which is the conformed dim_date, and the model",
        "/// then disagrees with itself about what a fiscal year is.",
        "model Model",
        "	culture: en-ZA",
        "	defaultPowerBIDataSourceVersion: powerBI_V3",
        "	discourageImplicitMeasures",
        "",
        "	annotation __PBI_TimeIntelligenceEnabled = 0",
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
    # Version fields are the ones the current schemas expect. They looked
    # like free text and are not: Desktop refuses a project whose scaffolding
    # declares a version it does not recognise, and does it by opening blank
    # rather than by saying so.
    (PBI / f"{PROJECT}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [
            {"report": {"path": f"{PROJECT}.Report"}},
        ],
        "settings": {"enableAutoRecovery": True},
    }, indent=2), encoding="utf-8")

    (MODEL_DIR / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "1.0",
        "settings": {},
    }, indent=2), encoding="utf-8")

    (MODEL_DIR / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId":
                   "00000000-0000-0000-0000-000000000001"},
    }, indent=2), encoding="utf-8")

    # The report is deliberately not written here.
    #
    # This function used to create a stub report alongside the model, and the
    # cleanup at the top of write() used to delete REPORT_DIR before doing so.
    # Between them they destroyed the real report: regenerating the model wiped
    # 79 visuals across 7 pages and replaced them with an empty page, leaving a
    # project that opened, bound correctly, and showed nothing.
    #
    # Nothing complained, because an empty report is a valid report. Ownership
    # is now split: this script owns the semantic model and the .pbip, and
    # scripts/generate_powerbi_report.py owns the report folder.


def render_expressions() -> str:
    if SOURCE == "csv":
        folder = str(REPO / "powerbi" / "data").replace("\\", "\\\\") + "\\\\"
        return "\n".join([
            "/// Where the CSV extracts live. One parameter, so moving the",
            "/// project to another machine is one edit rather than sixteen.",
            f'expression DataFolder = "{folder}" meta '
            '[IsParameterQuery=true, Type="Text", '
            "IsParameterQueryRequired=true]",
            "",
        ])
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



# --------------------------------------------------------------------------
# TMSL
# --------------------------------------------------------------------------
def bim_column(name: str, sql_type: str, table: str) -> dict:
    """One column, in TMSL's JSON rather than TMDL's text.

    The same decisions as `render_column`, expressed twice because the two
    formats are not convertible by string manipulation. Keeping them in one
    file at least makes a divergence visible in a diff.
    """
    dtype = tmdl_type(sql_type)
    column: dict = {
        "name": column_name(table, name),
        "dataType": dtype,
        "sourceColumn": name,
    }
    if dtype in ("int64", "double", "decimal"):
        column["summarizeBy"] = ("none" if NEVER_SUMMARISE.search(name)
                                 else "sum")
    else:
        column["summarizeBy"] = "none"

    if table == "dim_date" and name == "full_date":
        column["isKey"] = True
    if name in DATA_CATEGORY:
        column["dataCategory"] = DATA_CATEGORY[name]
    if HIDDEN.search(name) or column_name(table, name) != friendly(name):
        column["isHidden"] = True
    if name.endswith("_zar"):
        column["formatString"] = '"R"#,0.00'
    elif name.endswith("_pct"):
        column["formatString"] = "0.0%"
    elif dtype == "dateTime":
        column["formatString"] = "yyyy-mm-dd"
    return column


def bim_table(table: str, columns: list[tuple[str, str]], cfg: dict,
              colmap: dict[str, set[str]]) -> dict:
    body: dict = {"name": table}
    if table == "dim_date":
        body["dataCategory"] = "Time"

    body["columns"] = [bim_column(n, t, table) for n, t in columns]

    measures = []
    for mname, expr, fmt, folder in MEASURES.get(table, []):
        measures.append({
            "name": mname,
            "expression": resolve_dax(expr, colmap),
            "formatString": fmt,
            "displayFolder": folder,
        })
    if measures:
        body["measures"] = measures

    mode = ("import" if (SOURCE == "csv" or cfg["mode"] == "import")
            else "directQuery")
    body["partitions"] = [{
        "name": table,
        "mode": mode,
        "source": {
            "type": "m",
            # TMSL takes the M as a list of lines. A single string with
            # newlines also parses, but Desktop rewrites it to a list on the
            # first save, which makes the next diff unreadable.
            "expression": ["let", *source_query(table, cfg, columns)],
        },
    }]
    return body


def render_bim(schemas: dict[str, list[tuple[str, str]]],
               colmap: dict[str, set[str]],
               relationships: list, roles: list[str]) -> str:
    """The whole model as TMSL.

    This exists because TMDL did not open. Power BI Desktop 2.156 reports
    `Missing required artifact 'model.bim'` for a TMDL project even with the
    "Store semantic model using TMDL format" preview feature switched on --
    the flag governs how Desktop *writes* a project, not what it will read.

    TMSL has no such dependency: it is the format every version of Desktop and
    every XMLA endpoint has always accepted. It is less pleasant to read than
    TMDL and still perfectly diffable, which is the right trade for an
    artifact whose main job is to open on someone else's machine.
    """
    tables = [bim_table(t, cols, TABLES[t], colmap)
              for t, cols in schemas.items()]

    model: dict = {
        "culture": "en-ZA",
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "discourageImplicitMeasures": True,
        "sourceQueryCulture": "en-ZA",
        "tables": tables,
        "relationships": [
            {
                "name": name,
                "fromTable": ft,
                "fromColumn": column_name(ft, fc),
                "toTable": tt,
                "toColumn": column_name(tt, tc),
                "crossFilteringBehavior": cf,
            }
            for name, ft, fc, tt, tc, cf in relationships
        ],
        "annotations": [
            {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
        ],
    }

    expressions = bim_expressions()
    if expressions:
        model["expressions"] = expressions

    role_objects = []
    for name, table, expr in ROLES:
        if name not in roles:
            continue
        role_objects.append({
            "name": name,
            "modelPermission": "read",
            "tablePermissions": [
                {"name": table, "filterExpression": resolve_dax(expr, colmap)},
            ],
        })
    if role_objects:
        model["roles"] = role_objects

    return json.dumps({
        "name": PROJECT,
        "compatibilityLevel": 1567,
        "model": model,
    }, indent=2)


def bim_expressions() -> list[dict]:
    if SOURCE == "csv":
        folder = str(REPO / "powerbi" / "data").replace("\\", "\\\\") + "\\\\"
        return [{
            "name": "DataFolder",
            "kind": "m",
            "expression": f'"{folder}" meta [IsParameterQuery=true, '
                          'Type="Text", IsParameterQueryRequired=true]',
        }]
    return [
        {"name": "ServerHostname", "kind": "m",
         "expression": '"adb-0000000000000000.0.azuredatabricks.net" meta '
                       '[IsParameterQuery=true, Type="Text", '
                       "IsParameterQueryRequired=true]"},
        {"name": "HttpPath", "kind": "m",
         "expression": '"/sql/1.0/warehouses/0000000000000000" meta '
                       '[IsParameterQuery=true, Type="Text", '
                       "IsParameterQueryRequired=true]"},
        {"name": "CatalogName", "kind": "m",
         "expression": '"drakens_prod" meta [IsParameterQuery=true, '
                       'Type="Text", IsParameterQueryRequired=true]'},
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", default=os.environ.get(
        "DRAKENS_DUCKDB_PATH", str(REPO / "data" / "drakens360.duckdb")))
    ap.add_argument("--source", choices=("csv", "databricks"), default="csv",
                    help="csv opens without a workspace; databricks is the "
                         "deployed shape")
    ap.add_argument("--format", choices=("bim", "tmdl"), default="bim",
                    help="bim opens in any Desktop; tmdl is the text format "
                         "and needs the TMDL preview feature")
    args = ap.parse_args()

    global SOURCE, FORMAT
    SOURCE = args.source
    FORMAT = args.format

    wh = Path(args.warehouse)
    if not wh.exists():
        print(f"no warehouse at {wh}; build it first")
        return 1
    try:
        con = duckdb.connect(str(wh), read_only=True)
    except duckdb.IOException as exc:
        print(f"warehouse is locked: {str(exc)[:100]}")
        return 1

    # Only the model is cleared. Removing REPORT_DIR here is what silently
    # deleted the report every time the model was regenerated.
    if MODEL_DIR.exists():
        shutil.rmtree(MODEL_DIR)
    MODEL_DIR.mkdir(parents=True)
    if FORMAT == "tmdl":
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
    written: list[str] = list(schemas)

    if not written:
        print("no gold tables found; build the warehouse first")
        return 1

    if FORMAT == "tmdl":
        (DEFN / "tables").mkdir(parents=True, exist_ok=True)
        for table, cols in schemas.items():
            (DEFN / "tables" / f"{table}.tmdl").write_text(
                render_table(table, cols, TABLES[table], colmap),
                encoding="utf-8")

    # Only relationships whose endpoints both exist are emitted. A dangling
    # relationship makes the whole model fail to load, with an error that
    # names the relationship rather than the missing table.
    kept = [r for r in RELATIONSHIPS if r[1] in written and r[3] in written]
    dropped = len(RELATIONSHIPS) - len(kept)

    # A role is only emitted when every table its expression reads is in the
    # model. Emitting one that references a missing table does not fail
    # loudly -- the whole model refuses to load, and the error names the role
    # rather than the table it could not find.
    skipped_roles: list[tuple[str, list[str]]] = []
    emitted_roles: list[str] = []
    for name, table, expr in ROLES:
        needed = set(re.findall(r"(\w+)\[", expr)) | {table}
        absent = sorted(t for t in needed if t in TABLES and t not in written)
        if table not in written or absent:
            skipped_roles.append((name, absent or [table]))
            continue
        emitted_roles.append(name)

    if FORMAT == "tmdl":
        (DEFN / "roles").mkdir(parents=True, exist_ok=True)
        for name, table, expr in ROLES:
            if name in emitted_roles:
                (DEFN / "roles" / f"{name}.tmdl").write_text(
                    render_role(name, table, expr, colmap), encoding="utf-8")

        (DEFN / "database.tmdl").write_text(
            "database\n\tcompatibilityLevel: 1567\n", encoding="utf-8")
        (DEFN / "model.tmdl").write_text(
            render_model(written, emitted_roles), encoding="utf-8")
        (DEFN / "relationships.tmdl").write_text(
            render_relationships(kept), encoding="utf-8")
        (DEFN / "expressions.tmdl").write_text(
            render_expressions(), encoding="utf-8")
    else:
        # TMSL goes in a single model.bim beside definition.pbism, which is
        # where every version of Desktop looks for it. The `definition`
        # folder must not also exist: a semantic model folder holding both a
        # model.bim and a definition folder is two models in one place.
        (MODEL_DIR / "model.bim").write_text(
            render_bim(schemas, colmap, kept, emitted_roles),
            encoding="utf-8")

    write_project_files()

    n_measures = sum(len(v) for k, v in MEASURES.items() if k in written)
    print(f"wrote {PROJECT}.pbip ({FORMAT}, {SOURCE})")
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
