param(
    [switch]$DownloadOnly,
    [switch]$OpenDownloadPage,
    [string]$InstallerPath = "$env:TEMP\com0com-setup.exe"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host "[free-setup] $msg"
}

Write-Step "Checking existing com0com installation..."
$setupcX86 = "C:\Program Files (x86)\com0com\setupc.exe"
$setupcX64 = "C:\Program Files\com0com\setupc.exe"

if (Test-Path $setupcX86 -or Test-Path $setupcX64) {
    Write-Step "com0com already installed."
    Write-Step "Run as Administrator: .\repair_com0com.ps1 -WindconPort COM30 -BridgePort COM31"
    exit 0
}

$downloadUrl = "https://sourceforge.net/projects/com0com/files/latest/download"

if ($OpenDownloadPage) {
    Write-Step "Opening download page in browser..."
    Start-Process $downloadUrl
    exit 0
}

Write-Step "Downloading free com0com installer from SourceForge..."
try {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $InstallerPath -UseBasicParsing
}
catch {
    Write-Warning "Automatic download failed. Open this URL manually: $downloadUrl"
    throw
}

Write-Step "Saved installer to: $InstallerPath"

if ($DownloadOnly) {
    Write-Step "Download-only mode complete."
    exit 0
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warning "Run this script as Administrator to install driver and create COM ports."
    Write-Step "After elevation, run: .\setup_free_virtual_ports.ps1"
    exit 1
}

Write-Step "Launching installer..."
Start-Process -FilePath $InstallerPath -Wait

if (-not (Test-Path $setupcX86) -and -not (Test-Path $setupcX64)) {
    Write-Warning "Installer finished but setupc.exe was not found."
    Write-Warning "If Secure Boot is enabled, unsigned test-signed driver install can fail."
    Write-Step "Fallback (free, no kernel driver): python -m uart_simulator.tools.virtual_terminal pair --left-port 7001 --right-port 7002"
    exit 2
}

Write-Step "Creating COM30 <-> COM31 pair..."
& "$PSScriptRoot\repair_com0com.ps1" -WindconPort COM30 -BridgePort COM31

Write-Step "Done. Start emulator with:"
Write-Host "  .\run_virtual_lab.ps1 -Mode sim -VirtualBackend manual -WindconPort COM30 -BridgePort COM31"
Write-Step "Then connect WINDCON to COM30."
