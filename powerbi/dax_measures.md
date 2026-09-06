# DAX measures

> Independent synthetic portfolio project. No real company data.

Measures are grouped by display folder. Every ratio is computed as
`DIVIDE(SUM(numerator), SUM(denominator))` — never as an average of a
pre-computed row-level percentage, which is the single most common way a
margin figure ends up wrong.

---

## Volume

```dax
Fuel Volume (L) =
SUM ( agg_site_daily_fuel[litres] )

Diesel Volume (L) =
SUM ( agg_site_daily_fuel[diesel_litres] )

Petrol Volume (L) =
SUM ( agg_site_daily_fuel[petrol_litres] )

Diesel Share % =
DIVIDE ( [Diesel Volume (L)], [Fuel Volume (L)] )

Volume per Site (L) =
DIVIDE ( [Fuel Volume (L)], [Trading Sites] )

Trading Sites =
DISTINCTCOUNT ( agg_site_daily_fuel[site_key] )
```

## Revenue and margin

```dax
Fuel Revenue =
SUM ( agg_site_daily_fuel[gross_sales_zar] )

Shop Revenue =
SUM ( agg_executive_daily_kpi[shop_revenue_zar] )

Total Revenue =
[Fuel Revenue] + [Shop Revenue]

Gross Margin =
SUM ( agg_site_daily_fuel[gross_margin_zar] )

-- Computed from the two sums, never as AVERAGE of a row-level percentage.
-- Averaging percentages weights a R200 transaction the same as a R20,000 one.
Gross Margin % =
DIVIDE ( [Gross Margin], [Total Revenue] )

Margin per Litre (c) =
DIVIDE ( [Gross Margin], [Fuel Volume (L)] ) * 100

-- The strategic number: regulated fuel is thin-margin volume, so the growth
-- story is what proportion of margin comes from everything else.
Non-Fuel Margin Share % =
VAR NonFuel =
    SUM ( agg_executive_daily_kpi[shop_margin_zar] )
RETURN
    DIVIDE ( NonFuel, [Gross Margin] + NonFuel )

Average Transaction Value =
DIVIDE ( [Fuel Revenue], [Transaction Count] )

Transaction Count =
SUM ( agg_site_daily_fuel[transaction_count] )
```

## Time intelligence

```dax
Fuel Volume LY =
CALCULATE ( [Fuel Volume (L)], SAMEPERIODLASTYEAR ( dim_date[full_date] ) )

Fuel Volume YoY % =
DIVIDE ( [Fuel Volume (L)] - [Fuel Volume LY], [Fuel Volume LY] )

Gross Margin YTD =
TOTALYTD ( [Gross Margin], dim_date[full_date] )

-- Fiscal year runs April to March, so the year-end date must be stated
-- explicitly. Omitting it silently gives a calendar-year YTD.
Gross Margin FYTD =
TOTALYTD ( [Gross Margin], dim_date[full_date], "31/03" )

Fuel Volume MAT =
CALCULATE (
    [Fuel Volume (L)],
    DATESINPERIOD ( dim_date[full_date], MAX ( dim_date[full_date] ), -12, MONTH )
)

Fuel Volume 7D Average =
AVERAGEX (
    DATESINPERIOD ( dim_date[full_date], MAX ( dim_date[full_date] ), -7, DAY ),
    [Fuel Volume (L)]
)
```

## Supply chain

```dax
Deliveries =
COUNTROWS ( fct_deliveries )

-- is_otif is computed once in the gold layer. Re-deriving the rule here from
-- delay_minutes and fill_rate would create a second definition that drifts.
OTIF Deliveries =
CALCULATE ( [Deliveries], fct_deliveries[is_otif] = TRUE () )

OTIF % =
DIVIDE ( [OTIF Deliveries], [Deliveries] )

Average Delay (min) =
AVERAGE ( fct_deliveries[delay_minutes] )

-- Stock on hand is semi-additive: it may be summed across locations but never
-- across time. Summing it over a month would report a month's worth of daily
-- snapshots as though the stock existed simultaneously.
Stock on Hand (L) =
CALCULATE (
    SUM ( fct_inventory_position[stock_on_hand_litres] ),
    LASTNONBLANK ( dim_date[full_date], 1 )
)

Days of Cover =
CALCULATE (
    AVERAGE ( fct_inventory_position[days_of_cover] ),
    LASTNONBLANK ( dim_date[full_date], 1 )
)

Sites at Stock-Out Risk =
CALCULATE (
    DISTINCTCOUNT ( fct_inventory_position[site_id] ),
    fct_inventory_position[is_stock_out_risk] = TRUE (),
    LASTNONBLANK ( dim_date[full_date], 1 )
)
```

