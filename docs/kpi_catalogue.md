# KPI catalogue

> **Independent synthetic portfolio project.** no data from any real company. All figures are generated.

Every KPI below is computed **once**, in the gold layer, and read unchanged by
Power BI, the ML feature sets and any ad-hoc query. That is the point of the
catalogue: a definition that lives in the BI tool gets reimplemented by whoever
builds the next report, and two dashboards eventually disagree in front of an
executive with no way to say which is right.

Each entry names where the definition lives, so there is always one answer to
"where does this number come from".

---

## Retail

| KPI | Definition | Computed in | Additive? |
|---|---|---|---|
| Fuel volume | Sum of litres dispensed | `agg_site_daily_fuel.litres` | Yes |
| Fuel revenue | Litres × pump price, before VAT | `fct_retail_fuel_sales.gross_sales_zar` | Yes |
| Gross margin | Revenue − cost of sales | `fct_retail_fuel_sales.gross_margin_zar` | Yes |
| Gross margin % | SUM(margin) ÷ SUM(revenue) | recomputed at query time | **No** |
| Margin per litre | SUM(margin) ÷ SUM(litres), in cents | recomputed at query time | **No** |
| Transactions | Count of sales lines | `agg_site_daily_fuel.transaction_count` | Yes |
| Average transaction value | SUM(revenue) ÷ COUNT(transactions) | recomputed at query time | **No** |
| Litres per site | SUM(litres) ÷ COUNT(DISTINCT site) | recomputed at query time | **No** |
| Diesel share % | Diesel litres ÷ total litres | `agg_site_daily_fuel.diesel_share_pct` | **No** |
| Loyalty penetration % | Loyalty transactions ÷ all transactions | `agg_site_daily_fuel.loyalty_penetration_pct` | **No** |

**Non-fuel margin share** is the strategic number. Regulated fuel is thin-margin
volume, so the growth story is what proportion of margin comes from everything
else:

```
non_fuel_margin_share_pct = shop_margin / (fuel_margin + shop_margin)
```

Computed in `agg_executive_daily_kpi`.

---

## Supply and distribution

| KPI | Definition | Computed in |
|---|---|---|
| OTIF % | Deliveries on time **and** in full ÷ all deliveries | `fct_deliveries.is_otif` |
| On time | Arrival within `otif_delay_threshold_minutes` (60) of plan | `fct_deliveries.is_on_time` |
| In full | Delivered ≥ 98% of planned volume | `fct_deliveries.is_in_full` |
| Days of cover | Stock on hand ÷ average daily usage | `fct_inventory_position.days_of_cover` |
| Stock-out risk | Days of cover < `stock_out_cover_days` (1.5) | `fct_inventory_position.is_stock_out_risk` |
| Stock on hand | Litres held. **Semi-additive** | `fct_inventory_position.stock_on_hand_litres` |
| Terminal utilisation % | Closing stock ÷ capacity | `fact_terminal_throughput.utilisation_pct` |
| Volumetric loss % | (Gross − net) ÷ gross receipts | `fact_terminal_receipts.loss_pct` |

**OTIF is defined once**, in `fct_deliveries`. Both thresholds come from
`dbt_project.yml` variables so a change is a single edit, and the ML
late-delivery model trains on the same definition the dashboard reports.

**Stock on hand is semi-additive**: sum it across locations, never across time.
Summing a month of daily snapshots reports the stock as though every day's
inventory existed simultaneously. In DAX this means `LASTNONBLANK` over the
date axis, which is documented on the measure.

---

## Commercial

| KPI | Definition | Computed in |
|---|---|---|
| Contracted volume | Litres under a contract | `fct_commercial_orders.volume_litres` |
| Discount leakage | Volume × discount cents per litre | `fct_commercial_orders.discount_value_zar` |
| Discount intensity % | Discount value ÷ revenue | `agg_customer_monthly.discount_intensity_pct` |
| Commitment achievement % | Achieved ÷ committed volume | `fact_contract_volume_commitments.achievement_pct` |
| Days sales outstanding | Days from invoice to payment | `fact_customer_invoices.days_to_payment` |
| Credit utilisation % | Outstanding ÷ credit limit | `fact_customer_credit_exposure.utilisation_pct` |
| Revenue at risk | Prior-period revenue of declining accounts | `agg_customer_monthly` |

