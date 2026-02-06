# Trigger immediate sync for all datasources with auto-sync enabled
# Usage: 
#   .\sync-now.ps1
#   .\sync-now.ps1 -ApiUrl http://localhost:8000
#   .\sync-now.ps1 -ConfigId "alfresco_12345"

param(
    [Parameter(Mandatory=$false)]
    [string]$ConfigId = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ApiUrl = "http://localhost:8000"
)

if ($ConfigId -ne "") {
    Write-Host "Triggering immediate sync for datasource: $ConfigId..." -ForegroundColor Cyan
    $endpoint = "$ApiUrl/api/datasource/$ConfigId/sync-now"
} else {
    Write-Host "Triggering immediate sync for all datasources with auto-sync enabled..." -ForegroundColor Cyan
    $endpoint = "$ApiUrl/api/datasource/sync-now-all"
}

try {
    $response = Invoke-RestMethod -Uri $endpoint -Method Post
    Write-Host "SUCCESS: Sync triggered." -ForegroundColor Green
    
    if ($response.triggered_count) {
        Write-Host "Triggered sync for $($response.triggered_count) datasource(s)" -ForegroundColor Green
    }
    
    if ($response.configs) {
        Write-Host "`nSyncing datasources:" -ForegroundColor Cyan
        foreach ($config in $response.configs) {
            Write-Host "  - $($config.source_type): $($config.config_id)" -ForegroundColor Gray
        }
    }
    
    if ($response.message) {
        Write-Host "`n$($response.message)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
