
# Complete Enterprise Dimensional Model

This is the **complete enterprise dimensional-model specification** for the synthetic downstream-energy platform.

> Independent synthetic portfolio project only. No internal Vivo Energy, Engen, Shell or Vitol data is used.

## Conformed Dimensions

### Core enterprise dimensions
1. `dim_date`
2. `dim_time`
3. `dim_country`
4. `dim_region`
5. `dim_province`
6. `dim_city`
7. `dim_currency`
8. `dim_business_unit`
9. `dim_legal_entity`
10. `dim_site`
11. `dim_site_type`
12. `dim_terminal`
13. `dim_depot`
14. `dim_warehouse`
15. `dim_product`
16. `dim_product_category`
17. `dim_product_brand`
18. `dim_unit_of_measure`
19. `dim_customer`
20. `dim_customer_segment`
21. `dim_customer_sector`
22. `dim_supplier`
23. `dim_supplier_type`
24. `dim_contract`
25. `dim_contract_type`
26. `dim_channel`
27. `dim_payment_method`
28. `dim_promotion`
29. `dim_price_zone`
30. `dim_tax`
31. `dim_cost_centre`
32. `dim_profit_centre`
33. `dim_gl_account`
34. `dim_employee`
35. `dim_role`
36. `dim_vehicle`
37. `dim_driver`
38. `dim_carrier`
39. `dim_route`
40. `dim_asset`
41. `dim_asset_type`
42. `dim_equipment`
43. `dim_tank`
44. `dim_pump`
45. `dim_incident_type`
46. `dim_incident_severity`
47. `dim_maintenance_type`
48. `dim_failure_mode`
49. `dim_loyalty_member`
50. `dim_digital_user`
51. `dim_device`
52. `dim_campaign`
53. `dim_weather`
54. `dim_energy_source`
55. `dim_ev_charger`
56. `dim_solar_asset`
57. `dim_airport`
58. `dim_airline`
59. `dim_port`
60. `dim_vessel`
61. `dim_lpg_cylinder_type`
62. `dim_delivery_status`
63. `dim_order_status`
64. `dim_shift`
65. `dim_forecourt_lane`
66. `dim_reason_code`
67. `dim_data_source`
68. `dim_scenario`
69. `dim_budget_version`
70. `dim_forecast_version`

## Fact Tables

### Retail and forecourt
1. `fact_retail_fuel_sales`
2. `fact_retail_fuel_payments`
3. `fact_shop_sales`
4. `fact_shop_returns`
5. `fact_forecourt_shift`
6. `fact_pump_meter_readings`
7. `fact_tank_dips`
8. `fact_price_changes`
9. `fact_promotions`
10. `fact_site_daily_operations`

### Commercial / B2B
11. `fact_commercial_orders`
12. `fact_commercial_order_lines`
13. `fact_commercial_deliveries`
14. `fact_contract_volume_commitments`
15. `fact_contract_pricing`
16. `fact_customer_invoices`
17. `fact_customer_receipts`
18. `fact_customer_credit_exposure`
19. `fact_customer_service_cases`

### Supply, procurement, storage and logistics
20. `fact_procurement_orders`
21. `fact_procurement_receipts`
22. `fact_import_cargoes`
23. `fact_terminal_receipts`
24. `fact_terminal_issues`
25. `fact_terminal_throughput`
26. `fact_inventory_snapshot`
27. `fact_inventory_movements`
28. `fact_inventory_adjustments`
29. `fact_stock_losses`
30. `fact_replenishment_orders`
31. `fact_deliveries`
32. `fact_delivery_events`
33. `fact_vehicle_trips`
34. `fact_route_performance`
35. `fact_fleet_costs`

### LPG
36. `fact_lpg_sales`
37. `fact_lpg_cylinder_movements`
38. `fact_lpg_bulk_deliveries`
39. `fact_lpg_inventory_snapshot`

### Lubricants
40. `fact_lubricant_sales`
41. `fact_lubricant_orders`
42. `fact_lubricant_inventory_snapshot`

### Aviation
43. `fact_aviation_sales`
44. `fact_aircraft_uplifts`
45. `fact_aviation_inventory_snapshot`

### Marine
46. `fact_marine_sales`
47. `fact_bunker_deliveries`
48. `fact_marine_inventory_snapshot`