**Discount leakage** is valued in rand rather than reported as a rate, because
that is what a commercial review is actually about: a 4 c/L discount sounds
trivial and is not, at volume.

---

## New energy

| KPI | Definition | Computed in |
|---|---|---|
| EV energy delivered | kWh dispensed | `fct_ev_charging_sessions.energy_kwh` |
| EV margin per kWh | Margin ÷ kWh | `fct_ev_charging_sessions.margin_zar_per_kwh` |
| Charger power utilisation % | Average power ÷ rated power | `fct_ev_charging_sessions.power_utilisation_pct` |
| Charger availability % | Time in `Available` or `Charging` | `fact_ev_charger_status` |
| Solar generation | kWh generated | `fct_solar_generation.energy_kwh` |
| Solar capacity factor | Actual ÷ theoretical maximum | `fct_solar_generation.capacity_factor` |
| CO₂ avoided | Solar kWh × grid emission factor | `fct_solar_generation.co2_avoided_kg` |
| Self-consumption % | Solar consumed on site ÷ generated | `fact_grid_import_export.self_consumption_pct` |

**Power utilisation** is the number that decides whether more chargers are worth
installing. A charger at 25% utilisation does not need a second unit beside it;
one at 80% does.

---

## Assets and reliability

| KPI | Definition | Computed in |
|---|---|---|
| Breakdown rate % | Unplanned ÷ all work orders | `fct_maintenance_work_orders.is_breakdown` |
| Planned maintenance % | Planned ÷ all work orders | `fct_maintenance_work_orders.is_planned` |
| Mean time to repair | Average repair hours | `fact_asset_failures.time_to_repair_hours` |
| Asset downtime | Hours out of service | `fact_asset_downtime.downtime_hours` |
| Lost revenue from downtime | Unplanned downtime × site rate | `fact_asset_downtime.lost_revenue_zar` |
| Maintenance SLA breach % | Response beyond the criticality target | `fct_maintenance_work_orders.sla_breached` |

The response-time target varies by criticality (4 hours for critical, 24
otherwise), so the SLA flag is computed against the asset's own target rather
than one global number.

---

## HSSEQ

| KPI | Definition | Computed in |
|---|---|---|
| Reportable incidents | Severity ≥ Moderate | `fact_hsseq_incidents.is_reportable` |
| Lost-time injuries | Incidents causing lost days | `fact_hsseq_incidents.is_lost_time_injury` |
| Near-miss ratio | Near misses ÷ reportable incidents | derived |
| Training compliance % | Non-expired mandatory records ÷ required | `fact_training_compliance` |
| Environmental events | Spills, leaks, exceedances | `fact_environmental_events` |

A **rising** near-miss ratio is usually good news: it means people are
reporting. Falling near-miss reporting alongside steady incidents is the
warning sign, and the KPI is documented that way so nobody optimises it in the
wrong direction.

---

## Executive

| KPI | Definition | Computed in |
|---|---|---|
| Total revenue | Fuel + shop | `agg_executive_daily_kpi.total_revenue_zar` |
| Total margin | Fuel + shop + EV | `agg_executive_daily_kpi.total_margin_zar` |
| Gross margin % | Total margin ÷ total revenue | `agg_executive_daily_kpi.gross_margin_pct` |
| Non-fuel margin share % | Shop margin ÷ total margin | `agg_executive_daily_kpi.non_fuel_margin_share_pct` |
| Trading sites | Sites with sales that day | `agg_executive_daily_kpi.trading_sites` |
| Investment score | Weighted percentile composite, 0–100 | `network_investment_scorecard.investment_score` |
| Margin at risk | Margin held by divestment candidates | derived |

---

## Network and coverage

The geographic KPIs behind the network map. These are the ones a capital
committee argues about, so each is computed in gold and exposed as a named
column rather than assembled in the report.

| KPI | Definition | Computed in |
|---|---|---|
| Margin per site | Total margin ÷ distinct trading sites | derived over `network_investment_scorecard` |
| Litres per site per day | Volume ÷ (sites × trading days) | `network_investment_scorecard.avg_daily_litres` |
| Corridor site share % | Sites on a national route ÷ all sites | `dim_site.on_national_route` |
| Sole-coverage corridor sites | Corridor sites that are the only site in their city | derived |
| Province margin concentration | Share of network margin in the top two provinces | derived |
| Metro margin share % | Metro sites' margin ÷ network margin | `dim_site.urban_class` |
| Network reach | Bounding extent of sites in filter context | derived, map header only |

