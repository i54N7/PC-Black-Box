$ErrorActionPreference = "Stop"

$TaskName = "PC Black Box Hardware Bridge"
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BridgeExe = Join-Path $BaseDir "HardwareBridgeRuntime\HardwareBridge.exe"
$JsonFile = Join-Path $BaseDir "hardware_sensors.json"

if (-not (Test-Path $BridgeExe)) {
    Write-Host "[ERROR] HardwareBridge.exe was not found:" -ForegroundColor Red
    Write-Host "  $BridgeExe"
    Read-Host "Press Enter to close"
    exit 1
}

$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Run the console bridge through a hidden PowerShell host.
$escapedBridge = $BridgeExe.Replace("'", "''")
$escapedJson = $JsonFile.Replace("'", "''")
$command = "& '$escapedBridge' '$escapedJson'"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "' + $command.Replace('"','\"') + '"') `
    -WorkingDirectory $BaseDir

$Principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Highest

# Replace/update the existing task with the hidden version.
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Principal $Principal `
    -Description "Hidden elevated sensor bridge for PC Black Box V7.1" `
    -Force | Out-Null

Write-Host ""
Write-Host "[SUCCESS] Hidden elevated Hardware Bridge task installed." -ForegroundColor Green
Write-Host "Task: $TaskName"
Write-Host ""
Write-Host "PC Black Box can now start the bridge with highest privileges"
Write-Host "without showing the bridge console window."
Write-Host ""
Read-Host "Press Enter to close"