## New energy

```dax
EV Sessions =
SUM ( agg_executive_daily_kpi[ev_sessions] )

EV Energy (kWh) =
SUM ( agg_executive_daily_kpi[ev_kwh] )

EV Margin per kWh =
DIVIDE (
    SUM ( fct_ev_charging_sessions[gross_margin_zar] ),
    SUM ( fct_ev_charging_sessions[energy_kwh] )
)

Solar Generation (kWh) =
SUM ( fct_solar_generation[energy_kwh] )

CO2 Avoided (t) =
DIVIDE ( SUM ( fct_solar_generation[co2_avoided_kg] ), 1000 )

EV Sites % =
DIVIDE (
    CALCULATE ( DISTINCTCOUNT ( dim_site[site_key] ),
                dim_site[has_ev_charging] = TRUE () ),
    DISTINCTCOUNT ( dim_site[site_key] )
)
```

## Network investment

```dax
Sites Scored =
COUNTROWS ( network_investment_scorecard )

Average Investment Score =
AVERAGE ( network_investment_scorecard[investment_score] )

Invest Candidates =
CALCULATE (
    [Sites Scored],
    CONTAINSSTRING ( network_investment_scorecard[investment_recommendation], "Invest" )
)

Divest Candidates =
CALCULATE (
    [Sites Scored],
    network_investment_scorecard[investment_recommendation] = "Divest Candidate"
)

-- What is actually at stake in the divestment conversation: the margin that
-- would leave the network with those sites.
Margin at Risk =
CALCULATE (
    SUM ( network_investment_scorecard[total_margin_zar] ),
    network_investment_scorecard[investment_recommendation] = "Divest Candidate"
)

Top Quartile Margin Share % =
DIVIDE (
    CALCULATE ( SUM ( network_investment_scorecard[total_margin_zar] ),
                network_investment_scorecard[investment_quartile] = 1 ),
    SUM ( network_investment_scorecard[total_margin_zar] )
)
```

## Data quality

```dax
Rows Landed =
SUM ( obs_cleansing_summary[raw_rows] )

Rows Quarantined =
SUM ( obs_cleansing_summary[quarantined_rows] )

Quarantine Rate % =
DIVIDE ( [Rows Quarantined], [Rows Landed] )

Feeds Breaching SLA =
CALCULATE (
    COUNTROWS ( obs_table_freshness ),
    obs_table_freshness[is_sla_breached] = TRUE ()
)

Worst Ingestion Lag (min) =
MAX ( obs_table_freshness[ingestion_lag_minutes] )

-- Traffic light for the platform health tile.
Pipeline Status =
VAR Breaches = [Feeds Breaching SLA]
VAR QRate = [Quarantine Rate %]
RETURN
    SWITCH (
        TRUE (),
        Breaches > 2 || QRate > 0.05, "Critical",
        Breaches > 0 || QRate > 0.02, "Degraded",
        "Healthy"
    )
```

## Formatting conventions

| Measure type | Format string |
|---|---|
| Volume | `#,##0,, "m L"` |
| Currency | `"R"#,##0,,;-"R"#,##0,,;"R0"` |
| Percentage | `0.0%` |
| Cents per litre | `0.0 "c/L"` |
| Counts | `#,##0` |

Currency measures use the South African rand throughout. `fact_cashflow` and
`fact_import_cargoes` carry non-ZAR amounts; those are converted in the gold
layer using `dim_currency[units_per_zar]` rather than in DAX, so a report never
shows a mixed-currency total.
