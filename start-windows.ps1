# Interactive installer / launcher for aiproxy on Windows.
# Parity with macOS start-mac.command + Dock start.sh:
#   - Cursor / Claude / Both / Quick start
#   - dry-run prompt
#   - save prefs (.aiproxy_runtime.env)
#   - start detached, open dashboard (?setup=1 unless SKIP_SETUP)
# Run via start-windows.bat (double-click) or:
#   powershell -ExecutionPolicy Bypass -File .\start-windows.ps1

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
Set-Location $Root

function Read-Choice([string]$Prompt, [string]$Default) {
    $v = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v.Trim()
}

function Write-PrefsFile([string]$Path, [int]$App, [string]$Mode, [bool]$DryRun, [bool]$SkipSetup = $false) {
    $savedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    @(
        "# aiproxy launcher preferences (local - not committed)"
        "APP=$App"
        "MODE=$Mode"
        "DRY_RUN=$(if ($DryRun) { 1 } else { 0 })"
        "SKIP_SETUP=$(if ($SkipSetup) { 1 } else { 0 })"
        "SAVED_AT=$savedAt"
    ) | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Read-PrefsFile([string]$Path) {
    $map = @{ app = 1; mode = "mitm"; dry_run = $true; skip_setup = $false; exists = $false }
    if (-not (Test-Path -LiteralPath $Path)) { return $map }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $i = $line.IndexOf("=")
        if ($i -lt 1) { return }
        $k = $line.Substring(0, $i)
        $v = $line.Substring($i + 1)
        switch ($k) {
            "APP" { $map.app = [int]$v }
            "MODE" { $map.mode = $v }
            "DRY_RUN" { $map.dry_run = ($v -eq "1") }
            "SKIP_SETUP" { $map.skip_setup = ($v -eq "1") }
        }
    }
    $map.exists = $true
    if ($map.app -eq 2) { $map.mode = "anthropic" }
    elseif ($map.app -in 1, 3) { $map.mode = "mitm" }
    return $map
}

Clear-Host
Write-Host "========================================"
Write-Host "  Token Saver - install & start (Windows)"
Write-Host "========================================"
Write-Host "Project: $Root"
Write-Host ""

# --- Python / venv ---
function Invoke-BootPython {
    param([Parameter(ValueFromRemainingArguments = $true)]$Rest)
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @Rest
        return
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python @Rest
        return
    }
    throw "Python 3 not found"
}

function Test-VenvPython([string]$PyPath) {
    if (-not (Test-Path -LiteralPath $PyPath)) { return $false }
    try {
        & $PyPath -c "import sys" | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

try {
    Invoke-BootPython --version | Out-Null
} catch {
    Write-Host "ERROR: Python 3 not found. Install from https://www.python.org/downloads/ (check 'Add to PATH') then re-run."
    Read-Host "Press Enter to close"
    exit 1
}

$venvDir = Join-Path $Root ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-VenvPython $venvPy)) {
    if (Test-Path -LiteralPath $venvDir) {
        Write-Host "Existing .venv is missing or broken - recreating ..."
        Remove-Item -Recurse -Force $venvDir
    } else {
        Write-Host "Creating virtualenv ..."
    }
    Invoke-BootPython -m venv $venvDir
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
}

