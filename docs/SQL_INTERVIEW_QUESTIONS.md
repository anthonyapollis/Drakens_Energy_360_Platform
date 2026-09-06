# SQL interview questions on this model

> Independent synthetic portfolio project. No real company data.

Questions against the Vivo Energy 360 schema, ordered from intermediate to
staff level. Each states what it is actually testing, because the point of a
technical question is to find out something specific rather than to see
whether the candidate has memorised a syntax.

Run them against `main_gold` in DuckDB, or `vivo_dev.gold` on Databricks.

---

## Intermediate

### 1. Volume by province and fuel grade

> Total litres and gross margin by province and fuel grade for the 2026
> fiscal year, highest margin first.

*Tests: joins to a conformed dimension, a non-calendar fiscal year, grouping.*

```sql
SELECT
    s.province,
    f.fuel_grade,
    SUM(f.litres)           AS litres,
    SUM(f.gross_margin_zar) AS gross_margin_zar
FROM main_gold.fct_retail_fuel_sales f
JOIN main_gold.dim_site s ON f.site_key = s.site_key AND s.is_current
JOIN main_gold.dim_date d ON f.date_key = d.date_key
WHERE d.fiscal_year = 2026
GROUP BY 1, 2
ORDER BY gross_margin_zar DESC;
```

The trap is `calendar_year`. The South African fiscal year runs April to
March, and `dim_date` carries both — a candidate who reaches for
`YEAR(transaction_ts)` has not read the dimension.

---

### 2. Margin percentage by site type

> Gross margin percentage by site type.

*Tests: whether the candidate understands that a ratio of sums is not a sum
of ratios.*

```sql
SELECT
    s.site_type,
    SUM(f.gross_margin_zar) / NULLIF(SUM(f.gross_sales_zar), 0) * 100
        AS gross_margin_pct
FROM main_gold.fct_retail_fuel_sales f
JOIN main_gold.dim_site s ON f.site_key = s.site_key AND s.is_current
GROUP BY 1;
```

The wrong answer is `AVG(line_margin_pct)`, which weights a R200 transaction
the same as a R20,000 one. `line_margin_pct` exists on the fact precisely so
this mistake is available to make; a good candidate notices and avoids it.

---

### 3. Sites with no sales in the last 30 days

> Which sites recorded no fuel sales in the last 30 days of data?

*Tests: anti-joins, and thinking about absence rather than presence.*

```sql
WITH bounds AS (
    SELECT MAX(date_key) AS max_key FROM main_gold.agg_site_daily_fuel
),
recent AS (
    SELECT DISTINCT a.site_key
    FROM main_gold.agg_site_daily_fuel a, bounds b
    JOIN main_gold.dim_date d ON a.date_key = d.date_key
    WHERE d.full_date >= (
        SELECT full_date - INTERVAL 30 DAY
        FROM main_gold.dim_date WHERE date_key = b.max_key
    )
)
SELECT s.site_id, s.site_name, s.province, s.site_status
FROM main_gold.dim_site s
LEFT JOIN recent r ON s.site_key = r.site_key
WHERE s.is_current AND r.site_key IS NULL;
```

`NOT IN` against a subquery that can return NULL silently returns nothing.
Watching whether a candidate reaches for `NOT IN`, `NOT EXISTS` or a left
anti-join is informative.

---

### 4. Top three sites per province

> The three highest-margin sites in each province.

*Tests: window functions, and the difference between the ranking functions.*

```sql
WITH ranked AS (
    SELECT
        province, site_name, total_margin_zar,
        ROW_NUMBER() OVER (PARTITION BY province ORDER BY total_margin_zar DESC) AS rn
    FROM main_gold.network_investment_scorecard
    WHERE country_code = 'ZA'
)
SELECT province, site_name, total_margin_zar
FROM ranked WHERE rn <= 3
ORDER BY province, rn;
```

Follow-up worth asking: what changes if two sites tie? `ROW_NUMBER` picks one
arbitrarily; `RANK` returns four rows; `DENSE_RANK` something else again.

---

## Advanced

### 5. Month-on-month volume growth with a gap

