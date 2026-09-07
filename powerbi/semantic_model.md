# Power BI semantic model design

> Independent synthetic portfolio project. no data from any real company. All figures are generated.

## Design position

The semantic model is deliberately thin. Business definitions — OTIF, stock-out
risk, gross margin percentage, investment score — are computed in the gold
layer, not in DAX. Every definition that lives in a report gets reimplemented
by the next person who builds a report, and two dashboards eventually disagree
in front of an executive with no way to say which is right.

DAX here does three things and nothing else:

1. aggregates measures that are additive in gold,
2. handles time intelligence, which genuinely belongs in the model,
3. handles the semi-additive cases (inventory) that SQL cannot express as a
   single stored value.

## Storage mode

| Table | Mode | Reason |
|---|---|---|
| `agg_executive_daily_kpi` | Import | 8,766 rows. Instant, and the executive page must never wait on a warehouse. |
| `network_investment_scorecard` | Import | 1,050 rows. |
| `agg_site_daily_fuel` | Import | ~975k rows. Compresses well; drives all trend visuals. |
| `dim_date`, `dim_site`, `dim_product`, `dim_customer` | Dual | Small enough to import, but Dual lets them join DirectQuery facts without a bridge. |
| `fct_retail_fuel_sales` | DirectQuery | 5m rows. Only reached on drill-through to transaction detail, which is rare and deserves to be slow rather than making the model enormous. |
| `fct_inventory_position` | DirectQuery | Near-real-time; an imported copy would be stale by definition. |
| `obs_table_freshness`, `obs_cleansing_summary` | Import | Tiny; refreshed with the model. |

The composite model is the point: the aggregate answers 95% of questions
instantly, and the transaction fact is there when someone needs to see the
actual line.

## Relationships

All single-direction, one-to-many, from dimension to fact. Bi-directional
filtering is not used anywhere.

```
dim_date[date_key]        1 --> *  agg_site_daily_fuel[date_key]
dim_date[date_key]        1 --> *  agg_executive_daily_kpi[date_key]
dim_date[date_key]        1 --> *  fct_retail_fuel_sales[date_key]
dim_date[date_key]        1 --> *  fct_deliveries[date_key]
dim_date[date_key]        1 --> *  fct_inventory_position[date_key]

dim_site[site_key]        1 --> *  agg_site_daily_fuel[site_key]
dim_site[site_key]        1 --> *  fct_retail_fuel_sales[site_key]
dim_site[site_key]        1 --> 1  network_investment_scorecard[site_key]

dim_product[product_key]  1 --> *  fct_retail_fuel_sales[product_key]
dim_customer[customer_key] 1 --> * fct_commercial_orders[customer_key]
```

`dim_date` is marked as the model's date table on `full_date`. Without that
mark, the time-intelligence functions below silently return wrong answers at
period boundaries.

### Why no bi-directional filters

Bi-directional relationships are the most common cause of a model that gives
different answers depending on which visual you look at, because they create
ambiguous filter paths that DAX resolves in ways nobody predicted. Where
cross-filtering is genuinely needed — filtering sites by whether they sold a
given product — it is done explicitly with `TREATAS` in the measure, which is
visible in the code rather than hidden in a relationship property.

## Row-level security

RLS mirrors the Unity Catalog row filter, so a user sees the same rows whether
they query through Power BI or directly in SQL. Two roles:

**`Regional Analyst`** — filtered to their provinces via the scope table:

```dax
[province] IN
    SELECTCOLUMNS(
        FILTER(
            bridge_security_user_scope,
            bridge_security_user_scope[user_principal] = USERPRINCIPALNAME()
                && bridge_security_user_scope[scope_type] = "province"
        ),
        "p", bridge_security_user_scope[scope_value]
    )
```

**`Executive`** — no row filter, but object-level security hides
`fct_retail_fuel_sales` and `dim_customer[customer_name]` entirely. Executives
need the aggregate, not the customer list, and the fastest way to cause a data
incident is to give everyone everything by default.

Applied to `dim_site` and allowed to propagate through the relationships, so
one filter secures every fact rather than needing a rule per table.

## Measure organisation

Measures live in a dedicated `_Measures` table with display folders:

