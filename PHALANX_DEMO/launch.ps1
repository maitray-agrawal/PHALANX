# PHALANX Demo Presentation Launcher for Windows PowerShell
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   PHALANX - Autonomous AI Payment Security Layer" -ForegroundColor White
Write-Host "   Interactive Product Demo & Competition Deck Launcher" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check if local backend is running
$BackendRunning = $false
try {
    $res = Invoke-WebRequest -Uri "http://127.0.0.1:8000/healthz" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($res.StatusCode -eq 200) {
        $BackendRunning = $true
        Write-Host "[OK] PHALANX Backend detected running on http://127.0.0.1:8000" -ForegroundColor Green
    }
} catch {}

if (-not $BackendRunning) {
    Write-Host "[INFO] Backend on port 8000 is offline. Presentation will run with verified local engine telemetry." -ForegroundColor Yellow
}

# Start local HTTP server to avoid CORS/local file restrictions
$Port = 3000
Write-Host "[LAUNCH] Starting lightweight local presentation server on port $Port..." -ForegroundColor Cyan
$ServerJob = Start-Job -ScriptBlock {
    param($Dir, $Port)
    Set-Location $Dir
    python -m http.server $Port
} -ArgumentList $ScriptDir, $Port

Start-Sleep -Seconds 2
$Url = "http://localhost:$Port"
Write-Host "[BROWSER] Launching presentation at $Url in your default browser..." -ForegroundColor Green
Start-Process $Url

Write-Host ""
Write-Host "Presentation is now running live!" -ForegroundColor White
Write-Host "Press Ctrl+C in this terminal when finished to stop the local web server." -ForegroundColor Gray

try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`nStopping presentation server..." -ForegroundColor Yellow
    Stop-Job $ServerJob -ErrorAction SilentlyContinue
    Remove-Job $ServerJob -ErrorAction SilentlyContinue
    Write-Host "Done." -ForegroundColor Gray
}
