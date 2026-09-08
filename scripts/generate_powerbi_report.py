"""Generate the Power BI report as PBIR.

PBIR is the folder-per-page report format: one JSON per page and one per
visual, rather than a single opaque `report.json`. It is the format that pairs
with TMDL, and the reason to use it here is the same reason the model is
TMDL — a report that lives in one large generated blob cannot be reviewed, and
a report nobody reviews drifts from the model it sits on.

Layout is authored in a small grid vocabulary rather than in raw pixels, so a
page reads as a description of what it shows instead of a list of
coordinates.

The report is built against the semantic model in
`DrakensEnergy360.SemanticModel`; every field reference below has to exist
there, and `--check` verifies that against the TMDL before writing anything.

Usage:
    python scripts/generate_powerbi_report.py
    python scripts/generate_powerbi_report.py --check
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECT = "DrakensEnergy360"
PBI = REPO / "powerbi"
MODEL_DIR = PBI / f"{PROJECT}.SemanticModel"
REPORT_DIR = PBI / f"{PROJECT}.Report"
DEFN = REPORT_DIR / "definition"

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"

# Canvas. 1280x720 is the 16:9 default and the size every Power BI Service
# viewport is tuned for; a custom canvas looks deliberate in Desktop and
# letterboxed everywhere else.
W, H = 1280, 720

# A 12-column grid with a 16px gutter, so visuals line up without anyone
# nudging pixels. `col()` and `row()` turn grid units into the absolute
# coordinates PBIR wants.
MARGIN, GUTTER, COLS = 16, 12, 12
HEADER_H = 64
COL_W = (W - 2 * MARGIN - (COLS - 1) * GUTTER) / COLS


def col(start: int, span: int) -> tuple[float, float]:
    x = MARGIN + start * (COL_W + GUTTER)
    width = span * COL_W + (span - 1) * GUTTER
    return x, width


def row(top: float, height: float) -> tuple[float, float]:
    return HEADER_H + MARGIN + top, height


# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
INK = "#16211C"
MUTED = "#5D6B64"
LINE = "#DFE5E1"
ACCENT = "#0B6E4F"
ACCENT_DARK = "#08512F"
GOLD = "#C8922A"
WARN = "#B3341F"
CANVAS = "#FBFCFB"

# Ordered invest -> divest, matching the mart's seven recommendation strings
# and the evidence pack's figures. A report and a report-about-the-report that
# disagree on what red means is a small thing that costs a lot of credibility.
RECOMMENDATION_ORDER = [
    ("Invest - Maintain Leadership", ACCENT_DARK),
    ("Invest - Expand", ACCENT),
    ("Invest - Refurbish", "#4B9B6E"),
    ("Hold", "#9EC7A5"),
    ("Hold - Strategic Coverage", GOLD),
    ("Review", "#D98B4A"),
    ("Divest Candidate", WARN),
]


def theme() -> dict:
    return {
        "name": "Drakens Energy 360",
        "dataColors": [ACCENT, GOLD, "#4B9B6E", "#D98B4A", "#9EC7A5", WARN,
                       ACCENT_DARK, MUTED, "#7FA8B8", "#8E6FA8"],
        "background": CANVAS,
        "foreground": INK,
        "tableAccent": ACCENT,
        "good": ACCENT,
        "neutral": GOLD,
        "bad": WARN,
        "textClasses": {
            "title": {"fontFace": "Segoe UI Semibold", "fontSize": 14,
                      "color": INK},
            "header": {"fontFace": "Segoe UI Semibold", "fontSize": 11,
                       "color": INK},
            "label": {"fontFace": "Segoe UI", "fontSize": 9, "color": MUTED},
            "callout": {"fontFace": "Segoe UI Light", "fontSize": 30,
                        "color": INK},
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{"show": True, "color": {"solid":
                                                            {"color": "#FFFFFF"}},
                                    "transparency": 0}],
                    "border": [{"show": True, "color": {"solid":
                                                        {"color": LINE}},
                                "radius": 6}],
                    "title": [{"show": True, "fontColor": {"solid":
                                                           {"color": INK}},
                               "fontSize": 11, "alignment": "left"}],
                    "visualHeader": [{"show": False}],
                }
            }
        },
    }


# --------------------------------------------------------------------------
# Field references
# --------------------------------------------------------------------------
def measure(table: str, name: str) -> dict:
    return {
        "field": {"Measure": {
            "Expression": {"SourceRef": {"Entity": table}},
            "Property": name}},
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": name,
    }


def column(table: str, name: str) -> dict:
    return {
        "field": {"Column": {
            "Expression": {"SourceRef": {"Entity": table}},
            "Property": name}},
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": name,
    }


def hierarchy(table: str, *levels: str) -> list[dict]:
    """A drill path, expressed as ordered projections on one axis."""
    return [column(table, level) for level in levels]


# --------------------------------------------------------------------------
# Visual builders
# --------------------------------------------------------------------------
_counter = {"n": 0}


def _name(prefix: str) -> str:
    _counter["n"] += 1
    return f"{prefix}{_counter['n']:03d}"


def visual(kind: str, x: float, y: float, width: float, height: float,
           query: dict | None = None, objects: dict | None = None,
           title: str | None = None, z: int | None = None) -> dict:
    _counter["n"] += 1
    obj = dict(objects or {})
    if title is not None:
        obj["title"] = [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
        }}]
    body: dict = {"visualType": kind}
    if query:
        body["query"] = {"queryState": query}
    if obj:
        body["objects"] = obj
    body["drillFilterOtherVisuals"] = True
    return {
        "$schema": f"{SCHEMA}/visualContainer/1.0.0/schema.json",
        "name": f"v{_counter['n']:04d}",
        "position": {"x": round(x, 1), "y": round(y, 1),
                     "width": round(width, 1), "height": round(height, 1),
                     "z": z if z is not None else _counter["n"],
                     "tabOrder": _counter["n"]},
        "visual": body,
    }


def literal(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def text_box(x, y, width, height, runs: list[tuple[str, dict]]) -> dict:
    paragraphs = [{
        "textRuns": [
            {"value": text, "textStyle": style} for text, style in runs
        ]
    }]
    return visual("textbox", x, y, width, height, objects={
        "general": [{"properties": {"paragraphs": paragraphs}}],
    })


def card(x, y, width, height, table, name, title) -> dict:
    return visual(
        "card", x, y, width, height,
        query={"Values": {"projections": [measure(table, name)]}},
        objects={
            "labels": [{"properties": {"fontSize": literal("26D"),
                                       "color": {"solid": {"color":
                                                           literal(f"'{INK}'")}}}}],
            "categoryLabels": [{"properties": {"fontSize": literal("9D")}}],
        },
        title=title)


def kpi_row(specs: list[tuple[str, str, str]], y: float,
            height: float = 96) -> list[dict]:
    """Cards spread evenly across the full grid width."""
    # Unpacked explicitly. `col()` returns (x, width) and `card()` takes
    # (x, y, width, height), so splatting the tuple silently passes the width
    # as the y coordinate -- which lays every card out at the wrong height and
    # the wrong size, and still writes valid JSON.
    span = COLS // len(specs)
    out = []
    for i, (table, name, title) in enumerate(specs):
        x, width = col(i * span, span)
        out.append(card(x, y, width, height, table, name, title))
    return out


def chart(kind, x, y, width, height, *, category=None, values=None,
          series=None, title=None, objects=None) -> dict:
    query: dict = {}
    if category:
        query["Category"] = {"projections": category}
    if values:
        query["Y"] = {"projections": values}
    if series:
        query["Series"] = {"projections": series}
    return visual(kind, x, y, width, height, query=query, title=title,
                  objects=objects)


def map_visual(x, y, width, height, *, latitude, longitude, size=None,
               legend=None, tooltips=None, title=None) -> dict:
    query = {
        "Y": {"projections": [latitude]},
        "X": {"projections": [longitude]},
    }
    if size:
        query["Size"] = {"projections": [size]}
    if legend:
        query["Category"] = {"projections": [legend]}
    if tooltips:
        query["Tooltips"] = {"projections": tooltips}
    return visual(
        "azureMap", x, y, width, height, query=query, title=title,
        objects={
            # Bubbles, not a filled map: the fact is per site, and a filled
            # map would force it up to a province and throw away the reason
            # the page exists.
            "mapControl": [{"properties": {
                "autoZoom": literal("true"),
                "style": literal("'grayscale_light'"),
            }}],
            "bubbleLayer": [{"properties": {
                "show": literal("true"),
                "size": literal("14D"),
                "transparency": literal("20D"),
            }}],
        })


def slicer(x, y, width, height, field, title, *, mode="Dropdown") -> dict:
    return visual(
        "slicer", x, y, width, height,
        query={"Values": {"projections": [field]}},
        objects={"general": [{"properties": {"mode": literal(f"'{mode}'")}}]},
        title=title)


def table_visual(x, y, width, height, projections, title) -> dict:
    return visual("tableEx", x, y, width, height,
                  query={"Values": {"projections": projections}}, title=title)


def matrix(x, y, width, height, *, rows, columns, values, title) -> dict:
    return visual("pivotTable", x, y, width, height, query={
        "Rows": {"projections": rows},
        "Columns": {"projections": columns},
        "Values": {"projections": values},
    }, title=title)


def header(page_title: str, subtitle: str) -> list[dict]:
    """A consistent title band, so pages are recognisable as one report."""
    return [
        visual("shape", 0, 0, W, HEADER_H, objects={
            "shape": [{"properties": {"tileShape": literal("'rectangle'")}}],
            "fill": [{"properties": {
                "show": literal("true"),
                "fillColor": {"solid": {"color": literal(f"'{INK}'")}},
            }}],
        }, z=0),
        text_box(MARGIN, 10, 640, 24, [
            (page_title, {"fontSize": {"value": "15D"},
                          "fontWeight": {"value": "bold"},
                          "color": {"value": "#FFFFFF"},
                          "fontFamily": {"value": "Segoe UI"}}),
        ]),
        text_box(MARGIN, 34, 760, 22, [
            (subtitle, {"fontSize": {"value": "9D"},
                        "color": {"value": "#C9D6CF"},
                        "fontFamily": {"value": "Segoe UI"}}),
        ]),
        text_box(W - 380 - MARGIN, 22, 380, 24, [
            ("Synthetic data. Drakens Energy is a fictional company.",
             {"fontSize": {"value": "8D"}, "color": {"value": "#8FA79B"},
              "fontFamily": {"value": "Segoe UI"}}),
        ]),
    ]


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
def page_executive() -> tuple[str, str, list[dict]]:
    v = header("Executive", "Network performance, one screen, no drill "
                            "required")

    v += kpi_row([
        ("agg_site_daily_fuel", "Fuel Volume (L)", "Fuel volume"),
        ("agg_site_daily_fuel", "Gross Margin", "Gross margin"),
        ("agg_site_daily_fuel", "Gross Margin %", "Margin rate"),
        ("agg_site_daily_fuel", "Trading Sites", "Trading sites"),
    ], y=row(0, 0)[0])

    top = row(112, 0)[0]
    x, width = col(0, 8)
    v.append(chart(
        "lineChart", x, top, width, 236,
        category=[column("dim_date", "Full Date")],
        values=[measure("agg_site_daily_fuel", "Gross Margin"),
                measure("agg_site_daily_fuel", "Fuel Revenue")],
        title="Revenue and margin over time"))

    x, width = col(8, 4)
    v.append(chart(
        "donutChart", x, top, width, 236,
        category=[column("dim_product", "Reporting Line")],
        values=[measure("agg_site_daily_fuel", "Gross Margin")],
        title="Margin by reporting line"))

    bottom = row(364, 0)[0]
    x, width = col(0, 4)
    v.append(chart(
        "barChart", x, bottom, width, 196,
        category=[column("dim_site", "Province")],
        values=[measure("agg_site_daily_fuel", "Margin per Site")],
        title="Margin per site, by province"))

    x, width = col(4, 4)
    v.append(chart(
        "columnChart", x, bottom, width, 196,
        category=[column("dim_date", "Day Name")],
        values=[measure("agg_site_daily_fuel", "Fuel Volume (L)")],
        title="Volume by day of week"))

    x, width = col(8, 4)
    v.append(chart(
        "clusteredColumnChart", x, bottom, width, 196,
        category=[column("dim_site", "Urban Class")],
        values=[measure("agg_site_daily_fuel", "Volume per Site (L)")],
        title="Throughput by location type"))

    return "executive", "Executive", v


def page_network() -> tuple[str, str, list[dict]]:
    v = header("Network", "Every site, what it earns, and what to do with it")

    x, width = col(0, 9)
    y, height = row(0, 432)
    v.append(map_visual(
        x, y, width, height,
        latitude=column("dim_site", "Latitude"),
        longitude=column("dim_site", "Longitude"),
        size=measure("network_investment_scorecard", "Sites Scored"),
        legend=column("network_investment_scorecard",
                      "Investment Recommendation"),
        tooltips=[column("dim_site", "Site Name"),
                  measure("agg_site_daily_fuel", "Gross Margin"),
                  measure("network_investment_scorecard",
                          "Average Investment Score")],
        title="Network by investment recommendation"))

    x, width = col(9, 3)
    v.append(slicer(x, y, width, 92, column("dim_site", "Province"),
                    "Province"))
    v.append(slicer(x, y + 104, width, 92,
                    column("dim_site", "Urban Class"), "Location type"))
    v.append(slicer(x, y + 208, width, 92,
                    column("network_investment_scorecard",
                           "Investment Recommendation"), "Recommendation"))
    v.append(card(x, y + 312, width, 120, "network_investment_scorecard",
                  "Corridor Sites", "Sites on a national route"))

    y2 = row(448, 0)[0]
    x, width = col(0, 5)
    v.append(chart(
        "clusteredBarChart", x, y2, width, 172,
        category=[column("network_investment_scorecard",
                         "Investment Recommendation")],
        values=[measure("network_investment_scorecard", "Sites Scored")],
        title="Sites by recommendation"))

    x, width = col(5, 7)
    v.append(table_visual(x, y2, width, 172, [
        column("dim_site", "Site Name"),
        column("dim_site", "Province"),
        measure("agg_site_daily_fuel", "Fuel Volume (L)"),
        measure("agg_site_daily_fuel", "Gross Margin"),
        measure("network_investment_scorecard", "Average Investment Score"),
    ], "Sites, highest margin first"))
    return "network", "Network", v


def page_site_detail() -> tuple[str, str, list[dict]]:
    """Drill-through target.

    A red bubble on the network page raises one question -- why -- and the
    scorecard answers it, because every component of the score is a named
    column rather than a coefficient. A recommendation that cannot be
    interrogated does not survive a capital meeting.
    """
    v = header("Site detail", "Drill through from any site. Every component "
                              "of the score, not just the score")

    y = row(0, 0)[0]
    v += kpi_row([
        ("agg_site_daily_fuel", "Fuel Volume (L)", "Volume"),
        ("agg_site_daily_fuel", "Gross Margin", "Margin"),
        ("agg_site_daily_fuel", "Margin per Litre (c)", "Margin per litre"),
        ("fct_maintenance_work_orders", "Breakdown Rate %", "Breakdown rate"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 6)
    v.append(chart(
        "lineChart", x, top, width, 220,
        category=[column("dim_date", "Full Date")],
        values=[measure("agg_site_daily_fuel", "Fuel Volume (L)")],
        title="This site's volume over time"))

    x, width = col(6, 6)
    v.append(chart(
        "barChart", x, top, width, 220,
        category=[column("network_investment_scorecard", "Demand Band")],
        values=[measure("network_investment_scorecard",
                        "Average Investment Score")],
        title="Score components"))

    bottom = row(348, 0)[0]
    x, width = col(0, 12)
    v.append(table_visual(x, bottom, width, 212, [
        column("fct_maintenance_work_orders", "Raised Timestamp"),
        column("fct_maintenance_work_orders", "Asset Type"),
        column("fct_maintenance_work_orders", "Criticality"),
        column("fct_maintenance_work_orders", "Maintenance Type"),
        measure("fct_maintenance_work_orders", "Maintenance Cost"),
    ], "Recent work orders at this site"))
    return "site-detail", "Site detail", v


def page_commercial() -> tuple[str, str, list[dict]]:
    v = header("Commercial", "Who buys, on what terms, and how concentrated "
                             "the book is")

    y = row(0, 0)[0]
    v += kpi_row([
        ("fct_commercial_orders", "Commercial Revenue", "Revenue"),
        ("fct_commercial_orders", "Commercial Margin", "Margin"),
        ("fct_commercial_orders", "Unmatched Customer Revenue %",
         "Revenue on an unmatched customer"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 6)
    v.append(chart(
        "clusteredColumnChart", x, top, width, 224,
        category=[column("dim_customer", "Credit Band")],
        values=[measure("fct_commercial_orders", "Commercial Revenue"),
                measure("fct_commercial_orders", "Commercial Margin")],
        title="Revenue and margin by credit band"))

    x, width = col(6, 6)
    v.append(chart(
        "treemap", x, top, width, 224,
        category=[column("dim_customer", "Sector")],
        values=[measure("fct_commercial_orders", "Commercial Revenue")],
        title="Revenue by sector"))

    bottom = row(352, 0)[0]
    x, width = col(0, 12)
    v.append(table_visual(x, bottom, width, 208, [
        column("dim_customer", "Customer Name"),
        column("dim_customer", "Sector"),
        column("dim_customer", "Credit Band"),
        measure("fct_commercial_orders", "Commercial Revenue"),
        measure("fct_commercial_orders", "Commercial Margin"),
    ], "Customers by revenue"))
    return "commercial", "Commercial", v


def page_supply() -> tuple[str, str, list[dict]]:
    v = header("Supply and distribution",
               "OTIF is a single number until you break it out, and then it "
               "tells you which fix to make")

    y = row(0, 0)[0]
    v += kpi_row([
        ("fct_deliveries", "Deliveries", "Deliveries"),
        ("fct_deliveries", "OTIF %", "On time and in full"),
        ("fct_deliveries", "Average Delay (min)", "Average delay"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 6)
    v.append(chart(
        "barChart", x, top, width, 224,
        category=[column("fct_deliveries", "Province")],
        values=[measure("fct_deliveries", "OTIF %")],
        title="OTIF by province"))

    x, width = col(6, 6)
    v.append(chart(
        "columnChart", x, top, width, 224,
        category=[column("fct_deliveries", "Punctuality Band")],
        values=[measure("fct_deliveries", "Deliveries")],
        title="Deliveries by punctuality band"))

    bottom = row(352, 0)[0]
    x, width = col(0, 7)
    v.append(chart(
        "lineChart", x, bottom, width, 208,
        category=[column("dim_date", "Full Date")],
        values=[measure("fct_deliveries", "OTIF %")],
        title="OTIF over time"))

    x, width = col(7, 5)
    v.append(chart(
        "scatterChart", x, bottom, width, 208,
        category=[column("fct_deliveries", "Route ID")],
        values=[measure("fct_deliveries", "Average Delay (min)"),
                measure("fct_deliveries", "Deliveries")],
        title="Delay against volume, by route"))
    return "supply", "Supply and distribution", v


def page_assets() -> tuple[str, str, list[dict]]:
    v = header("Assets and reliability",
               "What breaks, how old it was, and what the downtime cost")

    y = row(0, 0)[0]
    v += kpi_row([
        ("fct_maintenance_work_orders", "Work Orders", "Work orders"),
        ("fct_maintenance_work_orders", "Breakdown Rate %", "Unplanned"),
        ("fct_maintenance_work_orders", "Maintenance Cost", "Maintenance cost"),
        ("network_investment_scorecard", "Downtime Hours", "Downtime"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 5)
    v.append(chart(
        "columnChart", x, top, width, 224,
        category=[column("fct_maintenance_work_orders", "Asset Age Band")],
        values=[measure("fct_maintenance_work_orders", "Breakdown Rate %")],
        title="Breakdown rate rises with age"))

    x, width = col(5, 7)
    v.append(matrix(
        x, top, width, 224,
        rows=[column("fct_maintenance_work_orders", "Asset Type")],
        columns=[column("fct_maintenance_work_orders", "Criticality")],
        values=[measure("fct_maintenance_work_orders", "Breakdown Rate %")],
        title="Breakdown rate by asset type and criticality"))

    bottom = row(352, 0)[0]
    x, width = col(0, 6)
    v.append(chart(
        "lineChart", x, bottom, width, 208,
        category=[column("dim_date", "Full Date")],
        values=[measure("fct_maintenance_work_orders", "Maintenance Cost")],
        title="Maintenance cost over time"))

    x, width = col(6, 6)
    v.append(chart(
        "barChart", x, bottom, width, 208,
        category=[column("fct_maintenance_work_orders", "Failure Mode")],
        values=[measure("fct_maintenance_work_orders", "Work Orders")],
        title="Work orders by failure mode"))
    return "assets", "Assets and reliability", v


def page_data_quality() -> tuple[str, str, list[dict]]:
    """The page that makes the cleansing claim checkable.

    Most reports have no equivalent, which is why "the data is clean" is
    usually an assertion. Putting the rejection rate on a page where an
    executive can see it is what turns it into a measurement someone will
    notice moving.
    """
    v = header("Data quality",
               "Every landed row accounted for: cleansed, deduplicated or "
               "quarantined, with the rule that rejected it")

    y = row(0, 0)[0]
    v += kpi_row([
        ("obs_cleansing_summary", "Rows Landed", "Rows landed"),
        ("obs_cleansing_summary", "Quarantine Rate %", "Quarantine rate"),
        ("obs_cleansing_summary", "Duplicate Rate %", "Duplicate rate"),
        ("obs_reconciliation_controls", "Control Pass Rate %",
         "Controls passing"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 7)
    v.append(table_visual(x, top, width, 232, [
        column("obs_cleansing_summary", "Table Name"),
        column("obs_cleansing_summary", "Raw Rows"),
        column("obs_cleansing_summary", "Cleansed Rows"),
        column("obs_cleansing_summary", "Quarantined Rows"),
        column("obs_cleansing_summary", "Quarantine Rate %"),
        column("obs_cleansing_summary", "Quarantine Status"),
    ], "Cleansing outcome, by table"))

    x, width = col(7, 5)
    v.append(chart(
        "barChart", x, top, width, 232,
        category=[column("obs_quarantine_reasons", "Failed Rule")],
        values=[column("obs_quarantine_reasons", "Failure Count")],
        title="Why rows were rejected"))

    bottom = row(360, 0)[0]
    x, width = col(0, 12)
    v.append(table_visual(x, bottom, width, 200, [
        column("obs_reconciliation_controls", "Control Code"),
        column("obs_reconciliation_controls", "Control Description"),
        column("obs_reconciliation_controls", "Control Owner"),
        column("obs_reconciliation_controls", "Variance %"),
        column("obs_reconciliation_controls", "Is Passing"),
    ], "Reconciliation controls: a wrong number is worse than a late one"))
    return "data-quality", "Data quality", v


PAGES = [page_executive, page_network, page_site_detail, page_commercial,
         page_supply, page_assets, page_data_quality]


# --------------------------------------------------------------------------
# Verification against the model
# --------------------------------------------------------------------------
def model_fields() -> dict[str, set[str]]:
    """Every table, column and measure the TMDL actually defines.

    A report is a set of promises about a model. Checking them here means a
    renamed column fails at generation with the field named, rather than in
    Desktop with a visual that silently renders blank -- which is how a broken
    report survives review.
    """
    fields: dict[str, set[str]] = {}
    tables_dir = MODEL_DIR / "definition" / "tables"
    if not tables_dir.exists():
        return fields
    for path in sorted(tables_dir.glob("*.tmdl")):
        table = path.stem
        text = path.read_text(encoding="utf-8")
        names = set(re.findall(r"^\tcolumn '([^']+)'", text, re.M))
        names |= set(re.findall(r"^\tmeasure '([^']+)'", text, re.M))
        fields[table] = names
    return fields


def check_layout(pages) -> list[str]:
    """Geometry a reader would notice and a JSON schema would not.

    Every mistake this catches produces a perfectly valid file: a visual
    hanging off the canvas, two visuals overlapping, a card too small to show
    its own number. Power BI renders all of them without complaint, so the
    only way they surface is someone opening the report and seeing it look
    wrong -- which is exactly the review this project is trying not to depend
    on.
    """
    problems: list[str] = []
    for _, display, visuals in pages:
        boxes = []
        for vis in visuals:
            pos = vis["position"]
            x, y = pos["x"], pos["y"]
            w, h = pos["width"], pos["height"]
            kind = vis["visual"]["visualType"]

            if x < 0 or y < 0 or x + w > W + 0.5 or y + h > H + 0.5:
                problems.append(
                    f"{display}: {kind} at ({x:.0f},{y:.0f}) size {w:.0f}x"
                    f"{h:.0f} falls outside the {W}x{H} canvas")
            if kind not in ("shape", "textbox") and (w < 80 or h < 60):
                problems.append(
                    f"{display}: {kind} is {w:.0f}x{h:.0f}, too small to read")
            boxes.append((kind, x, y, w, h))

        # Overlap, ignoring the header band and its text, which are layered
        # deliberately.
        content = [b for b in boxes if b[0] not in ("shape", "textbox")]
        for i, (k1, x1, y1, w1, h1) in enumerate(content):
            for k2, x2, y2, w2, h2 in content[i + 1:]:
                if (x1 < x2 + w2 - 1 and x2 < x1 + w1 - 1
                        and y1 < y2 + h2 - 1 and y2 < y1 + h1 - 1):
                    problems.append(
                        f"{display}: {k1} and {k2} overlap")
    return problems


def check_pages(pages) -> list[str]:
    fields = model_fields()
    if not fields:
        return ["semantic model not generated; run "
                "scripts/generate_powerbi_model.py first"]

    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for _, display, visuals in pages:
        for vis in visuals:
            query = vis["visual"].get("query", {}).get("queryState", {})
            for role in query.values():
                for projection in role.get("projections", []):
                    ref = projection["field"]
                    kind = "Measure" if "Measure" in ref else "Column"
                    entity = ref[kind]["Expression"]["SourceRef"]["Entity"]
                    prop = ref[kind]["Property"]
                    if (entity, prop) in seen:
                        continue
                    seen.add((entity, prop))
                    if entity not in fields:
                        problems.append(
                            f"{display}: table '{entity}' is not in the model")
                    elif prop not in fields[entity]:
                        problems.append(
                            f"{display}: {entity}[{prop}] is not in the model")
    return problems


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def write(pages) -> None:
    if DEFN.exists():
        shutil.rmtree(DEFN)
    (DEFN / "pages").mkdir(parents=True)

    # A Report folder must not contain both formats. An earlier version of the
    # model generator left a legacy `report.json` beside the PBIR `definition`
    # folder, which is two reports in one place and no way for Desktop to know
    # which is meant.
    legacy = REPORT_DIR / "report.json"
    if legacy.exists():
        legacy.unlink()

    (REPORT_DIR / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json",
        "version": "1.0",
        "datasetReference": {
            "byPath": {"path": f"../{PROJECT}.SemanticModel"},
        },
    }, indent=2), encoding="utf-8")

    (DEFN / "report.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/report/2.0.0/schema.json",
        "themeCollection": {"customTheme": {"name": "Drakens Energy 360",
                                            "reportThemeType": "Custom"}},
        "layoutOptimization": "None",
        "resourcePackages": [{
            "name": "SharedResources",
            "type": "SharedResources",
            "items": [{"name": "Drakens Energy 360", "path":
                       "BaseThemes/DrakensEnergy360.json", "type": "BaseTheme"}],
        }],
    }, indent=2), encoding="utf-8")

    theme_dir = (REPORT_DIR / "StaticResources" / "SharedResources"
                 / "BaseThemes")
    theme_dir.mkdir(parents=True, exist_ok=True)
    (theme_dir / "DrakensEnergy360.json").write_text(
        json.dumps(theme(), indent=2), encoding="utf-8")

    (DEFN / "pages" / "pages.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [name for name, _, _ in pages],
        "activePageName": pages[0][0],
    }, indent=2), encoding="utf-8")

    for name, display, visuals in pages:
        page_dir = DEFN / "pages" / name
        (page_dir / "visuals").mkdir(parents=True)
        (page_dir / "page.json").write_text(json.dumps({
            "$schema": f"{SCHEMA}/page/1.0.0/schema.json",
            "name": name,
            "displayName": display,
            "displayOption": "FitToPage",
            "height": H,
            "width": W,
        }, indent=2), encoding="utf-8")
        for vis in visuals:
            vis_dir = page_dir / "visuals" / vis["name"]
            vis_dir.mkdir(parents=True)
            (vis_dir / "visual.json").write_text(
                json.dumps(vis, indent=2), encoding="utf-8")

    (REPORT_DIR / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId":
                   "00000000-0000-0000-0000-000000000002"},
    }, indent=2), encoding="utf-8")

    (PBI / f"{PROJECT}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify field references and write nothing")
    args = ap.parse_args()

    pages = [fn() for fn in PAGES]
    problems = check_pages(pages) + check_layout(pages)

    if problems:
        print(f"{len(problems)} problem(s) found:")
        for problem in problems:
            print(f"  {problem}")
        if args.check:
            return 1
        print("  refusing to write a report that cannot bind")
        return 1

    if args.check:
        n_visuals = sum(len(v) for _, _, v in pages)
        print(f"{len(pages)} pages, {n_visuals} visuals: every field resolves "
              "against the model and the layout is clean")
        return 0

    write(pages)
    # Written, then counted from disk. The report is generated by one script
    # and the model by another, and the model's cleanup once deleted this
    # entire folder -- so the check that matters is what survived, not what
    # was intended.
    on_disk = len(list((DEFN / "pages").rglob("visual.json")))
    n_visuals = sum(len(v) for _, _, v in pages)
    if on_disk != n_visuals:
        print(f"  WARNING: wrote {n_visuals} visuals but {on_disk} are on disk")
    print(f"wrote {PROJECT}.Report")
    print(f"  {len(pages)} pages, {n_visuals} visuals, 1 theme")
    for _, display, visuals in pages:
        print(f"    {display:28} {len(visuals):>2} visuals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
