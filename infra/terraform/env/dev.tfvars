#############################################################################
# Development. Cheap and disposable: spot compute, LRS storage, no streaming,
# short retention, small budget.
#############################################################################

environment  = "dev"
location     = "southafricanorth"
tenant_id    = "00000000-0000-0000-0000-000000000000" # set per tenant
cost_centre  = "CC013"
owner_email  = "data.platform@example.invalid"
oncall_email = "data.platform@example.invalid"

spark_version      = "15.4.x-scala2.12"
allowed_node_types = ["Standard_D4ds_v5"]
max_workers        = 4

eventhub_throughput_units = 1
enable_streaming          = false

bronze_retention_days = 90
monthly_budget_zar    = 8000
budget_start_date     = "2026-01-01T00:00:00Z"
