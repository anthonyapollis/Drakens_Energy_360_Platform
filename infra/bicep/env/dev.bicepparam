using '../main.bicep'

param environment = 'dev'
param location = 'southafricanorth'
param ownerEmail = 'data.platform@example.invalid'
param oncallEmail = 'data.platform@example.invalid'
param costCentre = 'CC013'
param monthlyBudget = 8000
param eventHubThroughputUnits = 1
param bronzeRetentionDays = 90
