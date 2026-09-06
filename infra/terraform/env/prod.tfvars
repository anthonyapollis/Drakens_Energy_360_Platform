#############################################################################
# Production. Differs from dev in the ways that matter for a live platform:
# zone-redundant storage, on-demand compute, streaming enabled, a real budget.
#############################################################################

environment  = "prod"
location     = "southafricanorth"
tenant_id    = "00000000-0000-0000-0000-000000000000" # set per tenant
cost_centre  = "CC013"
owner_email  = "data.platform@example.invalid"
oncall_email = "data.platform.oncall@example.invalid"

spark_version      = "15.4.x-scala2.12"
allowed_node_types = ["Standard_D8ds_v5", "Standard_E8ds_v5", "Standard_E16ds_v5"]
max_workers        = 16

eventhub_throughput_units = 4
enable_streaming          = true

bronze_retention_days = 2555
monthly_budget_zar    = 180000
budget_start_date     = "2026-01-01T00:00:00Z"
