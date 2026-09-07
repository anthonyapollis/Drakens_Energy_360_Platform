# Data dictionary

> **Independent synthetic portfolio project.** Drakens Energy is a fictional company; no real company's data is used. Every value described here is generated.

Generated from `data/lake/_manifest.json` (profile `portfolio`). Regenerate with `python scripts/generate_data_dictionary.py` after changing the model; do not edit by hand.

## Summary

| | |
|---|---:|
| Conformed dimensions | 70 |
| Bridge tables | 12 |
| Fact tables | 85 |
| Fact rows | 37,202,000 |
| Dimension rows | 5,237,720 |
| Total columns | 1,729 |

## Fact tables by domain

### Retail and forecourt

10 tables, 11,680,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_retail_fuel_sales` | 5,000,000 | 20 |
| `fact_shop_sales` | 3,000,000 | 16 |
| `fact_retail_fuel_payments` | 900,000 | 12 |
| `fact_pump_meter_readings` | 800,000 | 12 |
| `fact_tank_dips` | 700,000 | 16 |
| `fact_site_daily_operations` | 500,000 | 15 |
| `fact_forecourt_shift` | 420,000 | 14 |
| `fact_price_changes` | 260,000 | 12 |
| `fact_shop_returns` | 60,000 | 11 |
| `fact_promotions` | 40,000 | 12 |

### Commercial and B2B

9 tables, 3,590,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_commercial_order_lines` | 900,000 | 14 |
| `fact_customer_invoices` | 620,000 | 15 |
| `fact_customer_receipts` | 560,000 | 11 |
| `fact_commercial_orders` | 550,000 | 21 |
| `fact_commercial_deliveries` | 380,000 | 18 |
| `fact_customer_credit_exposure` | 300,000 | 13 |
| `fact_contract_pricing` | 120,000 | 12 |
| `fact_contract_volume_commitments` | 90,000 | 13 |
| `fact_customer_service_cases` | 70,000 | 13 |

### Supply and storage

11 tables, 3,519,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_inventory_snapshot` | 1,200,000 | 17 |
| `fact_inventory_movements` | 900,000 | 13 |
| `fact_replenishment_orders` | 260,000 | 13 |
| `fact_procurement_receipts` | 250,000 | 16 |
| `fact_terminal_issues` | 210,000 | 13 |
| `fact_procurement_orders` | 190,000 | 13 |
| `fact_terminal_throughput` | 180,000 | 15 |
| `fact_terminal_receipts` | 140,000 | 13 |
| `fact_inventory_adjustments` | 120,000 | 13 |
| `fact_stock_losses` | 60,000 | 13 |
| `fact_import_cargoes` | 9,000 | 14 |

### Logistics and fleet

5 tables, 2,070,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_delivery_events` | 1,100,000 | 14 |
| `fact_vehicle_trips` | 340,000 | 18 |
| `fact_deliveries` | 300,000 | 23 |
| `fact_fleet_costs` | 180,000 | 12 |
| `fact_route_performance` | 150,000 | 15 |

### LPG

4 tables, 890,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_lpg_sales` | 400,000 | 16 |
| `fact_lpg_cylinder_movements` | 300,000 | 12 |
| `fact_lpg_inventory_snapshot` | 120,000 | 12 |
| `fact_lpg_bulk_deliveries` | 70,000 | 13 |

### Lubricants

3 tables, 610,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_lubricant_sales` | 350,000 | 15 |
| `fact_lubricant_orders` | 150,000 | 12 |
| `fact_lubricant_inventory_snapshot` | 110,000 | 12 |

### Aviation

3 tables, 290,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_aircraft_uplifts` | 130,000 | 14 |
| `fact_aviation_sales` | 120,000 | 15 |
| `fact_aviation_inventory_snapshot` | 40,000 | 12 |

### Marine

3 tables, 180,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_marine_sales` | 90,000 | 15 |
| `fact_bunker_deliveries` | 60,000 | 13 |
| `fact_marine_inventory_snapshot` | 30,000 | 11 |

