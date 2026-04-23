param(
    [string]$Port = "COM11",
    [int]$Baud = 115200,
    [int]$Node = 1
)

$ErrorActionPreference = "Stop"

# In PowerShell 7+, failing native commands can become terminating errors
# when this preference is enabled. Disable it so dependency probes can fail safely.
if ($null -ne (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"

python -c "import serial" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[emu] Installing missing dependency: pyserial"
    python -m pip install pyserial -q
}

Write-Host "[emu] Starting on $Port @ $Baud, node=$Node"
python -m uart_simulator.emulator.server --port $Port --baud $Baud --node $Node
