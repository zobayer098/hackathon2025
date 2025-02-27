# Define the .env file path
$envFilePath = "src\.env"

# Clear the contents of the .env file
Set-Content -Path $envFilePath -Value ""

# Append new values to the .env file
$azureAiProjectConnectionString = azd env get-value AZURE_AIPROJECT_CONNECTION_STRING
$azureAiagentDeploymentName = azd env get-value AZURE_AI_AGENT_DEPLOYMENT_NAME
$azureAiAgentId = azd env get-value AZURE_AI_AGENT_ID
$azureTenantId = azd env get-value AZURE_TENANT_ID
$searchConnectionName = azd env get-value AZURE_AI_SEARCH_CONNECTION_NAME

Add-Content -Path $envFilePath -Value "AZURE_AIPROJECT_CONNECTION_STRING=$azureAiProjectConnectionString"
Add-Content -Path $envFilePath -Value "AZURE_AI_AGENT_DEPLOYMENT_NAME=$azureAiagentDeploymentName"
Add-Content -Path $envFilePath -Value "AZURE_AI_AGENT_ID=$azureAiAgentId"
Add-Content -Path $envFilePath -Value "AZURE_TENANT_ID=$azureTenantId"
Add-Content -Path $envFilePath -Value "AZURE_AI_SEARCH_CONNECTION_NAME=$searchConnectionName"