param(
    [string]$WindconPort = "COM10",
    [string]$BridgePort = "COM11",
    [int]$PairIndex = 0
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[com0com] Elevation required. Re-launching as Administrator..."
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-WindconPort", $WindconPort,
        "-BridgePort", $BridgePort,
        "-PairIndex", $PairIndex
    )
    try {
        Start-Process -FilePath "powershell.exe" -ArgumentList $argList -Verb RunAs | Out-Null
    }
    catch {
        throw "Elevation was cancelled. Re-run this script and accept the UAC prompt."
    }
    return
}

$setupc = "C:\Program Files (x86)\com0com\setupc.exe"
if (-not (Test-Path $setupc)) {
    $setupc = "C:\Program Files\com0com\setupc.exe"
}
if (-not (Test-Path $setupc)) {
    throw "setupc.exe not found. Install com0com first."
}

Write-Host "[com0com] Using: $setupc"
Write-Host "[com0com] Ensuring at least one pair exists..."

$setupDir = Split-Path -Parent $setupc
Push-Location $setupDir
try {
    & $setupc install - - | Out-Null

$left = "CNCA$PairIndex"
$right = "CNCB$PairIndex"

Write-Host "[com0com] Assigning pair $left <-> $right as $WindconPort <-> $BridgePort"
    & $setupc change $left "PortName=$WindconPort" | Out-Null
    & $setupc change $right "PortName=$BridgePort" | Out-Null
    & $setupc change $left "RealPortName=$WindconPort" | Out-Null
    & $setupc change $right "RealPortName=$BridgePort" | Out-Null

Write-Host "[com0com] Current pairs:"
    & $setupc list
}
finally {
    Pop-Location
}

$bus = Get-PnpDevice | Where-Object { $_.FriendlyName -match "com0com - bus for serial port pair emulator" } | Select-Object -First 1
if ($null -ne $bus) {
    $problem = $bus | Get-PnpDeviceProperty DEVPKEY_Device_ProblemCode -ErrorAction SilentlyContinue
    if ($null -ne $problem -and $problem.Data -eq 52) {
        $secureBootOn = $null
        try {
            $secureBootOn = Confirm-SecureBootUEFI
        }
        catch {
            # Some systems/firmware do not expose this cmdlet result.
            $secureBootOn = $null
        }

        Write-Warning "[com0com] Driver blocked (ProblemCode 52: signature enforcement)."
        if ($secureBootOn -eq $true) {
            Write-Warning "[com0com] Secure Boot is ON, so Windows refuses testsigning changes."
            Write-Warning "[com0com] Option A: Disable Secure Boot in BIOS/UEFI, then run: bcdedit /set testsigning on, reboot, rerun this script."
            Write-Warning "[com0com] Option B: Use a signed virtual serial solution instead of com0com."
        }
        else {
            Write-Warning "[com0com] Run elevated cmd: bcdedit /set testsigning on"
            Write-Warning "[com0com] Reboot, then run this script again."
        }
        return
    }
}

Write-Host "[com0com] Done. If ports still do not appear in Device Manager, reboot once to ensure driver loads correctly."