### Loyalty and digital

6 tables, 5,460,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_loyalty_transactions` | 2,000,000 | 14 |
| `fact_digital_events` | 1,500,000 | 16 |
| `fact_digital_sessions` | 700,000 | 14 |
| `fact_mobile_payments` | 520,000 | 13 |
| `fact_loyalty_points_balance` | 480,000 | 12 |
| `fact_campaign_responses` | 260,000 | 14 |

### New energy

6 tables, 2,340,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_solar_generation` | 650,000 | 17 |
| `fact_site_energy_consumption` | 600,000 | 12 |
| `fact_ev_charger_status` | 400,000 | 13 |
| `fact_grid_import_export` | 380,000 | 12 |
| `fact_energy_costs` | 160,000 | 14 |
| `fact_ev_charging_sessions` | 150,000 | 22 |

### Assets and maintenance

6 tables, 1,560,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_asset_meter_readings` | 900,000 | 14 |
| `fact_asset_inspections` | 200,000 | 14 |
| `fact_spare_parts_usage` | 190,000 | 14 |
| `fact_asset_downtime` | 120,000 | 14 |
| `fact_maintenance_work_orders` | 80,000 | 23 |
| `fact_asset_failures` | 70,000 | 15 |

### HSSEQ

7 tables, 763,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_training_compliance` | 260,000 | 14 |
| `fact_safety_observations` | 180,000 | 12 |
| `fact_permit_to_work` | 150,000 | 14 |
| `fact_vehicle_safety_events` | 90,000 | 15 |
| `fact_near_misses` | 46,000 | 12 |
| `fact_environmental_events` | 22,000 | 14 |
| `fact_hsseq_incidents` | 15,000 | 19 |

### Finance and planning

12 tables, 4,250,000 rows.

| Table | Rows | Columns |
|---|---:|---:|
| `fact_general_ledger` | 1,400,000 | 18 |
| `fact_finance_revenue_cost` | 420,000 | 16 |
| `fact_accounts_receivable` | 380,000 | 14 |
| `fact_daily_executive_kpi` | 380,000 | 20 |
| `fact_opex` | 320,000 | 12 |
| `fact_accounts_payable` | 300,000 | 12 |
| `fact_forecast` | 300,000 | 15 |
| `fact_budget` | 260,000 | 12 |
| `fact_budget_vs_actual` | 240,000 | 14 |
| `fact_cashflow` | 120,000 | 12 |
| `fact_working_capital` | 90,000 | 14 |
| `fact_capex` | 40,000 | 15 |

## Dimensions

