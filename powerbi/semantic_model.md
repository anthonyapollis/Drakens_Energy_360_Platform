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
