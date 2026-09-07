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
        f"{len(df):,} synthetic sites across {df.province.nunique()} provinces. "
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
            for fn in (fig_demand_shape, fig_cleansing, fig_quarantine_reasons,
                       fig_network_map, fig_investment_mix,
                       fig_province_performance):
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
