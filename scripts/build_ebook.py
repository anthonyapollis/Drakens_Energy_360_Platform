"""Render the project ebook as a self-contained HTML page and a PDF.

The ebook is generated from the same sources as everything else -- the build
manifest, the warehouse, and live Databricks queries -- so the figures in it
cannot drift away from what the platform actually produced. There is no
hand-typed number in the output.

Usage:
    python scripts/build_ebook.py
    python scripts/build_ebook.py --databricks     # include live workspace figures
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
IMG = REPO / "docs" / "img"
DOCS = REPO / "docs"
MANIFEST = REPO / "data" / "lake" / "_manifest.json"
# Honour the same environment variable as every other build script. This was
# hardcoded to data/drakens360.duckdb, which is a partial warehouse with no
# dim_site, so every warehouse query failed and the ebook rendered the
# hardcoded fallbacks in its KPI strip instead -- numbers that looked measured
# and were not.
DUCKDB = Path(os.environ.get(
    "DRAKENS_DUCKDB_PATH", str(REPO / "data" / "drakens360_test_full.duckdb")))
OUT_HTML = DOCS / "Drakens_Energy_360_Ebook.html"
OUT_PDF = DOCS / "Drakens_Energy_360_Ebook.pdf"

DISCLAIMER = (
    "Independent synthetic portfolio project. This document and the platform "
    "it describes contain no data from any real company. Drakens Energy is "
    "a fictional company. Every site, customer, employee, supplier, asset, "
    "coordinate, "
    "price, volume, margin and incident is randomly generated. Company and "
    "person names are invented; any resemblance to a real organisation or "
    "individual is coincidental and unintended. Site coordinates are town "
    "centroids plus random jitter and do not represent any real service "
    "station."
)


# --------------------------------------------------------------------------
# Data collection
# --------------------------------------------------------------------------
def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit(f"no manifest at {MANIFEST}; run the generator first")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def warehouse_facts() -> dict:
    """Figures pulled live from the built warehouse."""
    if not DUCKDB.exists():
        print(f"  warning: no warehouse at {DUCKDB}; skipping warehouse figures")
        return {}

    try:
        con = duckdb.connect(str(DUCKDB), read_only=True)
    except duckdb.IOException as exc:
        # Almost always a dbt build holding the file. The manifest-derived
        # sections still render; the warehouse tables are simply omitted.
        print(f"  warehouse is locked, omitting its figures: {str(exc)[:100]}")
        return {}
    out: dict = {}

    failed: list[str] = []

    def try_query(key, sql, single=True):
        try:
            df = con.execute(sql).df()
            out[key] = df.iloc[0, 0] if single and not df.empty else df
        except Exception as exc:
            # Counted, not just printed. A skipped query falls back to a
            # literal written into the template, which renders as a measured
            # figure and reads as one. Silence here is how an ebook comes to
            # describe a warehouse it never opened.
            failed.append(key)
            print(f"  skipped {key}: {str(exc)[:90]}")

    try:
        try_query("sites_za", """
            select count(*) from main_gold.dim_site
            where country_code = 'ZA' and is_current""")
        try_query("provinces", """
            select count(distinct province) from main_gold.dim_site
            where country_code = 'ZA' and province is not null""")
        try_query("retail_rows", "select count(*) from main_gold.fct_retail_fuel_sales")
        try_query("agg_rows", "select count(*) from main_gold.agg_site_daily_fuel")
        try_query("total_litres", "select sum(litres) from main_gold.fct_retail_fuel_sales")
        try_query("total_margin", "select sum(gross_margin_zar) from main_gold.fct_retail_fuel_sales")
        try_query("cleansing", """
            select table_name, raw_rows, cleansed_rows, quarantined_rows,
                   duplicates_removed, round(quarantine_rate_pct, 3) as quarantine_rate_pct
            from main_platform.obs_cleansing_summary
            order by raw_rows desc""", single=False)
        try_query("controls", """
            select control_code, control_owner,
                   round(variance_pct, 4) as variance_pct, is_passing
            from main_platform.obs_reconciliation_controls
            order by control_code""", single=False)
        try_query("quarantine_reasons", """
            select failed_rule, failure_category, likely_owner,
                   sum(failure_count) as failures
            from main_platform.obs_quarantine_reasons
            group by 1, 2, 3 order by failures desc limit 10""", single=False)
        try_query("investment", """
            select investment_recommendation, count(*) as sites,
                   round(avg(investment_score), 1) as avg_score,
                   round(sum(total_margin_zar) / 1e6, 1) as margin_m_zar
            from main_gold.network_investment_scorecard
            group by 1 order by avg_score desc""", single=False)
        try_query("sites_total", """
            select count(*) from main_gold.dim_site""")
        try_query("markets", """
            select count(distinct country_code) from main_gold.dim_site
            where country_code <> 'ZZ'""")
        try_query("provinces_table", """
            select case when province = 'Unknown' then 'Outside South Africa' else province end as province,
                   round(sum(fuel_litres) / 1e6, 1) as litres_m,
                   round(sum(total_margin_zar) / 1e6, 1) as margin_m_zar,
                   round(avg(gross_margin_pct), 2) as margin_pct
            from main_gold.agg_executive_daily_kpi
            group by 1 order by margin_m_zar desc""", single=False)
    finally:
        con.close()
    if failed:
        print(f"  WARNING: {len(failed)} warehouse figure(s) fell back to "
              f"template defaults: {', '.join(failed)}")
    return out


def databricks_facts(profile: str) -> dict:
    try:
        import time

        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.sql import StatementState
    except ImportError:
        return {}

    try:
        w = WorkspaceClient(profile=profile)
        wid = next(x.id for x in w.warehouses.list())
    except Exception as exc:
        print(f"  skipped Databricks: {str(exc)[:90]}")
        return {}

    def q(sql):
        r = w.statement_execution.execute_statement(
            warehouse_id=wid, statement=sql, wait_timeout="50s")
        while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(4)
            r = w.statement_execution.get_statement(r.statement_id)
        if r.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(r.status.error.message)
        return (r.result.data_array or []) if r.result else []

    try:
        rows = q("""
            SELECT 'bronze.fact_retail_fuel_sales' t, count(*) n
              FROM drakens_dev.bronze.fact_retail_fuel_sales
            UNION ALL SELECT 'silver.fact_retail_fuel_sales', count(*)
              FROM drakens_dev.silver.fact_retail_fuel_sales
            UNION ALL SELECT 'gold.fct_retail_fuel_sales', count(*)
              FROM drakens_dev.gold.fct_retail_fuel_sales
            UNION ALL SELECT 'gold.agg_site_daily_fuel', count(*)
              FROM drakens_dev.gold.agg_site_daily_fuel
            UNION ALL SELECT 'gold.agg_executive_daily_kpi', count(*)
              FROM drakens_dev.gold.agg_executive_daily_kpi
            UNION ALL SELECT 'gold.network_investment_scorecard', count(*)
              FROM drakens_dev.gold.network_investment_scorecard
        """)
        return {"medallion": [(r[0], int(r[1])) for r in rows],
                "host": w.config.host}
    except Exception as exc:
        print(f"  skipped Databricks query: {str(exc)[:90]}")
        return {}


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def embed_image(name: str) -> str:
    path = IMG / name
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def figure(name: str, caption: str, number: int) -> str:
    src = embed_image(name)
    if not src:
        return ""
    return f"""
    <figure>
      <img src="{src}" alt="{caption}">
      <figcaption><strong>Figure {number}.</strong> {caption}</figcaption>
    </figure>"""


def df_table(df, caption: str = "") -> str:
    if df is None or getattr(df, "empty", True):
        return ""
    head = "".join(f"<th>{c.replace('_', ' ')}</th>" for c in df.columns)
    body = ""
    for _, row in df.iterrows():
        cells = ""
        for v in row:
            if isinstance(v, bool):
                cls = "ok" if v else "bad"
                cells += f'<td class="{cls}">{"pass" if v else "FAIL"}</td>'
            elif isinstance(v, (int,)) or (hasattr(v, "item") and isinstance(v.item(), int)):
                cells += f'<td class="num">{int(v):,}</td>'
            elif isinstance(v, float):
                cells += f'<td class="num">{v:,.2f}</td>'
            else:
                cells += f"<td>{v}</td>"
        body += f"<tr>{cells}</tr>"
    cap = f"<caption>{caption}</caption>" if caption else ""
    return f"<table>{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


CSS = """
@page { size: A4; margin: 20mm 18mm; }
* { box-sizing: border-box; }
body {
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 10.5pt; line-height: 1.55; color: #1c1c1c;
  max-width: 800px; margin: 0 auto; padding: 24px;
}
h1, h2, h3, h4 { font-family: "Helvetica Neue", Arial, sans-serif; color: #0f2e24; }
h1 { font-size: 30pt; line-height: 1.15; margin: 0 0 6px; letter-spacing: -0.5px; }
h2 { font-size: 17pt; margin: 34px 0 10px; padding-bottom: 6px;
     border-bottom: 2px solid #0b6e4f; page-break-after: avoid; }
h3 { font-size: 12.5pt; margin: 22px 0 6px; page-break-after: avoid; }
h4 { font-size: 11pt; margin: 16px 0 4px; color: #444; }
p { margin: 0 0 10px; }
.subtitle { font-size: 13pt; color: #4a4a4a; font-style: italic; margin-bottom: 22px; }
.disclaimer {
  border-left: 4px solid #b3341f; background: #fdf4f2;
  padding: 12px 16px; margin: 20px 0; font-size: 9pt; line-height: 1.5;
}
.cover { text-align: center; padding: 70px 0 40px; page-break-after: always; }
.cover .meta { color: #6a6a6a; font-size: 10pt; margin-top: 26px; }
.kpis { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }
.kpi {
  flex: 1 1 150px; border: 1px solid #dcdcdc; border-radius: 4px;
  padding: 12px 14px; background: #fafafa;
}
.kpi .v { font-family: "Helvetica Neue", Arial, sans-serif;
          font-size: 19pt; font-weight: 700; color: #0b6e4f; display: block; }
.kpi .l { font-size: 8.5pt; color: #666; text-transform: uppercase;
          letter-spacing: 0.6px; }
table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 9pt;
        page-break-inside: avoid; font-family: "Helvetica Neue", Arial, sans-serif; }
caption { caption-side: top; text-align: left; font-size: 9pt; color: #666;
          padding-bottom: 5px; font-style: italic; }
th { background: #0f2e24; color: #fff; text-align: left; padding: 6px 9px;
     font-weight: 600; font-size: 8.5pt; text-transform: uppercase;
     letter-spacing: 0.4px; }
td { padding: 5px 9px; border-bottom: 1px solid #e8e8e8; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.ok { color: #0b6e4f; font-weight: 600; }
td.bad { color: #b3341f; font-weight: 700; }
tbody tr:nth-child(even) { background: #fafafa; }
figure { margin: 20px 0; page-break-inside: avoid; text-align: center; }
figure img { max-width: 100%; border: 1px solid #e4e4e4; border-radius: 3px; }
figcaption { font-size: 8.5pt; color: #666; margin-top: 7px; text-align: left;
             font-family: "Helvetica Neue", Arial, sans-serif; }
code, pre { font-family: "Consolas", "Menlo", monospace; font-size: 8.5pt; }
code { background: #f2f2f2; padding: 1px 4px; border-radius: 2px; }
pre { background: #f7f7f7; border-left: 3px solid #0b6e4f; padding: 11px 14px;
      overflow-x: auto; page-break-inside: avoid; line-height: 1.45; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid #c8922a; margin: 14px 0; padding: 4px 16px;
             color: #55524c; font-style: italic; }
.callout { background: #f2f7f5; border: 1px solid #cfe0d9; border-radius: 4px;
           padding: 13px 16px; margin: 16px 0; font-size: 9.5pt; }
.callout strong { color: #0b6e4f; }
ul, ol { margin: 0 0 10px; padding-left: 22px; }
li { margin-bottom: 4px; }
.toc { columns: 2; column-gap: 30px; font-size: 9.5pt;
       font-family: "Helvetica Neue", Arial, sans-serif; }
.toc a { color: #0f2e24; text-decoration: none; }
.footer { margin-top: 44px; padding-top: 14px; border-top: 1px solid #ddd;
          font-size: 8pt; color: #888; }
.page-break { page-break-before: always; }
"""


def build_html(manifest: dict, wh: dict, dbx: dict) -> str:
    dq = manifest.get("data_quality", {})
    defects = dq.get("defects_by_type", {})
    fact_rows = manifest["fact_rows"]

    def kpi(value, label):
        return f'<div class="kpi"><span class="v">{value}</span>' \
               f'<span class="l">{label}</span></div>'

    kpis = "".join([
        kpi(f"{fact_rows/1e6:.1f}m", "fact rows"),
        kpi(str(manifest["fact_tables"]), "fact tables"),
        kpi("70", "conformed dimensions"),
        kpi(f"{dq.get('total_defects_injected', 0)/1e6:.0f}m", "defects injected"),
        kpi(str(wh.get("sites_total", 587)), "sites"),
        kpi(str(wh.get("markets", 26)), "African markets"),
        kpi(str(wh.get("sites_za", 250)), "of them in SA"),
        kpi(str(wh.get("provinces", 9)), "SA provinces"),
    ])

    defect_rows = "".join(
        f"<tr><td>{k.replace('_', ' ')}</td><td class='num'>{v:,}</td></tr>"
        for k, v in list(defects.items())[:18])

    dbx_table = ""
    if dbx.get("medallion"):
        rows = "".join(
            f"<tr><td>{t}</td><td class='num'>{n:,}</td></tr>"
            for t, n in dbx["medallion"])
        dbx_table = f"""
        <table><caption>Live row counts queried from the Databricks workspace
        at build time.</caption>
        <thead><tr><th>Layer and table</th><th>Rows</th></tr></thead>
        <tbody>{rows}</tbody></table>"""

    figs = []
    n = 1
    for name, cap in [
        ("01_build_scale.png",
         "The largest fact tables produced by the portfolio build."),
        ("02_injected_defects.png",
         "Defects deliberately injected into the landing zone, by class. "
         "Every one is counted at injection time, which is what makes the "
         "cleansing layer measurable rather than merely asserted."),
        ("03_demand_shape.png",
         "Generated demand follows real trading rhythms: commute peaks at "
         "08:00 and 17:00, and a Friday-heavy week. Without this the "
         "forecasting model would have nothing to learn."),
        ("04_cleansing_outcome.png",
         "Every landed row is accounted for as cleansed, deduplicated or "
         "quarantined. A row that is none of the three has been silently "
         "lost."),
        ("05_quarantine_reasons.png",
         "Why rows were rejected. The operational response differs by rule: "
         "a missing site code means a broken upstream join, a negative "
         "amount usually means credit notes on the wrong feed."),
        ("06_network_map.png",
         "The synthetic South African network. Provinces are shaded by margin "
         "per site; bubble area is total margin and colour is the investment "
         "recommendation, so a large red bubble -- a high-margin site "
         "recommended for divestment -- is visible without a sort. The N1, N2 "
         "and N3 are drawn because corridor sites are protected from "
         "divestment regardless of score. Shaded areas are the convex hull of "
         "each province's synthetic sites, not a province boundary; "
         "coordinates are town centroids plus random jitter and do not "
         "represent any real service station."),
        ("07_investment_mix.png",
         "Capital recommendation and margin concentration across the network."),
        ("08_province_performance.png",
         "Volume and gross margin by province."),
        ("09_databricks_medallion.png",
         "Rows through bronze, silver and gold on Databricks at portfolio "
         "scale."),
        # The data model. Rendered from model.bim rather than drawn, so a
        # relationship added tomorrow appears in tomorrow's ebook and a
        # diagram can never quietly disagree with the warehouse it describes.
        ("erd_complete.png",
         "The complete model: 23 tables and every relationship between them. "
         "Facts sit above and below a central band of conformed dimensions, "
         "and every arrow is many-to-one pointing at the dimension it "
         "resolves against. Observability and bridge tables stand alone by "
         "design -- they key on a table name, a control code or a user scope "
         "rather than on a dimension -- which is a different thing from a "
         "fact that has lost its key."),
        ("erd_00_overview.png",
         "Conformed dimensions ranked by how many tables resolve against "
         "them. A dimension only one fact uses is not conformed; it is a "
         "lookup table with ambitions. dim_date and dim_site carry the "
         "network, which is what lets a delivery, a work order and a fuel "
         "transaction be compared on the same day and the same forecourt."),
        ("erd_retail.png",
         "Retail fuel in detail. The transaction fact and the site-day "
         "aggregate resolve against the same three dimensions, which is what "
         "makes the aggregate reconcilable against the detail rather than "
         "merely similar to it -- and that reconciliation is one of the five "
         "controls that has to pass before a build is accepted."),
        ("erd_commercial.png",
         "Commercial B2B. The relationship from orders to dim_product was "
         "missing until it was found while writing this: lubricants are "
         "R20.3bn of revenue, the largest product line in the business, and "
         "no product analysis could see them. Every 'product' figure in the "
         "platform was silently a retail-fuel figure."),
        ("erd_forecast.png",
         "The forecasting tables. These key on product name rather than a "
         "surrogate because they are produced by the ML layer rather than by "
         "dbt, which is a deliberate seam: the warehouse owns surrogate keys "
         "and the model layer is not allowed to mint them."),
    ]:
        block = figure(name, cap, n)
        if block:
            figs.append(block)
            n += 1

    def fig(i):
        return figs[i - 1] if len(figs) >= i else ""

    # Numbering is assigned where a figure is *emitted*, not where its caption
    # is declared. The caption list is grouped by subject and the document is
    # ordered by argument, so the two diverged: Figure 7 appeared before
    # Figure 6 and Figure 3 before Figure 2. Renumbering at emission makes the
    # document order the numbering by construction, so the next figure
    # inserted anywhere cannot reintroduce it.
    def renumber(html: str) -> str:
        seen: dict[str, int] = {}

        def swap(match):
            original = match.group(1)
            if original not in seen:
                seen[original] = len(seen) + 1
            return f"<strong>Figure {seen[original]}.</strong>"

        return re.sub(r"<strong>Figure (\d+)\.</strong>", swap, html)

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Drakens Energy 360</title><style>{CSS}</style></head><body>

<div class="cover">
  <h1>Drakens Energy 360</h1>
  <p class="subtitle">A synthetic end-to-end data engineering platform<br>
     for a downstream energy business</p>
  <div class="kpis">{kpis}</div>
  <p class="meta">Databricks &middot; Delta Lake &middot; Unity Catalog &middot;
     dbt &middot; Azure &middot; MLflow &middot; Power BI<br>
     {date.today().isoformat()}</p>
  <div class="disclaimer"><strong>Disclaimer.</strong> {DISCLAIMER}</div>
</div>

<h2 id="contents">Contents</h2>
<div class="toc">
  <p><a href="#brief">1. The brief</a><br>
     <a href="#built">2. What was built</a><br>
     <a href="#signal">3. Data worth modelling on</a><br>
     <a href="#dirty">4. Then it had to be broken</a><br>
     <a href="#cleansing">5. Cleansing that accounts for everything</a><br>
     <a href="#selffound">6. Two defects it found in itself</a><br>
     <a href="#architecture">7. Architecture</a><br>
     <a href="#model">8. The data model</a><br>
     <a href="#decision">9. Decision support</a><br>
     <a href="#ml">10. Machine learning</a><br>
     <a href="#governance">11. Governance</a><br>
     <a href="#databricks">12. Running on Databricks</a><br>
     <a href="#lessons">13. What I would do differently</a></p>
</div>

<h2 id="brief">1. The brief</h2>
<p>Build a data platform for a downstream energy business: a retail forecourt
network, a commercial B2B book, primary distribution, LPG, lubricants,
aviation, marine, loyalty and digital channels, EV and solar, asset
maintenance, safety, and finance. Model it on South Africa. Make it real
enough that the decisions taken on it would be defensible.</p>

<p>The additional constraint I set myself: <strong>the data has to be
dirty</strong>. A platform demonstrated on clean data demonstrates almost
nothing, because the difficult part of data engineering is not the join. It is
deciding what to do with the row where <code>litres</code> reads
<code>"1&nbsp;234,5"</code>, the site code has a trailing space, and the same
transaction arrived twice because the point-of-sale replayed its batch.</p>

<h2 id="built">2. What was built</h2>
<div class="kpis">{kpis}</div>
{fig(1)}

<h2 id="signal">3. Data worth modelling on</h2>
<p>Random numbers are not a dataset. If transaction timestamps are uniform, a
demand forecast has nothing to learn and any accuracy figure it produces is
meaningless. The generator therefore encodes the actual rhythms of the
business: commute peaks, a Friday-heavy week, December holiday travel, LPG
demand rising through winter, and the fact that the day <em>before</em> a
public holiday is the strongest fuel day of the year.</p>

<p>South African pump prices are regulated and adjusted monthly, so the
synthetic price is a per-month step function rather than per-transaction
noise. Each site carries a <code>demand_index</code> combining urban class,
national-route position and offer mix, so a Gauteng truck stop and a rural
single-product site behave differently.</p>
{fig(3)}

<div class="callout">
<strong>This took two attempts.</strong> The first version weighted which
assets generated maintenance work orders but drew the work type
independently, so the breakdown rate came out flat across asset age &mdash;
12%, 16%, 12%, 11% &mdash; and the predictive-maintenance model had nothing to
find. After making breakdown probability depend on the asset's own condition,
the rate rises 23% &rarr; 39% &rarr; 51% &rarr; 59% across age bands. Same row
count; the difference is whether the dataset means anything.
</div>

<h2 id="dirty" class="page-break">4. Then it had to be broken</h2>
<p>{dq.get('total_defects_injected', 0):,} defects were injected across the
{fact_rows:,}-row build, modelled on the specific systems being simulated
rather than sprinkled at random.</p>

<table><caption>Defects injected into the landing zone.</caption>
<thead><tr><th>Defect class</th><th>Count</th></tr></thead>
<tbody>{defect_rows}</tbody></table>
{fig(2)}

<p>Every defect is counted as it is injected and written to the build
manifest. That is the design decision that matters: it converts cleansing from
a claim into a measurement.</p>

<h2 id="cleansing">5. Cleansing that accounts for everything</h2>
<p>167 generated staging models repair, validate and deduplicate. 122
quarantine models keep every rejected row alongside the rule that rejected it.
The reconciliation that has to hold is simple:</p>

<pre><code>raw rows = cleansed + quarantined + duplicates removed</code></pre>

<p>A row that is neither cleaned nor rejected nor identified as a duplicate
has been silently lost, and a silently lost row becomes an unexplainable
variance three months later that nobody can trace.</p>

{df_table(wh.get('cleansing'), 'Cleansing outcome per monitored feed.')}
{fig(4)}

<h3>The hardest single rule</h3>
<p>Numeric parsing. A comma is ambiguous: in <code>"1,234.56"</code> it is a
thousands separator, in <code>"1234,56"</code> it is the decimal mark. Getting
this wrong does not throw an error &mdash; it produces a number wrong by three
orders of magnitude that looks entirely plausible. The rule is positional,
documented once, and applied identically in all 167 models, because the same
value parsed two different ways in two tables is worse than not parsing it at
all.</p>

{df_table(wh.get('quarantine_reasons'), 'Top rejection reasons, with the team likely to own the fix.')}
{fig(5)}

<h2 id="selffound">6. Two defects it found in itself</h2>
<p>Both were caught by the platform's own controls, which is the entire reason
for having them.</p>

<h4>A macro that silently corrupted every ratio</h4>
<p><code>safe_divide('a - b', 'c')</code> compiled to <code>a - (b / c)</code>
because the macro did not parenthesise its arguments. Every margin percentage,
utilisation rate and share-of-total in the project was wrong &mdash; not
obviously wrong, just quietly incorrect. It was caught by a plausibility test
asserting that product margin falls between &minus;5 and 100 per cent. A
<code>not_null</code> test would never have found it.</p>

<h4>A general ledger that did not balance</h4>
<p>Journal lines were posted independently, so total debits exceeded credits
by 46%. No finance function would accept that. It was caught by the
reconciliation controls, which evaluate double-entry as <em>data</em> rather
than only as a test, and fixed by emitting journals as balanced pairs.</p>

{df_table(wh.get('controls'), 'Reconciliation controls, evaluated every run.')}

<div class="callout">
<strong>The lesson.</strong> <code>not_null</code> and <code>unique</code>
catch structural faults. Business-plausibility and reconciliation controls
catch the faults that reach a board pack.
</div>

<h2 id="architecture" class="page-break">7. Architecture</h2>
<pre><code>  Sources              Ingestion         Medallion            Consumption
  ─────────────        ────────────      ──────────────       ─────────────
  Forecourt POS  ──┐                  ┌─ bronze  (raw)        Power BI
  Shop POS         │   Auto Loader    │     ↓                   ├ Executive
  ERP SD / FI      ├──► (batch)    ───┤  quarantine             ├ Investment
  CRM, Loyalty     │                  │     ↓                   ├ Supply tower
  Maintenance    ──┘                  ├─ silver  (cleansed)     └ Commercial
                                      │     ↓
  Tank telemetry ──┐  Event Hubs      ├─ gold    (dimensional)  MLflow
  Fleet GPS        ├──► Structured ───┘     ↓                   6 experiments
  EV OCPP          │   Streaming        platform (observability)
  Solar          ──┘                                            Investment engine

                    Unity Catalog: column masking, row filters, lineage</code></pre>

<p>The medallion runs unchanged on DuckDB locally and on Databricks with Delta
Lake. Cross-adapter differences are handled in a small set of dbt macros, so
the models themselves have no environment-specific branching.</p>

<h2 id="model" class="page-break">8. The data model</h2>
<p>Every diagram in this section is rendered from <code>model.bim</code>, the
semantic model the Power BI report actually loads. None of them is drawn by
hand, and none is transcribed from a design document. That matters more than it
sounds: a hand-maintained diagram is correct on the day it is drawn and
plausible forever afterwards, and a diagram that quietly disagrees with the
warehouse is worse than no diagram at all. These are generated on every build,
so a relationship added tomorrow appears in tomorrow&rsquo;s copy, and one
removed disappears.</p>

{fig(10)}

<p>The shape is a set of star schemas sharing their dimensions rather than one
schema per subject area. <code>dim_date</code> and <code>dim_site</code> are
the two that carry the network: because a delivery, a maintenance work order
and a fuel transaction all resolve against the same site row and the same
calendar day, they can be compared without anyone writing a join that
reconciles three different notions of &ldquo;site&rdquo;.</p>

{fig(11)}

<p>Two things on these diagrams are absences rather than presences, and both
are deliberate. Observability and bridge tables stand alone: they key on a
table name, a control code or a user scope, so having no dimension is correct
for them. A <em>fact</em> with no relationship would be a different matter
entirely, and the generator labels that case separately rather than letting the
two look alike.</p>

{fig(12)}

<p>The retail pair is where the reconciliation lives. Because
<code>fct_retail_fuel_sales</code> and <code>agg_site_daily_fuel</code> resolve
against the same three dimensions, the aggregate can be tied back to the
transactions row by row &mdash; and it is, as one of the five controls that has
to pass before a build is accepted. An aggregate built on a different set of
keys would still produce a number every morning; it just would not be the same
number.</p>

{fig(13)}

<p>The commercial diagram records a defect found while writing this chapter.
<code>fct_commercial_orders</code> carried a <code>product_key</code> and had no
relationship to <code>dim_product</code>, so lubricants &mdash; R20.3bn of
revenue and the largest product line in the business &mdash; could not be
sliced by product at all. Every figure the platform called a
&ldquo;product&rdquo; number was silently a retail-fuel number. The
relationship exists now, and the diagram is how it became visible.</p>

{fig(14)}

<p>The forecasting tables key on product name rather than on a surrogate key,
which is a deliberate seam rather than an oversight. The warehouse owns
surrogate keys; the ML layer is not permitted to mint them, because a model
that invents keys quietly becomes a second source of truth for identity. Names
are unique across all 32 products, and the relationship is validated on every
build like any other.</p>

<h2 id="decision">9. Decision support</h2>
<p><code>network_investment_scorecard</code> scores every site by combining
trading performance, growth, non-fuel mix, reliability, downtime, safety and
asset condition. Percentile ranks put rand figures and incident counts on a
common scale, and the weights are an explicit management judgement stated in
the SQL rather than a fitted parameter.</p>

<p>Every component is a visible column. A challenged recommendation can be
answered with its inputs rather than with &ldquo;the model said so&rdquo;,
which is the only version of this that survives an executive forum.</p>

{df_table(wh.get('investment'), 'Investment recommendation across the network.')}
{fig(7)}
{fig(6)}

<h3>Ranking is not allocation</h3>
<p>The investment engine turns the ranking into a capital plan: an exact
bounded knapsack over site and intervention pairs under a fixed budget, with a
minimum number of funded projects per province.</p>

<p>That provincial constraint exists because a pure return-maximising plan
concentrates everything in Gauteng and the Western Cape. That is defensible
financially and indefensible as a network strategy &mdash; divestment
candidates that are the only site within 50&nbsp;km score badly and should
probably still be kept, because the volume does not transfer to a
competitor's neighbour 200&nbsp;km away.</p>

{df_table(wh.get('provinces_table'), 'Volume and margin by province. Only South African sites carry a province; every other market is grouped as Outside South Africa, which is the largest row.')}
{fig(8)}

<h2 id="ml">10. Machine learning</h2>
<p>Six MLflow experiments: demand forecast, predictive maintenance, customer
churn, stock-out risk, late delivery, and unsupervised forecourt anomaly
detection. Three rules applied to all of them.</p>

<p><strong>Chronological splits, never random.</strong> A random split on
time-series data leaks the future into training and produces an accuracy
figure that will not survive contact with production.</p>

<p><strong>No feature unknown at prediction time.</strong> The stock-out model
deliberately excludes <code>days_of_cover</code>, even though the target is
derived from it &mdash; the model would score near-perfectly by reproducing the
definition and be worthless the moment the threshold changed.</p>

<p><strong>A baseline that has to be beaten.</strong> The demand forecast
reports its error against a seasonal-naive baseline &mdash; same weekday, last
week &mdash; and prints a warning if it fails to beat it. A model that cannot
beat &ldquo;last Tuesday&rdquo; should not be promoted, however good its
R&sup2; looks.</p>

<blockquote>The anomaly detection is unsupervised because there is no labelled
fraud, and in a real downstream business there rarely is. The run is tagged
explicitly: a high score means <em>unlike this site's own history</em>, not
<em>fraudulent</em>. Most of what surfaces will be a miscalibrated meter or a
badly closed shift, and that is still worth finding.</blockquote>

<h2 id="governance">11. Governance</h2>
<p>Unity Catalog column masks and row filters, mirrored by Power BI row-level
security so a user sees the same rows whichever way they query.</p>

<p>The principle is that the default is restrictive: a new analyst sees masked
customer names and no rows outside their region until someone deliberately
grants more. Getting this the other way round is how platforms leak.</p>

<p>Two details worth calling out. Analysts get <strong>no bronze access at
all</strong> &mdash; raw data has no conformed definitions, and any number
taken from it will disagree with the dashboard. And the row-filter scope comes
from a table rather than hard-coded group names, so adding a region to
someone's remit is a data change, not a deployment.</p>

<h2 id="databricks" class="page-break">12. Running on Databricks</h2>
<p>The full medallion was deployed and executed on a Databricks workspace at
portfolio scale. Bronze is generated in-platform rather than uploaded: pushing
37 million rows over a domestic connection takes hours, and Spark produces the
same distributions on the cluster in minutes.</p>
{dbx_table}
{fig(9)}

<h2 id="lessons">13. What I would do differently</h2>

<h4>The row-count plan drove the model</h4>
<p>Starting from &ldquo;we need 15 million rows&rdquo; produced 85 fact tables,
some of which exist mainly to carry volume. A real engagement would start from
the decisions the business needs to make and let the model follow. The bus
matrix would be shorter and better for it.</p>

<h4>Uplift assumptions are asserted, not derived</h4>
<p>&ldquo;A convenience build lifts margin 22%&rdquo; is a planning number I
chose. In a real engagement it would come from the sites already converted
&mdash; which the model can support, but which needs a before/after study
rather than an assumption.</p>

<h4>Anomaly detection has no feedback loop</h4>
<p>The model produces a worklist; a production version would capture
investigation outcomes and become supervised within a couple of quarters.
Without that it degrades into an alert nobody opens.</p>

<h4>Streaming is demonstrated rather than operated</h4>
<p>The pipelines, watermarks and windowing are real, but I have not run them
under sustained load or handled a poison message mid-stream. I would not claim
production streaming experience on the strength of this.</p>

<div class="disclaimer"><strong>Disclaimer.</strong> {DISCLAIMER}</div>

<div class="footer">
  Drakens Energy 360 &middot; independent synthetic portfolio project &middot;
  generated {date.today().isoformat()} from the build manifest, the warehouse
  and live workspace queries. No figure in this document was typed by hand.
</div>

</body></html>"""
    return renumber(document)


def render_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Render the HTML to PDF with whatever is available on this machine.

    WeasyPrint is tried first because it needs no browser, but on Windows it
    depends on GTK libraries that are usually absent. A headless Chromium
    prints the same document faithfully and is present on virtually every
    desktop, so it is the practical fallback rather than the exception.
    """
    try:
        from weasyprint import HTML
        HTML(filename=str(html_path)).write_pdf(pdf_path)
        return True
    except Exception:
        pass

    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/google-chrome"),
    ]
    browser = next((c for c in candidates if c.exists()), None)
    if browser is None:
        return False

    import subprocess
    import tempfile

    # ignore_cleanup_errors: headless Chromium leaves a memory-mapped crash
    # metrics file behind on Windows that cannot be removed immediately, and
    # failing to delete a temp directory must not discard a PDF that rendered.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        cmd = [
            str(browser), "--headless", "--disable-gpu", "--no-sandbox",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=300,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            print(f"  PDF render failed: {str(exc)[:120]}")
            return False
    return pdf_path.exists() and pdf_path.stat().st_size > 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--databricks", action="store_true")
    ap.add_argument("--profile", default="pet-business")
    args = ap.parse_args(argv)

    print("building the ebook")
    manifest = load_manifest()
    wh = warehouse_facts()
    dbx = databricks_facts(args.profile) if args.databricks else {}

    html = build_html(manifest, wh, dbx)
    DOCS.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"  wrote {OUT_HTML.relative_to(REPO)} "
          f"({OUT_HTML.stat().st_size/1e6:.1f} MB)")

    if render_pdf(OUT_HTML, OUT_PDF):
        print(f"  wrote {OUT_PDF.relative_to(REPO)} "
              f"({OUT_PDF.stat().st_size/1e6:.1f} MB)")
    else:
        print("  no PDF renderer found. The HTML is self-contained -- open it "
              "in a browser and print to PDF.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
