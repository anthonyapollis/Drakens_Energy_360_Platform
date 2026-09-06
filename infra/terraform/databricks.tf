#############################################################################
# Databricks workspace configuration: Unity Catalog, clusters, jobs, policies
#
# Independent synthetic portfolio project.
#############################################################################

provider "databricks" {
  host = azurerm_databricks_workspace.main.workspace_url
}

#############################################################################
# Unity Catalog
#############################################################################
resource "databricks_storage_credential" "uc" {
  name = "sc-${local.prefix}"
  azure_managed_identity {
    access_connector_id = azurerm_databricks_access_connector.uc.id
  }
  comment = "Managed identity for Unity Catalog. No key or SAS token exists to leak."
}

resource "databricks_external_location" "lake" {
  for_each = toset(["bronze", "silver", "gold", "platform"])

  name            = "el-${local.prefix}-${each.key}"
  url             = "abfss://${each.key}@${azurerm_storage_account.lake.name}.dfs.core.windows.net/"
  credential_name = databricks_storage_credential.uc.name
  comment         = "External location for the ${each.key} layer."
}

resource "databricks_catalog" "main" {
  name    = "vivo_${var.environment}"
  comment = <<-EOT
    Vivo Energy 360 synthetic downstream-energy platform (${var.environment}).
    Independent portfolio project; contains no internal Vivo Energy, Engen,
    Shell or Vitol data. All sites, customers, prices and coordinates are
    generated.
  EOT

  properties = {
    purpose     = "synthetic_portfolio_project"
    environment = var.environment
  }

  # A catalog per environment is a hard isolation boundary: a dev job
  # physically cannot write to prod because the grant does not exist.
  isolation_mode = "ISOLATED"
}

resource "databricks_schema" "layer" {
  for_each = {
    bronze           = "Raw landing zone. Append-only, schema-on-read, no business logic."
    silver           = "Cleansed, typed, deduplicated and conformed business events."
    silver_snapshots = "dbt Type-2 snapshots of slowly changing dimensions."
    quarantine       = "Rows rejected by the bronze contract, with the rule that rejected them."
    gold             = "Dimensional marts and aggregates serving Power BI and ML."
    platform         = "Operational metadata: run log, data quality, freshness, controls."
    ml               = "Feature tables, model inputs and scored outputs."
  }

  catalog_name = databricks_catalog.main.name
  name         = each.key
  comment      = each.value
}

#############################################################################
# Groups and grants
#############################################################################
resource "databricks_grants" "catalog" {
  catalog = databricks_catalog.main.name

  grant {
    principal  = "vivo_platform_engineers"
    privileges = ["ALL_PRIVILEGES"]
  }
  grant {
    principal  = "vivo_data_analysts"
    privileges = ["USE_CATALOG"]
  }
  grant {
    principal  = "vivo_data_scientists"
    privileges = ["USE_CATALOG"]
  }
  grant {
    principal  = "vivo_executives"
    privileges = ["USE_CATALOG"]
  }
}

