# Put Token Saver in the Start menu and on the Desktop - the Windows version
# of the macOS Dock app. "Token Saver" starts the proxy with your saved
# settings (or just opens the dashboard if it is already running);
# "Stop Token Saver" stops it.
#
#   powershell -ExecutionPolicy Bypass -File .\windows\install-shortcuts.ps1
#   ... -NoDesktop    Start menu only
#   ... -Remove       take the shortcuts away again
#
# The shortcuts point at this folder, so run this again if you move it.
param(
    [switch]$Remove,
    [switch]$NoDesktop,
    # Where the shortcuts go; overridable so a test can use a scratch folder.
    # DoNotVerify: GetFolderPath returns "" for a folder that does not exist
    # yet, and the folder is created below.
    [string]$StartMenuDir = [Environment]::GetFolderPath("Programs", [System.Environment+SpecialFolderOption]::DoNotVerify),
    [string]$DesktopDir = [Environment]::GetFolderPath("Desktop", [System.Environment+SpecialFolderOption]::DoNotVerify)
)

$ErrorActionPreference = "Stop"
if (-not $StartMenuDir) { throw "No Start menu folder for this user; pass -StartMenuDir." }
if (-not $DesktopDir -and -not $NoDesktop) { throw "No Desktop folder for this user; pass -DesktopDir or -NoDesktop." }
if (-not $PSBoundParameters.ContainsKey("StartMenuDir")) { $StartMenuDir = Join-Path $StartMenuDir "Token Saver" }
$Res = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path -LiteralPath (Join-Path $Res "..")).Path
$Icon = Join-Path $Res "token-saver.ico"
# The full path: a shortcut's target is not looked up on PATH the way a
# typed command is.
$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

$StartLnk = "Token Saver.lnk"
$StopLnk = "Stop Token Saver.lnk"
$placed = @(
    @{ Dir = $StartMenuDir; Names = @($StartLnk, $StopLnk) }
)
if (-not $NoDesktop) { $placed += @{ Dir = $DesktopDir; Names = @($StartLnk) } }

if ($Remove) {
    foreach ($p in $placed) {
        foreach ($n in $p.Names) {
            $path = Join-Path $p.Dir $n
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Force
                Write-Host "Removed $path"
            }
        }
    }
    if ((Test-Path -LiteralPath $StartMenuDir) -and -not (Get-ChildItem -LiteralPath $StartMenuDir -Force)) {
        Remove-Item -LiteralPath $StartMenuDir -Force
    }
    exit 0
}

function New-Shortcut([string]$Path, [string]$Script, [string]$ExtraArgs, [string]$Description) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($Path)
    $lnk.TargetPath = $PowerShell
    $scriptPath = Join-Path $Res $Script
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" $ExtraArgs".Trim()
    $lnk.WorkingDirectory = $Root
    $lnk.IconLocation = "$Icon,0"
    $lnk.Description = $Description
    # 7 = minimized: the console PowerShell needs flashes in the taskbar at
    # most, instead of opening in front of the dashboard.
    $lnk.WindowStyle = 7
    $lnk.Save()
    Write-Host "Added $Path"
}

foreach ($p in $placed) {
    New-Item -ItemType Directory -Force -Path $p.Dir | Out-Null
    foreach ($n in $p.Names) {
        if ($n -eq $StartLnk) {
            New-Shortcut (Join-Path $p.Dir $n) "start.ps1" "-FromShortcut" "Start Token Saver and open its dashboard"
        } else {
            New-Shortcut (Join-Path $p.Dir $n) "stop.ps1" "-FromShortcut" "Stop Token Saver"
        }
    }
}
exit 0
