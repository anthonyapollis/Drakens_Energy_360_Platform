"""Render the visual evidence pack for the case study and ebook.

Every figure is drawn from data the pipeline actually produced -- the build
manifest, the DuckDB warehouse, and live queries against the Databricks gold
schema. Nothing here is illustrative: if a chart shows a number, that number
came out of a run.

Usage:
    python scripts/build_evidence_pack.py                # local figures only
    python scripts/build_evidence_pack.py --databricks   # also query the workspace
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

REPO = Path(__file__).resolve().parent.parent
IMG = REPO / "docs" / "img"
MANIFEST = Path(os.environ.get("DRAKENS_MANIFEST",
                               REPO / "data" / "lake" / "_manifest.json"))
# Same environment variable the dbt profile and the ML experiments read, so a
# figure is never drawn from a different warehouse than the numbers it is
# being compared against.
DUCKDB = Path(os.environ.get("DRAKENS_DUCKDB_PATH",
                             REPO / "data" / "drakens360.duckdb"))

# A restrained palette: one accent, one warning, greys for everything else.
INK = "#1c1c1c"
GREY = "#8a8a8a"
LIGHT = "#d8d8d8"
ACCENT = "#0b6e4f"
WARN = "#b3341f"
GOLD = "#c8922a"

plt.rcParams.update({
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.edgecolor": LIGHT,
    "axes.labelcolor": INK,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "text.color": INK,
    "xtick.color": GREY,
    "ytick.color": GREY,
    "figure.facecolor": "white",
})

CAPTION = ("Independent synthetic portfolio project. Generated data; "
           "no real company data.")

# Figures 1 and 2 come from the build manifest, which records the full
# portfolio generation. The warehouse figures come from whichever DuckDB the
# run is pointed at, and that is not always the same build. Rather than let
# the reader assume one scale across the pack, every warehouse figure is
# stamped with the warehouse it was actually drawn from.
WAREHOUSE_NOTE = ""


def _coverage_note(con) -> str:
    """Say what a South-Africa-only map leaves out.

    The estate spans 26 African markets and only the South African sites carry
    a province, so every province map here is a cut of the network rather than
    the network. A map that does not say so is read as the whole thing, which
    is a bigger error than any number on it.
    """
    try:
        total, za = con.execute(
            "select count(*), count(*) filter (where country_code = 'ZA') "
            "from main_gold.dim_site").fetchone()
    except Exception:
        return ""
    if total == za:
        return ""
    return (f" -- the South African estate, {za} of {total} sites; the "
            f"remaining {total - za} are in other African markets and have "
            f"no province")


def warehouse_caption() -> str:
    return (f"{WAREHOUSE_NOTE} {CAPTION}".strip() if WAREHOUSE_NOTE
            else CAPTION)


def _finish(fig, name: str, caption: str = CAPTION):
    # Placed below the figure box, not inside it. At y=0.005 the caption sat
    # on top of rotated tick labels on any chart with long category names;
    # a negative y puts it under everything, and `bbox_inches="tight"` grows
    # the saved image to include it.
    fig.text(0.01, -0.03, caption, fontsize=6.5, color=GREY, ha="left",
             va="top")
    IMG.mkdir(parents=True, exist_ok=True)
    path = IMG / name
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  wrote {path.relative_to(REPO)}")
    return path


def thousands(x, _pos=None):
    if abs(x) >= 1e9:
        return f"{x/1e9:.1f}bn"
    if abs(x) >= 1e6:
        return f"{x/1e6:.1f}m"
    if abs(x) >= 1e3:
        return f"{x/1e3:.0f}k"
    return f"{x:.0f}"


# ==========================================================================
# 1. Build scale
# ==========================================================================
def fig_build_scale(manifest: dict):
    tables = manifest["tables"]
    facts = {k: v["rows"] for k, v in tables.items() if k.startswith("fact_")}
    top = pd.Series(facts).sort_values(ascending=False).head(15)[::-1]

    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    bars = ax.barh(top.index.str.replace("fact_", ""), top.values,
                   color=[ACCENT if v >= 1e6 else GREY for v in top.values])
    ax.xaxis.set_major_formatter(FuncFormatter(thousands))
    ax.set_xlabel("rows")
    ax.set_title("Largest fact tables in the portfolio build")
    for b, v in zip(bars, top.values, strict=False):
        ax.text(v * 1.01, b.get_y() + b.get_height() / 2, f"{v:,}",
                va="center", fontsize=7.5, color=GREY)
    ax.margins(x=0.16)
    total = manifest["fact_rows"]
    ax.text(0.99, -0.13, f"{len(facts)} fact tables, {total:,} fact rows in total",
            transform=ax.transAxes, ha="right", fontsize=8, color=INK)
    return _finish(fig, "01_build_scale.png")


# ==========================================================================
# 2. Injected defects
# ==========================================================================
def fig_defects(manifest: dict):
    dq = manifest.get("data_quality", {})
    by_type = dq.get("defects_by_type", {})
    if not by_type:
        return None
    # The per-cell text typing dwarfs everything; show it separately so the
    # row-level defects remain legible.
    text_typed = by_type.get("numeric_delivered_as_text", 0)
    rest = {k: v for k, v in by_type.items() if k != "numeric_delivered_as_text"}
    s = pd.Series(rest).sort_values()[-14:]

    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    ax.barh(s.index.str.replace("_", " "), s.values, color=WARN, alpha=0.85)
    ax.set_xscale("log")
    ax.set_xlabel("defects injected (log scale)")
    ax.set_title("Data defects deliberately injected into the landing zone")
    for i, v in enumerate(s.values):
        ax.text(v * 1.1, i, f"{v:,}", va="center", fontsize=7.5, color=GREY)
    ax.margins(x=0.30)
    ax.text(0.0, -0.15,
            f"Plus {text_typed:,} numeric values delivered as locale-formatted "
            f"text.\nTotal {dq.get('total_defects_injected', 0):,} defects "
            f"across {manifest['fact_rows']:,} fact rows.",
            transform=ax.transAxes, fontsize=8, color=INK, va="top")
    return _finish(fig, "02_injected_defects.png")


# ==========================================================================
# 3. Demand shape
# ==========================================================================
def fig_demand_shape(con):
    hourly = con.execute("""
        select hour(transaction_ts) as h, count(*) as n
        from main_gold.fct_retail_fuel_sales
        where transaction_ts is not null
        group by 1 order by 1
    """).df()
    dow = con.execute("""
        select day_name, sum(litres) as litres
        from main_gold.agg_site_daily_fuel
        group by 1
    """).df()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday"]
    dow = dow.set_index("day_name").reindex(order).reset_index()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.4))
    ax1.fill_between(hourly.h, hourly.n, color=ACCENT, alpha=0.18)
    ax1.plot(hourly.h, hourly.n, color=ACCENT, lw=2)
    ax1.set_title("Transactions by hour of day")
    ax1.set_xlabel("hour")
    ax1.set_xticks(range(0, 24, 3))
    ax1.yaxis.set_major_formatter(FuncFormatter(thousands))
    peak = int(hourly.loc[hourly.n.idxmax(), "h"])
    ax1.annotate(f"evening peak {peak:02d}:00",
                 xy=(peak, hourly.n.max()),
                 xytext=(peak - 8, hourly.n.max() * 0.92),
                 fontsize=7.5, color=GREY,
                 arrowprops=dict(arrowstyle="->", color=GREY, lw=0.8))

    colors = [GOLD if d in ("Friday", "Saturday") else GREY for d in dow.day_name]
    ax2.bar([d[:3] for d in dow.day_name], dow.litres, color=colors)
    ax2.set_title("Volume by day of week")
    ax2.yaxis.set_major_formatter(FuncFormatter(thousands))
    ax2.set_ylabel("litres")

    fig.suptitle("Generated demand follows real trading rhythms",
                 fontsize=11, fontweight="bold", y=1.04)
    return _finish(fig, "03_demand_shape.png", warehouse_caption())


# ==========================================================================
# 4. Cleansing outcome
# ==========================================================================
def fig_cleansing(con):
    try:
        df = con.execute("""
            select table_name, raw_rows, cleansed_rows, quarantined_rows,
                   duplicates_removed, quarantine_rate_pct
            from main_platform.obs_cleansing_summary
            order by raw_rows desc
        """).df()
    except Exception:
        print("  skipping cleansing figure: obs_cleansing_summary not built")
        return None
    if df.empty:
        return None
    df = df.head(10)[::-1]
    labels = df.table_name.str.replace("fact_", "")

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.barh(labels, df.cleansed_rows, color=ACCENT, label="cleansed")
    ax.barh(labels, df.duplicates_removed, left=df.cleansed_rows,
            color=GOLD, label="duplicates removed")
    ax.barh(labels, df.quarantined_rows,
            left=df.cleansed_rows + df.duplicates_removed,
            color=WARN, label="quarantined")
    ax.xaxis.set_major_formatter(FuncFormatter(thousands))
    ax.set_xlabel("rows")
    ax.set_title("Every landed row is accounted for: cleansed, deduplicated or quarantined")
    ax.legend(frameon=False, fontsize=8, ncols=3, loc="lower right")
    for i, (_, r) in enumerate(df.iterrows()):
        ax.text(r.raw_rows * 1.01, i, f"{r.quarantine_rate_pct:.2f}% rejected",
                va="center", fontsize=7, color=GREY)
    ax.margins(x=0.22)
    return _finish(fig, "04_cleansing_outcome.png", warehouse_caption())


def fig_quarantine_reasons(con):
    try:
        df = con.execute("""
            select failed_rule, failure_category, sum(failure_count) as n
            from main_platform.obs_quarantine_reasons
            group by 1, 2 order by n desc limit 12
        """).df()
    except Exception:
        print("  skipping quarantine-reasons figure: model not built")
        return None
    if df.empty:
        return None
    df = df[::-1]
    cmap = {"Missing Required Field": WARN, "Invalid Sign": GOLD,
            "Out of Range": ACCENT, "Invalid Timestamp": "#3d6fa5",
            "Other": GREY}
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.barh(df.failed_rule.str.replace("_", " "), df.n,
            color=[cmap.get(c, GREY) for c in df.failure_category])
    ax.xaxis.set_major_formatter(FuncFormatter(thousands))
    ax.set_title("Why rows were rejected")
    ax.set_xlabel("rule failures")
    handles = [plt.Rectangle((0, 0), 1, 1, color=v) for v in cmap.values()]
    ax.legend(handles, cmap.keys(), frameon=False, fontsize=7.5, loc="lower right")
    ax.margins(x=0.16)
    return _finish(fig, "05_quarantine_reasons.png", warehouse_caption())


# ==========================================================================
# 5. Geography
# ==========================================================================
PROVINCES_GPKG = REPO / "data" / "geo" / "za_provinces.gpkg"

# Mainland South Africa, as a clipping envelope: (minx, miny, maxx, maxy).
MAINLAND = (16.2, -35.2, 33.2, -22.0)

# Public geographic reference. Only the metros the national routes run
# between are used; no route geometry is claimed, and no synthetic site is
# placed on a line.
METROS = {
    "Cape Town": (18.4241, -33.9249),
    "Johannesburg": (28.0473, -26.2041),
    "Durban": (31.0218, -29.8587),
    "Gqeberha": (25.6022, -33.9608),
    "Bloemfontein": (26.1596, -29.0852),
    "Polokwane": (29.4689, -23.9045),
    "Kimberley": (24.7499, -28.7282),
    "Mbombela": (30.9694, -25.4753),
}
CORRIDORS = {
    "N1": ["Cape Town", "Kimberley", "Bloemfontein", "Johannesburg",
           "Polokwane"],
    "N2": ["Cape Town", "Gqeberha", "Durban"],
    "N3": ["Johannesburg", "Durban"],
}

# Recommendation colours run invest -> divest, keyed on the exact strings the
# mart emits. A near-miss on a label falls through to grey and quietly turns
# the most important encoding on the map into noise.
REC_COLOURS = {
    "Invest - Maintain Leadership": "#08512f",
    "Invest - Expand": ACCENT,
    "Invest - Refurbish": "#4b9b6e",
    "Hold": "#9ec7a5",
    "Hold - Strategic Coverage": GOLD,
    "Review": "#d98b4a",
    "Divest Candidate": WARN,
}

# Equirectangular correction at South African latitudes. Without it a degree
# of longitude is drawn as wide as a degree of latitude and the country comes
# out visibly stretched.
SA_ASPECT = 1 / np.cos(np.radians(28))


def load_provinces():
    """Real province boundaries, or None if the reference data is absent.

    Natural Earth 1:10m admin-1, filtered to South Africa. Public-domain
    cartographic reference; the boundaries are real, everything plotted on top
    of them is generated. Earlier versions of this figure drew the convex hull
    of each province's own sites instead, which was honest but is not a map.
    """
    if not PROVINCES_GPKG.exists():
        return None
    try:
        import geopandas as gpd
        provinces = gpd.read_file(PROVINCES_GPKG)
    except Exception as exc:
        print(f"  province boundaries unavailable: {str(exc)[:80]}")
        return None

    # Clip to the mainland. Natural Earth attaches the Prince Edward Islands
    # to the Western Cape, and they sit at 46 degrees south and 38 east --
    # roughly 1,800 km off the coast. Left in, they stretch the country's
    # bounding box by half again, so every map drawn to fit that box renders
    # South Africa small in a field of empty ocean, with a two-pixel speck in
    # one corner. No synthetic site is placed there.
    return provinces.clip(MAINLAND)


def scorecard(con):
    return con.execute("""
        select site_id, site_name, province, city, urban_class,
               on_national_route, has_ev_charging, has_solar,
               investment_score, investment_recommendation,
               total_margin_zar, litres_total, avg_daily_litres,
               breakdown_rate_pct, avg_asset_age_years, site_age_years,
               non_fuel_margin_share_pct,
               solar_kwh, ev_session_count, latitude, longitude
        from main_gold.network_investment_scorecard
        where country_code = 'ZA'
          and latitude is not null and longitude is not null
    """).df()


def draw_basemap(ax, provinces, values=None, cmap="YlGn", edge="white",
                 face="#eef1ef", lw=0.8):
    """Draw the province outlines, optionally shaded by `values`."""
    if provinces is None:
        return None
    if values is None:
        provinces.plot(ax=ax, facecolor=face, edgecolor=edge, linewidth=lw,
                       zorder=1)
        return None
    # The Series index carries whatever the groupby was keyed on, so it is
    # renamed explicitly rather than assumed. Getting this wrong merges on
    # nothing and every province comes out unshaded.
    lookup = values.rename("_v").reset_index()
    lookup.columns = ["name", "_v"]
    merged = provinces.merge(lookup, on="name", how="left")
    merged.plot(ax=ax, column="_v", cmap=cmap, edgecolor=edge, linewidth=lw,
                zorder=1, missing_kwds={"color": "#f2f2f2"})
    return merged


def fit_to_bounds(ax, provinces, fig=None, pad=0.35):
    """Clamp the axis to the country's own extent.

    Left to autoscale, the axis pads to whatever the widest artist needs and
    the map drifts inside a box it does not fill. Aspect is handled by
    `style_map`; the axes rectangle is sized to match in the caller, because
    stretching the data to fill a box distorts the country and stretching the
    box to fit the data is the only correction that does not.
    """
    if provinces is None:
        return
    x0, y0, x1, y1 = provinces.total_bounds
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)


def geo_ratio(bounds, pad=0.35) -> float:
    """Width-to-height ratio a region needs to render undistorted."""
    x_min, y_min, x_max, y_max = bounds
    lon = (x_max - x_min) + 2 * pad
    lat = (y_max - y_min) + 2 * pad
    return lon * math.cos(math.radians((y_min + y_max) / 2)) / max(lat, 1e-9)


def inch_rect(fig, left, bottom, width, height):
    """Convert an inch rectangle to the figure fractions add_axes wants."""
    return [left / fig.get_figwidth(), bottom / fig.get_figheight(),
            width / fig.get_figwidth(), height / fig.get_figheight()]


def map_rect(fig, x0, y0, width, bounds, pad=0.35):
    """An axes rectangle shaped like the region it will hold.

    `set_aspect` is not used anywhere in these maps. Asked to honour an aspect
    ratio, matplotlib shrinks whichever side it likes -- measured here, it cut
    the map's width from 6.1 to 4.1 inches and left the height alone, so the
    country sat in the top half of a box it never filled.

    Sizing the rectangle to the data instead makes the fit exact and
    predictable: with `aspect='auto'` the axes maps longitude to width and
    latitude to height linearly, so a box whose proportions equal
    `lon_range x cos(latitude) : lat_range` renders the country undistorted
    and fills the box completely.
    """
    x_min, y_min, x_max, y_max = bounds
    lon = (x_max - x_min) + 2 * pad
    lat = (y_max - y_min) + 2 * pad
    ratio = lon * math.cos(math.radians((y_min + y_max) / 2)) / max(lat, 1e-9)
    height = (width * fig.get_figwidth()) / ratio / fig.get_figheight()
    return [x0, y0, width, height]


def style_map(ax, title=None, fontsize=9.5):
    ax.set_aspect("auto")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    if title:
        ax.set_title(title, loc="left", fontsize=fontsize)


def fig_network_map(con):
    """The hero map: where the network is, what it earns, what to do with it.

    Three encodings on one canvas, each answering a different question:
    provinces shaded by margin per site answer "which regions earn", bubble
    area answers "which individual sites matter", and bubble colour answers
    "what should we do about them". The corridor overlay is there because
    corridor sites are protected from divestment regardless of score, and the
    capital plan is unreadable without seeing which those are.
    """
    from matplotlib.lines import Line2D

    df = scorecard(con)
    if df.empty:
        return None
    provinces = load_provinces()

    # Axes are placed explicitly rather than through a gridspec. With a fixed
    # aspect ratio a gridspec cell keeps its own height and the map floats in
    # a band of white inside it; sizing the box to the country's own
    # proportions -- roughly 1.45 wide to 1 tall once latitude is corrected --
    # is the only way to make the map fill the space it is given.
    # Laid out in inches rather than figure fractions. The map's height
    # follows from its width and the country's shape, so the figure is sized
    # around the map instead of the map being squeezed into a figure -- which
    # is what left it floating in white in every earlier attempt.
    bounds = (provinces.total_bounds if provinces is not None
              else (16.4, -34.9, 33.0, -22.1))

    map_w = 6.4
    map_h = map_w / geo_ratio(bounds)
    right_w = 5.9
    gap, margin_l, margin_r = 0.70, 0.15, 0.15
    top_pad, legend_band = 0.42, 0.95

    fig_w = margin_l + map_w + gap + right_w + margin_r
    fig_h = legend_band + map_h + top_pad
    fig = plt.figure(figsize=(fig_w, fig_h))

    ax = fig.add_axes(inch_rect(fig, margin_l, legend_band, map_w, map_h))

    # The right column is split so the two panels together span the map.
    inset_h = map_h * 0.46
    rank_h = map_h - inset_h - 0.55
    right_x = margin_l + map_w + gap
    ax_rank = fig.add_axes(inch_rect(
        fig, right_x, legend_band + inset_h + 0.55, right_w, rank_h))
    ax_inset = fig.add_axes(inch_rect(
        fig, right_x, legend_band, right_w, inset_h))

    prov = (df.groupby("province")
              .agg(sites=("total_margin_zar", "size"),
                   margin=("total_margin_zar", "sum"))
              .assign(margin_per_site=lambda d: d.margin / d.sites))

    merged = draw_basemap(ax, provinces, prov.margin_per_site)
    if merged is not None:
        for _, row in merged.iterrows():
            point = row.geometry.representative_point()
            ax.annotate(row["name"], (point.x, point.y), fontsize=7,
                        color=INK, ha="center", alpha=0.8, zorder=6)

    for name, stops in CORRIDORS.items():
        xs = [METROS[s][0] for s in stops]
        ys = [METROS[s][1] for s in stops]
        ax.plot(xs, ys, color=INK, linewidth=1.4, alpha=0.35, zorder=3,
                linestyle=(0, (6, 3)))
        mid = len(xs) // 2
        ax.annotate(name, (xs[mid], ys[mid]), fontsize=7, color=INK,
                    alpha=0.65, zorder=6, xytext=(4, 4),
                    textcoords="offset points")

    def bubbles(target, frame, scale):
        mx = max(float(frame.total_margin_zar.max()), 1.0)
        sizes = np.clip(frame.total_margin_zar / mx * scale, scale * 0.07,
                        scale)
        colours = [REC_COLOURS.get(r, GREY)
                   for r in frame.investment_recommendation]
        target.scatter(frame.longitude, frame.latitude, s=sizes, c=colours,
                       alpha=0.85, edgecolors="white", linewidths=0.35,
                       zorder=5)

    bubbles(ax, df, 115)
    for lon, lat in METROS.values():
        ax.plot(lon, lat, marker="s", ms=3.2, color=INK, zorder=7)
    fit_to_bounds(ax, provinces)
    style_map(ax, "Recommendation, margin and corridor exposure", 10.5)

    present = set(df.investment_recommendation)
    handles = [Line2D([], [], marker="o", linestyle="none", markersize=6,
                      markerfacecolor=c, markeredgecolor="white", label=k)
               for k, c in REC_COLOURS.items() if k in present]
    handles.append(Line2D([], [], color=INK, alpha=0.35,
                          linestyle=(0, (6, 3)), label="national corridor"))
    ax.legend(handles=handles, loc="upper center",
              bbox_to_anchor=(0.5, -0.01), fontsize=7, frameon=False, ncol=4,
              handletextpad=0.5, columnspacing=1.1)

    order = prov.sort_values("margin_per_site")
    lo, hi = prov.margin_per_site.min(), prov.margin_per_site.max()
    span = max(hi - lo, 1e-9)
    cmap = plt.get_cmap("YlGn")
    ax_rank.barh(order.index,
                 order.margin_per_site,
                 color=[cmap(0.15 + 0.65 * (v - lo) / span)
                        for v in order.margin_per_site],
                 edgecolor="white", linewidth=0.6)
    ax_rank.set_title("Margin per site, by province", loc="left", fontsize=9.5)
    ax_rank.xaxis.set_major_formatter(FuncFormatter(thousands))
    ax_rank.tick_params(labelsize=7.5)
    ax_rank.grid(axis="x", alpha=0.15, linewidth=0.5)
    for province, value in order.margin_per_site.items():
        ax_rank.annotate(f"{int(prov.loc[province, 'sites'])} sites",
                         (value, province), xytext=(3, 0),
                         textcoords="offset points", va="center",
                         fontsize=6.5, color=GREY)

    gp = df[df.province == "Gauteng"]
    if not gp.empty:
        pad = 0.30
        x0, x1 = gp.longitude.min() - pad, gp.longitude.max() + pad
        y0, y1 = gp.latitude.min() - pad, gp.latitude.max() + pad
        if provinces is not None:
            provinces.plot(ax=ax_inset, facecolor="#eef1ef",
                           edgecolor="white", linewidth=0.8, zorder=1)
        bubbles(ax_inset, gp, 95)
        ax_inset.set_xlim(x0, x1)
        ax_inset.set_ylim(y0, y1)
        style_map(ax_inset, f"Gauteng detail ({len(gp):,} sites)")
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False,
                                   edgecolor=INK, linewidth=0.9, alpha=0.55,
                                   zorder=8))

    caption = (
        f"{len(df):,} synthetic sites across {df.province.nunique()} "
        f"provinces{_coverage_note(con)}. "
        "Bubble area is total margin; colour is the investment recommendation. "
        "Province boundaries are Natural Earth 1:10m admin-1 (public domain); "
        "everything drawn on them is generated.\n"
        "Coordinates are South African town centroids plus random jitter and "
        "do not represent any real service station. " + warehouse_caption()
    )
    return _finish(fig, "06_network_map.png", caption)


def fig_map_multiples(con):
    """The same country, read six ways.

    A single map answers one question. A network planner asks six, and
    flipping between six separate figures makes them impossible to compare --
    the eye cannot hold the shape of Limpopo from one page to the next. Small
    multiples on a fixed basemap and a fixed extent put the comparison on one
    page, which is the whole point of the form.
    """
    df = scorecard(con)
    if df.empty:
        return None
    provinces = load_provinces()

    panels = [
        ("Throughput", "avg_daily_litres", "litres per site per day",
         "YlGnBu", False),
        ("Margin per site", "total_margin_zar", "rand per site",
         "YlGn", False),
        ("Asset condition", "breakdown_rate_pct",
         "% of work orders unplanned", "OrRd", False),
        ("Non-fuel margin", "non_fuel_margin_share_pct",
         "% of margin from shop, EV and LPG", "PuBu", False),
        ("New energy", "_new_energy", "% of sites with EV or solar",
         "BuPu", False),
        ("Corridor exposure", "_corridor", "% of sites on a national route",
         "Greys", False),
    ]
    df["_new_energy"] = (df.has_ev_charging.astype(bool)
                         | df.has_solar.astype(bool)).astype(float) * 100
    df["_corridor"] = df.on_national_route.astype(bool).astype(float) * 100

    fig, axes = plt.subplots(2, 3, figsize=(12.4, 7.2))
    for ax, (title, column, unit, cmap, _) in zip(axes.ravel(), panels,
                                                  strict=False):
        # Mean per province for rates, sum-per-site for money: taking a mean
        # of a total would say a province with one big site outperforms one
        # with thirty, which is the opposite of what the map should show.
        if column == "total_margin_zar":
            values = (df.groupby("province")[column].sum()
                      / df.groupby("province")[column].size())
        else:
            values = df.groupby("province")[column].mean()

        merged = draw_basemap(ax, provinces, values, cmap=cmap)
        fit_to_bounds(ax, provinces, pad=0.2)
        style_map(ax, title)

        if merged is not None:
            vmin, vmax = float(values.min()), float(values.max())
            leader = values.idxmax()
            ax.annotate(f"highest: {leader}", (0.5, -0.04),
                        xycoords="axes fraction", ha="center", fontsize=7,
                        color=INK)
            ax.annotate(f"{thousands(vmin)} to {thousands(vmax)} {unit}",
                        (0.5, -0.10), xycoords="axes fraction", ha="center",
                        fontsize=6.5, color=GREY)

        # A site layer keeps the reader oriented: a choropleth alone hides
        # that the Northern Cape's shading rests on seven sites. White with a
        # dark edge so the dots read on both the palest and the darkest fills
        # -- a single flat colour disappears into one end of every ramp.
        ax.scatter(df.longitude, df.latitude, s=5, c="white",
                   edgecolors=INK, linewidths=0.45, alpha=0.75, zorder=5)

    fig.suptitle("The same network, read six ways", x=0.012, ha="left",
                 fontsize=12, fontweight="bold")
    fig.subplots_adjust(top=0.90, hspace=0.30)
    caption = (
        "Provinces shaded by the panel's measure; dots are the synthetic "
        "sites, identical in every panel so the six are comparable. Province "
        "boundaries are Natural Earth 1:10m admin-1 (public domain).\n"
        + warehouse_caption())
    return _finish(fig, "10_map_multiples.png", caption)


def fig_investment_mix(con):
    df = con.execute("""
        select investment_recommendation, count(*) sites,
               avg(investment_score) avg_score,
               sum(total_margin_zar) margin
        from main_gold.network_investment_scorecard
        group by 1 order by avg_score desc
    """).df()
    if df.empty:
        return None
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 3.8))
    colors = [ACCENT if "Invest" in r else GOLD if "Hold" in r else WARN
              for r in df.investment_recommendation]
    ax1.bar(range(len(df)), df.sites, color=colors)
    ax1.set_xticks(range(len(df)))
    ax1.set_xticklabels([r.replace(" - ", "\n") for r in df.investment_recommendation],
                        fontsize=7, rotation=0)
    ax1.set_ylabel("sites")
    ax1.set_title("Capital recommendation by site")
    for i, v in enumerate(df.sites):
        ax1.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=7.5)

    ax2.bar(range(len(df)), df.margin / 1e6, color=colors)
    ax2.set_xticks(range(len(df)))
    ax2.set_xticklabels([r.replace(" - ", "\n") for r in df.investment_recommendation],
                        fontsize=7)
    ax2.set_ylabel("gross margin (R million)")
    ax2.set_title("Margin concentration")
    fig.suptitle("Where the network earns, and where capital should go",
                 fontsize=11, fontweight="bold", y=1.04)
    return _finish(fig, "07_investment_mix.png", warehouse_caption())


def fig_province_performance(con):
    df = con.execute("""
        select province,
               sum(fuel_litres)/1e6 as litres_m,
               sum(total_margin_zar)/1e6 as margin_m,
               avg(gross_margin_pct) as margin_pct
        from main_gold.agg_executive_daily_kpi
        group by 1 order by margin_m desc
    """).df()
    if df.empty:
        return None

    # Rows whose site never resolved to a province are a data-quality result,
    # not a province. Charting them as a bar labelled "nan" alongside Gauteng
    # invites the reader to treat unresolved volume as a region -- so the
    # bucket is named, moved to the end, and coloured as a warning. Dropping
    # it silently would be worse: on a partial build it can carry more margin
    # than every real province combined, and that is worth seeing.
    unresolved = df.province.isna()
    df.loc[unresolved, "province"] = "unresolved"
    df = pd.concat([df[~unresolved], df[unresolved]], ignore_index=True)
    n_unresolved = int(unresolved.sum())

    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    x = np.arange(len(df))
    vol_colours = [WARN if p == "unresolved" else GREY for p in df.province]
    mar_colours = [WARN if p == "unresolved" else ACCENT for p in df.province]
    ax.bar(x - 0.2, df.litres_m, 0.4, label="volume (m litres)",
           color=vol_colours)
    ax.bar(x + 0.2, df.margin_m, 0.4, label="gross margin (R m)",
           color=mar_colours, hatch=["//" if p == "unresolved" else ""
                                     for p in df.province])
    ax.set_xticks(x)
    ax.set_xticklabels(df.province, rotation=30, ha="right", fontsize=8)
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("Volume and margin by province")
    if n_unresolved:
        share = df.loc[df.province == "unresolved", "margin_m"].sum() \
            / max(df.margin_m.sum(), 1e-9)
        ax.text(0.5, -0.34,
                f"{share:.0%} of margin sits on sites that did not resolve to "
                "a province. On a partial build this is expected -- the site\n"
                "dimension is incomplete -- and on a full build it would be a "
                "referential defect worth failing the run over.",
                transform=ax.transAxes, ha="center", fontsize=7, color=WARN)
    return _finish(fig, "08_province_performance.png", warehouse_caption())



# ==========================================================================
# 7. Commercial and operational analysis
# ==========================================================================
def fig_executive_trend(con):
    """Revenue, margin and margin rate over the whole modelled window.

    A daily series at this length is unreadable as a line, and a monthly one
    hides the weekly rhythm the generator works hard to produce. Both are
    drawn: the daily series faint, a 28-day rolling mean over it, and the
    margin rate on its own axis underneath, because a rate and a total on one
    axis is how a chart ends up saying nothing about either.
    """
    df = con.execute("""
        select full_date,
               sum(total_revenue_zar) as revenue,
               sum(total_margin_zar)  as margin,
               sum(fuel_litres)       as litres
        from main_gold.agg_executive_daily_kpi
        where full_date is not null
        group by 1 order by 1
    """).df()
    if df.empty:
        return None
    df["full_date"] = pd.to_datetime(df.full_date)
    df["margin_pct"] = df.margin / df.revenue.replace(0, np.nan) * 100
    roll = df.set_index("full_date").rolling("28D").mean()

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10.4, 5.6), sharex=True,
        gridspec_kw={"height_ratios": [2.1, 1.0], "hspace": 0.12})

    ax1.plot(df.full_date, df.revenue, color=GREY, lw=0.5, alpha=0.45,
             label="daily")
    ax1.plot(roll.index, roll.revenue, color=ACCENT, lw=2.0,
             label="revenue, 28-day mean")
    ax1.plot(roll.index, roll.margin, color=GOLD, lw=2.0,
             label="margin, 28-day mean")
    ax1.fill_between(roll.index, 0, roll.margin, color=GOLD, alpha=0.12)
    ax1.yaxis.set_major_formatter(FuncFormatter(thousands))
    ax1.set_ylabel("rand per day")
    ax1.set_title("Network revenue and margin", loc="left")
    ax1.legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
    ax1.grid(alpha=0.15, linewidth=0.5)

    ax2.plot(roll.index, roll.margin_pct, color=INK, lw=1.6)
    ax2.set_ylabel("margin %")
    ax2.set_title("Gross margin rate", loc="left", fontsize=9.5)
    ax2.grid(alpha=0.15, linewidth=0.5)
    # One decimal: the rate moves inside a single percentage point, and
    # a zero-decimal axis prints the same label five times.
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}%"))
    return _finish(fig, "11_executive_trend.png", warehouse_caption())


def fig_seasonality(con):
    """Month against day of week, as a heatmap.

    The demand generator shapes volume by hour, weekday, month and public
    holiday. A line chart shows one of those at a time; a heatmap shows the
    interaction, which is where the pattern either looks like a real trading
    calendar or looks like noise with a trend bolted on.
    """
    # Mean litres per trading day, not the sum.
    #
    # The modelled window runs to the end of August, so January through August
    # occur in three calendar years and September through December in two.
    # Summed, the last four months come out roughly a third lower and the
    # chart shows the shape of the extract window while looking exactly like
    # seasonality -- which is what the first version of this figure did, under
    # a caption confidently describing a summer peak that was not there.
    df = con.execute("""
        select month_name, day_name,
               sum(fuel_litres) / count(distinct full_date) as litres
        from main_gold.agg_executive_daily_kpi
        group by 1, 2
    """).df()
    if df.empty:
        return None

    months = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]
    grid = (df.pivot_table(index="month_name", columns="day_name",
                           values="litres", aggfunc="mean")
              .reindex(index=months, columns=days))

    # Indexed to the overall mean so the colour scale reads as "against a
    # normal day" rather than in litres.
    indexed = grid / np.nanmean(grid.to_numpy()) * 100

    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    im = ax.imshow(indexed.to_numpy(), cmap="RdYlGn", aspect="auto",
                   vmin=100 - np.nanmax(abs(indexed.to_numpy() - 100)),
                   vmax=100 + np.nanmax(abs(indexed.to_numpy() - 100)))
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels([d[:3] for d in days], fontsize=8.5)
    ax.set_yticks(range(len(months)))
    ax.set_yticklabels([m[:3] for m in months], fontsize=8.5)
    for i in range(len(months)):
        for j in range(len(days)):
            v = indexed.to_numpy()[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                        fontsize=6.8,
                        color="white" if abs(v - 100) > 12 else INK)
    cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("volume index, 100 = network average", fontsize=8)
    cb.outline.set_visible(False)
    ax.set_title("Volume by month and day of week", loc="left")
    ax.text(0.0, -0.13,
            "Mean litres per trading day, indexed to 100. Per day rather than "
            "per month because the modelled window ends in August: summed, "
            "September to December would read a third low and look like "
            "seasonality.",
            transform=ax.transAxes, fontsize=7.5, color=GREY)
    return _finish(fig, "12_seasonality.png", warehouse_caption())


def fig_credit_and_sector(con):
    """Two commercial questions the credit committee actually asks.

    Left: does the credit band mean anything -- do worse-rated customers
    actually pay later and discount harder? Right: how concentrated is the
    book, because a customer list whose top decile carries most of the revenue
    is a different risk from one that does not.
    """
    band = con.execute("""
        select credit_band,
               count(distinct customer_key) as customers,
               sum(revenue_zar)             as revenue,
               avg(margin_pct)              as margin_pct,
               avg(discount_intensity_pct)  as discount_pct
        from main_gold.agg_customer_monthly
        where credit_band is not null
        group by 1 order by 1
    """).df()
    cust = con.execute("""
        select customer_key, sum(revenue_zar) as revenue
        from main_gold.agg_customer_monthly
        group by 1 having sum(revenue_zar) > 0
    """).df()
    if band.empty or cust.empty:
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.6, 4.2))

    x = np.arange(len(band))
    ax1.bar(x - 0.2, band.margin_pct, 0.4, color=ACCENT, label="margin %")
    ax1.bar(x + 0.2, band.discount_pct, 0.4, color=WARN, label="discount %")
    ax1.set_xticks(x)
    ax1.set_xticklabels(band.credit_band)
    ax1.set_xlabel("credit band")
    ax1.set_title("Margin and discount by credit band", loc="left",
                  fontsize=10)
    ax1.legend(frameon=False, fontsize=8)
    ax1.set_ylabel("% of revenue")
    ax1.grid(axis="y", alpha=0.15, linewidth=0.5)
    ax1.set_ylim(0, float(band.margin_pct.max()) * 1.32)
    # Counts sit above the bars. Below the axis they collided with the axis
    # label, which is the kind of overlap that survives review because the
    # chart is still readable and quietly looks unfinished.
    for i, row in band.iterrows():
        ax1.annotate(f"{int(row.customers):,} customers",
                     (i, float(row.margin_pct)), xytext=(0, 6),
                     textcoords="offset points", ha="center", fontsize=7,
                     color=GREY)

    share = (cust.revenue.sort_values(ascending=False).cumsum()
             / cust.revenue.sum() * 100).to_numpy()
    pct = np.arange(1, len(share) + 1) / len(share) * 100
    ax2.plot(pct, share, color=ACCENT, lw=2)
    ax2.plot([0, 100], [0, 100], color=GREY, lw=1, linestyle=(0, (4, 3)),
             label="perfectly even book")
    top_decile = float(np.interp(10, pct, share))
    ax2.axvline(10, color=WARN, lw=1, alpha=0.6)
    ax2.annotate(f"top 10% of customers\ncarry {top_decile:.0f}% of revenue",
                 (10, top_decile), xytext=(16, top_decile - 22),
                 fontsize=8, color=INK,
                 arrowprops=dict(arrowstyle="->", color=GREY, lw=0.8))
    ax2.set_xlabel("cumulative share of customers (%)")
    ax2.set_ylabel("cumulative share of revenue (%)")
    ax2.set_title("Revenue concentration", loc="left", fontsize=10)
    ax2.legend(frameon=False, fontsize=8, loc="lower right")
    ax2.grid(alpha=0.15, linewidth=0.5)
    return _finish(fig, "13_commercial.png", warehouse_caption())


def fig_delivery_performance(con):
    """Where the distribution plan actually breaks.

    OTIF as a single network number is the least useful form of it. Broken out
    by province and by trip length, it says whether lateness is a routing
    problem, a distance problem, or one region's problem -- which are three
    different fixes.
    """
    prov = con.execute("""
        select province,
               count(*)                             as deliveries,
               avg(case when is_otif then 1.0 else 0 end) * 100 as otif_pct,
               avg(delay_minutes)                   as avg_delay
        from main_gold.fct_deliveries
        where province is not null
        group by 1 having count(*) > 30
        order by otif_pct
    """).df()
    dist = con.execute("""
        select case
                 when distance_km < 50   then '< 50'
                 when distance_km < 150  then '50-150'
                 when distance_km < 300  then '150-300'
                 when distance_km < 600  then '300-600'
                 else '600+'
               end as band,
               count(*) as deliveries,
               avg(case when is_otif then 1.0 else 0 end) * 100 as otif_pct
        from main_gold.fct_deliveries
        where distance_km is not null
        group by 1
    """).df()
    if prov.empty:
        return None

    order = ["< 50", "50-150", "150-300", "300-600", "600+"]
    dist = dist.set_index("band").reindex(order).dropna().reset_index()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.6, 4.2),
                                   gridspec_kw={"width_ratios": [1.25, 1.0]})

    network = float(prov.deliveries @ prov.otif_pct / prov.deliveries.sum())
    colours = [WARN if v < network else ACCENT for v in prov.otif_pct]
    ax1.barh(prov.province, prov.otif_pct, color=colours, edgecolor="white",
             linewidth=0.6)
    ax1.axvline(network, color=INK, lw=1, linestyle=(0, (4, 3)))
    ax1.annotate(f"network {network:.1f}%", (network, -0.7),
                 xytext=(4, 0), textcoords="offset points", fontsize=7.5,
                 color=INK)
    ax1.set_xlabel("on time and in full (%)")
    ax1.set_title("OTIF by province", loc="left", fontsize=10)
    ax1.grid(axis="x", alpha=0.15, linewidth=0.5)
    ax1.tick_params(labelsize=8)
    for i, row in prov.iterrows():
        ax1.annotate(f"{int(row.deliveries):,}", (row.otif_pct, i),
                     xytext=(4, 0), textcoords="offset points", va="center",
                     fontsize=6.5, color=GREY)

    ax2.plot(dist.band, dist.otif_pct, color=ACCENT, lw=2, marker="o", ms=5)
    ax2.set_xlabel("trip distance (km)")
    ax2.set_ylabel("OTIF (%)")
    ax2.set_title("OTIF by trip length", loc="left", fontsize=10)
    ax2.grid(alpha=0.15, linewidth=0.5)
    for _, row in dist.iterrows():
        ax2.annotate(f"{int(row.deliveries):,}", (row.band, row.otif_pct),
                     xytext=(0, 9), textcoords="offset points", ha="center",
                     fontsize=7, color=GREY)
    return _finish(fig, "14_delivery_performance.png", warehouse_caption())


def fig_asset_reliability(con):
    """The signal the maintenance model is allowed to learn from.

    Breakdown rate rises with asset age and with criticality, and this figure
    is the reason the predictive-maintenance experiment reports an age-only
    baseline: if age explains most of the separation, a model has to beat age
    before it has earned a place in the pipeline.
    """
    age = con.execute("""
        select asset_age_band,
               count(*) as work_orders,
               avg(case when is_breakdown then 1.0 else 0 end) * 100 as rate
        from main_gold.fct_maintenance_work_orders
        where asset_age_band is not null
        group by 1
    """).df()
    # A cell computed from one work order is not a rate, it is that work
    # order. Cells below the threshold are left blank rather than printed as
    # a confident 0% or 100%, which is what they were before: the first draft
    # of this figure showed a POS Terminal / Critical cell at 100% on a single
    # row, sitting in the same colour scale as cells built from 300.
    typ = con.execute("""
        select asset_type, criticality,
               avg(case when is_breakdown then 1.0 else 0 end) * 100 as rate,
               count(*) as work_orders
        from main_gold.fct_maintenance_work_orders
        where asset_type is not null and criticality is not null
        group by 1, 2
        having count(*) >= 20
    """).df()
    if age.empty:
        return None

    order = ["0-5", "5-10", "10-15", "15+"]
    age = age.set_index("asset_age_band").reindex(order).dropna().reset_index()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.8, 4.6),
                                   gridspec_kw={"width_ratios": [1.0, 1.30],
                                                "wspace": 0.38})

    bars = ax1.bar(age.asset_age_band, age.rate,
                   color=plt.get_cmap("OrRd")(
                       np.linspace(0.35, 0.85, len(age))),
                   edgecolor="white", linewidth=0.6)
    ax1.set_xlabel("asset age band (years)")
    ax1.set_ylabel("unplanned work orders (%)")
    ax1.set_title("Breakdown rate rises with age", loc="left", fontsize=10)
    ax1.grid(axis="y", alpha=0.15, linewidth=0.5)
    for b, row in zip(bars, age.itertuples(), strict=False):
        ax1.annotate(f"{row.rate:.0f}%\n{int(row.work_orders):,} WOs",
                     (b.get_x() + b.get_width() / 2, row.rate),
                     xytext=(0, 4), textcoords="offset points", ha="center",
                     fontsize=7, color=GREY)

    pivot = typ.pivot_table(index="asset_type", columns="criticality",
                            values="rate", aggfunc="mean")
    for col in ("Critical", "High", "Medium", "Low"):
        if col not in pivot.columns:
            pivot[col] = np.nan
    pivot = pivot[["Critical", "High", "Medium", "Low"]]
    im = ax2.imshow(pivot.to_numpy(), cmap="OrRd", aspect="auto")
    ax2.set_xticks(range(len(pivot.columns)))
    ax2.set_xticklabels(pivot.columns, fontsize=8)
    ax2.set_yticks(range(len(pivot.index)))
    ax2.set_yticklabels(pivot.index, fontsize=8)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.to_numpy()[i, j]
            if np.isfinite(v):
                ax2.text(j, i, f"{v:.0f}", ha="center", va="center",
                         fontsize=7,
                         color="white" if v > np.nanmean(pivot.to_numpy())
                         else INK)
    ax2.set_title("Breakdown rate by asset type and criticality",
                  loc="left", fontsize=10)
    cb = fig.colorbar(im, ax=ax2, shrink=0.85, pad=0.02)
    cb.set_label("% unplanned", fontsize=8)
    cb.outline.set_visible(False)
    return _finish(fig, "15_asset_reliability.png", warehouse_caption())


def fig_investment_frontier(con):
    """Every candidate project, and the line the budget actually drew.

    The optimiser's output is a list, and a list does not show why one project
    was funded and a similar one was not. Plotting return against capital does:
    the funded set is not simply the top of the ROI ranking, because provincial
    minimums and corridor protection pull specific projects in.
    """
    plan_path = REPO / "data" / "network_investment_plan.csv"
    if not plan_path.exists():
        return None
    plan = pd.read_csv(plan_path)
    if plan.empty or "selected" not in plan:
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.4, 4.4),
                                   gridspec_kw={"width_ratios": [1.25, 1.0],
                                                "wspace": 0.34})

    sel = plan[plan.selected.astype(bool)]
    rej = plan[~plan.selected.astype(bool)]

    # Capital cost takes one value per intervention type, so an honest scatter
    # is five vertical lines with several hundred points stacked on each. A
    # little horizontal jitter separates them without moving any point far
    # enough to misread its cost.
    rng = np.random.default_rng(7)

    def jitter(values):
        return values / 1e6 + rng.normal(0, 0.055, len(values))

    ax1.scatter(jitter(rej.capex_zar), rej.roi_pct, s=14, c=GREY, alpha=0.30,
                label=f"not funded ({len(rej):,})", linewidths=0)
    ax1.scatter(jitter(sel.capex_zar), sel.roi_pct, s=18, c=ACCENT,
                alpha=0.75, label=f"funded ({len(sel):,})", linewidths=0)
    ax1.set_xlabel("capital required (R m)")
    ax1.set_ylabel("expected return (% per year)")
    ax1.set_title("Candidate projects: return against capital", loc="left",
                  fontsize=10)
    ax1.legend(frameon=False, fontsize=8, loc="upper right")
    ax1.grid(alpha=0.15, linewidth=0.5)

    by_type = (sel.groupby("intervention")
                  .agg(projects=("site_id", "size"),
                       capex=("capex_zar", "sum"),
                       uplift=("expected_annual_uplift_zar", "sum"))
                  .sort_values("capex"))
    y = np.arange(len(by_type))
    ax2.barh(y - 0.2, by_type.capex / 1e6, 0.4, color=GREY, label="capital")
    ax2.barh(y + 0.2, by_type.uplift / 1e6, 0.4, color=ACCENT,
             label="annual uplift")
    ax2.set_yticks(y)
    # Wrapped, because the intervention names are long enough to run into the
    # bars at this width.
    ax2.set_yticklabels([n.replace(" ", "\n", 1) for n in by_type.index],
                        fontsize=8)
    ax2.set_xlabel("R m")
    ax2.set_title("Funded plan by intervention", loc="left", fontsize=10)
    ax2.legend(frameon=False, fontsize=8)
    ax2.grid(axis="x", alpha=0.15, linewidth=0.5)
    for i, row in enumerate(by_type.itertuples()):
        ax2.annotate(f"{int(row.projects)} sites",
                     (max(row.capex, row.uplift) / 1e6, i), xytext=(4, 0),
                     textcoords="offset points", va="center", fontsize=6.5,
                     color=GREY)
    return _finish(fig, "16_investment_frontier.png", warehouse_caption())


def fig_model_scorecard(_con=None):
    """Every model against the baseline it has to beat.

    Read straight from the MLflow tracking store, so a model that stops
    beating its baseline changes this figure on the next run rather than
    waiting for someone to remember to redraw it.
    """
    import sqlite3

    db = REPO / "mlruns" / "mlflow.db"
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        runs = pd.read_sql_query(
            "SELECT e.name AS experiment, r.run_uuid, r.start_time "
            "FROM runs r JOIN experiments e "
            "ON r.experiment_id = e.experiment_id "
            "WHERE r.status = 'FINISHED'", conn)
        metrics = pd.read_sql_query(
            "SELECT run_uuid, key, value FROM metrics", conn)
    finally:
        conn.close()
    if runs.empty:
        return None

    latest = (runs.sort_values("start_time")
                  .groupby("experiment", as_index=False).last())
    wide = (metrics[metrics.run_uuid.isin(latest.run_uuid)]
            .merge(latest[["experiment", "run_uuid"]], on="run_uuid")
            .pivot_table(index="experiment", columns="key", values="value",
                         aggfunc="last"))
    wide.index = wide.index.str.replace("drakens_energy_360_", "", regex=False)

    rows = []
    for name, r in wide.iterrows():
        auc = r.get("roc_auc")
        if pd.isna(auc):
            continue
        base = r.get("baseline_roc_auc_age_only")
        rows.append({
            "model": name.replace("_", " ").title(),
            "score": float(auc),
            "baseline": float(base) if pd.notna(base) else 0.5,
            "baseline_label": ("age-only" if pd.notna(base) else "chance"),
        })
    if not rows:
        return None
    scored = pd.DataFrame(rows).sort_values("score")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.8, 4.0),
                                   gridspec_kw={"width_ratios": [1.3, 1.0]})

    y = np.arange(len(scored))
    # A model has to clear its baseline by a margin worth deploying for, not
    # by a rounding error. Stock-out risk scores 0.510 against a chance
    # baseline of 0.500: nominally ahead, and useless.
    MEANINGFUL = 0.02
    beats = scored.score > scored.baseline + MEANINGFUL
    ax1.barh(y, scored.score, color=[ACCENT if b else WARN for b in beats],
             edgecolor="white", linewidth=0.6, height=0.62)
    for i, row in enumerate(scored.itertuples()):
        ax1.plot([row.baseline, row.baseline], [i - 0.36, i + 0.36],
                 color=INK, lw=1.8)
        ax1.annotate(f"{row.score:.3f}", (row.score, i), xytext=(4, 0),
                     textcoords="offset points", va="center", fontsize=7.5,
                     color=GREY)
    ax1.set_yticks(y)
    ax1.set_yticklabels(scored.model, fontsize=8.5)
    ax1.set_xlim(0.45, 1.0)
    ax1.set_xlabel("ROC-AUC")
    ax1.set_title("Each model against the baseline it must beat (black bar)",
                  loc="left", fontsize=10)
    ax1.grid(axis="x", alpha=0.15, linewidth=0.5)

    # The demand forecast is a regression and has no AUC, so it gets its own
    # panel rather than a meaningless bar on the one above.
    demand = wide.loc["demand_forecast"] if "demand_forecast" in wide.index \
        else None
    if demand is not None and pd.notna(demand.get("mae")):
        labels = ["seasonal naive\n(last week, same day)", "model"]
        values = [float(demand.get("baseline_mae", np.nan)),
                  float(demand.get("mae"))]
        bars = ax2.bar(labels, values, color=[GREY, ACCENT],
                       edgecolor="white", linewidth=0.6, width=0.55)
        ax2.set_ylabel("mean absolute error (litres)")
        ax2.set_title("Demand forecast against its baseline", loc="left",
                      fontsize=10)
        ax2.grid(axis="y", alpha=0.15, linewidth=0.5)
        for b, v in zip(bars, values, strict=False):
            ax2.annotate(f"{v:,.1f}",
                         (b.get_x() + b.get_width() / 2, v), xytext=(0, 4),
                         textcoords="offset points", ha="center", fontsize=8,
                         color=INK)
        improvement = float(demand.get("mae_improvement_pct", np.nan))
        if np.isfinite(improvement):
            ax2.annotate(f"{improvement:.1f}% better", (1, values[1]),
                         xytext=(0, 26), textcoords="offset points",
                         ha="center", fontsize=9, color=ACCENT,
                         fontweight="bold")
    else:
        ax2.axis("off")

    failed = int((~beats).sum())
    ax1.text(0.0, -0.20,
             "The black marker is the baseline each model has to beat. A bar "
             f"that does not clear it by at least {MEANINGFUL:.2f} has not "
             "earned its place in the pipeline:\n"
             f"{failed} of {len(scored)} classifiers here have not.",
             transform=ax1.transAxes, fontsize=7.5, color=GREY, va="top")
    return _finish(fig, "17_model_scorecard.png")


def fig_site_distribution(con):
    """How unequal the network is, and where the score comes from.

    Left: the distribution of site throughput, because a network average is a
    poor summary of a population this skewed. Right: what actually drives the
    investment score, as the correlation between each component and the total.
    """
    df = con.execute("""
        select avg_daily_litres, total_margin_zar, investment_score,
               urban_class, r_contribution, r_throughput, r_growth,
               r_non_fuel, r_reliability, r_uptime, r_safety,
               r_asset_condition
        from main_gold.network_investment_scorecard
        where avg_daily_litres is not null
    """).df()
    if df.empty:
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.6, 4.2))

    classes = [c for c in ("Metro", "Urban", "Town", "Rural")
               if c in set(df.urban_class)]
    data = [df.loc[df.urban_class == c, "avg_daily_litres"].dropna()
            for c in classes]
    parts = ax1.violinplot(data, showmedians=True, widths=0.8)
    for body in parts["bodies"]:
        body.set_facecolor(ACCENT)
        body.set_alpha(0.35)
    for key in ("cmedians", "cmaxes", "cmins", "cbars"):
        if key in parts:
            parts[key].set_color(INK)
            parts[key].set_linewidth(1.0)
    ax1.set_xticks(range(1, len(classes) + 1))
    ax1.set_xticklabels(classes, fontsize=8.5)
    ax1.set_ylabel("litres per site per day")
    ax1.set_title("Throughput distribution by location type", loc="left",
                  fontsize=10)
    ax1.grid(axis="y", alpha=0.15, linewidth=0.5)
    for i, c in enumerate(classes, start=1):
        ax1.annotate(f"n={len(df[df.urban_class == c]):,}", (i, 0),
                     xytext=(0, -30), textcoords="offset points",
                     ha="center", fontsize=7, color=GREY)

    components = ["r_contribution", "r_throughput", "r_growth", "r_non_fuel",
                  "r_reliability", "r_uptime", "r_safety",
                  "r_asset_condition"]
    corr = (df[[*components, "investment_score"]].corr()["investment_score"]
            .drop("investment_score").sort_values())
    ax2.barh([c.replace("r_", "").replace("_", " ") for c in corr.index],
             corr.to_numpy(),
             color=[WARN if v < 0 else ACCENT for v in corr],
             edgecolor="white", linewidth=0.6)
    ax2.axvline(0, color=INK, lw=0.8)
    ax2.set_xlabel("correlation with the investment score")
    ax2.set_title("What drives the score", loc="left", fontsize=10)
    ax2.grid(axis="x", alpha=0.15, linewidth=0.5)
    ax2.tick_params(labelsize=8)
    ax2.text(0.0, -0.22,
             "Weights are a stated management judgement, not a fitted "
             "parameter, so a challenged recommendation can be answered with "
             "its inputs.",
             transform=ax2.transAxes, fontsize=7, color=GREY)
    return _finish(fig, "18_site_distribution.png", warehouse_caption())


# ==========================================================================
# 6. Databricks evidence
# ==========================================================================
def fig_databricks_medallion(profile: str):
    """Live row counts through bronze, silver and gold on Databricks."""
    try:
        import time

        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.sql import StatementState
    except ImportError:
        print("  skipping Databricks figure: SDK not installed")
        return None

    w = WorkspaceClient(profile=profile)
    wid = next(x.id for x in w.warehouses.list())

    def q(sql):
        r = w.statement_execution.execute_statement(
            warehouse_id=wid, statement=sql, wait_timeout="50s")
        while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(4)
            r = w.statement_execution.get_statement(r.statement_id)
        if r.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(r.status.error.message)
        return (r.result.data_array or []) if r.result else []

    rows = q("""
        SELECT 'bronze' layer, 'fact_retail_fuel_sales' t, count(*) n
          FROM drakens_dev.bronze.fact_retail_fuel_sales
        UNION ALL SELECT 'silver', 'fact_retail_fuel_sales', count(*)
          FROM drakens_dev.silver.fact_retail_fuel_sales
        UNION ALL SELECT 'gold', 'fct_retail_fuel_sales', count(*)
          FROM drakens_dev.gold.fct_retail_fuel_sales
        UNION ALL SELECT 'gold', 'agg_site_daily_fuel', count(*)
          FROM drakens_dev.gold.agg_site_daily_fuel
        UNION ALL SELECT 'gold', 'agg_executive_daily_kpi', count(*)
          FROM drakens_dev.gold.agg_executive_daily_kpi
        UNION ALL SELECT 'gold', 'network_investment_scorecard', count(*)
          FROM drakens_dev.gold.network_investment_scorecard
    """)
    df = pd.DataFrame(rows, columns=["layer", "table", "n"])
    df["n"] = df.n.astype(int)

    fig, ax = plt.subplots(figsize=(7.8, 4.2))
    colors = {"bronze": "#a8703c", "silver": "#9aa0a6", "gold": GOLD}
    labels = [f"{r.layer}.{r.table}" for _, r in df.iterrows()]
    ax.barh(labels[::-1], df.n[::-1], color=[colors[layer] for layer in df.layer[::-1]])
    ax.set_xscale("log")
    ax.set_xlabel("rows (log scale)")
    ax.set_title("Databricks: rows through the medallion, portfolio scale")
    for i, v in enumerate(df.n[::-1]):
        ax.text(v * 1.15, i, f"{v:,}", va="center", fontsize=7.5, color=GREY)
    ax.margins(x=0.28)
    return _finish(
        fig, "09_databricks_medallion.png",
        "Live counts queried from the Databricks workspace. "
        "Independent synthetic portfolio project.")


# ==========================================================================
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--databricks", action="store_true",
                    help="also query the Databricks workspace")
    ap.add_argument("--profile", default="pet-business")
    args = ap.parse_args(argv)

    print("building evidence pack")
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        fig_build_scale(manifest)
        fig_defects(manifest)
    else:
        print(f"  no manifest at {MANIFEST}; run the generator first")

    if DUCKDB.exists():
        try:
            con = duckdb.connect(str(DUCKDB), read_only=True)
            global WAREHOUSE_NOTE
            rows = con.execute(
                "select count(*) from main_gold.fct_retail_fuel_sales").fetchone()[0]
            WAREHOUSE_NOTE = (
                f"Drawn from {DUCKDB.name} "
                f"({rows:,} retail transactions in gold).")
        except duckdb.IOException as exc:
            # Almost always a dbt build holding the file. The manifest figures
            # above are already written; producing those and reporting why the
            # rest are missing beats failing the whole run.
            print(f"  warehouse is locked, skipping its figures: {str(exc)[:100]}")
            print("done")
            return 0
        try:
            for fn in (fig_demand_shape, fig_cleansing,
                       fig_quarantine_reasons, fig_network_map,
                       fig_investment_mix, fig_province_performance,
                       fig_map_multiples, fig_executive_trend,
                       fig_seasonality, fig_credit_and_sector,
                       fig_delivery_performance, fig_asset_reliability,
                       fig_investment_frontier, fig_model_scorecard,
                       fig_site_distribution):
                try:
                    fn(con)
                except Exception as exc:
                    print(f"  skipped {fn.__name__}: {exc}")
        finally:
            con.close()
    else:
        print(f"  no warehouse at {DUCKDB}; run dbt build first")

    if args.databricks:
        try:
            fig_databricks_medallion(args.profile)
        except Exception as exc:
            print(f"  skipped Databricks figure: {exc}")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
