# Token Saver on Windows

Local proxy between **Cursor** / **Claude Code** and the model APIs. Strips bulky JSON context to save tokens, then forwards upstream.

**Dashboard:** [http://127.0.0.1:8081/](http://127.0.0.1:8081/) · **Printable guide (Mac + Windows):** [README.pdf](README.pdf)

> **Python note:** Use the **Windows** Python launcher or `python.exe` to create the venv. After that, always run aiproxy with **`.venv\Scripts\python.exe`** (not a random global `python`) so deps resolve.
>
> Cross-platform overview (incl. macOS Dock app): [README.md](README.md). Double-click `start-windows.bat` for the guided install.

---

## 1. Install (once)

**Easiest:** double-click [`start-windows.bat`](start-windows.bat)

It opens a console, installs deps if needed, asks **Cursor / Claude / Both / Quick start** (same as macOS), dry-run yes/no, offers the **Start menu / Desktop shortcuts**, **saves prefs** to `.aiproxy_runtime.env`, starts the proxy in the background, and opens the dashboard with the setup wizard (`?setup=1`) unless you chose **Don’t show this again**.

| Action | Command |
|--------|---------|
| Start (background) | `powershell -ExecutionPolicy Bypass -File .\windows\start.ps1` |
| Stop | `powershell -ExecutionPolicy Bypass -File .\windows\stop.ps1` |
| Guided install | `start-windows.bat` |
| Shortcuts | `powershell -ExecutionPolicy Bypass -File .\windows\install-shortcuts.ps1` (`-NoDesktop`, `-Remove`) |

**Shortcuts** — the Windows version of the Mac Dock app. **Token Saver** (Start menu + Desktop) starts the proxy with your saved settings and opens the dashboard, or just focuses the dashboard if it is already running; **Stop Token Saver** (Start menu) stops it. They run hidden, so a failed start shows a message box with the last lines of the error log instead of a console you would never see. The shortcuts point at this folder: run `install-shortcuts.ps1` again if you move it.

**Apply & restart** in the browser wizard works on Windows the same as on the Mac Dock app (uses `windows\stop.ps1` + `windows\start.ps1`).

Open the dashboard anytime: [http://127.0.0.1:8081/](http://127.0.0.1:8081/) · **Setup** button always brings the wizard back.

Or manually in **PowerShell**:

```powershell
cd $HOME\code\aiproxy
# adjust path if your clone lives elsewhere
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

If `python` is missing, try:

```powershell
py -3 -m venv .venv
```

**Optional activate** (then bare `python` is the venv):

```powershell
.\.venv\Scripts\Activate.ps1
```

If execution policy blocks activate:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Safest without activate:

```powershell
.\.venv\Scripts\python.exe -m aiproxy --dry-run
```

Print ready-to-copy snippets:

```powershell
.\.venv\Scripts\python.exe -m aiproxy --print-cursor-settings
.\.venv\Scripts\python.exe -m aiproxy --print-claude-settings
```

---

## 2. Pick a mode

The guided launcher and setup wizard use the **same choices as macOS**:

| Choice | Mode started | Best for | CA cert? |
|--------|--------------|----------|----------|
| **1 Cursor** | `mitm` | Cursor default models (Dock/Windows parity) | Yes |
| **2 Claude Code** | `anthropic` | Claude via `ANTHROPIC_BASE_URL` | No |
| **3 Both** | `mitm` | Cursor + Claude (`HTTPS_PROXY`) | Yes |
| **4 Quick start** | saved | Replay last saved prefs | — |

Advanced CLI modes (not in the wizard menu):

| Mode | Command | Notes |
|------|---------|-------|
| **openai** | `.\.venv\Scripts\python.exe -m aiproxy --mode openai` | Cursor OpenAI Base URL / BYOK |
| **reverse** | `.\.venv\Scripts\python.exe -m aiproxy --mode reverse` | BYOK + Claude JSON bridge |
| **mitm** | `.\.venv\Scripts\python.exe -m aiproxy --mode mitm` | Full HTTPS intercept (same as choice 1) |

`config.yaml` defaults to `mode: mitm` (matches the Cursor launcher path). Pass `--mode` to override.

**Recommendation**

- Match macOS / Dock: use **start-windows.bat** → Cursor or Claude or Both
- BYOK-only Cursor → `--mode openai` or `--mode reverse` from CLI
- Avoid raw mitm only if you do not want to trust the CA; Claude-only needs no CA

Dry-run first (logs savings, does **not** change bodies):

```powershell
.\.venv\Scripts\python.exe -m aiproxy --dry-run
```

When you’re happy with the dashboard:

```powershell
.\.venv\Scripts\python.exe -m aiproxy
```

---

## 3. Connect Cursor (OpenAI BYOK — recommended)

Default Cursor models talk protobuf to Cursor’s servers — this proxy **cannot strip those**. Use an OpenAI-compatible model with a Base URL instead.

**Terminal 1**

```powershell
cd $HOME\code\aiproxy
.\.venv\Scripts\python.exe -m aiproxy --dry-run
```

**Cursor**

1. Settings → **Models**
2. OpenAI API Key → your key
3. OpenAI **Base URL** → `http://127.0.0.1:8080/v1`
4. Select an OpenAI-compatible model
5. Chat. Watch [http://127.0.0.1:8081/](http://127.0.0.1:8081/)

No CA install. Leave `http.proxy` **unset**.

---

## 4. Connect Claude Code (recommended)

**Terminal 1 — start reverse proxy**

```powershell
cd $HOME\code\aiproxy
.\.venv\Scripts\python.exe -m aiproxy --dry-run
```

**Terminal 2 — run Claude through it**

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8080"
# keep your existing key if you use one:
# $env:ANTHROPIC_API_KEY = "sk-ant-..."
claude
```

**cmd.exe**

```bat
set ANTHROPIC_BASE_URL=http://127.0.0.1:8080
claude
```

Inside Claude, run `/status` and confirm the base URL is `http://127.0.0.1:8080`.

**Persist for every Claude session** — `%USERPROFILE%\.claude\settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080"
  }
}
```

Your API key stays wherever you already keep it (`ANTHROPIC_API_KEY` or Claude login). aiproxy forwards `x-api-key` / `Authorization` unchanged.

An `env` entry in `settings.json` wins over a shell variable. To bypass the proxy for one run without editing the file: `claude --settings '{"env":{"ANTHROPIC_BASE_URL":"https://api.anthropic.com"}}'`.

**What the proxy does with Claude Code traffic.** Anthropic `/v1/messages` requests do not go through the generic strip rules in `config.yaml` → `strip` at all. Those rules edit earlier messages and the system prompt, which breaks Claude Code's prompt cache and its thinking blocks (the API answers 400) and costs more than it saves. Instead the proxy:

- never touches `system`, `tools`, `metadata`, `cache_control`, thinking blocks, assistant turns or any earlier message;
- makes one lossless edit to the **newest** user message only: a `tool_result` byte-identical to one already in the conversation becomes a short stub pointing at the earlier copy, and that decision is replayed identically on every later request (`logs\claude_state.json`);
- forwards `count_tokens` untouched;
- prices from the response's `usage` (input, cache read, 5m/1h cache write, output) and shows the result as the **Claude Code** row on the dashboard; the saving figure there is an estimate, labelled as such.

Settings are under `claude:` in `config.yaml` (`enabled: false` forwards untouched and still measures). Background and reasoning: [CLAUDE-CODE-NOTES.md](CLAUDE-CODE-NOTES.md).

**What this covers.** The `claude` CLI, and any app that lets you set an Anthropic or OpenAI base URL. **Not** the Claude desktop app: its chat talks to claude.ai, and its Code tab ignores `ANTHROPIC_BASE_URL` (checked 5–6 October 2026).

---

## 5. Verify it’s working

| Check | Expected |
|-------|----------|
| Dashboard | [http://127.0.0.1:8081/](http://127.0.0.1:8081/) loads |
| Send a chat | **Requested** counters rise |
| Strip rules fire | **Saved** tokens/chars > 0 (or notes in dry-run logs) |
| `logs\` | `*.meta.json` before/after dumps when bodies change |

Safe rollout:

1. `--dry-run` → watch dashboard  
2. Tune `config.yaml` → `strip` if needed  
3. Restart **without** `--dry-run` to forward stripped bodies  

---

## 6. MITM (Cursor default models, no BYOK)

Use this when you don’t have OpenAI BYOK. aiproxy streams SSE/Connect responses immediately so chats can reply (mitmproxy’s default body buffering used to stall them). Agent request bodies are still mostly protobuf — limited stripping.

**Start**

```powershell
.\.venv\Scripts\python.exe -m aiproxy --mode mitm --dry-run
```

First run creates the mitmproxy CA at:

`%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem`

**Trust the CA (once)**

1. Double-click `%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer`  
   (if only `.pem` exists, rename/copy to `.cer` or open via certmgr)
2. **Install Certificate…** → **Local Machine** (or Current User)
3. Place in **Trusted Root Certification Authorities**
4. Finish

Or PowerShell (Admin):

```powershell
Import-Certificate -FilePath "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer" `
  -CertStoreLocation Cert:\LocalMachine\Root
```

**Point Cursor at the proxy**

`Ctrl+Shift+P` → **Open User Settings (JSON)** — typically:

`%APPDATA%\Cursor\User\settings.json`

```json
{
  "http.proxy": "http://127.0.0.1:8080",
  "http.proxySupport": "override",
  "http.proxyStrictSSL": false,
  "cursor.general.disableHttp2": true
}
```

Fully quit Cursor, then relaunch from a shell with the CA for Node:

**PowerShell**

```powershell
$env:NODE_EXTRA_CA_CERTS = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
Start-Process "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe"
```

Path may vary (e.g. Installer vs Store). If `Start-Process` fails, start Cursor from the Start menu after setting `NODE_EXTRA_CA_CERTS` in the same session / user env vars.

**Claude via MITM**

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:8080"
$env:HTTP_PROXY = "http://127.0.0.1:8080"
$env:NODE_EXTRA_CA_CERTS = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
claude
```

If chats send but never reply, turn MITM off (remove `http.proxy*`) and use the reverse-proxy path instead.

---

## 7. Ports & files

| What | Where |
|------|--------|
| Proxy | `127.0.0.1:8080` (`listen_port` in `config.yaml`) |
| Dashboard | `127.0.0.1:8081` (`dashboard_port`) |
| Config | `config.yaml` — the launcher, the shortcuts and the printed instructions all follow the ports set here |
| Launcher logs / pid | `%LOCALAPPDATA%\TokenSaver\logs\` (`proxy.log`, `proxy.err.log`, `starts.log`), `proxy.pid` |
| Launcher prefs | `.aiproxy_runtime.env` (saved) / `.aiproxy_session.env` (this run) |
| Stats (persisted across launches) | `logs\stats.json` |
| Body dumps | `logs\` |
| mitmproxy CA | `%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem` |
| Cursor settings | `%APPDATA%\Cursor\User\settings.json` |
| Claude settings | `%USERPROFILE%\.claude\settings.json` |

---

## 8. Firewall / port already in use

If start fails with “address already in use”:

```powershell
netstat -ano | findstr :8080
```

Stop the other process, or change ports in `config.yaml` (`listen_port`, `dashboard_port`).

### Memorable dashboard URL

Default alias is **http://tokensaver.local/** (no port). Install once from an **Administrator** PowerShell in the project root — hosts entry + startup task that forwards `:80` using `dashboard_port` from `config.yaml` (auto-detected if the port changes later):

```powershell
cd C:\path\to\ai-token-saver
# Prefer the absolute path (relative .\ .venv\… under elevation is easy to get wrong)
& "$(Get-Location)\.venv\Scripts\python.exe" -m aiproxy --install-hostname
```

Or:

```powershell
& "C:\path\to\ai-token-saver\.venv\Scripts\python.exe" -m aiproxy --install-hostname `
  -c "C:\path\to\ai-token-saver\config.yaml"
```

Direct URL still works: `http://127.0.0.1:8081/` · ops board: `http://tokensaver.local/v2`

Allow local access if Windows Firewall prompts — aiproxy only needs **inbound** on `127.0.0.1` (loopback); no public exposure required.

---

## 9. Quick reference

```powershell
cd $HOME\code\aiproxy
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# reverse proxy (Cursor BYOK + Claude) — default
.\.venv\Scripts\python.exe -m aiproxy --dry-run

# Claude Code
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8080"
claude

# Cursor: Settings → Models → OpenAI Base URL = http://127.0.0.1:8080/v1

# snippets
.\.venv\Scripts\python.exe -m aiproxy --print-cursor-settings
.\.venv\Scripts\python.exe -m aiproxy --print-claude-settings

# memorable dashboard URL (once; Admin PowerShell; use absolute path)
& "$(Get-Location)\.venv\Scripts\python.exe" -m aiproxy --install-hostname
# → http://tokensaver.local/  and  http://tokensaver.local/v2

# shortcuts (Start menu + Desktop; -NoDesktop / -Remove)
powershell -ExecutionPolicy Bypass -File .\windows\install-shortcuts.ps1

# tests (each prints "ok")
.\.venv\Scripts\python.exe -m aiproxy.test_stripper
.\.venv\Scripts\python.exe -m aiproxy.test_set_content
.\.venv\Scripts\python.exe -m aiproxy.test_claude_path
.\.venv\Scripts\python.exe -m aiproxy.test_windows_scripts
```