| Dimension | Rows | Columns |
|---|---:|---:|
| `dim_airline` | 18 | 5 |
| `dim_airport` | 12 | 8 |
| `dim_asset` | 50,000 | 11 |
| `dim_asset_type` | 12 | 4 |
| `dim_budget_version` | 4 | 4 |
| `dim_business_unit` | 8 | 4 |
| `dim_campaign` | 320 | 8 |
| `dim_carrier` | 375 | 6 |
| `dim_channel` | 5 | 3 |
| `dim_city` | 88 | 9 |
| `dim_contract` | 40,000 | 16 |
| `dim_contract_type` | 5 | 3 |
| `dim_cost_centre` | 14 | 4 |
| `dim_country` | 29 | 8 |
| `dim_currency` | 25 | 4 |
| `dim_customer` | 150,000 | 19 |
| `dim_customer_sector` | 12 | 3 |
| `dim_customer_segment` | 5 | 3 |
| `dim_data_source` | 14 | 7 |
| `dim_date` | 974 | 20 |
| `dim_delivery_status` | 6 | 3 |
| `dim_depot` | 120 | 8 |
| `dim_device` | 6 | 3 |
| `dim_digital_user` | 1,800,000 | 7 |
| `dim_driver` | 18,000 | 8 |
| `dim_employee` | 45,000 | 16 |
| `dim_energy_source` | 4 | 4 |
| `dim_equipment` | 12,500 | 5 |
| `dim_ev_charger` | 2,600 | 7 |
| `dim_failure_mode` | 8 | 3 |
| `dim_forecast_version` | 8 | 4 |
| `dim_forecourt_lane` | 12 | 3 |
| `dim_gl_account` | 20 | 6 |
| `dim_incident_severity` | 5 | 4 |
| `dim_incident_type` | 9 | 3 |
| `dim_legal_entity` | 12 | 6 |
| `dim_loyalty_member` | 2,400,000 | 7 |
| `dim_lpg_cylinder_type` | 4 | 5 |
| `dim_maintenance_type` | 5 | 3 |
| `dim_order_status` | 7 | 3 |
| `dim_payment_method` | 6 | 4 |
| `dim_port` | 8 | 7 |
| `dim_price_zone` | 30 | 5 |
| `dim_product` | 31 | 19 |
| `dim_product_brand` | 4 | 3 |
| `dim_product_category` | 5 | 4 |
| `dim_profit_centre` | 20 | 4 |
| `dim_promotion` | 420 | 7 |
| `dim_province` | 9 | 5 |
| `dim_pump` | 38,000 | 7 |
| `dim_reason_code` | 9 | 3 |
| `dim_region` | 7 | 3 |
| `dim_role` | 12 | 3 |
| `dim_route` | 4,000 | 8 |
| `dim_scenario` | 5 | 3 |
| `dim_shift` | 3 | 4 |
| `dim_site` | 4,200 | 30 |
| `dim_site_type` | 7 | 3 |
| `dim_solar_asset` | 1,900 | 8 |
| `dim_supplier` | 3,000 | 16 |
| `dim_supplier_type` | 8 | 3 |
| `dim_tank` | 21,000 | 9 |
| `dim_tax` | 5 | 6 |
| `dim_terminal` | 180 | 13 |
| `dim_time` | 1,440 | 7 |
| `dim_unit_of_measure` | 6 | 5 |
| `dim_vehicle` | 15,000 | 9 |
| `dim_vessel` | 640 | 6 |
| `dim_warehouse` | 60 | 6 |
| `dim_weather` | 7 | 3 |

## Bridge tables

| Bridge | Rows | Columns |
|---|---:|---:|
| `bridge_asset_site` | 50,000 | 3 |
| `bridge_customer_contract` | 225,069 | 3 |
| `bridge_customer_hierarchy` | 150,000 | 4 |
| `bridge_customer_site` | 79,634 | 3 |
| `bridge_employee_site` | 64,552 | 3 |
| `bridge_product_hierarchy` | 31 | 4 |
| `bridge_route_site` | 12,137 | 3 |
| `bridge_security_user_scope` | 89 | 3 |
| `bridge_site_hierarchy` | 4,200 | 5 |
| `bridge_site_product` | 25,248 | 4 |
| `bridge_site_promotion` | 7,267 | 3 |
| `bridge_supplier_product` | 9,225 | 3 |

## Column detail

Full column listings for the most-used tables. Every other table follows the same naming conventions.

### `dim_site`

4,200 rows, 30 columns.