```
_Measures
├── Volume
├── Revenue and Margin
├── Time Intelligence
├── Supply Chain
├── New Energy
├── Network Investment
└── Data Quality
```

## Refresh

Incremental refresh on `agg_site_daily_fuel` and `fct_retail_fuel_sales`:

- **Archive**: 3 years
- **Incremental window**: 10 days
- **Detect data changes**: on `_dbt_loaded_at`
- **Refresh policy**: only partitions whose `_dbt_loaded_at` moved are rebuilt

The 10-day window matches the `incremental_lookback_days` variable in
`dbt_project.yml`. If the two disagree, Power BI will either miss late-arriving
corrections or needlessly rebuild partitions, so they are documented as a pair
and changed together.

## Aggregation awareness

`agg_site_daily_fuel` is registered as a user-defined aggregation over
`fct_retail_fuel_sales`:

| Agg column | Summarisation | Detail column |
|---|---|---|
| `litres` | Sum | `fct_retail_fuel_sales[litres]` |
| `gross_sales_zar` | Sum | `fct_retail_fuel_sales[gross_sales_zar]` |
| `gross_margin_zar` | Sum | `fct_retail_fuel_sales[gross_margin_zar]` |
| `transaction_count` | Count | `fct_retail_fuel_sales[transaction_id]` |
| `date_key` | GroupBy | `fct_retail_fuel_sales[date_key]` |
| `site_key` | GroupBy | `fct_retail_fuel_sales[site_key]` |

A query grouped by month and province is answered from the aggregate without
touching the transaction fact. A query that also slices by payment method
falls through to DirectQuery automatically, because payment method is not in
the aggregate. This is what makes a 5-million-row model feel like a small one.

---

## Geospatial design

A downstream network is a geographic business. Where a site sits relative to a
corridor, a metro and its neighbours determines what it earns, so the map is
not decoration on this model — it is the primary navigation surface, and the
one page an executive opens first.

### Why Azure Maps and not the default map visual

Power BI ships three map visuals and they are not interchangeable.

| Visual | Used here for | Why not the others |
|---|---|---|
| **Azure Maps** | The network page: bubble layer, heat layer, reference layer | The only built-in visual supporting multiple simultaneous layers, GeoJSON reference layers and traffic/road context |
| **Shape map** | Province choropleth on the executive page | Deterministic — binds on a key in the supplied TopoJSON, so it cannot geocode a province to the wrong country |
| **Filled/bubble map (Bing)** | Not used | Geocodes text at render time. "Nelspruit" resolves to more than one place worldwide, and a silently mis-geocoded site is worse than no map |

The rule underneath all three: **never let a visual geocode.** Every site
carries `latitude` and `longitude` from `dim_site`, set to *Data category:
Latitude / Longitude* and summarisation *Don't summarize*. Leaving
summarisation on Sum is the single most common cause of a map that renders one
bubble in the Southern Ocean, because it averages nothing and sums everything.

### Layer stack on the network page

Azure Maps renders bottom to top; the order is what makes the page readable
rather than a wash of colour.

| # | Layer | Encoding | Answers |
|---|---|---|---|
| 1 | Reference layer | Province TopoJSON, filled by `[Margin per Site]` | Which regions earn |
| 2 | Heat map layer | Weighted by `[Fuel Volume (L)]`, radius 22px | Where demand concentrates, independent of site count |
| 3 | Bubble layer | Size = `[Gross Margin]`, colour = `Investment Recommendation` | Which individual sites to act on |
| 4 | Traffic / road overlay | Azure Maps roads | Corridor position, without shipping route geometry |

Layers 2 and 3 deliberately encode different things. The heat layer is
volume-weighted and ignores how many sites produce it, so a single very large
site and a cluster of small ones look different — which is exactly the
distinction a network planner needs and a bubble layer alone hides.

### Bubble encoding

```
Size    →  [Gross Margin]        continuous, area-proportional
Colour  →  Investment Recommendation   7-band ordered scale, invest → divest
Border  →  On National Route           white ring on corridor sites
Tooltip →  report page tooltip (below)
```

Colour is bound to the mart column, not to a DAX `SWITCH` written in the
report. Binding in the report means the next report rebuilds the bands from
memory and the two pages disagree about which sites are divestment
candidates — the same argument the gold layer exists to prevent.

