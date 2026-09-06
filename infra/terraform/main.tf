#############################################################################
# Vivo Energy 360 - Azure and Databricks infrastructure
#
# Independent synthetic portfolio project. Provisions the platform that runs
# the synthetic workload; no real company data is involved.
#
# One configuration, three environments. Everything that differs between dev,
# test and prod is a variable, because the alternative -- three copies that
# drift -- is how a prod deployment ends up untested.
#
#   terraform workspace select dev && terraform apply -var-file=env/dev.tfvars
#############################################################################

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.40"
    }
  }

  # Remote state with locking. Local state on a shared platform is how two
  # engineers destroy each other's resources.
  backend "azurerm" {
    resource_group_name  = "rg-vivo360-tfstate"
    storage_account_name = "stvivo360tfstate"
    container_name       = "tfstate"
    key                  = "vivo360.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

locals {
  prefix = "vivo360-${var.environment}"

  tags = {
    project     = "vivo-energy-360"
    environment = var.environment
    managed_by  = "terraform"
    data_class  = "synthetic"
    cost_centre = var.cost_centre
    owner       = var.owner_email
  }
}

#############################################################################
# Resource group
#############################################################################
resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags
}

#############################################################################
# Storage - ADLS Gen2 with hierarchical namespace
#############################################################################
resource "azurerm_storage_account" "lake" {
  name                     = replace("st${local.prefix}", "-", "")
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = var.environment == "prod" ? "ZRS" : "LRS"

  # Required for ADLS Gen2 semantics; without it this is blob storage and
  # directory operations become expensive copies.
  is_hns_enabled = true

  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false # force Entra ID auth

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = var.environment == "prod" ? 30 : 7
    }
  }

  tags = local.tags
}

resource "azurerm_storage_container" "layer" {
  for_each = toset(["bronze", "silver", "gold", "platform", "checkpoints"])

  name                  = each.key
  storage_account_name  = azurerm_storage_account.lake.name
  container_access_type = "private"
}

# Lifecycle: bronze is append-only history and is the largest thing on the
# platform. Cooling it after 90 days and archiving after a year is the single
# biggest storage saving available, and bronze is almost never re-read once
# silver is built.
resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.lake.id

  rule {
    name    = "bronze-tiering"
    enabled = true
    filters {
      prefix_match = ["bronze/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than    = 90
        tier_to_archive_after_days_since_modification_greater_than = 365
        delete_after_days_since_modification_greater_than          = var.bronze_retention_days
      }
      version {
        delete_after_days_since_creation = 30
      }
    }
  }

  rule {
    name    = "checkpoint-cleanup"
    enabled = true
    filters {
      prefix_match = ["checkpoints/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        # Old checkpoint versions only; never the current offsets, which are
        # what make streaming ingestion exactly-once.
        delete_after_days_since_modification_greater_than = 90
      }
    }
  }
}

#############################################################################
# Databricks workspace
#############################################################################
resource "azurerm_databricks_workspace" "main" {
  name                = "dbw-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = var.environment == "prod" ? "premium" : "standard"

  # Premium is not optional in prod: Unity Catalog row filters, column masks
  # and cluster policies all require it, and those are the controls the
  # governance design depends on.
  managed_resource_group_name = "rg-${local.prefix}-managed"

  tags = local.tags
}

# Access connector: how Unity Catalog reaches storage without any credential
# being stored anywhere.
resource "azurerm_databricks_access_connector" "uc" {
  name                = "dbac-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

resource "azurerm_role_assignment" "uc_storage" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.uc.identity[0].principal_id
}

#############################################################################
# Event Hubs - streaming telemetry ingress
#############################################################################
resource "azurerm_eventhub_namespace" "telemetry" {
  name                = "evhns-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = var.environment == "prod" ? "Standard" : "Basic"
  capacity            = var.eventhub_throughput_units

  auto_inflate_enabled     = var.environment == "prod"
  maximum_throughput_units = var.environment == "prod" ? 10 : null

  tags = local.tags
}

resource "azurerm_eventhub" "topic" {
  for_each = {
    tank-telemetry = { partitions = 8, retention = 3 }
    fleet-gps      = { partitions = 12, retention = 3 }
    ev-ocpp        = { partitions = 4, retention = 7 }
    solar-inverter = { partitions = 4, retention = 3 }
  }

  name                = each.key
  namespace_name      = azurerm_eventhub_namespace.telemetry.name
  resource_group_name = azurerm_resource_group.main.name
  # Partition count cannot be changed after creation on Basic/Standard, so it
  # is sized for peak here rather than for today's volume.
  partition_count   = each.value.partitions
  message_retention = each.value.retention
}

#############################################################################
# Key Vault - secrets, referenced by Databricks secret scope
#############################################################################
resource "azurerm_key_vault" "main" {
  name                       = "kv-${substr(replace(local.prefix, "-", ""), 0, 20)}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = var.tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = var.environment == "prod"
  soft_delete_retention_days = 30

  enable_rbac_authorization = true

  tags = local.tags
}

#############################################################################
# Data Factory - orchestration for the batch feeds
#############################################################################
resource "azurerm_data_factory" "main" {
  name                = "adf-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  identity {
    type = "SystemAssigned"
  }

  dynamic "github_configuration" {
    for_each = var.environment == "dev" ? [1] : []
    content {
      account_name    = var.github_account
      branch_name     = "main"
      git_url         = "https://github.com"
      repository_name = var.github_repo
      root_folder     = "/adf"
    }
  }

  tags = local.tags
}

resource "azurerm_role_assignment" "adf_databricks" {
  scope                = azurerm_databricks_workspace.main.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_data_factory.main.identity[0].principal_id
}

#############################################################################
# Monitoring
#############################################################################
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = var.environment == "prod" ? 90 : 30
  tags                = local.tags
}

resource "azurerm_monitor_action_group" "oncall" {
  name                = "ag-${local.prefix}-oncall"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "vivo360"

  email_receiver {
    name          = "data-platform"
    email_address = var.oncall_email
  }

  tags = local.tags
}

# Budget alerts. A platform that can silently cost ten times its estimate is a
# platform that will be switched off by finance rather than by engineering.
resource "azurerm_consumption_budget_resource_group" "main" {
  name              = "budget-${local.prefix}"
  resource_group_id = azurerm_resource_group.main.id

  amount     = var.monthly_budget_zar
  time_grain = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThan"
      threshold_type = "Actual"
      contact_emails = [var.oncall_email]
    }
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.oncall_email]
  }
}
