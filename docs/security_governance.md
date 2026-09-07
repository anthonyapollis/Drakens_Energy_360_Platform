# Security and governance

> **Independent synthetic portfolio project.** No internal Vivo Energy, Engen,
> Shell or Vitol data. Every customer, employee and loyalty member named in
> this platform is generated. The controls below are modelled as they would be
> in production, on synthetic data.

---

## The principle

**Restrictive by default.** A new analyst added to the analyst group sees
masked customer names and no rows outside their region until someone
deliberately grants more. Getting this the other way round — open by default,
locked down by exception — is how data platforms leak, because the exceptions
are always found later than the access.

---

## Identity and groups

Groups are managed in the account console via SCIM, not created by the
platform code. Five of them:

| Group | Sees | Notably does not see |
|---|---|---|
| `vivo_platform_engineers` | Everything | — |
| `vivo_data_analysts` | Gold, masked PII, own provinces | Bronze, silver, customer names |
| `vivo_commercial_team` | Gold, unmasked customers | Bronze, silver |
| `vivo_data_scientists` | Silver and gold, own the `ml` schema | Bronze |
| `vivo_executives` | Two aggregate tables only | All transaction detail |

**Analysts get no bronze access at all.** This is deliberate and occasionally
unpopular. Raw data has no conformed definitions; any number taken from it will
disagree with the dashboard, and the resulting argument costs more than the
convenience saved.

**Executives get less, not more.** Object-level security hides
`fct_retail_fuel_sales` and `dim_customer` entirely. They need the aggregate,
not the customer list, and the fastest route to a data incident is giving
everyone everything by default because of seniority.

---

## Isolation

One Unity Catalog **catalog per environment** — `vivo_dev`, `vivo_test`,
`vivo_prod` — with `isolation_mode = ISOLATED`.

This is a hard boundary, not a convention. A development job physically cannot
write to production because the grant does not exist. Schema names are
identical across environments so the same dbt models and notebooks run
unchanged, parameterised only by catalog.

---

## Column masking

Masks are functions applied at query time. The underlying data is never copied,
so there is exactly one customer table and no "safe copy" to drift out of sync
with it.

| Column | Masked to | Unmasked for |
|---|---|---|
| `dim_customer.customer_name` | First three characters, rest asterisked | Commercial team, engineers |
| `dim_customer.credit_limit_zar` | `NULL` | Commercial team, engineers |
| `fct_retail_fuel_sales.loyalty_member_id` | SHA-256 pseudonym | Engineers |

Two details worth the space:

**The name mask keeps three characters.** An analyst can still tell two
customers apart in a chart without seeing who they are. A full mask makes
segmentation analysis impossible and pushes people to request an exemption.

**The loyalty mask is a stable pseudonym, not a null.** The value stays
joinable and countable — so cohort analysis still works — but cannot be
resolved back to a person.

---

## Row-level security

A regional analyst should not see another region's sites at all.

```sql
CREATE OR REPLACE FUNCTION gold.province_row_filter(province STRING)
RETURN
    is_account_group_member('vivo_platform_engineers')
    OR is_account_group_member('vivo_executives')
    OR EXISTS (
        SELECT 1 FROM gold.bridge_security_user_scope s
        WHERE s.user_principal = current_user()
          AND (s.scope_type = 'all'
               OR (s.scope_type = 'province' AND s.scope_value = province))
    );
```

Applied to `dim_site`, `network_investment_scorecard` and
`agg_executive_daily_kpi`, and allowed to propagate through relationships so
one filter secures every fact rather than needing a rule per table.

**The scope comes from a table, not from group names.** Adding a province to
someone's remit is a data change, not a deployment. Hard-coding regions into
group membership means every reorganisation becomes an engineering ticket.

Power BI RLS mirrors the same table, so a user sees identical rows whether they
query through the dashboard or directly in SQL. If the two disagree, one of
them is a leak.

---

## Classification and tagging

| Tag | Applied to | Meaning |
|---|---|---|
| `data_classification=confidential` | `dim_customer`, `dim_employee` | Contains personal data |
| `data_classification=restricted` | `agg_executive_daily_kpi`, `network_investment_scorecard` | Commercially sensitive |
| `data_classification=internal` | Most facts | Normal business data |
| `contains_pii=true` | Customer and employee dimensions | Drives the masking policy |

Tags make "which tables contain personal data" a query rather than a
conversation, which matters the first time someone has to answer it under time
pressure.

---

## Credentials

**No credential appears anywhere in this repository.**

- Storage access is via a system-assigned managed identity on the Databricks
  access connector. There is no key or SAS token to leak.
- Event Hubs connection strings live in Key Vault, surfaced through a
  Databricks secret scope and referenced as `{{secrets/vivo360/...}}`. The
  streaming notebook never sees the value.
- Deployment authenticates by OAuth through the Databricks CLI.
  `scripts/deploy_databricks.py` never reads, writes or prints a token.
- Storage accounts have `allowSharedKeyAccess = false`, so Entra ID is the only
  authentication path even for someone who wants a shortcut.

---

## Lineage and audit

Unity Catalog captures table- and column-level lineage automatically. Combined
with the `_source_file` column every bronze row carries, any figure in a board
pack can be traced back to the specific file it came from.

Databricks audit logs route to Log Analytics with 90-day retention in
production, which is what makes "who queried the customer table last March" an
answerable question.

---

## Data retention

| Layer | Retention | Reasoning |
|---|---|---|
| Bronze | 7 years | Regulatory and reprocessing; cooled at 90 days, archived at 1 year |
| Silver | Indefinite | Rebuilt from bronze if needed |
| Gold | Indefinite | Small relative to its value |
| Quarantine | 90 days | Long enough to diagnose, short enough not to accumulate |
| Delta history | 7 days minimum | Below this, time travel and concurrent readers break |

The VACUUM retention floor is enforced in code, not left to a parameter someone
might shorten to reclaim space. Reclaiming a few gigabytes by breaking time
travel is a trade nobody makes deliberately, and several people have made it by
accident.

---

## What this design does not cover

Stated plainly, because a governance document that claims completeness is
misleading:

- **No data subject access or erasure workflow.** The masking and pseudonym
  design supports one, but the process itself is not built.
- **No key rotation automation.** Managed identity avoids most of the need;
  the Event Hubs secret would still need a rotation schedule.
- **No network isolation.** Production would use private endpoints and a
  VNet-injected workspace. This deployment is public-endpoint.
- **Row filters are not tested at scale.** They are correct, but their query
  cost under concurrent executive load has not been measured.