> Month-on-month volume growth per site, treating a month with no sales as
> zero rather than skipping it.

*Tests: the classic `LAG` trap — gaps in the data.*

```sql
WITH months AS (
    SELECT DISTINCT calendar_year, month_number,
           MIN(date_key) AS month_key
    FROM main_gold.dim_date
    GROUP BY 1, 2
),
sites AS (
    SELECT DISTINCT site_key FROM main_gold.agg_site_daily_fuel
),
-- The cross join is the point: it creates the missing months so LAG steps
-- over a real zero rather than silently comparing across a gap.
scaffold AS (
    SELECT s.site_key, m.calendar_year, m.month_number
    FROM sites s CROSS JOIN months m
),
actual AS (
    SELECT a.site_key, d.calendar_year, d.month_number,
           SUM(a.litres) AS litres
    FROM main_gold.agg_site_daily_fuel a
    JOIN main_gold.dim_date d ON a.date_key = d.date_key
    GROUP BY 1, 2, 3
)
SELECT
    sc.site_key, sc.calendar_year, sc.month_number,
    COALESCE(ac.litres, 0) AS litres,
    LAG(COALESCE(ac.litres, 0)) OVER (
        PARTITION BY sc.site_key ORDER BY sc.calendar_year, sc.month_number
    ) AS prior_month_litres
FROM scaffold sc
LEFT JOIN actual ac
    ON sc.site_key = ac.site_key
   AND sc.calendar_year = ac.calendar_year
   AND sc.month_number = ac.month_number
ORDER BY sc.site_key, sc.calendar_year, sc.month_number;
```

A `LAG` over only the months that exist compares March to January and calls
it month-on-month. It is a real bug that reaches production regularly.

---

### 6. Semi-additive stock

> Total stock on hand across the network, by month.

*Tests: whether the candidate recognises a semi-additive measure.*

```sql
WITH latest_per_month AS (
    SELECT
        d.calendar_year, d.month_number, i.site_id, i.product_id,
        i.stock_on_hand_litres,
        ROW_NUMBER() OVER (
            PARTITION BY d.calendar_year, d.month_number, i.site_id, i.product_id
            ORDER BY i.snapshot_ts DESC
        ) AS rn
    FROM main_gold.fct_inventory_position i
    JOIN main_gold.dim_date d ON i.date_key = d.date_key
)
SELECT calendar_year, month_number, SUM(stock_on_hand_litres) AS stock_on_hand
FROM latest_per_month
WHERE rn = 1
GROUP BY 1, 2 ORDER BY 1, 2;
```

`SUM(stock_on_hand_litres) GROUP BY month` is wrong and looks right. It adds
up every daily snapshot as though the stock existed simultaneously, inflating
the answer by roughly the number of snapshots in the month. Stock may be
summed across locations, never across time.

---

### 7. Type-2 history

> Each site's ownership model as it was on 30 June 2025, including sites that
> have since changed.

*Tests: SCD2 comprehension — the most common dimensional-modelling gap.*

```sql
SELECT site_id, site_name, ownership_model,
       effective_from_date, effective_to_date
FROM main_silver_snapshots.snap_dim_site
WHERE DATE '2025-06-30' >= dbt_valid_from
  AND (dbt_valid_to IS NULL OR DATE '2025-06-30' < dbt_valid_to);
```

Filtering `WHERE is_current` gives today's answer to a question about the
past. The half-open interval matters too: `<= dbt_valid_to` double-counts on
the changeover date.

---

### 8. Customers whose volume halved

> Customers whose volume in the most recent quarter fell by more than half
> against the prior quarter, with the rand value at risk.

*Tests: multi-CTE reasoning and translating a business question into SQL.*

