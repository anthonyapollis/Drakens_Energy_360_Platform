//////////////////////////////////////////////////////////////////////////////
// Drakens Energy 360 - Azure infrastructure (Bicep)
//
// Independent synthetic portfolio project. No real company data.
//
// Functional equivalent of infra/terraform for organisations standardised on
// ARM-native tooling. Terraform remains the reference implementation because
// it also manages the Databricks workspace objects -- Unity Catalog, cluster
// policies, jobs -- which Bicep cannot reach. Where both are used, Bicep
// provisions the Azure resources and the Databricks provider is run
// separately against the resulting workspace.
//
//   az deployment sub create \
//     --location southafricanorth \
//     --template-file main.bicep \
//     --parameters @env/dev.bicepparam
//////////////////////////////////////////////////////////////////////////////

targetScope = 'subscription'

@description('Deployment environment.')
@allowed(['dev', 'test', 'prod'])
param environment string

@description('Azure region. South Africa North keeps data in-country.')
param location string = 'southafricanorth'

@description('Owning team, tagged on every resource.')
param ownerEmail string

@description('Where failure alerts and budget warnings go.')
param oncallEmail string

@description('Cost centre tag, used for chargeback.')
param costCentre string = 'CC013'

@description('Monthly spend cap that triggers budget alerts, in ZAR.')
param monthlyBudget int = 25000

@description('Event Hubs throughput units. One TU handles about 1MB/s ingress.')
param eventHubThroughputUnits int = 1

@description('Days raw landed files are retained before deletion.')
param bronzeRetentionDays int = 2555

var prefix = 'drakens360-${environment}'
var isProd = environment == 'prod'

var tags = {
  project: 'drakens-energy-360'
  environment: environment
  managedBy: 'bicep'
  dataClass: 'synthetic'
  costCentre: costCentre
  owner: ownerEmail
}

//////////////////////////////////////////////////////////////////////////////
// Resource group
//////////////////////////////////////////////////////////////////////////////
resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: 'rg-${prefix}'
  location: location
  tags: tags
}

//////////////////////////////////////////////////////////////////////////////
// Platform resources
//////////////////////////////////////////////////////////////////////////////
module platform 'modules/platform.bicep' = {
  name: 'platform-${environment}'
  scope: rg
  params: {
    prefix: prefix
    location: location
    tags: tags
    isProd: isProd
    eventHubThroughputUnits: eventHubThroughputUnits
    bronzeRetentionDays: bronzeRetentionDays
    oncallEmail: oncallEmail
  }
}

//////////////////////////////////////////////////////////////////////////////
// Budget
//
// A platform that can silently cost ten times its estimate is a platform that
// gets switched off by finance rather than by engineering. Alerts fire on
// actual spend at 50/80/100% and on forecast at 100%, so the warning arrives
// before the money is gone rather than after.
//////////////////////////////////////////////////////////////////////////////
resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'budget-${prefix}'
  properties: {
    category: 'Cost'
    amount: monthlyBudget
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: '2026-01-01T00:00:00Z'
    }
    filter: {
      dimensions: {
        name: 'ResourceGroupName'
        operator: 'In'
        values: [rg.name]
      }
    }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        contactEmails: [oncallEmail]
        thresholdType: 'Actual'
      }
      actual80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        contactEmails: [oncallEmail]
        thresholdType: 'Actual'
      }
      actual100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: [oncallEmail]
        thresholdType: 'Actual'
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: [oncallEmail]
        thresholdType: 'Forecasted'
      }
    }
  }
}

output resourceGroupName string = rg.name
output workspaceUrl string = platform.outputs.databricksWorkspaceUrl
output storageAccountName string = platform.outputs.storageAccountName
output accessConnectorId string = platform.outputs.accessConnectorId
