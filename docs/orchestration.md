# Orchestration and SLAs

> **Independent synthetic portfolio project.** No internal Vivo Energy, Engen,
> Shell or Vitol data.

---

## The daily cycle

```
02:00  Source extracts land in the bronze volume
03:00  vivo360_medallion_prod starts
       ├─ ingest_bronze     Auto Loader, ~8 min
       ├─ build_silver      contract, quarantine, dedup, SCD2, ~14 min
       ├─ build_gold        marts and aggregates, ~11 min
       ├─ data_quality      controls and freshness, ~3 min
       └─ optimize_tables   OPTIMIZE, clustering, VACUUM, ~6 min
04:00  ML scoring (weekly retrain, daily inference)
06:00  Power BI incremental refresh
07:00  Dashboards available
```

The gap between 04:00 and 06:00 is deliberate slack. A pipeline scheduled to
finish exactly when the business needs it will miss on the first day something
runs slowly, and that day always comes.

## Task order, and why

**Quality before maintenance.** `optimize_tables` runs *after* `data_quality`,
not before. OPTIMIZE on a table that failed its controls just rewrites bad data
more efficiently and makes the rollback harder.

**Silver before gold, always.** Gold reads only silver, never bronze. That is
what keeps the conformed definitions in one place.

**No task runs on success notifications.** `email_notifications` fires only on
failure. An alert that arrives every morning is an alert nobody reads by the
second week.

## Failure handling

| Failure | Behaviour | Reasoning |
|---|---|---|
| A source file is missing | Task succeeds, freshness records a breach | One late feed should not block the other thirteen |
| A reconciliation control fails | Task **fails**, warehouse does not publish | A wrong number is worse than a late one |
| Quarantine rate exceeds 5% | Recorded as `Critical`, job continues | Needs investigation, not necessarily a halt |
| A schema change appears | New column lands in bronze via schema evolution | Bronze must never lose data it was sent |
| The job exceeds 2 hours | Health rule alerts, job continues | Duration drift is the earliest warning of a scaling problem |

There is no automatic retry on the medallion job. A retry on a data pipeline
usually reprocesses the same bad input and produces the same failure twenty
minutes later, having consumed another cluster-hour. The streaming job does
restart automatically, because there the failure is far more often transient.

## SLAs by feed

SLAs live in `dim_data_source`, not in code, so changing one is a data change.

| Feed | Pattern | SLA | Consequence of a breach |
|---|---|---|---|
| Tank telemetry | Event stream | 15 min | Stock-out risk is stale; replenishment plans on old levels |
| Fleet GPS | Event stream | 15 min | Delivery ETAs degrade |
| EV charge points | Event stream | 15 min | A faulted charger earns nothing until someone is told |
| Solar inverters | Event stream | 15 min | Underperformance goes unnoticed |
| ERP sales and distribution | CDC | 60 min | Commercial reporting lags |
| ERP finance | CDC | 60 min | Ledger reconciliation delayed |
| Terminal automation | CDC | 60 min | Stock movements delayed |
| Forecourt POS | Batch file | 240 min | Yesterday's retail numbers are late |
| Shop POS | Batch file | 240 min | Non-fuel margin is late |
| Maintenance system | Batch file | 240 min | Work-order reporting is late |

The 15-minute streams are the ones that matter operationally. A four-hour batch
SLA on the forecourt feed is fine because nobody acts on retail volume within
four hours; a four-hour SLA on tank telemetry would make the stock-out alert
useless.

## Streaming

The continuous job runs the four telemetry streams with `availableNow` in
non-production and a 30-second processing trigger in production. Watermarks are
sized per stream to the worst realistic lateness:

| Stream | Watermark | Why |
|---|---|---|
| Tank telemetry | 30 min | Gauges buffer locally through a comms outage |
| Fleet GPS | 15 min | Vehicles lose signal in terrain and flush on reconnect |
| EV OCPP | 10 min | Charge points reconnect quickly |
| Solar inverters | 20 min | Site connectivity is the constraint |

Too tight and real events are dropped; too loose and Spark holds unbounded
state. Both failure modes are quiet, which is why the numbers are documented
next to the reason rather than left in the code.

## Environments

| | dev | test | prod |
|---|---|---|---|
| Schedule | manual | daily 02:00 | daily 03:00 |
| Data scale | demo | test | portfolio |
| Compute | spot | spot | on-demand |
| Streaming | off | on | on |
| Alerts | none | team | on-call |

Streaming is off in dev deliberately: an always-on stream in a development
workspace is the most reliable way to produce a surprising invoice.

## Monitoring

Three tables, in the order the on-call engineer reads them:

1. `obs_table_freshness` — which feed is late?
2. `obs_cleansing_summary` — did the rejection rate move?
3. `obs_reconciliation_controls` — is a published number wrong?

A rejection rate that moves is the earliest signal that an upstream system
changed, and it usually appears days before anyone notices a number looks odd
in a report.