```sql
WITH quarters AS (
    SELECT customer_key, customer_id, calendar_year,
           CEIL(month_number / 3.0) AS quarter,
           SUM(volume_litres) AS volume,
           SUM(revenue_zar)   AS revenue
    FROM main_gold.agg_customer_monthly
    GROUP BY 1, 2, 3, 4
),
sequenced AS (
    SELECT *,
           LAG(volume)  OVER (PARTITION BY customer_key ORDER BY calendar_year, quarter) AS prior_volume,
           LAG(revenue) OVER (PARTITION BY customer_key ORDER BY calendar_year, quarter) AS prior_revenue,
           ROW_NUMBER() OVER (PARTITION BY customer_key ORDER BY calendar_year DESC, quarter DESC) AS recency
    FROM quarters
)
SELECT customer_id, calendar_year, quarter,
       prior_volume, volume,
       (volume - prior_volume) / NULLIF(prior_volume, 0) * 100 AS volume_change_pct,
       prior_revenue - revenue AS revenue_at_risk_zar
FROM sequenced
WHERE recency = 1
  AND prior_volume > 0
  AND volume < prior_volume * 0.5
ORDER BY revenue_at_risk_zar DESC;
```

---

## Staff level

### 9. Diagnose a slow query

> This runs for eleven minutes. What is wrong, and what would you change?

```sql
SELECT s.province, SUM(f.gross_sales_zar)
FROM main_gold.fct_retail_fuel_sales f
JOIN main_gold.dim_site s ON f.site_id = s.site_id
WHERE YEAR(f.transaction_ts) = 2026
GROUP BY 1;
```

*Tests: whether the candidate can reason about physical execution, not just
write correct SQL.*

Four separate problems:

1. **`YEAR(transaction_ts)` is not sargable.** Wrapping the partition column
   in a function defeats partition pruning, so the engine scans all five
   million rows. Filter on `date_key BETWEEN 20260101 AND 20261231`, which
   the table is partitioned on.
2. **Joining on `site_id` rather than `site_key`.** The natural key is a
   string; the surrogate is the clustering key. String joins at this scale
   are materially slower.
3. **No `is_current` filter.** `dim_site` is Type-2, so this multiplies every
   fact row by the number of historical versions of its site — inflating the
   answer as well as the runtime. This is the serious bug: the query is
   *wrong*, not merely slow.
4. **The aggregate exists.** `agg_site_daily_fuel` already has this at a
   thousandth of the row count.

The rewrite:

```sql
SELECT a.province, SUM(a.gross_sales_zar)
FROM main_gold.agg_site_daily_fuel a
WHERE a.date_key BETWEEN 20260101 AND 20261231
GROUP BY 1;
```

A candidate who finds the correctness bug in point 3 before the performance
points is thinking about the right things.

---

### 10. Find the double-count

> Finance reports that total fuel revenue in the dashboard is about 4% higher
> than the general ledger. How do you find out why?

*Tests: systematic diagnosis under ambiguity — the actual job.*

There is no single answer. What matters is the order of investigation:

```sql
-- 1. Is the fact itself duplicated?
SELECT transaction_id, COUNT(*)
FROM main_gold.fct_retail_fuel_sales
GROUP BY 1 HAVING COUNT(*) > 1;

-- 2. Does the aggregate still tie to the detail?
SELECT
    (SELECT SUM(gross_sales_zar) FROM main_gold.fct_retail_fuel_sales) AS detail,
    (SELECT SUM(gross_sales_zar) FROM main_gold.agg_site_daily_fuel)   AS agg;

-- 3. Is a Type-2 join fanning out?
SELECT COUNT(*) AS fact_rows,
       (SELECT COUNT(*) FROM main_gold.fct_retail_fuel_sales) AS expected
FROM main_gold.fct_retail_fuel_sales f
JOIN main_gold.dim_site s ON f.site_key = s.site_key;   -- no is_current

-- 4. Is the cleansing layer losing or duplicating rows?
SELECT * FROM main_platform.obs_cleansing_summary
WHERE raw_rows <> cleansed_rows + quarantined_rows + duplicates_removed;

-- 5. Do the controls already know?
SELECT * FROM main_platform.obs_reconciliation_controls WHERE NOT is_passing;
```

The strongest answer starts at step 5: the platform already runs these
controls, so the first question is whether one is failing, not whether to
write a new query. The second-strongest recognises that a 4% gap is
suspiciously close to a scope difference — the dashboard may include a
business unit or a period the ledger extract excludes, and reconciling
*scope* comes before reconciling arithmetic.

---

