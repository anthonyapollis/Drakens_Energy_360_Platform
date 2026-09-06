using '../main.bicep'

param environment = 'prod'
param location = 'southafricanorth'
param ownerEmail = 'data.platform@example.invalid'
param oncallEmail = 'data.platform.oncall@example.invalid'
param costCentre = 'CC013'
param monthlyBudget = 180000
param eventHubThroughputUnits = 4
param bronzeRetentionDays = 2555
