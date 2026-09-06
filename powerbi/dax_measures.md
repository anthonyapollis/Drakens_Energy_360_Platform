
# Suggested DAX measures

Assume the primary fact table is `'Fact Retail Fuel Sales'`.

```DAX
Fuel Revenue :=
SUM ( 'Fact Retail Fuel Sales'[gross_sales_lcy] )

Fuel COGS :=
SUM ( 'Fact Retail Fuel Sales'[estimated_cogs_lcy] )

Fuel Gross Margin :=
[Fuel Revenue] - [Fuel COGS]

Fuel Gross Margin % :=
DIVIDE ( [Fuel Gross Margin], [Fuel Revenue] )

Litres Sold :=
SUM ( 'Fact Retail Fuel Sales'[litres] )

Fuel Transactions :=
DISTINCTCOUNT ( 'Fact Retail Fuel Sales'[transaction_id] )

Average Litres per Transaction :=
DIVIDE ( [Litres Sold], [Fuel Transactions] )

Average Selling Price per Litre :=
DIVIDE ( [Fuel Revenue], [Litres Sold] )

Gross Margin per Litre :=
DIVIDE ( [Fuel Gross Margin], [Litres Sold] )

Active Sites :=
DISTINCTCOUNT ( 'Fact Retail Fuel Sales'[site_id] )

Litres per Active Site :=
DIVIDE ( [Litres Sold], [Active Sites] )

Loyalty Transactions :=
CALCULATE (
    [Fuel Transactions],
    'Fact Retail Fuel Sales'[loyalty_flag] = TRUE ()
)

Loyalty Penetration % :=
DIVIDE ( [Loyalty Transactions], [Fuel Transactions] )

Revenue YoY % :=
VAR CurrentRevenue = [Fuel Revenue]
VAR PriorRevenue =
    CALCULATE (
        [Fuel Revenue],
        SAMEPERIODLASTYEAR ( 'Dim Date'[Date] )
    )
RETURN
    DIVIDE ( CurrentRevenue - PriorRevenue, PriorRevenue )
```

For South Africa, use ZAR as the semantic-model display currency. For cross-market reporting, keep both `amount_lcy` and a governed reporting-currency amount.