### 11. Design a question

> Marketing wants to know whether the loyalty programme actually drives
> incremental volume. What would you build?

*Tests: whether the candidate pushes back on an unanswerable question.*

The naive query compares loyalty and non-loyalty transactions:

```sql
SELECT loyalty_flag, AVG(litres), COUNT(*)
FROM main_gold.fct_retail_fuel_sales
GROUP BY 1;
```

This answers nothing. Loyalty members self-select: people who already refuel
often are the ones who sign up. The difference measures who joins, not what
joining causes.

Better approaches, in ascending order of rigour:

1. **Within-member before/after.** Compare each member's volume before and
   after joining, using `dim_loyalty_member.joined_date`. Controls for the
   member, not for whatever prompted them to join.
2. **Difference-in-differences** against non-members over the same period,
   which removes seasonality and price movements common to both.
3. **A staged rollout.** `bridge_site_promotion` records which sites ran which
   promotion; sites that ran it later are a control group for sites that ran
   it earlier.
4. **A holdout.** The only design that actually establishes causation, and
   the only one that has to be agreed *before* the campaign runs.

The right answer to marketing is that options 1 to 3 give a directional
estimate now, and that option 4 needs to be built into the next campaign. A
candidate who runs the naive query and reports "loyalty members buy 23% more"
has given a confidently wrong answer to the CEO.

---

### 12. Sole-coverage sites

> Which divestment candidates are the only site within 50 km, and what volume
> would the network lose?

*Tests: spatial reasoning in SQL, and understanding that a model output is an
input to a decision rather than the decision.*

```sql
WITH sites AS (
    SELECT site_id, site_name, province, latitude, longitude,
           investment_recommendation, avg_daily_litres, total_margin_zar
    FROM main_gold.network_investment_scorecard
    WHERE country_code = 'ZA' AND site_status = 'Operating'
),
-- Haversine. A naive Euclidean distance on degrees is wrong at South African
-- latitudes: a degree of longitude is about 15% shorter here than a degree
-- of latitude.
pairs AS (
    SELECT
        a.site_id AS site_id, b.site_id AS neighbour_id,
        6371 * 2 * ASIN(SQRT(
            POWER(SIN(RADIANS(b.latitude - a.latitude) / 2), 2)
            + COS(RADIANS(a.latitude)) * COS(RADIANS(b.latitude))
            * POWER(SIN(RADIANS(b.longitude - a.longitude) / 2), 2)
        )) AS km
    FROM sites a
    JOIN sites b ON a.site_id <> b.site_id
)
SELECT
    s.site_id, s.site_name, s.province,
    s.avg_daily_litres, s.total_margin_zar,
    MIN(p.km) AS nearest_neighbour_km
FROM sites s
JOIN pairs p ON s.site_id = p.site_id
WHERE s.investment_recommendation = 'Divest Candidate'
GROUP BY 1, 2, 3, 4, 5
HAVING MIN(p.km) > 50
ORDER BY s.avg_daily_litres DESC;
```

The business point: these sites score badly and should probably still be
kept. A network that optimises purely on site-level return abandons corridors,
and the volume does not transfer to a neighbour 200 km away — it goes to a
competitor. This is exactly why `network_investment_scorecard` exposes
`on_national_route` next to the recommendation rather than hiding it inside
the score.

---

## What each question is really for

| # | Level | Looking for |
|---|---|---|
| 1 | Intermediate | Reads the dimension before writing SQL |
| 2 | Intermediate | Understands ratio-of-sums |
| 3 | Intermediate | Handles absence and NULL safely |
| 4 | Intermediate | Knows the ranking functions apart |
| 5 | Advanced | Anticipates gaps in time series |
| 6 | Advanced | Recognises semi-additivity unprompted |
| 7 | Advanced | Can query Type-2 history correctly |
| 8 | Advanced | Translates a business question accurately |
| 9 | Staff | Reasons about physical execution; finds correctness bugs first |
| 10 | Staff | Diagnoses systematically; uses what the platform already knows |
| 11 | Staff | Refuses to answer an unanswerable question |
| 12 | Staff | Knows a model output is an input to a decision |
