# Stop Token Saver / aiproxy for this project (Windows).
# Mirrors macos/stop.sh - used by wizard Apply & restart and start-windows.bat.
param(
    [switch]$Quiet,
    # Set by the "Stop Token Saver" shortcut: confirm in a message box, since
    # the shortcut's window is hidden.
    [switch]$FromShortcut
)

$ErrorActionPreference = "Continue"
$Res = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path -LiteralPath (Join-Path $Res "..")).Path
$Support = Join-Path $env:LOCALAPPDATA "TokenSaver"
$PidFile = Join-Path $Support "proxy.pid"

function Stop-PidTree([int]$ProcessId) {
    if ($ProcessId -le 0) { return }
    # Never stop the PowerShell running this script. The dashboard's
    # "Apply & restart" starts that PowerShell from inside the proxy, so it is
    # a child of the very process being stopped: walking the tree used to
    # reach it first, kill it, and leave the old proxy running with nothing
    # restarted.
    if ($ProcessId -eq $PID) { return }
    try {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue
        foreach ($c in $children) {
            Stop-PidTree -ProcessId ([int]$c.ProcessId)
        }
    } catch {}
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    } catch {}
}

if (Test-Path -LiteralPath $PidFile) {
    $raw = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue)
    if ($raw -match '(\d+)') {
        Stop-PidTree -ProcessId ([int]$Matches[1])
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

# Belt-and-suspenders: anything still running from this project's venv / config.
try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return }
        # This script's own command line names this project (and, when the
        # clone is called "aiproxy", matches the pattern below).
        if ([int]$_.ProcessId -eq $PID) { return }
        if ($cmd -like "*$Root*" -and $cmd -match 'aiproxy|mitmdump|mitm_entry') {
            try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
} catch {}

# Do NOT stop the tokensaver.local scheduled task / port alias - that stays installed.
if (-not $Quiet) {
    Write-Host "Proxy stopped."
}
if ($FromShortcut) {
    try { (New-Object -ComObject WScript.Shell).Popup("Token Saver stopped.", 3, "Token Saver", 64) | Out-Null } catch {}
}
exit 0
