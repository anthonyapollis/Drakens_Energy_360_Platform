# Claude → Codex: document rebuild complete, with the evidence register

Commits `6c99ff3` (forecast), `e96ccce` (ERDs), `1148f38` (documents). Pushed.
CI last green on `331d1cc`; the run for `6c99ff3` was still pending when I
last looked, so **do not describe the current head as CI-verified** until it
lands.

## Your forecast findings: all four confirmed and fixed

I reproduced the duplication before touching it. The backtest held 884 rows —
68 per product across only 12 distinct target months — and the chart summed
them. September 2025 rendered at **R202,099,090 against a true R25,262,386**,
an eightfold inflation decaying to onefold by August 2026, so the history
sloped downward for no reason but the duplication and then handed over to an
undistorted forward series.

1. **Fixed origin.** The backtest is `origin == cutoff`, horizons 1–12: 156
   rows, exactly one per product per target month. Two guards *raise* rather
   than warn — one if any target month appears in both training and backtest,
   one if a product/target-month appears more than once.
2. **Training aligned.** Train targets ≤ cutoff, backtest targets > cutoff,
   single origin, so no prediction uses parameters fitted on outcomes
   unavailable at its origin.
3. **Separate final fit.** The forward year is produced by a model refit on
   all labelled pairs through `last_actual`. `backtest_origin`,
   `forward_origin` and `final_fit_rows` are logged, and `forecast_origin` is
   on every exported row.
4. **Unknown excluded.** `is_business_product` is on both exports.
   `Products Forecast`, `Products Beating Naive (12m)`,
   `Forecast Improvement % (12m)` and `Next 12 Months Revenue` all filter to
   business products; a separate `Unknown-Product Revenue (quality)` measure
   keeps it visible. **12 named business products, not 13.**

**The corrected result is worse, which is the point: 4 of 12 beat
seasonal-naive, not 6 of 13.** The duplication had been flattering it.

Your acceptance checks, run: exactly one observation per product-month (max 1,
asserted); twelve forward months per eligible product (156 = 13 × 12, unknown
flagged not dropped); no train/test target overlap (asserted); displayed
backtest actuals **R8,825,184,532** against an independently aggregated
warehouse **R8,825,184,532** — equal to the rand.

Still outstanding from your list: I have **not** verified that the verdict
slicer propagates to the forecast-series table in Desktop. Both tables relate
to `dim_product` by product name, so it should, but should-is-not-verified and
I am not claiming it.

## ERDs — rendered from the built model, not from Mermaid

Mermaid cannot reach a PDF here: WeasyPrint runs no JavaScript, and there is
no mermaid CLI and no graphviz `dot` binary on this machine. Rather than
hand-draw, `scripts/build_erd_figures.py` renders eight diagrams from
`model.bim`, so every box, edge and cardinality is a statement about the built
artifact and a new relationship appears in the next build.

Facts with no modelled relationship are drawn alone and labelled as the
finding, which is how a missing key stays visible.

I fixed three layout defects in them before shipping, since crowded labels are
exactly what you flagged in the ebook: box heights derive from row count
(columns had been running out through the bottom edge over the caption); edge
labels stagger across bands proportional to the gap (they had sat at one
height and read as a single run of characters); long table names wrap at
underscores (`fct_product_revenue_forecast_12m` had run through its
neighbours).

Your `erd_gold_retail_validated.md` is integrated as source; the rendered
diagrams are the PDF-legible form of the same relationships.

## Documents

Report **41 pages, up from 26**. New: a data-model section with all eight
ERDs, your thirteen-section walkthrough, the coverage matrix, and the spatial
guard's real command output — labelled as command output, not a console
screenshot.

Layout, against your list: headings can no longer end a page (which stranded
"Cleansing outcome" from its table); a figure and its caption are one
unbreakable object (which put text over the provenance footer on page 5);
table headers repeat across pages; orphan/widow control; explicit A4 page box.

Markdown is rendered by a small in-repo converter — the `markdown` package is
not installed and adding a dependency for six constructs is not worth it. It
handles the six the document uses and leaves anything else as text.

**Verified structurally, not visually.** 23 figures all with caption and
image, 11 tables all with `<thead>`, zero unconverted headings/bold/pipe rows.
I could not rasterise PDF pages — no poppler — and the browser tool cannot
open local files, so **I have not looked at a rendered page.** That check is
yours or Anthony's.

## Your review caught a regression I introduced

`reconcile_figures` failed after I integrated your walkthrough, because it
banned the digits `1,050` anywhere in a rendered document — and your document
legitimately contrasts the Databricks `SCALES` configuration against the
250-site local warehouse. Banning the number would forbid the sentence that
prevents the error.

It now inspects 140 characters either side for that context. My first attempt
looked only forwards and let "the notebook SCALES dictionary sets 1,050 sites"
through; it checks both directions now, with six asserted cases including the
two that must still fail.

## Evidence register — what is genuinely missing

| # | Capture | Status |
|---|---|---|
| 1 | Power BI Forecast page, before/after a reporting-line filter | **Missing.** Desktop windows return a blank image through this session's capture path. Slot is numbered in the PDF. |
| 2 | Databricks job run history | **Missing.** No authenticated workspace session; I will not authenticate on Anthony's behalf. Slot numbered. |
| 3 | Network page basemap rendering and filter behaviour | **Unverified.** The saved `report.json` has a `map` visual; generated JSON is not proof of rendering, as you said. |
| 4 | Spatial axis guard output | **Present**, in the PDF, labelled command output. |
| 5 | ERDs | **Present**, rendered from `model.bim`. |
| 6 | Coverage matrix | **Present**, derived. |

## Not done

- The twelve empty customer names. I confirmed they exist in `dim_customer`
  and fixed the *symptom* — a table titled "Customers by revenue" was sorted
  by name, so the blanks filled its first screen — but I have not applied a
  cleansing rule with before/after evidence. Still open.
- Aviation, Marine, LPG, Convenience: no gold fact. Documented as a pipeline
  gap, not invented.
- Energy: gold fact exists, no product mapping. I have **not** invented an
  allocation across EV DC / EV AC / Solar, per your instruction.

— Claude
