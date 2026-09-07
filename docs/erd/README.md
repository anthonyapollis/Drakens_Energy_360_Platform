# ERD — conformed dimensions

> **Independent synthetic portfolio project.** Drakens Energy is a fictional company; no real company's data is used.

Generated from the build manifest by `scripts/generate_erd.py`.

The value of a conformed dimension is its **reach**: `dim_site` joins retail, supply, maintenance and safety, which is what makes it possible to ask one question of all four. It is also why an error in a high-reach dimension is wrong in dozens of places at once.

```mermaid
erDiagram
    DIM_DATE {
        string date_id PK
        int joins_85_fact_tables
    }
    DIM_DATA_SOURCE {
        string data_source_id PK
        int joins_85_fact_tables
    }
    DIM_SITE {
        string site_id PK
        int joins_46_fact_tables
    }
    DIM_PRODUCT {
        string product_id PK
        int joins_32_fact_tables
    }
    DIM_CUSTOMER {
        string customer_id PK
        int joins_15_fact_tables
    }
    DIM_TERMINAL {
        string terminal_id PK
        int joins_11_fact_tables
    }
    DIM_VEHICLE {
        string vehicle_id PK
        int joins_8_fact_tables
    }
    DIM_COST_CENTRE {
        string cost_centre_id PK
        int joins_7_fact_tables
    }
    DIM_ASSET {
        string asset_id PK
        int joins_6_fact_tables
    }
    DIM_BUSINESS_UNIT {
        string business_unit_id PK
        int joins_6_fact_tables
    }
    RETAIL_FACTS {
        int 10_tables
    }
    COMMERCIAL_FACTS {
        int 9_tables
    }
    SUPPLY_FACTS {
        int 11_tables
    }
    LOGISTICS_FACTS {
        int 5_tables
    }
    PRODUCTS_FACTS {
        int 13_tables
    }
    DIGITAL_FACTS {
        int 6_tables
    }
    ENERGY_FACTS {
        int 6_tables
    }
    ASSETS_FACTS {
        int 6_tables
    }
    HSSEQ_FACTS {
        int 7_tables
    }
    FINANCE_FACTS {
        int 12_tables
    }
    DIM_DATE ||--o{ ASSETS_FACTS : ""
    DIM_DATE ||--o{ COMMERCIAL_FACTS : ""
    DIM_DATE ||--o{ DIGITAL_FACTS : ""
    DIM_DATE ||--o{ ENERGY_FACTS : ""
    DIM_DATE ||--o{ FINANCE_FACTS : ""
    DIM_DATE ||--o{ HSSEQ_FACTS : ""
    DIM_DATE ||--o{ LOGISTICS_FACTS : ""
    DIM_DATE ||--o{ PRODUCTS_FACTS : ""
    DIM_DATE ||--o{ RETAIL_FACTS : ""
    DIM_DATE ||--o{ SUPPLY_FACTS : ""
    DIM_DATA_SOURCE ||--o{ ASSETS_FACTS : ""
    DIM_DATA_SOURCE ||--o{ COMMERCIAL_FACTS : ""
    DIM_DATA_SOURCE ||--o{ DIGITAL_FACTS : ""
    DIM_DATA_SOURCE ||--o{ ENERGY_FACTS : ""
    DIM_DATA_SOURCE ||--o{ FINANCE_FACTS : ""
    DIM_DATA_SOURCE ||--o{ HSSEQ_FACTS : ""
    DIM_DATA_SOURCE ||--o{ LOGISTICS_FACTS : ""
    DIM_DATA_SOURCE ||--o{ PRODUCTS_FACTS : ""
    DIM_DATA_SOURCE ||--o{ RETAIL_FACTS : ""
    DIM_DATA_SOURCE ||--o{ SUPPLY_FACTS : ""
    DIM_SITE ||--o{ ASSETS_FACTS : ""
    DIM_SITE ||--o{ DIGITAL_FACTS : ""
    DIM_SITE ||--o{ ENERGY_FACTS : ""
    DIM_SITE ||--o{ FINANCE_FACTS : ""
    DIM_SITE ||--o{ HSSEQ_FACTS : ""
    DIM_SITE ||--o{ LOGISTICS_FACTS : ""
    DIM_SITE ||--o{ PRODUCTS_FACTS : ""
    DIM_SITE ||--o{ RETAIL_FACTS : ""
    DIM_SITE ||--o{ SUPPLY_FACTS : ""
    DIM_PRODUCT ||--o{ COMMERCIAL_FACTS : ""
    DIM_PRODUCT ||--o{ FINANCE_FACTS : ""
    DIM_PRODUCT ||--o{ LOGISTICS_FACTS : ""
    DIM_PRODUCT ||--o{ PRODUCTS_FACTS : ""
    DIM_PRODUCT ||--o{ RETAIL_FACTS : ""
    DIM_PRODUCT ||--o{ SUPPLY_FACTS : ""
    DIM_CUSTOMER ||--o{ COMMERCIAL_FACTS : ""
    DIM_CUSTOMER ||--o{ FINANCE_FACTS : ""
    DIM_CUSTOMER ||--o{ PRODUCTS_FACTS : ""
    DIM_TERMINAL ||--o{ HSSEQ_FACTS : ""
    DIM_TERMINAL ||--o{ LOGISTICS_FACTS : ""
    DIM_TERMINAL ||--o{ SUPPLY_FACTS : ""
    DIM_VEHICLE ||--o{ COMMERCIAL_FACTS : ""
    DIM_VEHICLE ||--o{ HSSEQ_FACTS : ""
    DIM_VEHICLE ||--o{ LOGISTICS_FACTS : ""
    DIM_VEHICLE ||--o{ PRODUCTS_FACTS : ""
    DIM_VEHICLE ||--o{ SUPPLY_FACTS : ""
    DIM_COST_CENTRE ||--o{ ENERGY_FACTS : ""
    DIM_COST_CENTRE ||--o{ FINANCE_FACTS : ""
    DIM_COST_CENTRE ||--o{ LOGISTICS_FACTS : ""
    DIM_ASSET ||--o{ ASSETS_FACTS : ""
    DIM_BUSINESS_UNIT ||--o{ FINANCE_FACTS : ""
```

