# Set refresh interval for all datasources
# Usage: 
#   .\set-refresh-interval.ps1 -Hours 1
#   .\set-refresh-interval.ps1 -Minutes 30
#   .\set-refresh-interval.ps1 -Seconds 120
#   .\set-refresh-interval.ps1 -Hours 1 -Minutes 30 -Seconds 45

param(
    [Parameter(Mandatory=$false)]
    [int]$Hours = 0,
    
    [Parameter(Mandatory=$false)]
    [int]$Minutes = 0,
    
    [Parameter(Mandatory=$false)]
    [int]$Seconds = 0,
    
    [Parameter(Mandatory=$false)]
    [string]$ApiUrl = "http://localhost:8000"
)

# Calculate total seconds
$totalSeconds = ($Hours * 3600) + ($Minutes * 60) + $Seconds

# Default to 60 seconds if nothing specified
if ($totalSeconds -eq 0) {
    $totalSeconds = 60
    Write-Host "No interval specified, using default of 60 seconds" -ForegroundColor Yellow
}

# Build human-readable string
$parts = @()
if ($Hours -gt 0) { $parts += "$Hours hour(s)" }
if ($Minutes -gt 0) { $parts += "$Minutes minute(s)" }
if ($Seconds -gt 0) { $parts += "$Seconds second(s)" }
$intervalStr = if ($parts.Count -gt 0) { $parts -join ", " } else { "$totalSeconds seconds" }

Write-Host "Setting refresh interval to $intervalStr ($totalSeconds total seconds) for all datasources..." -ForegroundColor Cyan

try {
    $response = Invoke-RestMethod -Uri "$ApiUrl/api/datasource/update-all-refresh-intervals?seconds=$totalSeconds" -Method Post
    Write-Host "SUCCESS: Refresh interval updated." -ForegroundColor Green
    Write-Host "Updated datasources: $($response.updated_count)" -ForegroundColor Green
    if ($response.configs) {
        Write-Host "`nUpdated configurations:" -ForegroundColor Cyan
        foreach ($config in $response.configs) {
            Write-Host "  - $($config.source_type): $($config.config_id)" -ForegroundColor Gray
        }
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
