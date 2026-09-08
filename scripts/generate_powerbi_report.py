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
import hashlib
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

# Which on-disk report format to write; set by --format.
#
# PBIR -- the folder-per-visual layout under `definition/` -- is the format
# worth reading in a diff, and the one this generator was written for. It is
# also a preview feature. A Desktop with that preview switched off does not
# refuse a PBIR report: it opens the project, loads the semantic model, and
# shows a single empty page. That is indistinguishable from a generator that
# produced nothing, which is how 79 visuals can be on disk and none on screen.
#
# So the default is the legacy single `report.json`, which every build of
# Desktop has always read. A portfolio artifact has to open on a machine whose
# settings nobody controls, and that outranks the nicer diff.
FORMAT = "legacy"

# Canvas. 1280x720 is the 16:9 default and the size every Power BI Service
# viewport is tuned for; a custom canvas looks deliberate in Desktop and
# letterboxed everywhere else.
W, H = 1280, 720

# A 12-column grid with a 16px gutter, so visuals line up without anyone
# nudging pixels. `col()` and `row()` turn grid units into the absolute
# coordinates PBIR wants.
MARGIN, GUTTER, COLS = 16, 12, 12
# 92, not 64. A 16pt title and a 10pt subtitle need about 70px of type plus
# the padding a textbox adds on its own; at 64 the title lost its ascender to
# the top of the band and the subtitle lost its descender to the bottom, and
# both looked like a font-size problem rather than a box-height one.
HEADER_H = 92
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
# The page sits on a tint and the tiles stay white, so each card reads as a
# raised surface. White tiles on a white page is why a report looks flat no
# matter how good the numbers are.
PAGE_BG = "#EEF2EF"
WALLPAPER = "#E4EAE6"
CARD_RULE = ACCENT

# The order single-series charts cycle through. Neighbours differ in hue as
# well as lightness, because a palette that varies only lightness reads as one
# colour in a screenshot and as nothing at all to a colour-blind reader.
#
# WARN is deliberately absent. Red is not a spare hue: a bar chart of OTIF by
# province came out entirely red purely because it was fourth in the rotation,
# which tells the reader those provinces are failing. Red is reserved for
# measures that are actually bad, and is applied by name.
ROTATION = ["#0B6E4F", "#2E6F8E", "#C8922A", "#4B9B6E", "#6E5C9E", "#3E8E7E",
            "#A8703C"]

# Text that sits on the dark header band. Checked, not assumed -- see
# check_contrast.
BAND_TEXT = "#FFFFFF"
BAND_SUBTLE = "#CFDCD5"
BAND_FAINT = "#AFC3B8"