| Column | Type | Description |
|---|---|---|
| `site_id` | code | Business key. |
| `site_name` | text | Descriptive attribute. |
| `country_code` | code | Coded value. |
| `province` | text | Descriptive attribute. |
| `city` | text | Descriptive attribute. |
| `urban_class` | text | Descriptive attribute. |
| `latitude` | decimal | Numeric measure. |
| `longitude` | decimal | Numeric measure. |
| `site_type` | text | Descriptive attribute. |
| `ownership_model` | text | Descriptive attribute. |
| `on_national_route` | boolean | Boolean indicator. |
| `site_key` | integer | Surrogate key. |
| `forecourt_lanes` | integer | Whole number. |
| `has_convenience` | boolean | Boolean indicator. |
| `has_qsr` | boolean | Boolean indicator. |
| `has_car_wash` | boolean | Boolean indicator. |
| `has_ev_charging` | boolean | Boolean indicator. |
| `has_solar` | boolean | Boolean indicator. |
| `has_lpg` | boolean | Boolean indicator. |
| `is_24_hour` | boolean | Boolean indicator. |
| `opened_date` | timestamp | Calendar date. |
| `site_status` | text | Descriptive attribute. |
| `demand_index` | decimal | Numeric measure. |
| `effective_from_date` | timestamp | Calendar date. |
| `effective_to_date` | timestamp | Calendar date. |
| `is_current` | boolean | Boolean indicator. |
| `scd_version` | integer | Whole number. |
| `record_source` | text | Descriptive attribute. |
| `dw_load_ts` | timestamp | Event timestamp. |
| `dw_hash_diff` | text | Descriptive attribute. |

### `dim_customer`

150,000 rows, 19 columns.

| Column | Type | Description |
|---|---|---|
| `customer_id` | code | Business key. |
| `customer_key` | integer | Surrogate key. |
| `customer_name` | text | Descriptive attribute. |
| `sector` | text | Descriptive attribute. |
| `segment` | text | Descriptive attribute. |
| `country_code` | code | Coded value. |
| `credit_band` | text | Descriptive attribute. |
| `credit_limit_zar` | decimal | Amount in South African rand. |
| `payment_terms_days` | integer | Whole number. |
| `onboarded_date` | timestamp | Calendar date. |
| `is_active` | boolean | Boolean indicator. |
| `revenue_index` | decimal | Numeric measure. |
| `effective_from_date` | timestamp | Calendar date. |
| `effective_to_date` | timestamp | Calendar date. |
| `is_current` | boolean | Boolean indicator. |
| `scd_version` | integer | Whole number. |
| `record_source` | text | Descriptive attribute. |
| `dw_load_ts` | timestamp | Event timestamp. |
| `dw_hash_diff` | text | Descriptive attribute. |

### `dim_product`

31 rows, 19 columns.

| Column | Type | Description |
|---|---|---|
| `product_id` | code | Business key. |
| `product_name` | text | Descriptive attribute. |
| `category` | text | Descriptive attribute. |
| `subcategory` | text | Descriptive attribute. |
| `uom` | text | Descriptive attribute. |
| `base_price_zar` | decimal | Amount in South African rand. |
| `base_cost_zar` | decimal | Amount in South African rand. |
| `regulated` | boolean | Boolean indicator. |
| `product_key` | integer | Surrogate key. |
| `brand` | text | Descriptive attribute. |
| `hazard_class` | text | Descriptive attribute. |
| `shelf_life_days` | integer | Whole number. |
| `effective_from_date` | timestamp | Calendar date. |
| `effective_to_date` | timestamp | Calendar date. |
| `is_current` | boolean | Boolean indicator. |
| `scd_version` | integer | Whole number. |
| `record_source` | text | Descriptive attribute. |
| `dw_load_ts` | timestamp | Event timestamp. |
| `dw_hash_diff` | text | Descriptive attribute. |

### `dim_date`

974 rows, 20 columns.

| Column | Type | Description |
|---|---|---|
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `full_date` | timestamp | Calendar date. |
| `day_of_month` | integer | Whole number. |
| `day_of_week` | integer | Whole number. |
| `day_name` | text | Descriptive attribute. |
| `day_of_year` | integer | Whole number. |
| `week_of_year` | integer | Whole number. |
| `month_number` | integer | Whole number. |
| `month_name` | text | Descriptive attribute. |
| `quarter_number` | integer | Whole number. |
| `quarter_name` | text | Descriptive attribute. |
| `calendar_year` | integer | Whole number. |
| `fiscal_year` | integer | Whole number. |
| `fiscal_quarter` | integer | Whole number. |
| `fiscal_period` | integer | Whole number. |
| `is_weekend` | boolean | Boolean indicator. |
| `is_public_holiday_za` | boolean | Boolean indicator. |
| `is_trading_day` | boolean | Boolean indicator. |
| `season_southern` | text | Descriptive attribute. |
| `school_holiday_za` | boolean | Boolean indicator. |