**Sole-coverage corridor sites are a constraint, not a metric.** They are the
sites the capital plan refuses to divest regardless of score, because losing
the only site in a town on a national route removes coverage that cannot be
bought back later at the same price. The number exists so the constraint is
visible on the map rather than buried in the optimiser.

**Network reach is deliberately approximate** — a bounding extent, not a
spatial statistic. It is labelled as such on the page. A precise-looking
number that is not precise is worse than an obviously rough one.

---

## Machine learning

Every model is judged on the decision it supports, not on the metric that
flatters it. A model without a stated baseline is a claim, not a result.

| Model | Decision it supports | Metric that matters | Baseline it must beat |
|---|---|---|---|
| Demand forecast | How much to deliver, and when | MAE in litres | Seasonal naive — last week, same weekday |
| Predictive maintenance | Which assets to visit this week | Precision and lift in the top 5% of the ranked queue | The base breakdown rate |
| Customer churn | Which accounts to call | Average precision; precision at top 5% | Prevalence |
| Stock-out risk | Which deliveries to bring forward | Recall at the chosen operating threshold | Prevalence at the prediction horizon |
| Late delivery | Which slots to re-plan | Lift in the top 10% | The overall late rate |
| Fraud / anomaly | Which transactions to review | Flagged-vs-normal separation on cash share and fill ratio | The population profile |

Four rules apply to all six, and each exists because breaking it produces a
model that scores well and is useless:

- **Chronological split, never random.** A random split lets the model see the
  future of the same site it is predicting.
- **No feature unknown at decision time.** Cost and labour hours are outcomes
  of a work order, not predictors of one.
- **A target measured after its features, not alongside them.** The stock-out
  model originally scored the *current* snapshot and reached ROC-AUC 0.998.
  That was the definition coming back out, not a result: the target is
  `days_of_cover` below a threshold, and both of that ratio's components were
  features, so the model divided one by the other and reproduced the rule.
  Dropping `days_of_cover` alone fixed nothing. The target is now the *next*
  snapshot of the same tank, which is also the only version anyone needs --
  a gauge already reports that a tank is low right now.
- **A stated baseline, reported next to the result.** A demand forecast
  claiming 97% accuracy means a feature has leaked.
- **The operating threshold comes from the cost asymmetry, not from 0.5.**
  Missing a stock-out costs roughly four times an unnecessary early delivery,
  so the stock-out threshold is chosen on F-beta with beta = 2.

Targets are read from the gold layer, not redefined in the notebook, so the
alert on the dashboard and the model's target are the same thing by
construction. When the `stock_out_cover_days` project variable changes, both
move together.

---

## Data platform

| KPI | Definition | Computed in |
|---|---|---|
| Ingestion lag | Latest ingest − latest event | `obs_table_freshness.ingestion_lag_minutes` |
| SLA status | Lag against the per-source SLA | `obs_table_freshness.sla_status` |
| Quarantine rate % | Rejected ÷ landed rows | `obs_cleansing_summary.quarantine_rate_pct` |
| Duplicate rate % | Deduplicated ÷ landed rows | `obs_cleansing_summary.duplicate_rate_pct` |
| Row reconciliation | raw = cleansed + quarantined + duplicates | `obs_cleansing_summary.row_count_reconciles` |
| Control pass rate | Passing ÷ all reconciliation controls | `obs_reconciliation_controls.is_passing` |

**Row reconciliation is the most important KPI on this list.** If it fails,
every other number on the page is suspect, because rows have been lost
somewhere in the pipeline and nobody can say which.

---

## Rules that apply to all of them

1. **Ratios are computed from sums, never averaged.** `AVG(margin_pct)`
   weights a R200 transaction the same as a R20,000 one and gives a different
   answer from the correct one.
2. **Percentages are non-additive.** A `_pct` column exists for inspecting a
   single row; aggregate by recomputing from the components.
3. **Snapshots are semi-additive.** Inventory sums across locations, never
   across time.
4. **Definitions live in gold.** If a KPI is only defined in DAX, it will be
   redefined differently within a quarter.
