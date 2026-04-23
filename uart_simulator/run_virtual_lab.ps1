param(
	[ValidateSet("sim", "real")]
	[string]$Mode = "sim",
	[ValidateSet("com0com", "manual")]
	[string]$VirtualBackend = "com0com",
	[string]$WindconPort = "COM10",
	[string]$BridgePort = "COM11",
	[string]$RealPort = "",
	[int]$Baud = 115200,
	[int]$Node = 1,
	[switch]$SkipVirtualSetup,
	[switch]$SuggestPairs
)

$ErrorActionPreference = "Stop"

# In PowerShell 7+, failing native commands can become terminating errors
# when this preference is enabled. Disable it so dependency probes can fail safely.
if ($null -ne (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)) {
	$PSNativeCommandUseErrorActionPreference = $false
}

# Run from project root regardless of invocation location.
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

# Work around editable-install Unicode path issue by importing from src directly.
$env:PYTHONPATH = Join-Path $projectRoot "src"

# Ensure runtime dependencies are available in the active interpreter.
Write-Host "[lab] Checking and installing dependencies..."
$depCheck = @"
import sys
try:
    import serial
except ImportError:
    sys.exit(1)
try:
    import PIL
except ImportError:
    sys.exit(2)
"@

python -c $depCheck -ErrorAction SilentlyContinue 2>$null
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
	Write-Host "[lab] Installing missing dependencies: pyserial, pillow"
	python -m pip install pyserial pillow -q 2>$null
}

Write-Host "[lab] PYTHONPATH=$env:PYTHONPATH"
Write-Host "[lab] Mode=$Mode | Backend=$VirtualBackend | WINDCON=$WindconPort | Bridge=$BridgePort | Baud=$Baud | Node=$Node"
if ($Mode -eq "real") {
	if ([string]::IsNullOrWhiteSpace($RealPort)) {
		throw "When Mode=real, set -RealPort (example: COM5)"
	}
	Write-Host "[lab] Real controller port: $RealPort"
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($VirtualBackend -eq "manual") {
	$SkipVirtualSetup = $true
	Write-Host "[lab] Backend=manual: using pre-created virtual COM pair (no com0com setup attempt)."
}
elseif (-not $SkipVirtualSetup.IsPresent -and -not $isAdmin) {
	Write-Host "[lab] Not running as Administrator; automatic com0com setup cannot run (WinError 740)."
	Write-Host "[lab] Falling back to --skip-virtual-setup. If COM10/COM11 do not exist, re-run in elevated PowerShell."
	$SkipVirtualSetup = $true
}

$pythonArgs = @(
	"-m", "uart_simulator.tools.virtual_lab",
	"--virtual-backend", $VirtualBackend,
	"--mode", $Mode,
	"--windcon-port", $WindconPort,
	"--bridge-port", $BridgePort,
	"--baud", $Baud,
	"--node", $Node
)

if ($Mode -eq "real") {
	$pythonArgs += @("--real-port", $RealPort)
}

if ($SkipVirtualSetup.IsPresent) {
	$pythonArgs += "--skip-virtual-setup"
}

if ($SuggestPairs.IsPresent) {
	$pythonArgs += "--suggest-pairs"
}

python @pythonArgs
