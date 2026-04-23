#!/usr/bin/env powershell
# WINDCON Simulator - One-Click Startup
# Usage: .\start_all.ps1 [-NoGUI]

param([switch]$NoGUI)

$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "WINDCON Simulator Startup" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Kill stale processes
Write-Host "[1/3] Cleaning up..." -ForegroundColor Yellow
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'virtual_lab|COM40|COM41|launch_app.py' -or $_.Name -match 'serial-discovery.exe'
} | ForEach-Object { 
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "  stopped $($_.ProcessId)" -ForegroundColor Green
}
Start-Sleep -Milliseconds 500

# Start bridge
Write-Host "[2/3] Starting bridge on COM41..." -ForegroundColor Yellow
Set-Location $proj
& ".\.venv\Scripts\Activate.ps1"
Start-Process python.exe -Args @(
    "-m", "uart_simulator.tools.virtual_lab",
    "--virtual-backend", "manual", "--mode", "sim",
    "--windcon-port", "COM40", "--bridge-port", "COM41",
    "--baud", "115200", "--node", "1", "--skip-virtual-setup"
) -NoNewWindow
Write-Host "  ✓ Bridge started" -ForegroundColor Green
Start-Sleep -Milliseconds 800

# Start GUI
if (-not $NoGUI) {
    Write-Host "[3/3] Starting GUI..." -ForegroundColor Yellow
    Start-Process "$proj\.venv\Scripts\python.exe" -Args "$proj\launch_app.py"
    Write-Host "  ✓ GUI started" -ForegroundColor Green
}
else {
    Write-Host "[3/3] GUI skipped (use -NoGUI flag)" -ForegroundColor Gray
}

Write-Host "`n✓ Startup complete!" -ForegroundColor Green
Write-Host "  WINDCON → connect to COM40" -ForegroundColor Cyan
Write-Host "  Emulator → listening on COM41`n" -ForegroundColor Cyan