# KPI cards carry a tint rather than plain white, so a row of numbers reads as
# a band of its own against the page. Kept very light: the callout on it is
# INK, and the pair has to pass the same contrast gate as everything else.
CARD_BG = "#F7FAF8"
# The KPI band sits a shade deeper than the rest, so the eye
# lands on the numbers first without needing a border to say so.
KPI_BG = "#EAF1EC"

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
            "title": {"fontFace": "Segoe UI Semibold", "fontSize": 15,
                      "color": INK},
            "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12,
                       "color": INK},
            "label": {"fontFace": "Segoe UI", "fontSize": 11, "color": MUTED},
            "callout": {"fontFace": "Segoe UI Light", "fontSize": 34,
                        "color": INK},
        },
        "visualStyles": {
            "*": {
                "*": {
                    # Every tile, not only the KPI cards. Half the page in
                    # white and half in a tint reads as two designs sharing a
                    # canvas; one surface colour throughout is what makes the
                    # page look composed rather than assembled.
                    "background": [{"show": True,
                                    "color": {"solid": {"color": CARD_BG}},
                                    "transparency": 0}],
                    "border": [{"show": True, "color": {"solid":
                                                        {"color": LINE}},
                                "radius": 8}],
                    "dropShadow": [{"show": True, "position": "Outer",
                                    "preset": "BottomRight",
                                    "color": {"solid": {"color": "#0B2318"}},
                                    "transparency": 88, "blur": 8}],
                    "title": [{"show": True, "fontColor": {"solid":
                                                           {"color": INK}},
                               "fontSize": 13, "alignment": "left",
                               "titleWrap": True}],
                    "visualHeader": [{"show": False}],
                    "labels": [{"color": {"solid": {"color": MUTED}},
                                "fontSize": 11}],
                    "categoryAxis": [{"showAxisTitle": False,
                                      "labelColor": {"solid":
                                                     {"color": MUTED}},
                                      "fontSize": 11,
                                      "gridlineShow": False}],
                    "valueAxis": [{"showAxisTitle": False,
                                   "labelColor": {"solid": {"color": MUTED}},
                                   "fontSize": 11,
                                   "gridlineColor": {"solid":
                                                     {"color": LINE}},
                                   "gridlineStyle": "dotted"}],
                    "legend": [{"position": "TopLeft", "showTitle": False,
                                "labelColor": {"solid": {"color": MUTED}},
                                "fontSize": 11}],
                },
            },
            "card": {
                "*": {
                    "background": [{"show": True,
                                    "color": {"solid": {"color": CARD_BG}},
                                    "transparency": 0}],
                    # The callout is the number people read from across a
                    # room; the label under it is the only thing that says
                    # what the number is, so it stays legible rather than
                    # shrinking to a caption.
                    "labels": [{"color": {"solid": {"color": INK}},
                                "fontSize": 32,
                                "fontFamily": "Segoe UI Light"}],
                    "categoryLabels": [{"color": {"solid": {"color": MUTED}},
                                        "fontSize": 11}],
                },
            },
            "tableEx": {
                "*": {
                    "values": [{"fontSize": 11}],
                    "columnHeaders": [{"fontSize": 11,
                                       "fontColor": {"solid":
                                                     {"color": INK}}}],
                    "total": [{"fontSize": 11}],
                },
            },
            "pivotTable": {
                "*": {
                    "values": [{"fontSize": 11}],
                    "columnHeaders": [{"fontSize": 11}],
                    "rowHeaders": [{"fontSize": 11}],
                },
            },
            "slicer": {
                "*": {
                    "items": [{"fontSize": 11}],
                    "header": [{"fontSize": 11}],
                },
            },
            "textbox": {
                "*": {
                    # Header text sits on the dark band. A textbox that keeps
                    # the default white tile paints over the band and hides
                    # white type on white -- which is exactly how the title
                    # band rendered as two blank rectangles.
                    "background": [{"show": False}],
                    "border": [{"show": False}],
                    "dropShadow": [{"show": False}],
                },
            },
            "shape": {
                "*": {
                    "background": [{"show": False}],
                    "border": [{"show": False}],
                    "dropShadow": [{"show": False}],
                },
            },
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


# Data roles are per visual type, and a projection on a role the visual does
# not have is not an error -- the visual simply draws nothing. A treemap took
# Category/Y like every bar chart in this file and rendered an empty tile.
ROLES = {
    "treemap":       {"category": "Group",    "values": "Values"},
    "pieChart":      {"category": "Category", "values": "Y"},
    "donutChart":    {"category": "Category", "values": "Y"},
    "funnel":        {"category": "Category", "values": "Y"},
    "gauge":         {"category": None,       "values": "Y"},
    "waterfallChart": {"category": "Category", "values": "Y"},
}
DEFAULT_ROLES = {"category": "Category", "values": "Y"}


def chart(kind, x, y, width, height, *, category=None, values=None,
          series=None, title=None, objects=None, color=None) -> dict:
    roles = ROLES.get(kind, DEFAULT_ROLES)
    query: dict = {}
    if category and roles["category"]:
        query[roles["category"]] = {"projections": category}
    if values:
        query[roles["values"]] = {"projections": values}
    if series:
        query["Series"] = {"projections": series}
    obj = dict(objects or {})
    if color is None and not series:
        # Rotate the palette rather than letting every single-series chart
        # take dataColors[0]. Deterministic, so a regenerated report is the
        # same report; varied, so a page of seven charts is not seven shades
        # of one green.
        color = ROTATION[_counter["n"] % len(ROTATION)]
    if color and not series:
        # A single-series chart takes dataColors[0] for every visual on the
        # page, so seven charts come out in seven shades of the same green.
        # Naming the colour per chart is what makes a page readable at a
        # glance instead of merely tidy.
        obj["dataPoint"] = [{"properties": {
            "fill": {"solid": {"color": literal(f"'{color}'")}}}}]
    return visual(kind, x, y, width, height, query=query, title=title,
                  objects=obj or None)


def combo(x, y, width, height, *, category, columns, line, title) -> dict:
    """Columns on one scale, a line on its own.

    Revenue and margin were plotted as two lines on a shared axis. Revenue is
    an order of magnitude larger, so margin rendered as a flat trace along the
    bottom -- a chart that technically contained the number and showed nothing
    about it. A rate belongs on its own axis.
    """
    return visual(
        "lineClusteredColumnComboChart", x, y, width, height,
        query={
            "Category": {"projections": category},
            "Y": {"projections": columns},
            "Y2": {"projections": line},
        },
        title=title,
        objects={
            "dataPoint": [{"properties": {
                "fill": {"solid": {"color": literal(f"'{ACCENT}'")}}}}],
            "y2Axis": [{"properties": {"show": literal("true")}}],
        })


def scatter(x, y, width, height, *, detail, x_measure, y_measure,
            size=None, legend=None, title=None) -> dict:
    """A scatter, which needs its axes named separately.

    Two measures stacked on the Y role is a valid clustered chart and an
    invalid scatter: Power BI asks for x- and y-axis pairs and refuses to
    draw. The roles are X and Y, and the category is Details, not Category.
    """
    # The details role is called Category. Named "Details" -- which is its
    # label in the field well -- every row aggregated into a single point, and
    # the chart drew one dot where 618 routes should be.
    query = {
        "Category": {"projections": [detail]},
        "X": {"projections": [x_measure]},
        "Y": {"projections": [y_measure]},
    }
    if size:
        query["Size"] = {"projections": [size]}
    if legend:
        query["Series"] = {"projections": [legend]}
    return visual("scatterChart", x, y, width, height, query=query,
                  title=title, objects={
                      "dataPoint": [{"properties": {
                          "fill": {"solid": {"color": literal(f"'{GOLD}'")}},
                      }}],
                  })


def map_visual(x, y, width, height, *, latitude, longitude, size=None,
               legend=None, tooltips=None, title=None) -> dict:
    query = {
        "Latitude": {"projections": [latitude]},
        "Longitude": {"projections": [longitude]},
    }
    if size:
        query["Size"] = {"projections": [size]}
    if legend:
        query["Category"] = {"projections": [legend]}
    if tooltips:
        query["Tooltips"] = {"projections": tooltips}
    # The built-in map, not azureMap. Azure Maps renders a sign-in prompt
    # where the map should be unless the viewer is signed in to a tenant that
    # allows it, which turns the one visual the network story depends on into
    # a login screen on someone else's machine.
    return visual(
        "map", x, y, width, height, query=query, title=title,
        objects={
            # Bubbles, not a filled map: the fact is per site, and a filled
            # map would force it up to a province and throw away the reason
            # the page exists.
            "mapControls": [{"properties": {"autoZoom": literal("true")}}],
            "mapStyles": [{"properties": {"mapStyle": literal("'road'")}}],
            "bubbles": [{"properties": {"bubbleSize": literal("-20D")}}],
            "dataPoint": [{"properties": {
                "defaultColor": {"solid": {"color": literal(f"'{ACCENT}'")}},
            }}],
        })


def slicer(x, y, width, height, field, title, *, mode="Dropdown") -> dict:
    return visual(
        "slicer", x, y, width, height,
        query={"Values": {"projections": [field]}},
        objects={"general": [{"properties": {"mode": literal(f"'{mode}'")}}]},
        title=title)


def table_visual(x, y, width, height, projections, title, *,
                 order_by=None, descending=True) -> dict:
    """A grid, optionally sorted by one of its own fields.

    Without an explicit order, Power BI sorts by the first column. A table
    titled "Customers by revenue" then opens sorted by customer name -- and
    the twelve customers whose name is an empty string sort to the very top,
    so the visual's entire first screen is blank rows. The title was a promise
    the query never made.
    """
    vis = visual("tableEx", x, y, width, height,
                 query={"Values": {"projections": projections}}, title=title)
    if order_by is not None:
        vis["visual"]["orderBy"] = {"field": order_by,
                                    "descending": bool(descending)}
    return vis


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
        # 8px down and 30 tall for a 16pt run. At 24 tall the ascender sat
        # above the box and the page title rendered with its top sliced off.
        text_box(MARGIN, 12, 700, 38, [
            (page_title, {"fontSize": {"value": "20D"},
                          "fontWeight": {"value": "bold"},
                          "color": {"value": BAND_TEXT},
                          "fontFamily": {"value": "Segoe UI"}}),
        ]),
        text_box(MARGIN, 52, 820, 28, [
            (subtitle, {"fontSize": {"value": "11D"},
                        "color": {"value": BAND_SUBTLE},
                        "fontFamily": {"value": "Segoe UI"}}),
        ]),
        text_box(W - 420 - MARGIN, 34, 420, 26, [
            ("Synthetic data. Drakens Energy is a fictional company.",
             {"fontSize": {"value": "9D"}, "color": {"value": BAND_FAINT},
              "fontFamily": {"value": "Segoe UI"}}),
        ]),
    ]


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
def page_executive() -> tuple[str, str, list[dict]]:
    v = header("Executive", "Network performance, one screen, no drill "
                            "required")

    # Six, so growth sits next to the level it applies to. A page that shows
    # only totals asks the reader to remember last year.
    v += kpi_row([
        ("agg_site_daily_fuel", "Fuel Volume (L)", "Fuel volume"),
        ("agg_site_daily_fuel", "Fuel Volume YoY %", "Volume vs last year"),
        ("agg_site_daily_fuel", "Gross Margin", "Gross margin"),
        ("agg_site_daily_fuel", "Gross Margin YoY %", "Margin vs last year"),
        ("agg_site_daily_fuel", "Gross Margin %", "Margin rate"),
        ("agg_site_daily_fuel", "Trading Sites", "Trading sites"),
    ], y=row(0, 0)[0])

    top = row(112, 0)[0]
    x, width = col(0, 8)
    v.append(combo(
        x, top, width, 236,
        # Monthly, not daily. 974 daily points in 700px is a texture, not a
        # trend; the month is the grain this number is actually reviewed at.
        category=[column("dim_date", "Year Month")],
        columns=[measure("agg_site_daily_fuel", "Fuel Revenue")],
        line=[measure("agg_site_daily_fuel", "Gross Margin %")],
        title="Revenue by month, with margin rate"))

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
        # Country, not province. Province is null for every site outside
        # South Africa because those sites do not have one, so a chart
        # grouped by province silently covers 250 of 587 sites and 36% of
        # the margin while being captioned as the network.
        category=[column("dim_site", "Country Code")],
        values=[measure("agg_site_daily_fuel", "Margin per Site")],
        title="Margin per site, by market"))

    x, width = col(4, 4)
    v.append(chart(
        "columnChart", x, bottom, width, 196,
        category=[column("dim_date", "Day Name")],
        # The average of a weekday, not its total. Totals compare seven bars
        # whose day counts differ across a part-year window, so the tallest
        # bar can be the one that simply occurred most often.
        values=[measure("agg_site_daily_fuel", "Average Daily Volume (L)")],
        title="Average volume by day of week"))

    x, width = col(8, 4)
    v.append(chart(
        "clusteredColumnChart", x, bottom, width, 196,
        category=[column("dim_site", "Urban Class")],
        values=[measure("agg_site_daily_fuel", "Volume per Site (L)")],
        title="Throughput by location type"))

    return "executive", "Executive", v