if (-not (Test-VenvPython $venvPy)) {
    Write-Host "ERROR: Could not create a working venv at:"
    Write-Host "  $venvPy"
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Installing / updating dependencies ..."
& $venvPy -m pip install --upgrade pip | Out-Null
& $venvPy -m pip install -r (Join-Path $Root "requirements.txt")
& $venvPy -m pip install -e $Root | Out-Null
Write-Host "Deps OK."
Write-Host ""

$prefPath = Join-Path $Root ".aiproxy_runtime.env"
$saved = Read-PrefsFile $prefPath

# --- Questions (same choices as macOS / setup wizard) ---
Write-Host "Which app are you connecting?"
Write-Host "  1) Cursor  (default models - MITM HTTPS proxy)"
Write-Host "  2) Claude Code  (ANTHROPIC_BASE_URL - no CA needed)"
Write-Host "  3) Both  (MITM - Cursor + Claude via HTTPS_PROXY)"
if ($saved.exists) {
    $dryLabel = if ($saved.dry_run) { "dry-run" } else { "live strip" }
    $appLabel = switch ($saved.app) { 2 { "Claude Code" } 3 { "Both" } default { "Cursor" } }
    Write-Host "  4) Quick start  (saved: $appLabel - $dryLabel)"
}
Write-Host ""
$defaultApp = if ($saved.exists) { "4" } else { "1" }
$app = Read-Choice "Choice [1/2/3$(if ($saved.exists) { '/4' } else { '' })] (default $defaultApp)" $defaultApp

$mode = "mitm"
$dryRun = $true
$appId = 1
$quick = $false

if ($app -eq "4") {
    if (-not $saved.exists) {
        Write-Host "No saved settings yet. Pick 1/2/3 once."
        Read-Host "Press Enter to close"
        exit 1
    }
    $quick = $true
    $appId = [int]$saved.app
    $mode = [string]$saved.mode
    $dryRun = [bool]$saved.dry_run
    Write-Host "-> Quick start: app=$appId mode=$mode dry_run=$dryRun"
} else {
    switch ($app) {
        "2" { $mode = "anthropic"; $appId = 2 }
        "3" { $mode = "mitm"; $appId = 3 }
        default { $mode = "mitm"; $appId = 1 }
    }
    $dry = Read-Choice "Dry-run first? (log savings, do not rewrite bodies) [Y/n]" "Y"
    $dryRun = ($dry -notmatch '^[nN]')
    Write-Host $(if ($dryRun) { "-> dry-run ON" } else { "-> dry-run OFF (will strip when rules match)" })
}

# Ports from config.yaml, so the instructions printed below match where the
# proxy will actually listen.
$listenPort = 8080
$dashPort = 8081
try {
    $ports = & $venvPy -c "import sys; from aiproxy.config import Config; c = Config.load(sys.argv[1]); print(c.listen_port, c.dashboard_port)" (Join-Path $Root "config.yaml")
    if ("$ports" -match '^(\d+) (\d+)$') { $listenPort = [int]$Matches[1]; $dashPort = [int]$Matches[2] }
} catch {}
$proxyUrl = "http://127.0.0.1:$listenPort"
$dash = "http://127.0.0.1:$dashPort/"
$ca = Join-Path $env:USERPROFILE ".mitmproxy\mitmproxy-ca-cert.pem"
$cer = Join-Path $env:USERPROFILE ".mitmproxy\mitmproxy-ca-cert.cer"

if (-not $quick) {
    Write-Host ""
    Write-Host "----------------------------------------"
    if ($mode -eq "anthropic") {
        Write-Host "Mode: anthropic reverse proxy"
        Write-Host "Start Claude in another terminal with:"
        Write-Host "  `$env:ANTHROPIC_BASE_URL = `"$proxyUrl`""
        Write-Host "  claude"
        Write-Host "  /status   # confirm base URL"
        Write-Host ""
        $writeClaude = Read-Choice "Write ANTHROPIC_BASE_URL into ~/.claude/settings.json? [y/N]" "N"
        if ($writeClaude -match '^[yY]') {
            $claudeDir = Join-Path $env:USERPROFILE ".claude"
            $settings = Join-Path $claudeDir "settings.json"
            New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null
            if (Test-Path $settings) {
                Write-Host "Existing $settings - leave it unchanged and set the env var manually,"
                Write-Host "or merge ANTHROPIC_BASE_URL under env yourself."
            } else {
                $json = @{
                    env = @{
                        ANTHROPIC_BASE_URL = $proxyUrl
                    }
                } | ConvertTo-Json -Depth 5
                # Windows PowerShell's "-Encoding UTF8" writes a byte-order
                # mark, and a JSON parser that does not expect one rejects the
                # whole file. Write plain UTF-8 instead.
                [System.IO.File]::WriteAllText($settings, $json, (New-Object System.Text.UTF8Encoding($false)))
                Write-Host "Wrote $settings"
            }
        }
    } else {
        Write-Host "Mode: mitm (Cursor default models)"
        Write-Host "Dashboard: $dash"
        Write-Host ""
        Write-Host "Cursor settings.json needs:"
        Write-Host @"
  {
    "http.proxy": "$proxyUrl",
    "http.proxySupport": "override",
    "http.proxyStrictSSL": false,
    "cursor.general.disableHttp2": true
  }
"@
        Write-Host ""
        Write-Host "Open: Ctrl+Shift+P -> Open User Settings (JSON)"
        Write-Host "File: $env:APPDATA\Cursor\User\settings.json"
        Write-Host ""

        if (-not (Test-Path $ca)) {
            Write-Host "Generating mitmproxy CA ..."
            & $venvPy -c @"
from pathlib import Path
from mitmproxy.certs import CertStore
p = Path.home() / '.mitmproxy'
p.mkdir(parents=True, exist_ok=True)
CertStore.from_store(str(p), 'mitmproxy', 2048)
print('CA ready')
"@
        }

        $trust = Read-Choice "Open mitmproxy CA for install into Trusted Root? [y/N]" "N"
        if ($trust -match '^[yY]') {
            $openPath = if (Test-Path $cer) { $cer } else { $ca }
            if (Test-Path $openPath) {
                Start-Process $openPath
                Write-Host "In the cert dialog: Install Certificate -> Local Machine -> Trusted Root Certification Authorities"
            } else {
                Write-Host "CA not found at $openPath - start proxy once, then re-run."
            }
        }

        Write-Host ""
        Write-Host "After proxy starts: fully quit Cursor, then relaunch from PowerShell with:"
        Write-Host "  `$env:NODE_EXTRA_CA_CERTS = `"$ca`""
        Write-Host "  Start-Process `"`$env:LOCALAPPDATA\Programs\cursor\Cursor.exe`""
        if ($appId -eq 3) {
            Write-Host ""
            Write-Host "For Claude Code in another terminal:"
            Write-Host "  `$env:HTTPS_PROXY = `"$proxyUrl`""
            Write-Host "  `$env:HTTP_PROXY = `"$proxyUrl`""
            Write-Host "  `$env:NODE_EXTRA_CA_CERTS = `"$ca`""
            Write-Host "  claude"
        }
    }

    # DoNotVerify: without it GetFolderPath returns "" when the Programs
    # folder is missing, and Join-Path then throws at the very end of the
    # install. No folder at all means no shortcut question.
    $programs = [Environment]::GetFolderPath("Programs", [System.Environment+SpecialFolderOption]::DoNotVerify)
    $startMenuLnk = if ($programs) { Join-Path $programs "Token Saver\Token Saver.lnk" } else { $null }
    if ($startMenuLnk -and -not (Test-Path -LiteralPath $startMenuLnk)) {
        Write-Host ""
        $sc = Read-Choice "Add Token Saver to the Start menu and Desktop (like the Mac Dock app)? [Y/n]" "Y"
        if ($sc -notmatch '^[nN]') {
            & (Join-Path $Root "windows\install-shortcuts.ps1")
        }
    }

    $save = Read-Choice "Save these settings for Quick start next time? [Y/n]" "Y"
    if ($save -notmatch '^[nN]') {
        Write-PrefsFile $prefPath $appId $mode $dryRun $false
        Write-PrefsFile (Join-Path $Root ".aiproxy_session.env") $appId $mode $dryRun $false
        Write-Host "-> saved to .aiproxy_runtime.env"
    } else {
        Write-PrefsFile (Join-Path $Root ".aiproxy_session.env") $appId $mode $dryRun $false
        Write-Host "-> session only (not saved for Quick start)"
    }
} else {
    # Quick start: refresh session from saved
    Write-PrefsFile (Join-Path $Root ".aiproxy_session.env") $appId $mode $dryRun ([bool]$saved.skip_setup)
}

Write-Host "----------------------------------------"
Write-Host "Starting aiproxy in the background (mode=$mode) ..."
Write-Host "Dashboard: $dash"
Write-Host "Stop later:  powershell -ExecutionPolicy Bypass -File .\windows\stop.ps1"
Write-Host "(or the 'Stop Token Saver' shortcut, if you added the shortcuts)"
Write-Host "========================================"
Write-Host ""

& (Join-Path $Root "windows\start.ps1")
$exit = $LASTEXITCODE
if ($exit -ne 0) {
    Write-Host "Start failed (exit $exit)."
    Read-Host "Press Enter to close"
    exit $exit
}

Write-Host ""
Write-Host "Proxy is running. Close this window anytime - use windows\stop.ps1 to stop."
Write-Host "In the browser setup wizard, Apply & restart works the same as on macOS."
Read-Host "Press Enter to close"