### `dim_asset`

50,000 rows, 11 columns.

| Column | Type | Description |
|---|---|---|
| `asset_id` | code | Business key. |
| `asset_key` | integer | Surrogate key. |
| `site_id` | code | Business key. |
| `asset_type` | text | Descriptive attribute. |
| `manufacturer` | text | Descriptive attribute. |
| `model_code` | code | Coded value. |
| `install_date` | timestamp | Calendar date. |
| `replacement_value_zar` | decimal | Amount in South African rand. |
| `criticality` | text | Descriptive attribute. |
| `age_years` | decimal | Numeric measure. |
| `failure_propensity` | decimal | Numeric measure. |

### `fact_retail_fuel_sales`

5,000,000 rows, 20 columns.

| Column | Type | Description |
|---|---|---|
| `transaction_id` | code | Business key. |
| `transaction_ts` | timestamp | Event timestamp. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `time_key` | integer | Minute-of-day key joining dim_time. |
| `site_id` | code | Business key. |
| `product_id` | code | Business key. |
| `pump_number` | integer | Whole number. |
| `forecourt_lane` | integer | Whole number. |
| `shift_name` | text | Descriptive attribute. |
| `litres` | decimal | Numeric measure. |
| `unit_price_zar` | decimal | Amount in South African rand. |
| `gross_sales_zar` | decimal | Amount in South African rand. |
| `cogs_zar` | decimal | Amount in South African rand. |
| `gross_margin_zar` | decimal | Amount in South African rand. |
| `payment_method` | text | Descriptive attribute. |
| `loyalty_flag` | boolean | Boolean indicator. |
| `loyalty_member_id` | code | Business key. |
| `is_fleet_sale` | boolean | Boolean indicator. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

### `fact_commercial_orders`

550,000 rows, 21 columns.

| Column | Type | Description |
|---|---|---|
| `order_id` | code | Business key. |
| `order_ts` | timestamp | Event timestamp. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `customer_id` | code | Business key. |
| `contract_id` | code | Business key. |
| `product_id` | code | Business key. |
| `sector` | text | Descriptive attribute. |
| `segment` | text | Descriptive attribute. |
| `channel` | text | Descriptive attribute. |
| `volume_litres` | decimal | Volume in litres. |
| `list_price_zar` | decimal | Amount in South African rand. |
| `discount_cents_per_litre` | decimal | Numeric measure. |
| `net_price_zar` | decimal | Amount in South African rand. |
| `revenue_zar` | decimal | Amount in South African rand. |
| `cogs_zar` | decimal | Amount in South African rand. |
| `gross_margin_zar` | decimal | Amount in South African rand. |
| `order_status` | text | Descriptive attribute. |
| `requested_delivery_date` | timestamp | Calendar date. |
| `payment_terms_days` | integer | Whole number. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

### `fact_deliveries`

300,000 rows, 23 columns.

| Column | Type | Description |
|---|---|---|
| `delivery_id` | code | Business key. |
| `planned_arrival_ts` | timestamp | Event timestamp. |
| `actual_arrival_ts` | timestamp | Event timestamp. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `route_id` | code | Business key. |
| `origin_terminal_id` | code | Business key. |
| `destination_site_id` | code | Business key. |
| `vehicle_id` | code | Business key. |
| `driver_id` | code | Business key. |
| `carrier_id` | code | Business key. |
| `product_id` | code | Business key. |
| `planned_litres` | decimal | Volume in litres. |
| `delivered_litres` | decimal | Volume in litres. |
| `fill_rate_pct` | decimal | Percentage. Non-additive: recompute from its components. |
| `distance_km` | decimal | Distance in kilometres. |
| `drop_count` | integer | Count. |
| `delay_minutes` | integer | Duration in minutes. |
| `is_late` | boolean | Boolean indicator. |
| `otif_flag` | boolean | Boolean indicator. |
| `delivery_status` | text | Descriptive attribute. |
| `reason_code` | code | Coded value. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

