#!/usr/bin/env powershell
# CAN Driver Installer for WINDCON Servo Assistant
# Must be run as Administrator

$windconDir = "C:\Users\user\Downloads\WINDCON Servo Assistant（国外版）\WINDCON Servo Assistant"
$zipPath = Join-Path $windconDir "CAN_driver.zip"
$extractDir = Join-Path $windconDir "CAN_driver_extracted"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "CAN Driver Installation" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "✗ Requires Administrator privilege" -ForegroundColor Red
    Write-Host "  Right-click PowerShell → 'Run as Administrator'`n" -ForegroundColor Yellow
    exit 1
}

# Check zip exists
Write-Host "[1/3] Checking CAN driver zip..." -ForegroundColor Yellow
if (-not (Test-Path $zipPath)) {
    Write-Host "✗ CAN_driver.zip not found`n" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Found CAN_driver.zip" -ForegroundColor Green

# Extract
Write-Host "[2/3] Extracting..." -ForegroundColor Yellow
if (-not (Test-Path $extractDir)) {
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $extractDir)
        Write-Host "  ✓ Extracted" -ForegroundColor Green
    }
    catch {
        Write-Host "✗ Extract failed: $_`n" -ForegroundColor Red
        exit 1
    }
}
else {
    Write-Host "  - Already extracted" -ForegroundColor Gray
}

# Run installer
Write-Host "[3/3] Launching installer..." -ForegroundColor Yellow
$installer = if ([Environment]::Is64BitOperatingSystem) { "DriverSetup64.exe" } else { "DriverSetup.exe" }
$installerPath = "$extractDir\driver\$installer"

if (-not (Test-Path $installerPath)) {
    Write-Host "✗ Installer not found: $installer`n" -ForegroundColor Red
    exit 1
}

& $installerPath
Write-Host "`n✓ Installer launched" -ForegroundColor Green
Write-Host "  Follow prompts, then reboot if needed`n" -ForegroundColor Yellow