def page_network() -> tuple[str, str, list[dict]]:
    v = header("Network", "Every site, what it earns, and what to do with it")

    # Six columns, not nine. The estate runs from Cape Verde to Mauritius and
    # from Morocco to Lesotho -- taller than it is wide -- so a 795x432
    # letterbox fitted the points by width and spent the rest on ocean. At
    # 6 columns the frame is roughly square and the bounding box fills it.
    x, width = col(0, 6)
    y, height = row(0, 404)
    # A coordinate scatter, not a basemap visual. Both basemap options failed
    # on a machine nobody controls: Azure Maps renders a sign-in prompt where
    # the map should be, and the built-in map is off unless Global > Security
    # has map visuals enabled -- and when it does draw, its auto-zoom falls
    # back to a world view as soon as a filter leaves it few enough points to
    # be unable to compute an extent, which is exactly when the reader is
    # looking hardest.
    #
    # A scatter on longitude and latitude has none of that. It always renders,
    # it rescales its axes to whatever survives the filter, and it needs no
    # external service. The cost is the coastline, and the coastline was never
    # the point: these are town centroids plus jitter, and what the page is
    # for is where the margin sits relative to everything else.
    # A real basemap here, and the coordinate scatter on the Geography page.
    # The two failure modes are different and so are the two jobs: this map
    # answers "where is the network" and wants a coastline; the scatter
    # answers "which coordinates are wrong" and has to render on any machine.
    # Map visuals require File > Options > Global > Security > Map and Filled
    # Map visuals, which is stated in the README.
    v.append(map_visual(
        x, y, width, height,
        latitude=column("dim_site", "Latitude"),
        longitude=column("dim_site", "Longitude"),
        size=measure("agg_site_daily_fuel", "Gross Margin"),
        legend=column("network_investment_scorecard",
                      "Investment Recommendation"),
        tooltips=[measure("agg_site_daily_fuel", "Fuel Volume (L)")],
        title="Network by investment recommendation"))

    x, width = col(6, 3)
    v.append(chart(
        "clusteredBarChart", x, y, width, 196,
        category=[column("network_investment_scorecard",
                         "Investment Recommendation")],
        values=[measure("network_investment_scorecard", "Sites Scored")],
        title="Sites by recommendation"))
    v.append(card(x, y + 208, width, 92, "network_investment_scorecard",
                  "Corridor Sites", "Sites on a national route"))
    v.append(card(x, y + 312, width, 92, "network_investment_scorecard",
                  "Divest Candidates", "Divest candidates"))

    x, width = col(9, 3)
    v.append(slicer(x, y, width, 124, column("dim_site", "Country Code"),
                    "Market"))
    v.append(slicer(x, y + 136, width, 124,
                    column("dim_site", "Urban Class"), "Location type"))
    v.append(slicer(x, y + 272, width, 132,
                    column("network_investment_scorecard",
                           "Investment Recommendation"), "Recommendation"))

    y2 = row(420, 0)[0]
    x, width = col(0, 12)
    v.append(table_visual(x, y2, width, 168, [
        column("dim_site", "Site Name"),
        column("dim_site", "Province"),
        measure("agg_site_daily_fuel", "Fuel Volume (L)"),
        measure("agg_site_daily_fuel", "Gross Margin"),
        measure("network_investment_scorecard", "Average Investment Score"),
    ], "Sites, highest margin first",
        order_by=measure("agg_site_daily_fuel", "Gross Margin")))
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
        ("fct_commercial_orders", "Commercial Revenue YoY %",
         "Revenue vs last year"),
        ("fct_commercial_orders", "Average Monthly Commercial Revenue",
         "Average month"),
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
    ], "Customers by revenue",
        order_by=measure("fct_commercial_orders", "Commercial Revenue")))
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
        title="OTIF by province (South Africa)"))

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
    v.append(scatter(
        x, bottom, width, 208,
        detail=column("fct_deliveries", "Route ID"),
        x_measure=measure("fct_deliveries", "Deliveries"),
        y_measure=measure("fct_deliveries", "Average Delay (min)"),
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
        # The model renamed this column because the measure of the same
        # name won the collision; asking for the old name is a field that
        # resolves to the wrong kind of thing.
        column("obs_cleansing_summary", "Quarantine Rate % (row)"),
        column("obs_cleansing_summary", "Quarantine Status"),
    ], "Cleansing outcome, by table"))

    x, width = col(7, 5)
    v.append(chart(
        "barChart", x, top, width, 232,
        category=[column("obs_quarantine_reasons", "Failed Rule")],
        values=[measure("obs_quarantine_reasons", "Rows Rejected")],
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


def page_machine_learning() -> tuple[str, str, list[dict]]:
    """The models, and whether they earned their place.

    A portfolio that shows six trained models and no baselines is showing six
    numbers, not six models. This page leads with how many actually beat the
    thing they have to beat -- three of five scored -- because the two that do
    not are the reason to believe the three that do. Predictive maintenance
    loses to knowing an asset's age, and stock-out risk is chance once the
    leak is removed. Both are on the page.
    """
    v = header("Machine learning",
               "Six models, the baseline each has to beat, and the two that "
               "do not")

    y = row(0, 0)[0]
    v += kpi_row([
        ("obs_ml_performance", "Models", "Models trained"),
        ("obs_ml_performance", "Models Beating Baseline", "Beat baseline"),
        ("obs_ml_performance", "Baseline Beat Rate %", "Of those scored"),
        ("obs_ml_performance", "Best ROC-AUC", "Best ROC-AUC"),
        ("obs_ml_performance", "Training Rows", "Training rows"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 7)
    # Percentage improvement, not raw lift. Raw lift mixes units: the demand
    # forecast's lift is -15.4 in litres of MAE while a classifier's is 0.34
    # of ROC-AUC, and plotting both on one axis renders every classifier as an
    # invisible sliver beside one enormous bar. The chart was arithmetically
    # correct and told the reader nothing.
    v.append(chart(
        "clusteredBarChart", x, top, width, 232,
        category=[column("obs_ml_performance", "Model")],
        values=[measure("obs_ml_performance", "Improvement over Baseline %")],
        title="Improvement over baseline, by model (negative means it lost)"))

    x, width = col(7, 5)
    v.append(chart(
        "donutChart", x, top, width, 232,
        category=[column("obs_ml_performance", "Verdict")],
        values=[measure("obs_ml_performance", "Models")],
        title="Verdicts"))

    bottom = row(360, 0)[0]
    x, width = col(0, 12)
    v.append(table_visual(x, bottom, width, 200, [
        column("obs_ml_performance", "Model"),
        column("obs_ml_performance", "Use Case"),
        column("obs_ml_performance", "Target"),
        column("obs_ml_performance", "Metric Name"),
        column("obs_ml_performance", "Metric Value"),
        column("obs_ml_performance", "Baseline Name"),
        column("obs_ml_performance", "Baseline Value"),
        column("obs_ml_performance", "Verdict"),
    ], "Every model, its baseline, and the verdict"))
    return "machine-learning", "Machine learning", v


def page_products() -> tuple[str, str, list[dict]]:
    """Every reporting line, on the two axes that decide what to stock.

    Volume and margin rate pull in opposite directions across this estate:
    road fuel is most of the litres and the thinnest margin because its price
    is gazetted, while convenience and lubricants are a rounding error in
    litres and where the margin rate actually is. A page that ranked products
    by either one alone would recommend the wrong thing.
    """
    v = header("Products",
               "What each line sells, what it earns, and how fast it is "
               "moving")

    y = row(0, 0)[0]
    v += kpi_row([
        ("fct_retail_fuel_sales", "Retail Litres", "Litres sold"),
        ("fct_retail_fuel_sales", "Retail Revenue", "Revenue"),
        ("fct_retail_fuel_sales", "Retail Margin %", "Margin rate"),
        ("fct_retail_fuel_sales", "Margin (c/L)", "Margin per litre"),
        ("fct_retail_fuel_sales", "Retail Litres YoY %", "Litres vs last year"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 5)
    v.append(chart(
        "barChart", x, top, width, 216,
        category=[column("dim_product", "Reporting Line")],
        values=[measure("fct_retail_fuel_sales", "Retail Litres")],
        title="Volume by reporting line"))

    x, width = col(5, 4)
    v.append(chart(
        "barChart", x, top, width, 216,
        category=[column("dim_product", "Reporting Line")],
        values=[measure("fct_retail_fuel_sales", "Margin (c/L)")],
        title="Margin per litre by line (cents)"))

    x, width = col(9, 3)
    v.append(slicer(x, top, width, 104,
                    column("dim_product", "Reporting Line"), "Reporting line"))
    v.append(slicer(x, top + 116, width, 100,
                    column("dim_product", "Price Regime"), "Price regime"))

    mid = row(344, 0)[0]
    x, width = col(0, 7)
    v.append(combo(
        x, mid, width, 216,
        category=[column("dim_date", "Year Month")],
        columns=[measure("fct_retail_fuel_sales", "Retail Litres")],
        line=[measure("fct_retail_fuel_sales", "Retail Margin %")],
        title="Monthly volume, with margin rate"))

    x, width = col(7, 5)
    # Coverage sits next to the product table on purpose. Five of the nine
    # reporting lines cannot be charted, for three different reasons, and a
    # reader who sees only the four that can will conclude the other five do
    # not exist rather than that the platform cannot yet see them.
    v.append(table_visual(x, mid, width, 100, [
        column("obs_product_coverage", "Reporting Line"),
        column("obs_product_coverage", "Status"),
        column("obs_product_coverage", "Gold Facts"),
    ], "Why some lines are blank: coverage by reporting line"))

    v.append(table_visual(x, mid + 112, width, 104, [
        column("dim_product", "Product Name"),
        measure("fct_retail_fuel_sales", "Retail Litres"),
        measure("fct_retail_fuel_sales", "Litres Share %"),
        measure("fct_retail_fuel_sales", "Margin (c/L)"),
        measure("fct_retail_fuel_sales", "Retail Litres YoY %"),
    ], "Every product, ranked",
        order_by=measure("fct_retail_fuel_sales", "Retail Litres")))
    return "products", "Products", v


def page_petroleum() -> tuple[str, str, list[dict]]:
    """The fuel book on its own, forecast included.

    Petroleum is the business: five grades carry effectively all the litres,
    four of them at a price the state sets monthly. That last fact is why the
    page leads with cents per litre rather than rand margin -- when the price
    is gazetted, the only margin lever left is mix and throughput.

    The forecast is here rather than on the ML page because this is where it
    would be used. Procurement orders a grade, not a network total.
    """
    v = header("Petroleum",
               "Five grades, a gazetted price, and a forecast procurement "
               "can order against")

    y = row(0, 0)[0]
    v += kpi_row([
        ("fct_retail_fuel_sales", "Retail Litres", "Fuel litres"),
        ("fct_retail_fuel_sales", "Margin (c/L)", "Margin per litre"),
        ("fct_retail_fuel_sales", "Average Pump Price", "Average pump price"),
        ("fct_retail_fuel_sales", "Regulated Litres %", "Price-regulated"),
        ("obs_ml_product_performance", "Forecast Improvement %",
         "Forecast beats naive by"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 6)
    v.append(chart(
        "barChart", x, top, width, 212,
        category=[column("fct_retail_fuel_sales", "Fuel Grade")],
        values=[measure("fct_retail_fuel_sales", "Retail Litres")],
        title="Litres by grade"))

    x, width = col(6, 6)
    v.append(chart(
        "clusteredBarChart", x, top, width, 212,
        category=[column("fct_retail_fuel_sales", "Fuel Grade")],
        values=[measure("fct_retail_fuel_sales", "Margin (c/L)")],
        title="Margin per litre by grade (cents)"))

    mid = row(340, 0)[0]
    x, width = col(0, 7)
    # Actual against both the model and the baseline it has to beat. Plotting
    # a forecast without the naive line lets any forecast look competent.
    v.append(chart(
        "lineChart", x, mid, width, 220,
        category=[column("fct_product_demand_forecast", "Full Date")],
        values=[measure("fct_product_demand_forecast", "Actual Litres"),
                measure("fct_product_demand_forecast", "Forecast Litres"),
                measure("fct_product_demand_forecast",
                        "Seasonal-Naive Litres")],
        title="Forecast against actual and seasonal-naive, holdout window"))

    x, width = col(7, 5)
    v.append(table_visual(x, mid, width, 220, [
        column("obs_ml_product_performance", "Product Name"),
        column("obs_ml_product_performance", "Mean Daily Litres"),
        column("obs_ml_product_performance", "Mae"),
        column("obs_ml_product_performance", "Baseline Mae"),
        column("obs_ml_product_performance", "Mae Improvement %"),
        column("obs_ml_product_performance", "Verdict"),
    ], "Forecast accuracy per grade, against seasonal-naive"))
    return "petroleum", "Petroleum", v


def page_geography() -> tuple[str, str, list[dict]]:
    """What the coordinates say, checked against real boundaries.

    Every other quality check in this platform compares a value against a rule
    or another column. This page carries the one check that compares a point
    against a polygon, and it is the only kind capable of catching a record
    that is internally consistent and geographically wrong.

    It found both kinds. Two sites sit across a provincial boundary from the
    province their record claims -- Sasolburg and Vereeniging, on opposite
    banks of the river that *is* the border. Fifteen coastal sites have
    coordinates in the sea, because the generator jitters around a town
    centroid without knowing where the coastline is. Neither would ever fail a
    column-level test.
    """
    v = header("Geography",
               "Coordinates checked against real boundaries, and how close "
               "the network sits to itself")

    y = row(0, 0)[0]
    v += kpi_row([
        ("obs_geo_site_analysis", "Sites Located", "Sites geocoded"),
        ("obs_geo_site_analysis", "Geocoding Pass Rate %", "In the right province"),
        ("obs_geo_site_analysis", "Province Mismatches", "Wrong province"),
        ("obs_geo_site_analysis", "Sites Outside Any Boundary", "In the sea"),
        ("obs_geo_site_analysis", "Overlapping Sites", "Under 1 km apart"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 6)
    # Every field on this visual comes from obs_geo_site_analysis. Mixing a
    # detail column from one table with axis measures from another only works
    # when the relationship filters in that direction, and this one runs the
    # other way -- which put all 586 sites on a single point.
    v.append(scatter(
        x, top, width, 224,
        detail=column("obs_geo_site_analysis", "Site Name"),
        x_measure=measure("obs_geo_site_analysis", "Geo Longitude"),
        y_measure=measure("obs_geo_site_analysis", "Geo Latitude"),
        size=measure("obs_geo_site_analysis", "Average Sites Within 25km"),
        legend=column("obs_geo_site_analysis", "Province Check"),
        title="Every coordinate, coloured by whether it passes the "
              "boundary check"))

    x, width = col(6, 3)
    v.append(chart(
        "barChart", x, top, width, 224,
        category=[column("obs_geo_site_analysis", "Proximity Band")],
        values=[measure("obs_geo_site_analysis", "Sites Located")],
        title="How close is the nearest other site"))

    x, width = col(9, 3)
    v.append(slicer(x, top, width, 108,
                    column("obs_geo_site_analysis", "Province Check"),
                    "Boundary check"))
    v.append(slicer(x, top + 120, width, 104,
                    column("obs_geo_site_analysis", "Proximity Band"),
                    "Proximity"))

    bottom = row(352, 0)[0]
    x, width = col(0, 12)
    v.append(table_visual(x, bottom, width, 200, [
        column("obs_geo_site_analysis", "Site Name"),
        column("obs_geo_site_analysis", "City"),
        column("obs_geo_site_analysis", "Recorded Province"),
        column("obs_geo_site_analysis", "Boundary Province"),
        column("obs_geo_site_analysis", "Province Check"),
        column("obs_geo_site_analysis", "Nearest Site km"),
        column("obs_geo_site_analysis", "Sites Within 5km"),
        column("obs_geo_site_analysis", "Proximity Band"),
    ], "Every site, its boundary check and its neighbours"))
    return "geography", "Geography", v


def page_forecast() -> tuple[str, str, list[dict]]:
    """A year ahead, per product, with the backtest that says whether to
    believe it.

    The model predicts twelve months directly rather than predicting one month
    and feeding its own answer back in, because a recursive forecast compounds
    its error twelve times over and arrives confident and wrong.

    Two things on this page keep it honest. The forward year is plotted
    against the backtest that precedes it, so the reader can see how the model
    did on months it had not seen before trusting months nobody has seen. And
    the per-product table reports the seasonal-naive comparison per line:
    6 of 13 products beat it, and the other 7 are named. On 32 months of
    history a twelve-month forecast is weakly identified, and the products
    where last year is still the better predictor should be forecast that way.
    """
    v = header("Forecast",
               "Twelve months ahead per product, and the backtest that says "
               "which lines to trust")

    y = row(0, 0)[0]
    v += kpi_row([
        ("fct_product_revenue_forecast_12m", "Next 12 Months Revenue",
         "Next 12 months"),
        ("obs_ml_product_forecast_12m", "Products Forecast", "Products"),
        ("obs_ml_product_forecast_12m", "Products Beating Naive (12m)",
         "Beat seasonal-naive"),
        ("obs_ml_product_forecast_12m", "Forecast Improvement % (12m)",
         "Better than naive by"),
        ("fct_product_revenue_forecast_12m", "Backtest Error %",
         "Backtest error"),
    ], y=y)

    top = row(112, 0)[0]
    x, width = col(0, 8)
    # Actual, forecast and naive on one axis: all three are monthly revenue in
    # rand, so this is a comparison rather than a scale error.
    v.append(chart(
        "lineChart", x, top, width, 232,
        category=[column("fct_product_revenue_forecast_12m", "Month Start")],
        values=[measure("fct_product_revenue_forecast_12m", "Actual Revenue"),
                measure("fct_product_revenue_forecast_12m",
                        "Forecast Revenue"),
                measure("fct_product_revenue_forecast_12m",
                        "Seasonal-Naive Revenue")],
        title="Backtest then forecast: actual, model and seasonal-naive"))

    x, width = col(8, 4)
    v.append(slicer(x, top, width, 112,
                    column("dim_product", "Reporting Line"), "Reporting line"))
    v.append(slicer(x, top + 124, width, 108,
                    column("obs_ml_product_forecast_12m", "Verdict"),
                    "Backtest verdict"))

    mid = row(360, 0)[0]
    x, width = col(0, 5)
    v.append(chart(
        "barChart", x, mid, width, 200,
        category=[column("obs_ml_product_forecast_12m", "Product Name")],
        values=[measure("obs_ml_product_forecast_12m",
                        "Forecast Improvement % (12m)")],
        title="Improvement over seasonal-naive, by product"))

    x, width = col(5, 7)
    v.append(table_visual(x, mid, width, 200, [
        column("obs_ml_product_forecast_12m", "Product Name"),
        column("obs_ml_product_forecast_12m", "Reporting Line"),
        column("obs_ml_product_forecast_12m", "Mean Monthly Revenue (R)"),
        column("obs_ml_product_forecast_12m", "Mae (R)"),
        column("obs_ml_product_forecast_12m", "Naive Mae (R)"),
        column("obs_ml_product_forecast_12m", "Improvement %"),
        column("obs_ml_product_forecast_12m", "Verdict"),
    ], "Backtest accuracy per product, against seasonal-naive"))
    return "forecast", "Forecast", v


PAGES = [page_executive, page_network, page_geography, page_site_detail,
         page_products, page_petroleum, page_commercial, page_supply,
         page_assets, page_data_quality, page_forecast,
         page_machine_learning]


# --------------------------------------------------------------------------
# Verification against the model
# --------------------------------------------------------------------------
def model_fields() -> dict[str, set[str]]:
    """Every column and measure the model defines, kept apart by kind.

    Kind matters. A model that renames a column because a measure already
    claimed the name -- `Quarantine Rate %` becoming `Quarantine Rate % (row)`
    -- leaves the name resolving perfectly while meaning something else. A
    check that pools both kinds into one set of names passes that, and Desktop
    then refuses the visual with "fields that need to be fixed".

    A report is a set of promises about a model. Checking them here means a
    renamed column fails at generation with the field named, rather than in
    Desktop with a visual that silently renders blank -- which is how a broken
    report survives review.

    Both model formats are read, because the model generator emits either one
    and this check is worthless if it quietly finds nothing: an empty result
    makes every field reference unverifiable, and unverifiable reads the same
    as correct.
    """
    fields: dict[str, dict[str, set[str]]] = {}

    bim = MODEL_DIR / "model.bim"
    if bim.exists():
        model = json.loads(bim.read_text(encoding="utf-8"))["model"]
        for table in model.get("tables", []):
            columns = table.get("columns", [])
            fields[table["name"]] = {
                "column": {c["name"] for c in columns},
                "measure": {m["name"] for m in table.get("measures", [])},
                # Only these get aggregated implicitly. A text column, or a
                # numeric one the model marks summarizeBy "none" (latitude and
                # longitude, keys, anything pre-averaged), is placed as-is.
                "aggregating": {
                    c["name"] for c in columns
                    if c.get("dataType") in ("int64", "double", "decimal")
                    and c.get("summarizeBy", "none") != "none"
                },
            }
        return fields

    tables_dir = MODEL_DIR / "definition" / "tables"
    if not tables_dir.exists():
        return fields
    for path in sorted(tables_dir.glob("*.tmdl")):
        text = path.read_text(encoding="utf-8")
        fields[path.stem] = {
            "column": set(re.findall(r"^\tcolumn '([^']+)'", text, re.M)),
            "measure": set(re.findall(r"^\tmeasure '([^']+)'", text, re.M)),
            "aggregating": set(),
        }
    return fields


def _luminance(hex_colour: str) -> float:
    """Relative luminance, per WCAG 2.1."""
    value = hex_colour.lstrip("#")
    parts = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in parts]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# Every pair of colours where one is text and the other is what it sits on.
# (description, foreground, background, minimum ratio)
#
# 4.5 is the WCAG AA threshold for body text and 3.0 for text at 18pt or
# above. Checking this at generation time is the difference between a palette
# that was reasoned about and one that happened to look right on the machine
# it was designed on -- the header disclaimer was two shades from unreadable
# and nothing would have said so.
TEXT_ON = [
    ("page title on the header band", BAND_TEXT, INK, 3.0),
    ("page subtitle on the header band", BAND_SUBTLE, INK, 4.5),
    ("synthetic-data disclaimer on the header band", BAND_FAINT, INK, 4.5),
    ("card callout on a card", INK, KPI_BG, 3.0),
    ("card category label on a card", MUTED, KPI_BG, 4.5),
    ("visual title on a tile", INK, CARD_BG, 4.5),
    ("axis and legend labels on a tile", MUTED, CARD_BG, 4.5),
    ("table values on a tile", INK, CARD_BG, 4.5),
]


def check_contrast() -> list[str]:
    problems = []
    for what, fg, bg, minimum in TEXT_ON:
        ratio = contrast_ratio(fg, bg)
        if ratio < minimum:
            problems.append(
                f"contrast: {what} is {ratio:.1f}:1 ({fg} on {bg}), below the "
                f"{minimum}:1 minimum -- it will not be readable")
    # A chart colour is not text, but a data label sits on top of it.
    for colour in ROTATION:
        ratio = contrast_ratio("#FFFFFF", colour)
        if ratio < 3.0 and contrast_ratio(INK, colour) < 3.0:
            problems.append(
                f"contrast: {colour} takes neither white nor dark text "
                f"legibly ({ratio:.1f}:1 white, "
                f"{contrast_ratio(INK, colour):.1f}:1 dark)")
    return problems


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


# Where implicit aggregation actually bites.
#
# The model sets discourageImplicitMeasures, so a summarisable column dropped
# on a chart axis has nothing to aggregate it and the visual refuses to draw.
# Tables and slicers are exempt: they place a column as a column, which is why
# a detail grid of raw columns renders perfectly while a bar chart built the
# same way does not.
AGGREGATING_ROLES = {"Y", "X", "Size"}
PLACES_COLUMNS_AS_IS = {"tableEx", "pivotTable", "slicer"}


def check_pages(pages) -> list[str]:
    fields = model_fields()
    if not fields:
        return ["semantic model not generated; run "
                "scripts/generate_powerbi_model.py first"]

    problems: list[str] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for _, display, visuals in pages:
        for vis in visuals:
            kind_of_visual = vis["visual"]["visualType"]
            query = vis["visual"].get("query", {}).get("queryState", {})
            for role_name, role in query.items():
                for projection in role.get("projections", []):
                    ref = projection["field"]
                    kind = "Measure" if "Measure" in ref else "Column"
                    entity = ref[kind]["Expression"]["SourceRef"]["Entity"]
                    prop = ref[kind]["Property"]
                    want = kind.lower()
                    key = (entity, prop, want, role_name, kind_of_visual)
                    if key in seen:
                        continue
                    seen.add(key)
                    if entity not in fields:
                        problems.append(
                            f"{display}: table '{entity}' is not in the model")
                        continue
                    defined = fields[entity]
                    if prop in defined[want]:
                        if (want == "column"
                                and role_name in AGGREGATING_ROLES
                                and kind_of_visual not in PLACES_COLUMNS_AS_IS
                                and prop in defined["aggregating"]):
                            problems.append(
                                f"{display}: {entity}[{prop}] is a "
                                f"summarisable column on the {role_name} role "
                                f"of a {kind_of_visual}, and the model "
                                f"discourages implicit measures -- it needs a "
                                f"measure")
                        continue
                    other = "measure" if want == "column" else "column"
                    if prop in defined[other]:
                        problems.append(
                            f"{display}: {entity}[{prop}] is a {other}, but "
                            f"the report asks for a {want}")
                    else:
                        problems.append(
                            f"{display}: {entity}[{prop}] is not in the model")
    return problems




# --------------------------------------------------------------------------
# Legacy serialisation
# --------------------------------------------------------------------------
def _section_id(name: str) -> str:
    """A stable 20-hex-character section name.

    Desktop generates these randomly. Deriving them from the page name keeps
    them stable across regenerations, so a re-run produces the same file
    rather than a diff in which every page looks new.
    """
    return hashlib.md5(name.encode()).hexdigest()[:20]


def _prototype_query(projections: list[dict]) -> dict:
    """Build the query a legacy visual carries.

    PBIR lets each projection name its own table inline. The legacy format
    does not: it declares every table once in `From` under a short alias, and
    each `Select` refers to that alias. So the same field reference has to be
    taken apart and rebuilt against a table-to-alias map that only exists once
    all of the visual's projections have been seen.
    """
    aliases: dict[str, str] = {}
    select: list[dict] = []
    seen: set[str] = set()
    for proj in projections:
        field = proj["field"]
        kind = "Measure" if "Measure" in field else "Column"
        body = field[kind]
        table = body["Expression"]["SourceRef"]["Entity"]
        if table not in aliases:
            # a, b, c ... in first-seen order, which is what Desktop itself
            # does, so a regenerated file compares cleanly against a saved one.
            aliases[table] = chr(ord("a") + len(aliases))
        ref = proj["queryRef"]
        if ref in seen:
            continue
        seen.add(ref)
        select.append({
            kind: {"Expression": {"SourceRef": {"Source": aliases[table]}},
                   "Property": body["Property"]},
            "Name": ref,
        })
    frm = [{"Name": alias, "Entity": table, "Type": 0}
           for table, alias in aliases.items()]
    return {"Version": 2, "From": frm, "Select": select}


def _legacy_text(objects: dict) -> dict:
    """Rewrite textbox styling into the plain strings the legacy format wants.

    PBIR wraps every style value -- `{"fontSize": {"value": "15D"}}`. The
    legacy format wants CSS-ish literals -- `{"fontSize": "15pt"}` -- and a
    run whose textStyle it cannot read is not an error: the run is dropped and
    the textbox renders as an empty white rectangle. That is why the title
    band came out as blank tiles with the text apparently missing.
    """
    out = json.loads(json.dumps(objects))
    for entry in out.get("general", []):
        for para in entry.get("properties", {}).get("paragraphs", []):
            for run in para.get("textRuns", []):
                style = run.get("textStyle") or {}
                flat = {}
                for key, value in style.items():
                    if isinstance(value, dict) and "value" in value:
                        value = value["value"]
                    if key == "fontSize" and isinstance(value, str):
                        # "15D" is a DAX-style double literal; CSS wants pt.
                        value = value.rstrip("D") + "pt"
                    flat[key] = value
                run["textStyle"] = flat
    return out


def legacy_container(vis: dict) -> dict:
    """One PBIR visual, rewritten as a legacy visualContainer.

    The position lands twice: once on the container itself and once in a
    `layouts` entry inside the config. Both are read, and a container that
    sets only one of them renders at the origin at default size.
    """
    pos = vis["position"]
    body = vis["visual"]
    state = body.get("query", {}).get("queryState", {})

    projections: dict[str, list[dict]] = {}
    every: list[dict] = []
    for role, spec in state.items():
        items = spec.get("projections", [])
        projections[role] = [{"queryRef": item["queryRef"]} for item in items]
        every.extend(items)

    objects = dict(body.get("objects") or {})
    if body["visualType"] == "textbox":
        objects = _legacy_text(objects)
    # `title` is a container property in the legacy format, not a visual one.
    # Left in `objects` it is dropped without complaint and every visual on
    # every page renders untitled.
    vc_objects = {}
    if "title" in objects:
        vc_objects["title"] = objects.pop("title")

    single: dict = {"visualType": body["visualType"]}
    if projections:
        single["projections"] = projections
    if every:
        query = _prototype_query(every)
        order = body.get("orderBy")
        if order:
            field = order["field"]["field"]
            kind = "Measure" if "Measure" in field else "Column"
            entity = field[kind]["Expression"]["SourceRef"]["Entity"]
            alias = next((f["Name"] for f in query["From"]
                          if f["Entity"] == entity), None)
            if alias:
                query["OrderBy"] = [{
                    # 1 ascending, 2 descending -- the legacy format's own
                    # encoding, not a boolean.
                    "Direction": 2 if order["descending"] else 1,
                    "Expression": {kind: {
                        "Expression": {"SourceRef": {"Source": alias}},
                        "Property": field[kind]["Property"]}},
                }]
        single["prototypeQuery"] = query
    single["drillFilterOtherVisuals"] = body.get(
        "drillFilterOtherVisuals", True)
    if objects:
        single["objects"] = objects
    if vc_objects:
        single["vcObjects"] = vc_objects

    position = {
        "x": pos["x"], "y": pos["y"], "z": pos.get("z", 0),
        "width": pos["width"], "height": pos["height"],
        "tabOrder": pos.get("tabOrder", 0),
    }
    config = {
        "name": vis["name"],
        "layouts": [{"id": 0, "position": position}],
        "singleVisual": single,
    }
    # config and filters are JSON *strings* inside the JSON document. That is
    # how the format has always stored them, and a nested object where a
    # string is expected fails the open with no useful message.
    return {**position, "config": json.dumps(config), "filters": "[]"}


def render_legacy(pages) -> dict:
    """The whole report as the single document Desktop has always read."""
    sections = []
    for ordinal, (name, display, visuals) in enumerate(pages):
        sections.append({
            "id": ordinal,
            "name": _section_id(name),
            "displayName": display,
            "filters": "[]",
            "ordinal": ordinal,
            "visualContainers": [legacy_container(v) for v in visuals],
            "config": json.dumps({"objects": {
                "background": [{"properties": {
                    "color": {"solid": {"color": literal(f"'{PAGE_BG}'")}},
                    "transparency": literal("0D"),
                }}],
                "outspace": [{"properties": {
                    "color": {"solid": {"color": literal(f"'{WALLPAPER}'")}},
                    "transparency": literal("0D"),
                }}],
            }}),
            "displayOption": 1,
            "width": W,
            "height": H,
        })

    config = {
        "version": "5.55",
        "themeCollection": {"baseTheme": {
            "name": PROJECT, "version": "5.55", "type": 2}},
        "activeSectionIndex": 0,
        "defaultDrillFilterOtherVisuals": True,
        "settings": {
            "useNewFilterPaneExperience": True,
            "allowChangeFilterTypes": True,
            "useStylableVisualContainerHeader": True,
            "queryLimitOption": 6,
            "exportDataMode": 1,
            "useDefaultAggregateDisplayName": True,
        },
    }
    return {
        "id": 0,
        "resourcePackages": [{"resourcePackage": {
            "name": "SharedResources",
            "type": 2,
            "items": [{"type": 202,
                       "path": f"BaseThemes/{PROJECT}.json",
                       "name": PROJECT}],
            "disabled": False,
        }}],
        "sections": sections,
        "config": json.dumps(config),
        "layoutOptimization": 0,
    }


def write_theme() -> None:
    theme_dir = (REPORT_DIR / "StaticResources" / "SharedResources"
                 / "BaseThemes")
    theme_dir.mkdir(parents=True, exist_ok=True)
    (theme_dir / f"{PROJECT}.json").write_text(
        json.dumps(theme(), indent=2), encoding="utf-8")


def write_scaffold() -> None:
    """The files both formats share."""
    (REPORT_DIR / "definition.pbir").write_text(json.dumps({
        "version": "1.0",
        "datasetReference": {
            "byPath": {"path": f"../{PROJECT}.SemanticModel"},
        },
    }, indent=2), encoding="utf-8")

    (REPORT_DIR / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId":
                   "00000000-0000-0000-0000-000000000002"},
    }, indent=2), encoding="utf-8")

    (PBI / f"{PROJECT}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2), encoding="utf-8")


def write_legacy(pages) -> None:
    # A Report folder must never hold both formats: Desktop picks one, and the
    # other sits in the same place as a second report, silently stale.
    if DEFN.exists():
        shutil.rmtree(DEFN)
    (REPORT_DIR / "report.json").write_text(
        json.dumps(render_legacy(pages), indent=2), encoding="utf-8")
    write_theme()
    write_scaffold()


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def write_pbir(pages) -> None:
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

    write_theme()

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

    write_scaffold()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify field references and write nothing")
    ap.add_argument("--format", choices=("legacy", "pbir"), default="legacy",
                    help="on-disk report format (default: legacy, which every "
                         "Desktop build reads without a preview feature)")
    args = ap.parse_args()

    global FORMAT
    FORMAT = args.format

    pages = [fn() for fn in PAGES]
    problems = check_pages(pages) + check_layout(pages) + check_contrast()

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

    n_visuals = sum(len(v) for _, _, v in pages)
    if FORMAT == "pbir":
        write_pbir(pages)
        on_disk = len(list((DEFN / "pages").rglob("visual.json")))
    else:
        write_legacy(pages)
        # Counted back out of the written file rather than trusted. The report
        # is generated by one script and the model by another, and the model's
        # cleanup once deleted this entire folder -- so what matters is what
        # survived, not what was intended.
        written = json.loads(
            (REPORT_DIR / "report.json").read_text(encoding="utf-8"))
        on_disk = sum(len(sec["visualContainers"])
                      for sec in written["sections"])
    if on_disk != n_visuals:
        print(f"  WARNING: wrote {n_visuals} visuals but {on_disk} are on disk")
    print(f"wrote {PROJECT}.Report ({FORMAT})")
    print(f"  {len(pages)} pages, {n_visuals} visuals, 1 theme")
    for _, display, visuals in pages:
        print(f"    {display:28} {len(visuals):>2} visuals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