### `fact_inventory_snapshot`

1,200,000 rows, 17 columns.

| Column | Type | Description |
|---|---|---|
| `snapshot_id` | code | Business key. |
| `snapshot_ts` | timestamp | Event timestamp. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `location_type` | text | Descriptive attribute. |
| `site_id` | code | Business key. |
| `terminal_id` | code | Business key. |
| `product_id` | code | Business key. |
| `capacity_litres` | decimal | Volume in litres. |
| `stock_on_hand_litres` | decimal | Volume in litres. |
| `ullage_litres` | decimal | Volume in litres. |
| `fill_pct` | decimal | Percentage. Non-additive: recompute from its components. |
| `average_daily_usage_litres` | decimal | Volume in litres. |
| `days_of_cover` | decimal | Numeric measure. |
| `is_stock_out_risk` | boolean | Boolean indicator. |
| `reorder_point_litres` | decimal | Volume in litres. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

### `fact_maintenance_work_orders`

80,000 rows, 23 columns.

| Column | Type | Description |
|---|---|---|
| `work_order_id` | code | Business key. |
| `raised_ts` | timestamp | Event timestamp. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `asset_id` | code | Business key. |
| `site_id` | code | Business key. |
| `asset_type` | text | Descriptive attribute. |
| `criticality` | text | Descriptive attribute. |
| `asset_age_years` | decimal | Numeric measure. |
| `maintenance_type` | text | Descriptive attribute. |
| `failure_mode` | text | Descriptive attribute. |
| `priority` | text | Descriptive attribute. |
| `response_hours` | decimal | Duration in hours. |
| `labour_hours` | decimal | Duration in hours. |
| `labour_cost_zar` | decimal | Amount in South African rand. |
| `parts_cost_zar` | decimal | Amount in South African rand. |
| `total_cost_zar` | decimal | Amount in South African rand. |
| `completed_ts` | timestamp | Event timestamp. |
| `is_completed` | boolean | Boolean indicator. |
| `is_breakdown` | boolean | Boolean indicator. |
| `technician_employee_id` | code | Business key. |
| `sla_breached` | boolean | Boolean indicator. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

### `fact_ev_charging_sessions`

150,000 rows, 22 columns.

| Column | Type | Description |
|---|---|---|
| `ev_session_id` | code | Business key. |
| `session_start_ts` | timestamp | Event timestamp. |
| `session_end_ts` | timestamp | Event timestamp. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `time_key` | integer | Minute-of-day key joining dim_time. |
| `ev_charger_id` | code | Business key. |
| `site_id` | code | Business key. |
| `connector_type` | text | Descriptive attribute. |
| `rated_power_kw` | decimal | Numeric measure. |
| `duration_minutes` | decimal | Duration in minutes. |
| `energy_kwh` | decimal | Energy in kilowatt hours. |
| `average_power_kw` | decimal | Numeric measure. |
| `tariff_zar_per_kwh` | decimal | Energy in kilowatt hours. |
| `revenue_zar` | decimal | Amount in South African rand. |
| `grid_cost_zar` | decimal | Amount in South African rand. |
| `gross_margin_zar` | decimal | Amount in South African rand. |
| `start_soc_pct` | decimal | Percentage. Non-additive: recompute from its components. |
| `end_soc_pct` | decimal | Percentage. Non-additive: recompute from its components. |
| `payment_method` | text | Descriptive attribute. |
| `session_ended_by` | text | Descriptive attribute. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