### Loyalty / Digital
49. `fact_loyalty_transactions`
50. `fact_loyalty_points_balance`
51. `fact_digital_events`
52. `fact_mobile_payments`
53. `fact_digital_sessions`
54. `fact_campaign_responses`

### EV / Solar / New Energy
55. `fact_ev_charging_sessions`
56. `fact_ev_charger_status`
57. `fact_solar_generation`
58. `fact_site_energy_consumption`
59. `fact_grid_import_export`
60. `fact_energy_costs`

### Maintenance / Assets
61. `fact_maintenance_work_orders`
62. `fact_asset_downtime`
63. `fact_asset_inspections`
64. `fact_asset_failures`
65. `fact_spare_parts_usage`
66. `fact_asset_meter_readings`

### HSSEQ
67. `fact_hsseq_incidents`
68. `fact_near_misses`
69. `fact_environmental_events`
70. `fact_safety_observations`
71. `fact_training_compliance`
72. `fact_permit_to_work`
73. `fact_vehicle_safety_events`

### Finance / Planning / Executive
74. `fact_finance_revenue_cost`
75. `fact_general_ledger`
76. `fact_accounts_receivable`
77. `fact_accounts_payable`
78. `fact_capex`
79. `fact_opex`
80. `fact_budget`
81. `fact_forecast`
82. `fact_budget_vs_actual`
83. `fact_cashflow`
84. `fact_working_capital`
85. `fact_daily_executive_kpi`

## Bridge / helper tables

1. `bridge_site_product`
2. `bridge_customer_contract`
3. `bridge_customer_site`
4. `bridge_site_promotion`
5. `bridge_employee_site`
6. `bridge_asset_site`
7. `bridge_supplier_product`
8. `bridge_route_site`
9. `bridge_customer_hierarchy`
10. `bridge_product_hierarchy`
11. `bridge_site_hierarchy`
12. `bridge_security_user_scope`

## Required grain examples

| Fact | Grain |
|---|---|
| `fact_retail_fuel_sales` | One row per fuel sales transaction line |
| `fact_shop_sales` | One row per convenience transaction line |
| `fact_commercial_order_lines` | One row per order-product line |
| `fact_inventory_snapshot` | One row per location-product-snapshot timestamp |
| `fact_deliveries` | One row per physical delivery |
| `fact_terminal_throughput` | One row per terminal-product-day |
| `fact_lpg_sales` | One row per LPG transaction |
| `fact_aviation_sales` | One row per aircraft uplift transaction |
| `fact_marine_sales` | One row per bunkering sale |
| `fact_loyalty_transactions` | One row per loyalty earn/burn event |
| `fact_digital_events` | One row per digital event |
| `fact_ev_charging_sessions` | One row per EV charging session |
| `fact_solar_generation` | One row per site/solar asset/telemetry interval |
| `fact_maintenance_work_orders` | One row per work order |
| `fact_hsseq_incidents` | One row per reported incident |
| `fact_general_ledger` | One row per posted journal line |
| `fact_budget` | One row per account/cost centre/period/version |
| `fact_daily_executive_kpi` | One row per site/business unit/day KPI snapshot |

## South African geography

The synthetic data generator must include:
- all 9 provinces
- major cities and towns
- approximately 1,050 synthetic South African service stations
- synthetic terminals, depots, distribution nodes and customer locations
- GPS coordinates jittered around real city/town centres
- no claim that generated station coordinates represent actual operational sites

## Fact volume target

The default portfolio build should exceed **15 million fact rows**.

For a stronger enterprise run, scale toward **100 million+ fact rows** across:
- retail fuel
- shop transactions
- digital events
- loyalty events
- inventory snapshots
- telemetry
- deliveries
- commercial orders
- finance

## Required deliverables

- Full ERD
- Domain-level star schemas
- Kimball bus matrix
- Complete data dictionary
- SQL DDL
- dbt staging/intermediate/marts
- dbt tests and documentation
- Databricks Bronze/Silver/Gold pipelines
- Delta Lake MERGE patterns
- Auto Loader and Structured Streaming
- Unity Catalog RBAC / masking / lineage
- CI/CD
- Power BI semantic model
- DAX measures
- ML use cases
- synthetic-data generator
- deployment guide
- portfolio case study
