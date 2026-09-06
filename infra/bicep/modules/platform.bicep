//////////////////////////////////////////////////////////////////////////////
// Platform resources: storage, Databricks, Event Hubs, Key Vault,
// Data Factory and monitoring.
//
// Independent synthetic portfolio project.
//////////////////////////////////////////////////////////////////////////////

param prefix string
param location string
param tags object
param isProd bool
param eventHubThroughputUnits int
param bronzeRetentionDays int
param oncallEmail string

var storageName = replace('st${prefix}', '-', '')

//////////////////////////////////////////////////////////////////////////////
// ADLS Gen2
//////////////////////////////////////////////////////////////////////////////
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: {
    name: isProd ? 'Standard_ZRS' : 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    // Hierarchical namespace gives real directory semantics. Without it this
    // is blob storage and a directory rename becomes a full copy.
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    // Shared keys disabled: authentication is Entra ID only, so there is no
    // account key that can be copied into a notebook and leaked.
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
    encryption: {
      services: {
        blob: { enabled: true }
        file: { enabled: true }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: {
      enabled: true
      days: isProd ? 30 : 7
    }
  }
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for name in ['bronze', 'silver', 'gold', 'platform', 'checkpoints']: {
    parent: blobService
    name: name
    properties: {
      publicAccess: 'None'
    }
  }
]

// Bronze is append-only history and the largest thing on the platform.
// Cooling then archiving it is the single biggest storage saving available,
// and it is almost never re-read once silver is built.
resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'bronze-tiering'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['bronze/']
            }
            actions: {
              baseBlob: {
                tierToCool: { daysAfterModificationGreaterThan: 90 }
                tierToArchive: { daysAfterModificationGreaterThan: 365 }
                delete: { daysAfterModificationGreaterThan: bronzeRetentionDays }
              }
              version: {
                delete: { daysAfterCreationGreaterThan: 30 }
              }
            }
          }
        }
      ]
    }
  }
}

//////////////////////////////////////////////////////////////////////////////
// Databricks
//////////////////////////////////////////////////////////////////////////////
resource databricks 'Microsoft.Databricks/workspaces@2024-05-01' = {
  name: 'dbw-${prefix}'
  location: location
  tags: tags
  sku: {
    // Premium is not optional in prod: Unity Catalog row filters, column
    // masks and cluster policies all require it.
    name: isProd ? 'premium' : 'standard'
  }
  properties: {
    managedResourceGroupId: subscriptionResourceId(
      'Microsoft.Resources/resourceGroups', 'rg-${prefix}-managed')
  }
}

// How Unity Catalog reaches storage with no credential stored anywhere.
resource accessConnector 'Microsoft.Databricks/accessConnectors@2023-05-01' = {
  name: 'dbac-${prefix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

var storageBlobDataContributor = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe')

resource ucStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, accessConnector.id, storageBlobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: storageBlobDataContributor
    principalId: accessConnector.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

//////////////////////////////////////////////////////////////////////////////
// Event Hubs
//////////////////////////////////////////////////////////////////////////////
resource ehNamespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: 'evhns-${prefix}'
  location: location
  tags: tags
  sku: {
    name: isProd ? 'Standard' : 'Basic'
    tier: isProd ? 'Standard' : 'Basic'
    capacity: eventHubThroughputUnits
  }
  properties: {
    isAutoInflateEnabled: isProd
    maximumThroughputUnits: isProd ? 10 : 0
    minimumTlsVersion: '1.2'
  }
}

// Partition count cannot be changed after creation, so each topic is sized
// for peak rather than for today's volume.
var eventHubs = [
  { name: 'tank-telemetry', partitions: 8, retention: 3 }
  { name: 'fleet-gps', partitions: 12, retention: 3 }
  { name: 'ev-ocpp', partitions: 4, retention: 7 }
  { name: 'solar-inverter', partitions: 4, retention: 3 }
]

resource topics 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = [
  for hub in eventHubs: {
    parent: ehNamespace
    name: hub.name
    properties: {
      partitionCount: hub.partitions
      messageRetentionInDays: hub.retention
    }
  }
]

//////////////////////////////////////////////////////////////////////////////
// Key Vault
//////////////////////////////////////////////////////////////////////////////
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${take(replace(prefix, '-', ''), 20)}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    // RBAC rather than access policies: one permission model across the
    // subscription instead of a second one only Key Vault uses.
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 30
    enablePurgeProtection: isProd ? true : null
  }
}

//////////////////////////////////////////////////////////////////////////////
// Data Factory
//////////////////////////////////////////////////////////////////////////////
resource dataFactory 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: 'adf-${prefix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

//////////////////////////////////////////////////////////////////////////////
// Monitoring
//////////////////////////////////////////////////////////////////////////////
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: isProd ? 90 : 30
  }
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${prefix}-oncall'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'vivo360'
    enabled: true
    emailReceivers: [
      {
        name: 'data-platform'
        emailAddress: oncallEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

// Route Databricks audit and cluster logs into Log Analytics, so a failed job
// can be investigated after the cluster that ran it has terminated.
resource databricksDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-databricks'
  scope: databricks
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      { category: 'clusters', enabled: true }
      { category: 'jobs', enabled: true }
      { category: 'notebook', enabled: true }
      { category: 'unityCatalog', enabled: true }
    ]
  }
}

output databricksWorkspaceUrl string = databricks.properties.workspaceUrl
output storageAccountName string = storage.name
output accessConnectorId string = accessConnector.id
output keyVaultUri string = keyVault.properties.vaultUri
output eventHubNamespace string = ehNamespace.name