resource "databricks_grants" "gold" {
  schema = "${databricks_catalog.main.name}.${databricks_schema.layer["gold"].name}"

  grant {
    principal  = "vivo_data_analysts"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
  grant {
    principal  = "vivo_data_scientists"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
  grant {
    principal  = "vivo_commercial_team"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}

# Analysts deliberately get no bronze access. Raw data has no conformed
# definitions, and any number taken from it will disagree with the dashboard.
resource "databricks_grants" "bronze" {
  schema = "${databricks_catalog.main.name}.${databricks_schema.layer["bronze"].name}"

  grant {
    principal  = "vivo_platform_engineers"
    privileges = ["ALL_PRIVILEGES"]
  }
}

#############################################################################
# Cluster policy - the main cost control
#############################################################################
resource "databricks_cluster_policy" "etl" {
  name = "vivo360-${var.environment}-etl"

  definition = jsonencode({
    "spark_version" : {
      "type" : "regex",
      "pattern" : "1[4-9]\\..*",
      "hidden" : false
    },
    # Autotermination is the difference between a forgotten cluster costing a
    # few rand and costing a few thousand.
    "autotermination_minutes" : {
      "type" : "range",
      "minValue" : 10,
      "maxValue" : 60,
      "defaultValue" : 20
    },
    "autoscale.min_workers" : {
      "type" : "fixed",
      "value" : 1
    },
    "autoscale.max_workers" : {
      "type" : "range",
      "maxValue" : var.max_workers,
      "defaultValue" : 4
    },
    "node_type_id" : {
      "type" : "allowlist",
      "values" : var.allowed_node_types,
      "defaultValue" : var.allowed_node_types[0]
    },
    # Spot instances for everything except prod, where an eviction mid-job
    # costs more in delay than the discount saves.
    "azure_attributes.availability" : {
      "type" : "fixed",
      "value" : var.environment == "prod" ? "ON_DEMAND_AZURE" : "SPOT_WITH_FALLBACK_AZURE"
    },
    "azure_attributes.spot_bid_max_price" : {
      "type" : "fixed",
      "value" : -1
    },
    "data_security_mode" : {
      "type" : "fixed",
      "value" : "USER_ISOLATION"
    },
    "custom_tags.project" : {
      "type" : "fixed",
      "value" : "vivo-energy-360"
    },
    "custom_tags.environment" : {
      "type" : "fixed",
      "value" : var.environment
    },
    "custom_tags.cost_centre" : {
      "type" : "fixed",
      "value" : var.cost_centre
    }
  })
}

#############################################################################
# SQL warehouse - serves Power BI
#############################################################################
resource "databricks_sql_endpoint" "bi" {
  name             = "wh-${local.prefix}-bi"
  cluster_size     = var.environment == "prod" ? "Medium" : "2X-Small"
  max_num_clusters = var.environment == "prod" ? 4 : 1

  # Serverless starts in seconds. For a warehouse serving interactive BI, a
  # five-minute cold start is the difference between people using the
  # dashboard and people asking for an extract.
  enable_serverless_compute = true
  auto_stop_mins            = var.environment == "prod" ? 30 : 10

  warehouse_type = "PRO"

  tags {
    custom_tags {
      key   = "project"
      value = "vivo-energy-360"
    }
    custom_tags {
      key   = "environment"
      value = var.environment
    }
  }
}

#############################################################################
# Secret scope backed by Key Vault
#############################################################################
resource "databricks_secret_scope" "kv" {
  name = "vivo360"

  keyvault_metadata {
    resource_id = azurerm_key_vault.main.id
    dns_name    = azurerm_key_vault.main.vault_uri
  }
}

#############################################################################
# Jobs
#############################################################################
resource "databricks_job" "medallion" {
  name        = "vivo360_medallion_${var.environment}"
  description = "Bronze -> silver -> gold, then data quality and table maintenance."

  # A schedule with no timeout is a schedule that can pile up. This one is
  # sized at roughly three times the observed runtime.
  timeout_seconds     = 10800
  max_concurrent_runs = 1

  schedule {
    # 03:00 SAST daily, ahead of the 06:00 dashboard refresh.
    quartz_cron_expression = "0 0 3 * * ?"
    timezone_id            = "Africa/Johannesburg"
  }

  job_cluster {
    job_cluster_key = "etl"
    new_cluster {
      spark_version      = var.spark_version
      node_type_id       = var.allowed_node_types[0]
      policy_id          = databricks_cluster_policy.etl.id
      data_security_mode = "USER_ISOLATION"
      autoscale {
        min_workers = 1
        max_workers = var.max_workers
      }
    }
  }

  task {
    task_key        = "ingest_bronze"
    job_cluster_key = "etl"
    notebook_task {
      notebook_path = "${var.notebook_root}/01_bronze_autoloader"
      base_parameters = {
        catalog = databricks_catalog.main.name
        mode    = "batch"
      }
    }
  }

  task {
    task_key        = "build_silver"
    job_cluster_key = "etl"
    depends_on { task_key = "ingest_bronze" }
    notebook_task {
      notebook_path   = "${var.notebook_root}/02_silver_conformance"
      base_parameters = { catalog = databricks_catalog.main.name }
    }
  }

  task {
    task_key        = "build_gold"
    job_cluster_key = "etl"
    depends_on { task_key = "build_silver" }
    notebook_task {
      notebook_path   = "${var.notebook_root}/03_gold_star_schema"
      base_parameters = { catalog = databricks_catalog.main.name }
    }
  }

  task {
    task_key        = "data_quality"
    job_cluster_key = "etl"
    depends_on { task_key = "build_gold" }
    notebook_task {
      notebook_path   = "${var.notebook_root}/05_data_quality_checks"
      base_parameters = { catalog = databricks_catalog.main.name }
    }
  }

  # Maintenance runs after quality, not before: OPTIMIZE on a table that
  # failed its checks just rewrites bad data more efficiently.
  task {
    task_key        = "optimize_tables"
    job_cluster_key = "etl"
    depends_on { task_key = "data_quality" }
    notebook_task {
      notebook_path   = "${var.notebook_root}/06_optimize_and_vacuum"
      base_parameters = { catalog = databricks_catalog.main.name }
    }
  }

  email_notifications {
    on_failure = [var.oncall_email]
    # No on_success mail. An alert that fires every day is an alert nobody
    # reads by the second week.
  }

  health {
    rules {
      metric = "RUN_DURATION_SECONDS"
      op     = "GREATER_THAN"
      value  = 7200
    }
  }

  tags = local.tags
}

resource "databricks_job" "streaming" {
  count = var.enable_streaming ? 1 : 0

  name        = "vivo360_streaming_${var.environment}"
  description = "Continuous tank, GPS, EV and solar telemetry ingestion."

  continuous {
    pause_status = "UNPAUSED"
  }

  job_cluster {
    job_cluster_key = "stream"
    new_cluster {
      spark_version      = var.spark_version
      node_type_id       = var.allowed_node_types[0]
      policy_id          = databricks_cluster_policy.etl.id
      data_security_mode = "USER_ISOLATION"
      num_workers        = 2
    }
  }

  task {
    task_key        = "telemetry"
    job_cluster_key = "stream"
    notebook_task {
      notebook_path = "${var.notebook_root}/04_streaming_telemetry"
      base_parameters = {
        catalog = databricks_catalog.main.name
        mode    = "production"
      }
    }
  }

  email_notifications {
    on_failure = [var.oncall_email]
  }

  tags = local.tags
}
