#############################################################################
# Test. Production-shaped so a release is validated against the same
# behaviour, but sized down and still on spot compute.
#############################################################################

environment  = "test"
location     = "southafricanorth"
tenant_id    = "00000000-0000-0000-0000-000000000000" # set per tenant
cost_centre  = "CC013"
owner_email  = "data.platform@example.invalid"
oncall_email = "data.platform@example.invalid"

spark_version      = "15.4.x-scala2.12"
allowed_node_types = ["Standard_D4ds_v5", "Standard_D8ds_v5"]
max_workers        = 8

eventhub_throughput_units = 1
# Streaming is on in test so the continuous job is exercised before prod,
# which is the whole point of having a test environment.
enable_streaming = true

bronze_retention_days = 365
monthly_budget_zar    = 30000
budget_start_date     = "2026-01-01T00:00:00Z"
