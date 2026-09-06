#############################################################################
# Variables. Everything that differs between environments lives here, so one
# configuration serves dev, test and prod.
#############################################################################

variable "environment" {
  type        = string
  description = "Deployment environment."
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test or prod."
  }
}

variable "location" {
  type        = string
  description = "Azure region. South Africa North keeps data in-country and cuts latency to SA users."
  default     = "southafricanorth"
}

variable "tenant_id" {
  type        = string
  description = "Entra ID tenant for Key Vault."
}

variable "cost_centre" {
  type        = string
  description = "Cost centre tag, used for chargeback."
  default     = "CC013"
}

variable "owner_email" {
  type        = string
  description = "Owning team, tagged on every resource."
}

variable "oncall_email" {
  type        = string
  description = "Where failure alerts and budget warnings go."
}

variable "spark_version" {
  type        = string
  description = "Databricks Runtime version."
  default     = "15.4.x-scala2.12"
}

variable "allowed_node_types" {
  type        = list(string)
  description = <<-EOT
    Node types the cluster policy permits. Restricting this is the main guard
    against someone launching a memory-optimised fleet for a job that needed
    four general-purpose workers.
  EOT
  default     = ["Standard_D4ds_v5", "Standard_D8ds_v5", "Standard_E8ds_v5"]
}

variable "max_workers" {
  type        = number
  description = "Autoscale ceiling enforced by the cluster policy."
  default     = 8
}

variable "eventhub_throughput_units" {
  type        = number
  description = "Event Hubs capacity. One TU handles ~1MB/s ingress."
  default     = 1
}

variable "enable_streaming" {
  type        = bool
  description = <<-EOT
    Whether to run the continuous telemetry job. Off outside prod: an
    always-on stream in a dev workspace is the most reliable way to produce a
    surprising invoice.
  EOT
  default     = false
}

variable "bronze_retention_days" {
  type        = number
  description = "How long raw landed files are kept before deletion."
  default     = 2555 # seven years
}

variable "monthly_budget_zar" {
  type        = number
  description = "Monthly spend cap that triggers budget alerts."
  default     = 25000
}

variable "budget_start_date" {
  type        = string
  description = "Budget period start, ISO 8601."
  default     = "2026-01-01T00:00:00Z"
}

variable "notebook_root" {
  type        = string
  description = "Workspace path the job notebooks are deployed to."
  default     = "/Shared/vivo_energy_360"
}

variable "github_account" {
  type        = string
  description = "GitHub account for the Data Factory git integration."
  default     = ""
}

variable "github_repo" {
  type        = string
  description = "GitHub repository for the Data Factory git integration."
  default     = ""
}
