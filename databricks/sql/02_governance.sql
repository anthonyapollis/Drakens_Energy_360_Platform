-- =====================================================================
-- Drakens Energy 360 - Unity Catalog governance
--
-- Three things are configured here, in the order they matter:
--   1. Group grants   - who can read which layer
--   2. Column masking - PII is masked by default, unmasked by exception
--   3. Row filtering  - a regional analyst sees only their provinces
--
-- The principle is that the *default* is restrictive. A new analyst added to
-- the analyst group sees masked customer names and no rows outside their
-- scope until someone deliberately grants more. Getting this the other way
-- round is how data platforms leak.
-- =====================================================================

USE CATALOG drakens_${env};

-- ---------------------------------------------------------------------
-- 1. Groups and grants
-- ---------------------------------------------------------------------
-- Groups are managed in the account console / SCIM, not created here.
--   drakens_platform_engineers - own the pipelines
--   drakens_data_analysts      - read gold, masked PII
--   drakens_commercial_team    - read gold + unmasked customer names
--   drakens_data_scientists    - read silver + gold, write ml schema
--   drakens_executives         - read the executive aggregates only

GRANT USE CATALOG ON CATALOG drakens_${env} TO `drakens_platform_engineers`;
GRANT USE CATALOG ON CATALOG drakens_${env} TO `drakens_data_analysts`;
GRANT USE CATALOG ON CATALOG drakens_${env} TO `drakens_commercial_team`;
GRANT USE CATALOG ON CATALOG drakens_${env} TO `drakens_data_scientists`;
GRANT USE CATALOG ON CATALOG drakens_${env} TO `drakens_executives`;

-- Engineers own bronze and silver outright.
GRANT ALL PRIVILEGES ON SCHEMA bronze TO `drakens_platform_engineers`;
GRANT ALL PRIVILEGES ON SCHEMA silver TO `drakens_platform_engineers`;
GRANT ALL PRIVILEGES ON SCHEMA gold TO `drakens_platform_engineers`;
GRANT ALL PRIVILEGES ON SCHEMA platform TO `drakens_platform_engineers`;

-- Analysts get gold only. Deliberately no bronze access: raw data has no
-- conformed definitions and any number taken from it will disagree with the
-- dashboard.
GRANT USE SCHEMA, SELECT ON SCHEMA gold TO `drakens_data_analysts`;
GRANT USE SCHEMA, SELECT ON SCHEMA platform TO `drakens_data_analysts`;

GRANT USE SCHEMA, SELECT ON SCHEMA gold TO `drakens_commercial_team`;

-- Scientists need silver for feature engineering and own the ml schema.
GRANT USE SCHEMA, SELECT ON SCHEMA silver TO `drakens_data_scientists`;
GRANT USE SCHEMA, SELECT ON SCHEMA gold TO `drakens_data_scientists`;
GRANT ALL PRIVILEGES ON SCHEMA ml TO `drakens_data_scientists`;

-- Executives see only the pre-aggregated tables, not transaction detail.
GRANT USE SCHEMA ON SCHEMA gold TO `drakens_executives`;
GRANT SELECT ON TABLE gold.agg_executive_daily_kpi TO `drakens_executives`;
GRANT SELECT ON TABLE gold.network_investment_scorecard TO `drakens_executives`;


-- ---------------------------------------------------------------------
-- 2. Column masking
-- ---------------------------------------------------------------------
-- Masks are functions applied at query time. The underlying data is never
-- copied or duplicated, so there is exactly one customer table and no
-- "safe copy" to drift out of sync.

CREATE OR REPLACE FUNCTION gold.mask_customer_name(name STRING)
RETURN CASE
    WHEN is_account_group_member('drakens_commercial_team') THEN name
    WHEN is_account_group_member('drakens_platform_engineers') THEN name
    -- Keep the first three characters so an analyst can still tell two
    -- customers apart in a chart without seeing the identity.
    ELSE CONCAT(SUBSTR(name, 1, 3), REPEAT('*', GREATEST(LENGTH(name) - 3, 0)))
END;

CREATE OR REPLACE FUNCTION gold.mask_credit_limit(amount DECIMAL(18,2))
RETURN CASE
    WHEN is_account_group_member('drakens_commercial_team') THEN amount
    WHEN is_account_group_member('drakens_platform_engineers') THEN amount
    ELSE NULL
END;

CREATE OR REPLACE FUNCTION gold.mask_loyalty_member(member_id STRING)
RETURN CASE
    WHEN is_account_group_member('drakens_platform_engineers') THEN member_id
    -- Analysts get a stable pseudonym: still joinable and countable, but not
    -- resolvable back to a person.
    ELSE sha2(concat(member_id, 'drakens360-pseudonym-salt'), 256)
END;

ALTER TABLE gold.dim_customer
    ALTER COLUMN customer_name SET MASK gold.mask_customer_name;

ALTER TABLE gold.dim_customer
    ALTER COLUMN credit_limit_zar SET MASK gold.mask_credit_limit;

ALTER TABLE gold.fct_retail_fuel_sales
    ALTER COLUMN loyalty_member_id SET MASK gold.mask_loyalty_member;


-- ---------------------------------------------------------------------
-- 3. Row filtering
-- ---------------------------------------------------------------------
-- A regional analyst should not see another region's sites at all. The scope
-- comes from a table, not from hard-coded group names, so adding a region to
-- someone's remit is a data change and not a deployment.

CREATE OR REPLACE FUNCTION gold.province_row_filter(province STRING)
RETURN
    is_account_group_member('drakens_platform_engineers')
    OR is_account_group_member('drakens_executives')
    OR EXISTS (
        SELECT 1
        FROM gold.bridge_security_user_scope s
        WHERE s.user_principal = current_user()
          AND (
                (s.scope_type = 'all')
             OR (s.scope_type = 'province' AND s.scope_value = province)
          )
    );

ALTER TABLE gold.dim_site
    SET ROW FILTER gold.province_row_filter ON (province);

ALTER TABLE gold.network_investment_scorecard
    SET ROW FILTER gold.province_row_filter ON (province);

ALTER TABLE gold.agg_executive_daily_kpi
    SET ROW FILTER gold.province_row_filter ON (province);


-- ---------------------------------------------------------------------
-- 4. Tagging for discovery and compliance reporting
-- ---------------------------------------------------------------------
ALTER TABLE gold.dim_customer
    SET TAGS ('data_classification' = 'confidential', 'contains_pii' = 'true');

ALTER TABLE gold.dim_employee
    SET TAGS ('data_classification' = 'confidential', 'contains_pii' = 'true');

ALTER TABLE gold.fct_retail_fuel_sales
    SET TAGS ('data_classification' = 'internal', 'business_domain' = 'retail');

ALTER TABLE gold.agg_executive_daily_kpi
    SET TAGS ('data_classification' = 'restricted', 'business_domain' = 'executive');

ALTER TABLE gold.network_investment_scorecard
    SET TAGS ('data_classification' = 'restricted', 'business_domain' = 'strategy');
