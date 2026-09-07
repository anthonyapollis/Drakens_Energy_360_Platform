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
MANIFEST = REPO / "data" / "lake" / "_manifest.json"
DUCKDB = REPO / "data" / "vivo360.duckdb"

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


def _finish(fig, name: str, caption: str = CAPTION):
    fig.text(0.01, 0.005, caption, fontsize=6.5, color=GREY, ha="left")
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
    return _finish(fig, "03_demand_shape.png")


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
    return _finish(fig, "04_cleansing_outcome.png")


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
    return _finish(fig, "05_quarantine_reasons.png")


# ==========================================================================
# 5. Network and commercial views
# ==========================================================================
def fig_network_map(con):
    df = con.execute("""
        select longitude, latitude, province, investment_score,
               investment_recommendation, total_margin_zar
        from main_gold.network_investment_scorecard
        where country_code = 'ZA' and latitude is not null
    """).df()
    if df.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.6, 6.2))
    sc = ax.scatter(df.longitude, df.latitude,
                    c=df.investment_score, cmap="RdYlGn",
                    s=np.clip(df.total_margin_zar / df.total_margin_zar.max() * 90, 6, 90),
                    alpha=0.85, edgecolors="white", linewidths=0.3)
    cb = fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
    cb.set_label("investment score", fontsize=8)
    cb.outline.set_visible(False)
    ax.set_title("Synthetic South African network, scored for investment")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.text(0.5, -0.10,
            f"{len(df):,} synthetic sites across {df.province.nunique()} provinces. "
            "Coordinates are town centroids plus random jitter\nand do not "
            "represent any real service station.",
            transform=ax.transAxes, ha="center", fontsize=7.5, color=GREY)
    return _finish(fig, "06_network_map.png")


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
    return _finish(fig, "07_investment_mix.png")


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
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    x = np.arange(len(df))
    ax.bar(x - 0.2, df.litres_m, 0.4, label="volume (m litres)", color=GREY)
    ax.bar(x + 0.2, df.margin_m, 0.4, label="gross margin (R m)", color=ACCENT)
    ax.set_xticks(x)
    ax.set_xticklabels(df.province, rotation=30, ha="right", fontsize=8)
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("Volume and margin by province")
    return _finish(fig, "08_province_performance.png")


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
          FROM vivo_dev.bronze.fact_retail_fuel_sales
        UNION ALL SELECT 'silver', 'fact_retail_fuel_sales', count(*)
          FROM vivo_dev.silver.fact_retail_fuel_sales
        UNION ALL SELECT 'gold', 'fct_retail_fuel_sales', count(*)
          FROM vivo_dev.gold.fct_retail_fuel_sales
        UNION ALL SELECT 'gold', 'agg_site_daily_fuel', count(*)
          FROM vivo_dev.gold.agg_site_daily_fuel
        UNION ALL SELECT 'gold', 'agg_executive_daily_kpi', count(*)
          FROM vivo_dev.gold.agg_executive_daily_kpi
        UNION ALL SELECT 'gold', 'network_investment_scorecard', count(*)
          FROM vivo_dev.gold.network_investment_scorecard
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
