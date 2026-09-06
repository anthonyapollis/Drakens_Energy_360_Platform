
# Data dictionary — core entities

## Dimensions

### dim_site
- `site_id` — synthetic surrogate/business identifier
- `site_name` — fictional site name
- `country_code`
- `province` — populated for South Africa
- `city`
- `brand` — synthetic modelling attribute
- `site_type`
- `latitude`, `longitude` — synthetic jittered coordinates
- `ownership_model`
- `convenience_flag`
- `ev_flag`
- `solar_flag`

### dim_product
- `product_id`
- `product_name`
- `product_group` — Fuel / LPG / Lubricant / Convenience
- `product_subgroup`
- `uom`

### dim_customer
- `customer_id`
- `customer_name`
- `sector`
- `country_code`
- `credit_band`
- `contract_type`

### dim_terminal
- `terminal_id`
- `terminal_name`
- `country_code`
- `capacity_litres`
- pipeline / rail / port flags

### dim_vehicle
- `vehicle_id`
- `vehicle_type`
- `capacity_litres`
- `carrier`

### dim_asset
- `asset_id`
- `site_id`
- `asset_type`
- `manufacturer`
- `install_date`

## Facts

### fact_retail_fuel_sales
Grain: one forecourt fuel transaction line.
Measures: litres, unit price, gross sales, estimated COGS, gross margin.

### fact_shop_sales
Grain: one convenience transaction line.
Measures: quantity, unit price, sales, COGS, margin.

### fact_commercial_orders
Grain: one customer/product order.
Measures: ordered/delivered volume, revenue.

### fact_inventory_snapshot
Grain: one product/location/time inventory observation.
Measures: capacity, stock, ullage, days cover.

### fact_deliveries
Grain: one physical delivery movement.
Measures: litres, distance, OTIF, delay.

### fact_procurement_receipts
Grain: one supplier receipt into a terminal.
Measures: quantity and procurement cost.

### fact_aviation_sales
Grain: one aircraft uplift.
Measures: litres and revenue.

### fact_marine_sales
Grain: one bunkering transaction.
Measures: litres and revenue.

### fact_lpg_sales
Grain: one LPG retail/commercial transaction.
Measures: kilograms and revenue.

### fact_lubricant_sales
Grain: one lubricant sale.
Measures: litres and revenue.

### fact_loyalty_transactions
Grain: one member reward transaction.
Measures: spend, earned points, redeemed points.

### fact_digital_events
Grain: one digital app event.

### fact_ev_charging_sessions
Grain: one charging session.
Measures: kWh, minutes, revenue.

### fact_solar_generation
Grain: one site telemetry interval.
Measures: generation, consumption, grid import.

### fact_maintenance_work_orders
Grain: one work order.
Measures: downtime and maintenance cost.

### fact_hsseq_incidents
Grain: one reported event.
Measures: lost time days, environmental release volume.