The ordered palette runs dark green (`Invest - Maintain Leadership`) through
gold (`Hold - Strategic Coverage`) to red (`Divest Candidate`), so the two
categories that need explaining in a capital meeting — a strategically
protected site and a divestment candidate — are the two that do not look like
anything else on the page.

### ArcGIS for Power BI, and when it earns its place

Azure Maps covers the network page. ArcGIS for Power BI (the Esri visual that
ships with Power BI Desktop) does things Azure Maps cannot, and the honest
position is that it is worth the extra dependency on exactly two pages.

| Capability | Azure Maps | ArcGIS for Power BI |
|---|---|---|
| Bubble, heat and reference layers | Yes | Yes |
| Cartographic basemaps (topographic, imagery, dark grey canvas) | Limited | Full Esri basemap gallery |
| Drive-time and distance catchments | No | Yes |
| Demographic and lifestyle reference layers | No | Yes (Esri data, licensed) |
| Address-level geocoding at scale | No | Yes (credit-consuming) |
| Available without extra licensing | Yes | Standard tier only |

**Where it earns its place**

*Catchment analysis on the investment page.* The question a capital committee
asks about a divestment candidate is not "what does it earn" — the scorecard
answers that — but "who else covers this area if it goes". A five- and
ten-minute drive-time polygon around each candidate, with the other sites
inside it, answers that directly. A radius circle does not: a site ten
kilometres away across a mountain is not a substitute, and on a straight-line
buffer it looks like one.

*Corridor coverage.* Drive-time bands along the N1, N2 and N3 show where the
network has a genuine gap rather than merely a low site count. Coverage is a
function of travel time, not of how many dots fall inside a province.

**Where it does not.** Everyday operational pages stay on Azure Maps. ArcGIS
credits are consumed per geocode and per analysis operation, so a page that
refreshes hourly and re-runs a drive-time analysis each time turns a
cartography decision into a recurring bill. Catchments are computed once, on
demand, by an analyst — not on every dashboard refresh.

### Geocoding: why the platform never does it at render time

Every site in this model carries `latitude` and `longitude` from `dim_site`.
Nothing on any map page is geocoded by the visual, and that is a deliberate
constraint rather than an accident of the data being available.

Text geocoding fails in a specific and dangerous way. It does not error — it
returns a confident wrong answer. Several South African town names occur in
more than one province, and several occur in other countries entirely; a
visual asked to resolve `"Springs"` or `"Richmond"` from a text column will
resolve it to *something*, and the resulting bubble looks exactly like a
correct one. A map that is 3% wrong in a way nobody can see is worse than a
map that refuses to draw.

So the rule is enforced at three points:

1. **The dimension carries coordinates.** They are generated as a town
   centroid plus jitter, and they are the only source of position on any page.
2. **Data categories are set explicitly** — *Latitude* and *Longitude* on
   those columns, and summarisation set to *Don't summarize*. Left on Sum, a
   map renders a single bubble in the Southern Ocean at the sum of every
   coordinate, which is the most common Power BI mapping failure and looks
   like a rendering bug rather than a modelling one.
3. **Geocoding is off in the tenant** for these reports, so a report author
   cannot reintroduce it by dragging a city name onto a map.

**If coordinates were missing.** Geocoding would happen once, in the pipeline,
not in the report: batch the distinct addresses through a geocoder, store the
result with its match score and the precision it resolved at, and reject
anything below rooftop or street level to a manual queue. That makes the
match quality a column that can be tested, filtered and shown, rather than an
invisible property of a visual. `dim_site` would gain
`geocode_precision` and `geocode_confidence`, and the map would filter on
them — a low-confidence site should be visible as low-confidence, not silently
plotted.

### Coordinate reference system

Everything is stored in WGS 84 (EPSG:4326), which is what both visuals expect
and what the generator produces.

Distance and area calculations do **not** happen in degrees. A degree of
longitude at Cape Town's latitude is about 92 km against 111 km for a degree
of latitude, so a "radius" measured in raw coordinate space is an ellipse that
gets more wrong the further south the site is. Where the platform needs real
distance — the corridor coverage measure, the catchment work above — it
projects to Hartebeesthoek94 / Lo29 or uses a proper geodesic distance. The
same correction is applied in the Python figures, where the map's axes are
sized to `longitude x cos(latitude) : latitude` rather than drawn square.