### `fact_solar_generation`

650,000 rows, 17 columns.

| Column | Type | Description |
|---|---|---|
| `solar_reading_id` | code | Business key. |
| `reading_ts` | timestamp | Event timestamp. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `time_key` | integer | Minute-of-day key joining dim_time. |
| `solar_asset_id` | code | Business key. |
| `site_id` | code | Business key. |
| `installed_kwp` | decimal | Numeric measure. |
| `interval_minutes` | integer | Duration in minutes. |
| `energy_kwh` | decimal | Energy in kilowatt hours. |
| `irradiance_w_m2` | decimal | Numeric measure. |
| `panel_temperature_celsius` | decimal | Numeric measure. |
| `inverter_efficiency_pct` | decimal | Percentage. Non-additive: recompute from its components. |
| `capacity_factor` | decimal | Numeric measure. |
| `is_daylight` | boolean | Boolean indicator. |
| `co2_avoided_kg` | decimal | Mass in kilograms. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

### `fact_general_ledger`

1,400,000 rows, 18 columns.

| Column | Type | Description |
|---|---|---|
| `journal_line_id` | code | Business key. |
| `posting_date` | timestamp | Calendar date. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `journal_id` | code | Business key. |
| `gl_account_code` | code | Coded value. |
| `account_class` | text | Descriptive attribute. |
| `cost_centre_code` | code | Coded value. |
| `profit_centre_code` | code | Coded value. |
| `legal_entity_code` | code | Coded value. |
| `debit_amount_zar` | decimal | Amount in South African rand. |
| `credit_amount_zar` | decimal | Amount in South African rand. |
| `signed_amount_zar` | decimal | Amount in South African rand. |
| `currency_code` | code | Coded value. |
| `document_type` | text | Descriptive attribute. |
| `is_reversal` | boolean | Boolean indicator. |
| `fiscal_period` | integer | Whole number. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

### `fact_hsseq_incidents`

15,000 rows, 19 columns.

| Column | Type | Description |
|---|---|---|
| `incident_id` | code | Business key. |
| `incident_ts` | timestamp | Event timestamp. |
| `date_key` | integer | Integer yyyymmdd key joining dim_date. |
| `site_id` | code | Business key. |
| `incident_type` | text | Descriptive attribute. |
| `severity` | text | Descriptive attribute. |
| `severity_rank` | integer | Whole number. |
| `is_lost_time_injury` | boolean | Boolean indicator. |
| `lost_days` | decimal | Numeric measure. |
| `people_affected` | integer | Whole number. |
| `estimated_cost_zar` | decimal | Amount in South African rand. |
| `is_reportable` | boolean | Boolean indicator. |
| `root_cause_category` | text | Descriptive attribute. |
| `corrective_actions_raised` | integer | Whole number. |
| `corrective_actions_closed` | integer | Whole number. |
| `investigation_days` | decimal | Numeric measure. |
| `reported_by_employee_id` | code | Business key. |
| `source_system_code` | code | Originating source system, joins dim_data_source. |
| `ingested_at` | timestamp | When the record landed in bronze. |

## Conventions

| Suffix | Meaning |
|---|---|
| `_id` | Business key from the source system |
| `_key` | Surrogate key generated by the warehouse |
| `_zar` | Amount in South African rand |
| `_pct` | Percentage. Non-additive: recompute from components, never average |
| `_ts` | Event timestamp |
| `_flag`, `is_`, `has_` | Boolean |

Two conventions matter more than the rest:

1. **Percentages are never additive.** A column ending `_pct` exists for inspection of a single row. Aggregate by recomputing from the numerator and denominator, never by averaging the column.
2. **Snapshot measures are semi-additive.** Stock on hand may be summed across locations but never across time. Summing a month of daily snapshots reports the stock as though it existed simultaneously.

