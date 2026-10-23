# Start aiproxy in the background (Windows). Mirrors macos/start.sh.
# - Does NOT kill a healthy existing proxy
# - Reads .aiproxy_session.env / .aiproxy_runtime.env
# - Opens dashboard (?setup=1 unless SKIP_SETUP=1)
param(
    [switch]$NoBrowser,
    # Set by the Start menu / Desktop shortcut (windows\install-shortcuts.ps1).
    [switch]$FromShortcut
)

$ErrorActionPreference = "Stop"
$Res = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path -LiteralPath (Join-Path $Res "..")).Path
$Support = Join-Path $env:LOCALAPPDATA "TokenSaver"
$LogDir = Join-Path $Support "logs"
$PidFile = Join-Path $Support "proxy.pid"
New-Item -ItemType Directory -Force -Path $Support, $LogDir | Out-Null

# A shortcut runs this in a hidden window, where a printed error is never
# seen: the click would simply do nothing. So a failure there is a message box.
function Stop-WithError([string]$Message) {
    Write-Host $Message
    if ($FromShortcut) {
        try { (New-Object -ComObject WScript.Shell).Popup($Message, 0, "Token Saver", 16) | Out-Null } catch {}
    }
    exit 1
}

if (-not (Test-Path -LiteralPath (Join-Path $Root "config.yaml"))) {
    Stop-WithError "config.yaml not found at $Root"
}

Set-Location $Root

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Stop-WithError "Token Saver is not installed yet. Double-click start-windows.bat in $Root once to install it."
}

# Ports come from config.yaml. They used to be fixed at 8080/8081 here, so
# moving the proxy off a busy port (as the README suggests) made this script
# wait on the wrong port, report failure and leave the proxy running.
$DashPort = 8081
try {
    $ports = & $VenvPy -c "import sys; from aiproxy.config import Config; c = Config.load(sys.argv[1]); print(c.listen_port, c.dashboard_port)" (Join-Path $Root "config.yaml")
    if ("$ports" -match '^(\d+) (\d+)$') { $DashPort = [int]$Matches[2] }
} catch {}

$DirectUrl = "http://127.0.0.1:$DashPort/"
$SetupUrl = "http://127.0.0.1:$DashPort/?setup=1"

function Test-Dashboard {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$DashPort/api/stats" -UseBasicParsing -TimeoutSec 1
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Open-Dashboard([string]$Url) {
    if ($NoBrowser) { return }
    try { Start-Process $Url } catch {}
}

# Healthy already - focus dashboard, do not restart.
if (Test-Dashboard) {
    Open-Dashboard $DirectUrl
    Write-Host "Proxy already running - opened dashboard."
    exit 0
}

# Stale PID only if dashboard is down.
if (Test-Path -LiteralPath $PidFile) {
    & (Join-Path $Res "stop.ps1") -Quiet
}

$App = "1"
$Mode = "mitm"
$DryRun = "1"
$SkipSetup = "0"
$PrefFile = Join-Path $Root ".aiproxy_runtime.env"
$SessionFile = Join-Path $Root ".aiproxy_session.env"
$LoadFile = $null
if (Test-Path -LiteralPath $SessionFile) { $LoadFile = $SessionFile }
elseif (Test-Path -LiteralPath $PrefFile) { $LoadFile = $PrefFile }

function Read-EnvFile([string]$Path) {
    $map = @{}
    Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $i = $line.IndexOf("=")
        if ($i -lt 1) { return }
        $map[$line.Substring(0, $i)] = $line.Substring($i + 1)
    }
    return $map
}

if ($LoadFile) {
    $envMap = Read-EnvFile $LoadFile
    if ($envMap.ContainsKey("APP")) { $App = $envMap["APP"] }
    if ($envMap.ContainsKey("MODE")) { $Mode = $envMap["MODE"] }
    if ($envMap.ContainsKey("DRY_RUN")) { $DryRun = $envMap["DRY_RUN"] }
    if ($envMap.ContainsKey("SKIP_SETUP")) { $SkipSetup = $envMap["SKIP_SETUP"] }
}
# Prefer persistent quick-start flag for skipping the setup modal.
if (Test-Path -LiteralPath $PrefFile) {
    $prefMap = Read-EnvFile $PrefFile
    if ($prefMap.ContainsKey("SKIP_SETUP")) { $SkipSetup = $prefMap["SKIP_SETUP"] }
}

switch ($App) {
    "2" { $Mode = "anthropic" }
    "3" { $Mode = "mitm" }
}
if ($DryRun -notin @("0", "1")) { $DryRun = "1" }
if ($SkipSetup -notin @("0", "1")) { $SkipSetup = "0" }
if ($SkipSetup -eq "1" -and -not (Test-Path -LiteralPath $PrefFile)) { $SkipSetup = "0" }

$env:AIPROXY_CONFIG = (Join-Path $Root "config.yaml")
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$Root;$env:PYTHONPATH" } else { $Root }

$Log = Join-Path $LogDir "proxy.log"
$errLog = Join-Path $LogDir "proxy.err.log"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Add-Content -LiteralPath (Join-Path $LogDir "starts.log") -Value "---- $stamp start mode=$Mode dry_run=$DryRun root=$Root ----"

# Start-Process joins -ArgumentList with spaces and quotes nothing, so a
# project folder with a space in its name ("Token Saver") split the config
# path into two arguments. Quote it here.
$argList = @("-m", "aiproxy", "--mode", $Mode, "-c", "`"$(Join-Path $Root 'config.yaml')`"")
if ($DryRun -eq "1") { $argList += "--dry-run" }

$proc = Start-Process -FilePath $VenvPy -ArgumentList $argList `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $Log `
    -RedirectStandardError $errLog `
    -PassThru

$proc.Id | Set-Content -LiteralPath $PidFile -Encoding ASCII
Set-Content -LiteralPath (Join-Path $Support "project_root") -Value $Root -Encoding UTF8
Set-Content -LiteralPath (Join-Path $Support "last_pid") -Value $proc.Id -Encoding ASCII

# Up to 30 s. Measured on a fresh install (Windows 11, Python 3.14): the
# dashboard answers 1 s after launch in anthropic mode and 2.5 s in mitm
# mode; the margin is for slower disks and a Defender scan of the new venv.
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    if ($proc.HasExited) { break }
    if (Test-Dashboard) { $ok = $true; break }
}

if (-not $ok) {
    $why = if ($proc.HasExited) { "The proxy exited." } else { "The proxy is running but not answering." }
    # Python writes the log as UTF-8; read it the same way, or a dash in a
    # log line shows up as mojibake in the message box.
    $tail = (Get-Content -LiteralPath $errLog -Tail 12 -Encoding UTF8 -ErrorAction SilentlyContinue) -join "`n"
    Stop-WithError "Token Saver did not come up: the dashboard is not answering on port $DashPort. $why`n`nLast lines of $errLog`:`n$tail"
}

if ($SkipSetup -eq "1") {
    Open-Dashboard $DirectUrl
} else {
    Open-Dashboard $SetupUrl
}

Write-Host "Proxy running (pid $($proc.Id)). Dashboard: $DirectUrl"
exit 0
