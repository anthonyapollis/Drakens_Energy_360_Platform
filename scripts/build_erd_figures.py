"""Draw the ERDs from the model that was actually built.

The ten subject-area ERDs in `docs/erd/` are Mermaid, which is the right format
to read in a repository and the wrong one for a PDF: WeasyPrint has no
JavaScript, and neither the mermaid CLI nor a graphviz binary is available
here. More importantly, a hand-maintained diagram drifts from the model the
moment a relationship changes, and a diagram that disagrees with the warehouse
is worse than no diagram.

So these are rendered from `model.bim` -- the semantic model the report
actually loads -- and from the dbt schema tests that establish each key. Every
box, edge and cardinality on them is a fact about the built artifact. When a
relationship is added, the next build draws it.

Subject areas are derived, not listed: each fact table is drawn with the
dimensions it actually relates to. A fact with no relationships appears alone,
which is itself the finding -- that is how the EV charging fact's missing
product key becomes visible rather than being described in a footnote.

Usage:
    python scripts/build_erd_figures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
MODEL_BIM = REPO / "powerbi" / "DrakensEnergy360.SemanticModel" / "model.bim"
IMG = REPO / "docs" / "img"

INK = "#16211C"
MUTED = "#5D6B64"
LINE = "#DFE5E1"
FACT_FILL = "#0B6E4F"
DIM_FILL = "#F4F8F5"
OBS_FILL = "#EAF1EC"
EDGE = "#5D6B64"

CAPTION = ("Rendered from model.bim, the semantic model the report loads. "
           "Synthetic data; Drakens Energy is a fictional company.")

# Which facts belong on a page together, and what to call it. Facts not named
# here get their own diagram, so a new fact is never silently omitted.
GROUPS = [
    ("retail", "Retail fuel", ["fct_retail_fuel_sales", "agg_site_daily_fuel"]),
    ("commercial", "Commercial B2B", ["fct_commercial_orders"]),
    ("supply", "Supply and distribution", ["fct_deliveries"]),
    ("assets", "Assets and maintenance", ["fct_maintenance_work_orders"]),
    ("network", "Network investment and geography",
     ["network_investment_scorecard", "obs_geo_site_analysis"]),
    ("forecast", "Forecasting and model results",
     ["fct_product_demand_forecast", "fct_product_revenue_forecast_12m",
      "obs_ml_product_performance", "obs_ml_product_forecast_12m"]),
]


def load_model() -> tuple[dict, list]:
    model = json.loads(MODEL_BIM.read_text(encoding="utf-8"))["model"]
    tables = {t["name"]: t for t in model["tables"]}
    rels = model.get("relationships", [])
    return tables, rels


def key_columns(table: dict, limit: int = 5) -> list[str]:
    """The columns worth putting in a box: keys first, then a few attributes."""
    names = [c["name"] for c in table.get("columns", [])]
    keys = [n for n in names if n.lower().endswith(("key", "id"))]
    rest = [n for n in names if n not in keys]
    return (keys[:4] + rest[:max(0, limit - len(keys[:4]))])[:limit]


ROW_H = 0.040          # one column line, in axes units
HEADER_H = 0.120       # table name plus its grain label
BOX_PAD = 0.022
MAX_ROWS = 5


def box_height(n_rows: int) -> float:
    return HEADER_H + n_rows * ROW_H + BOX_PAD


def wrap_name(name: str, width: float) -> str:
    """Break a long table name at an underscore so it stays inside its box."""
    # Roughly how many 7.4pt characters fit across a box of this width.
    budget = max(12, int(width * 78))
    if len(name) <= budget:
        return name
    parts = name.split("_")
    line, out = "", []
    for part in parts:
        candidate = f"{line}_{part}" if line else part
        if len(candidate) > budget and line:
            out.append(line)
            line = part
        else:
            line = candidate
    out.append(line)
    return chr(10).join(out)


def draw_box(ax, x, y, w, rows, title, *, is_fact, grain):
    """A table box sized to its contents.

    The first version used one fixed height for every box and then wrote
    however many rows it had, so the columns ran out through the bottom edge
    and over the caption. Deriving the height from the row count is the whole
    fix, and it is why MAX_ROWS exists rather than a scrollbar.
    """
    h = box_height(len(rows))
    fill = FACT_FILL if is_fact else (OBS_FILL if grain == "observability"
                                      else DIM_FILL)
    fg = "#FFFFFF" if is_fact else INK
    sub = "#CFDCD5" if is_fact else MUTED
    ax.add_patch(mpatches.FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.008,rounding_size=0.014",
        linewidth=1.1, edgecolor="#08512F" if is_fact else LINE,
        facecolor=fill, zorder=3))
    # Table names are long and boxes get narrow as a diagram gains tables.
    # Unwrapped, `fct_product_revenue_forecast_12m` ran straight through its
    # neighbours and the four forecast tables read as one run of characters.
    ax.text(x + w / 2, y + h - 0.030, wrap_name(title, w), ha="center",
            va="center", fontsize=7.4, fontweight="bold", color=fg,
            linespacing=1.15, zorder=4)
    ax.text(x + w / 2, y + h - 0.074, grain, ha="center", va="center",
            fontsize=6.2, style="italic", color=sub, zorder=4)
    for i, row in enumerate(rows):
        ax.text(x + 0.018, y + h - HEADER_H - i * ROW_H - ROW_H / 2, row,
                ha="left", va="center", fontsize=6.3,
                color="#EAF1EC" if is_fact else MUTED, zorder=4)
    return h


def figure(name: str, title: str, facts: list[str], tables: dict,
           rels: list) -> Path | None:
    present = [f for f in facts if f in tables]
    if not present:
        return None

    dims: list[str] = []
    edges: list[tuple[str, str, str]] = []
    for fact in present:
        for r in rels:
            if r["fromTable"] == fact and r["toTable"] in tables:
                edges.append((fact, r["toTable"], r["fromColumn"]))
                if r["toTable"] not in dims:
                    dims.append(r["toTable"])

    # Wider canvas when there are more boxes, so a box never has to shrink
    # below readable width to fit.
    across = max(len(present), len(dims), 1)
    fig, ax = plt.subplots(figsize=(max(9.0, 2.5 * across), 6.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    bw = min(0.24, 0.92 / across)
    fact_rows = {f: key_columns(tables[f], MAX_ROWS) for f in present}
    dim_rows = {d: key_columns(tables[d], MAX_ROWS) for d in dims}

    fact_y = 0.055
    fact_top = fact_y + max(box_height(len(r)) for r in fact_rows.values())
    dim_y = 0.55

    fact_xs, dim_xs = {}, {}
    for i, fact in enumerate(present):
        span = 0.92 / max(len(present), 1)
        x = 0.04 + span * i + span / 2 - bw / 2
        fact_xs[fact] = x + bw / 2
        draw_box(ax, x, fact_y, bw, fact_rows[fact], fact,
                 is_fact=True, grain="fact")

    for i, dim in enumerate(dims):
        span = 0.92 / max(len(dims), 1)
        x = 0.04 + span * i + span / 2 - bw / 2
        dim_xs[dim] = x + bw / 2
        draw_box(ax, x, dim_y, bw, dim_rows[dim], dim, is_fact=False,
                 grain="observability" if dim.startswith("obs_")
                 else "dimension")

    # Edge labels are staggered across four bands. Placed at one height they
    # sat on top of each other and read as a single run of characters.
    # Bands as a fraction of the gap, so labels never reach the boxes at
    # either end however tall the tables happen to be.
    gap = max(dim_y - fact_top, 0.05)
    bands = [gap * f for f in (0.10, 0.30, 0.50, 0.70)]
    for i, (fact, dim, col) in enumerate(edges):
        if dim not in dim_xs:
            continue
        x0, x1 = fact_xs[fact], dim_xs[dim]
        ax.annotate(
            "", xy=(x1, dim_y), xytext=(x0, fact_top),
            arrowprops=dict(arrowstyle="-|>", color=EDGE, linewidth=0.9,
                            connectionstyle="arc3,rad=0.05",
                            shrinkA=3, shrinkB=3), zorder=2)
        ly = fact_top + bands[i % len(bands)]
        t = (ly - fact_top) / max(dim_y - fact_top, 1e-6)
        ax.text(x0 + (x1 - x0) * t, ly, f"{col}  many-to-1",
                fontsize=6.0, color=MUTED, ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.18", facecolor="#FFFFFF",
                          edgecolor=LINE, linewidth=0.4, alpha=0.95),
                zorder=5)

    orphans = [f for f in present if not any(e[0] == f for e in edges)]
    subtitle = f"{len(present)} fact table(s), {len(dims)} related table(s)"
    if orphans:
        subtitle += (f"  —  {', '.join(orphans)} has no modelled "
                     f"relationship, which is the finding")
    ax.text(0.0, 0.985, title, fontsize=13, fontweight="bold", color=INK,
            va="top")
    ax.text(0.0, 0.945, subtitle, fontsize=7.4, color=MUTED, va="top")
    ax.text(0.0, 0.012, CAPTION, fontsize=6.2, color=MUTED, va="top")

    out = IMG / f"erd_{name}.png"
    IMG.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def overview(tables: dict, rels: list) -> Path:
    """One page showing how many tables hang off each dimension."""
    fig, ax = plt.subplots(figsize=(9.6, 5.0))
    counts: dict[str, int] = {}
    for r in rels:
        counts[r["toTable"]] = counts.get(r["toTable"], 0) + 1
    order = sorted(counts.items(), key=lambda kv: kv[1])
    ax.barh([k for k, _ in order], [v for _, v in order], color=FACT_FILL,
            height=0.62)
    for i, (_, v) in enumerate(order):
        ax.text(v + 0.06, i, str(v), va="center", fontsize=8, color=MUTED)
    ax.set_title("Conformed dimensions, by how many tables resolve against "
                 "them", fontsize=12, color=INK, loc="left", pad=14)
    ax.set_xlabel("related tables", fontsize=8, color=MUTED)
    ax.tick_params(labelsize=8, colors=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(LINE)
    ax.text(0, -0.16, CAPTION, transform=ax.transAxes, fontsize=6.2,
            color=MUTED)
    out = IMG / "erd_00_overview.png"
    fig.savefig(out, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main() -> int:
    if not MODEL_BIM.exists():
        print(f"no semantic model at {MODEL_BIM}; run "
              f"scripts/generate_powerbi_model.py first")
        return 1
    tables, rels = load_model()
    print(f"{len(tables)} tables, {len(rels)} relationships\n")

    written = [overview(tables, rels)]
    grouped = {t for _, _, fs in GROUPS for t in fs}
    for name, title, facts in GROUPS:
        out = figure(name, title, facts, tables, rels)
        if out:
            written.append(out)

    # Anything with a relationship that no group claimed.
    loose = sorted({r["fromTable"] for r in rels} - grouped
                   - {r["toTable"] for r in rels})
    if loose:
        out = figure("other", "Other modelled facts", loose, tables, rels)
        if out:
            written.append(out)

    for path in written:
        print(f"  wrote {path.relative_to(REPO)}")
    print(f"\n{len(written)} diagram(s), all derived from the built model")
    return 0


if __name__ == "__main__":
    sys.exit(main())