### Drill path

```
Province  →  Metro / urban class  →  City  →  Site
```

Drill is configured on a hierarchy in `dim_site`, so drilling the map
cross-filters every other visual on the page through the existing
relationships rather than through visual-level interactions. Drill-through
targets a per-site detail page carrying throughput, asset condition, incident
history and the site's own scorecard components.

Because the scorecard exposes each component as a named column
(`r_contribution`, `r_throughput`, `r_growth`, `r_non_fuel`, `r_reliability`,
`r_uptime`, `r_safety`, `r_asset_condition`), the drill-through page can show
*why* a site scored what it did. A map that shows a red bubble and cannot
explain it produces an argument, not a decision.

### Report page tooltip

A custom report page tooltip (320 × 240 px), rather than the default field
list:

- Site name, city, province, urban class
- Sparkline: 13-week litres trend
- `[Gross Margin]`, `[Margin per Litre (c)]`, `[Non-Fuel Margin Share %]`
- `[Breakdown Rate %]` and `[Downtime Hours]`
- Investment score with its quartile

Hover-level answers are what keep an executive on the map instead of paging
through a table.

### The measures the map binds to

```dax
Margin per Site =
DIVIDE (
    [Gross Margin],
    DISTINCTCOUNT ( dim_site[site_key] )
)

Corridor Coverage Gap =
-- Corridor sites with no neighbouring site within the same city.
-- These are the sites the capital plan protects from divestment
-- regardless of score, so the map has to show them as a category.
VAR CorridorSites =
    CALCULATETABLE (
        VALUES ( dim_site[site_key] ),
        dim_site[on_national_route] = TRUE ()
    )
VAR SoleCoverage =
    FILTER (
        CorridorSites,
        CALCULATE ( DISTINCTCOUNT ( dim_site[site_key] ),
                    ALLEXCEPT ( dim_site, dim_site[city] ) ) = 1
    )
RETURN
    COUNTROWS ( SoleCoverage )

Network Reach km2 =
-- Rough bounding extent of the sites currently in filter context.
-- Deliberately approximate: it is a scale indicator on the map header,
-- not a spatial statistic, and it is labelled as such on the page.
VAR LatSpan = MAX ( dim_site[latitude] ) - MIN ( dim_site[latitude] )
VAR LonSpan = MAX ( dim_site[longitude] ) - MIN ( dim_site[longitude] )
RETURN
    LatSpan * 111 * LonSpan * 111 * COS ( RADIANS ( 28 ) )
```

### Performance

A bubble layer with one mark per site is fine at roughly a thousand sites and
is not fine at a hundred thousand. Three things keep the page responsive:

- The map binds to `network_investment_scorecard` — **one row per site,
  already aggregated in gold** — never to the transaction fact. Rendering a
  map from 37 million rows and letting the visual group them is the most
  reliable way to build a page nobody waits for.
- The scorecard is in Import mode. It is small, it changes daily, and
  DirectQuery would put a geocode-free but still round-tripping query behind
  every hover.
- The heat layer reads the daily aggregate `agg_site_daily_fuel`, so the
  volume weighting resolves through the user-defined aggregation rather than
  the detail fact.

### Row-level security and the map

The province row filter (see *Row-level security*) applies to `dim_site`,
which the map's tables reach through the existing relationships — so a
regional analyst sees their own provinces and the map extent re-fits to them.

Two consequences worth stating, because both are easy to get wrong:

- **`[Margin per Site]` is a ratio and is therefore safe under RLS**; a
  regional analyst sees their own provinces' figure, not a filtered numerator
  over a network-wide denominator. This works only because the denominator is
  `DISTINCTCOUNT` over the filtered `dim_site`, not a hard-coded site count.
- **The reference layer must be filtered too.** A TopoJSON province shape is
  drawn by the visual whether or not any data survives the filter, so a
  restricted user would otherwise see nine provinces outlined with only two
  filled — which discloses the shape of what they cannot see. The reference
  layer is bound to the same filtered table so unauthorised provinces do not
  render at all.
