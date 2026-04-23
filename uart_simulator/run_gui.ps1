$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

# Keep imports reliable without editable install.
$env:PYTHONPATH = Join-Path $projectRoot "src"

Write-Host "[gui] Starting WINDCON simulator UI"
python launch_app.py