## Dimension reach

| Conformed dimension | Fact tables | Domains |
|---|---:|---:|
| `dim_date` | 85 | 10 |
| `dim_data_source` | 85 | 10 |
| `dim_site` | 46 | 9 |
| `dim_product` | 32 | 6 |
| `dim_customer` | 15 | 3 |
| `dim_terminal` | 11 | 3 |
| `dim_vehicle` | 8 | 5 |
| `dim_cost_centre` | 7 | 3 |
| `dim_asset` | 6 | 1 |
| `dim_business_unit` | 6 | 1 |
| `dim_supplier` | 5 | 2 |
| `dim_time` | 5 | 3 |
| `dim_gl_account` | 4 | 1 |
| `dim_digital_user` | 4 | 1 |
| `dim_airport` | 3 | 1 |
| `dim_port` | 3 | 1 |
| `dim_vessel` | 3 | 2 |
| `dim_legal_entity` | 3 | 1 |
| `dim_contract` | 3 | 1 |
| `dim_route` | 3 | 1 |
| `dim_driver` | 3 | 2 |
| `dim_loyalty_member` | 3 | 2 |
| `dim_depot` | 3 | 1 |
| `dim_warehouse` | 3 | 2 |
| `dim_airline` | 2 | 1 |
| `dim_carrier` | 2 | 1 |
| `dim_ev_charger` | 2 | 1 |
| `dim_campaign` | 1 | 1 |
| `dim_profit_centre` | 1 | 1 |
| `dim_promotion` | 1 | 1 |
| `dim_pump` | 1 | 1 |
| `dim_solar_asset` | 1 | 1 |
| `dim_tank` | 1 | 1 |
| `dim_employee` | 1 | 1 |

## Domain diagrams

- [Retail and forecourt](erd_retail.md)
- [Commercial and B2B](erd_commercial.md)
- [Supply and storage](erd_supply.md)
- [Logistics and fleet](erd_logistics.md)
- [LPG, lubricants, aviation and marine](erd_products.md)
- [Loyalty and digital](erd_digital.md)
- [New energy](erd_energy.md)
- [Assets and maintenance](erd_assets.md)
- [HSSEQ](erd_hsseq.md)
- [Finance and planning](erd_finance.md)

