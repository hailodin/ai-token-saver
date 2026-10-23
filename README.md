# Token Saver (aiproxy)

Local proxy between **Cursor** / **Claude Code** and the model APIs. It strips bulky or duplicate context from requests so you send fewer tokens, then forwards the cleaned request upstream.

| | |
|---|---|
| **Dashboard** | [http://127.0.0.1:8081/](http://127.0.0.1:8081/) |
| **Memorable URL** | [http://tokensaver.local/](http://tokensaver.local/) *(optional — see below)* |
| **Ops board** | [http://127.0.0.1:8081/v2](http://127.0.0.1:8081/v2) |
| **Printable guide** | [README.pdf](README.pdf) |

<table>
  <tr>
    <td align="center"><img src="dark-dashboard.png" alt="Dark dashboard" /></td>
    <td align="center"><img src="light-dashboard.png" alt="Light dashboard" /></td>
  </tr>
  <tr>
    <td align="center">Dark</td>
    <td align="center">Light</td>
  </tr>
</table>

---

## Quick start

### macOS

1. Double-click **`start-mac.command`** — installs deps, asks Cursor vs Claude, starts the proxy.
2. Double-click **`Install to Applications.app`** (or **`install-to-applications.command`**) — puts **Token Saver** in `/Applications` with the Dock icon.
3. Open **Token Saver** → dashboard opens; complete the setup wizard (or use Quick start if you’ve saved prefs).
4. Optional: check **Don’t show this again** (enabled once settings are saved) so later launches skip the wizard.
5. Dock click while running → focuses the existing dashboard tab (or opens a new one if none). **Quit** from the Dock stops the proxy.

### Windows

1. Double-click **`start-windows.bat`** — installs deps, asks Cursor / Claude / Both / Quick start (same as macOS), saves prefs, starts the proxy in the background, opens the dashboard.
2. Say yes to the shortcuts question (or run `windows\install-shortcuts.ps1`) to get **Token Saver** / **Stop Token Saver** in the Start menu and on the Desktop — the Windows version of the Dock app.
3. Stop with the shortcut or `powershell -ExecutionPolicy Bypass -File .\windows\stop.ps1`.
4. Full Windows notes (shortcuts, ports, CA trust, what happens to Claude Code traffic): [README-Windows.md](README-Windows.md)

> Always run the proxy with the **venv Python** (`.venv/bin/python` on Mac, `.venv\Scripts\python.exe` on Windows) — not system `python`.

---

## 1. Install (once)

| OS | Easiest | Manual |
|----|---------|--------|
| **macOS** | `start-mac.command` | `python3 -m venv .venv` then `.venv/bin/python -m pip install -r requirements.txt -e .` |
| **Windows** | `start-windows.bat` | `python -m venv .venv` then `.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e .` |

Print ready-to-copy Cursor / Claude snippets:

```bash
# macOS / Linux
.venv/bin/python -m aiproxy --print-cursor-settings
.venv/bin/python -m aiproxy --print-claude-settings
```

```powershell
# Windows
.\.venv\Scripts\python.exe -m aiproxy --print-cursor-settings
.\.venv\Scripts\python.exe -m aiproxy --print-claude-settings
```

### macOS Dock app

```bash
./install-to-applications.command
# or double-click "Install to Applications.app"
open -a "Token Saver"
```

| Behavior | Detail |
|----------|--------|
| Prefs | `.aiproxy_runtime.env` / `.aiproxy_session.env` (Quick start + setup wizard) |
| First launch | Opens dashboard with setup wizard (`?setup=1`) unless **Don’t show this again** was saved |
| Dock click (app open) | Focuses an existing `127.0.0.1:8081` / `tokensaver.local` tab; otherwise opens a new tab |
| Dock Quit | Stops proxy + dashboard processes |
| Logs | `~/Library/Logs/TokenSaver/proxy.log` |
| After moving the repo | Re-run the installer (refreshes `ProjectRoot` + icon) |
| Other Mac / new icon | `git pull`, then re-run the installer — `/Applications` is not updated by git alone |

The optional `tokensaver.local` port-80 forwarder is **not** stopped on Quit (system service).

Allow **Token Saver → Chrome/Safari** under System Settings → Privacy & Security → Automation if Dock focus can’t switch tabs.

**Icon still stale after install?** Quit Token Saver, re-run the installer (it clears the icon cache and restarts Dock), then drag **Token Saver** out of the Dock and back from `/Applications` if needed.

---

## 2. Pick a mode

| Mode | Best for | CA cert? |
|------|----------|----------|
| **mitm** | Cursor default models (HTTPS intercept) | Yes |
| **reverse** | Cursor BYOK **and** Claude Code (JSON strip) | No |
| **openai** | Cursor OpenAI Base URL / BYOK only | No |
| **anthropic** | Claude Code via `ANTHROPIC_BASE_URL` only | No |

**Recommendation**

- Cursor without BYOK → **mitm**
- Claude Code / Cursor BYOK → **reverse** / **anthropic** / **openai**
- On Windows, the guided launcher matches macOS (Cursor → mitm, Claude → anthropic). For BYOK-only Cursor, use `--mode openai` / `--mode reverse` — see [README-Windows.md](README-Windows.md).

Start dry-run first (logs savings, does **not** change bodies):

```bash
.venv/bin/python -m aiproxy --dry-run          # macOS
.\.venv\Scripts\python.exe -m aiproxy --dry-run # Windows
```

---

## 3. Connect Cursor

### MITM (default models) — macOS

```bash
.venv/bin/python -m aiproxy --mode mitm --dry-run
```

Trust the CA once:

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem
```

Cursor `settings.json`:

```json
{
  "http.proxy": "http://127.0.0.1:8080",
  "http.proxySupport": "override",
  "http.proxyStrictSSL": false,
  "cursor.general.disableHttp2": true
}
```

Quit Cursor fully (**Cmd+Q**), then:

```bash
export NODE_EXTRA_CA_CERTS="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"
open -a Cursor
```

### OpenAI BYOK (Mac or Windows)

```bash
.venv/bin/python -m aiproxy --mode openai --dry-run
```

Cursor → Settings → Models → OpenAI Base URL: `http://127.0.0.1:8080/v1`  
No CA. Leave `http.proxy` unset. Optional path when using your own OpenAI key — see [README-Windows.md](README-Windows.md).

---

## 4. Connect Claude Code

**Terminal 1 — proxy**

```bash
.venv/bin/python -m aiproxy --mode anthropic --dry-run   # or --mode reverse
```

**Terminal 2 — Claude**

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8080"
claude
```

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8080"
claude
```

Persist in `~/.claude/settings.json` (Windows: `%USERPROFILE%\.claude\settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080"
  }
}
```

Not covered: **claude.ai** in the browser, **Claude Desktop** (no Base URL hook).

---

## 5. Memorable dashboard URL (optional)

So you can open **http://tokensaver.local/** without `:8081`:

```bash
# macOS — use the absolute venv path with sudo
cd /path/to/ai-token-saver
sudo "$(pwd)/.venv/bin/python" -m aiproxy --install-hostname
```

```powershell
# Windows — Administrator PowerShell
cd C:\path\to\ai-token-saver
& "$(Get-Location)\.venv\Scripts\python.exe" -m aiproxy --install-hostname
```

Installs `/etc/hosts` (or Windows hosts) → `tokensaver.local`, plus a small `:80` → dashboard forwarder.

---

## 6. Verify

| Check | Expected |
|-------|----------|
| Dashboard | [http://127.0.0.1:8081/](http://127.0.0.1:8081/) loads |
| Chat in Cursor / Claude | **Requested** counters rise |
| Strip rules fire | **Saved** > 0 (or dry-run log notes) |
| `logs/` | `*.meta.json` when bodies change |

Safe rollout: dry-run → tune `config.yaml` `strip:` → restart without `--dry-run`.

---

## 7. What gets stripped

Configured in `config.yaml` under `strip:`

| Rule | Idea |
|------|------|
| `max_messages` | Keep last N turns (+ system) |
| `max_chars_recent` / `max_chars_old` | Cap huge file dumps |
| `dedupe_file_blocks` | Collapse duplicate path/code blocks |
| `max_tool_result_chars` | Truncate old tool output |
| `max_bidi_file_chars` | Stub bulky file blobs in Cursor agent frames |
| `drop_reasoning_parts` | Drop thinking/reasoning blobs |
| `compress_system` / `max_system_chars` | Shrink oversized system prompts |
| `drop_keys` | Remove noisy JSON fields |

**Cursor (mitm):** agent protobuf / WebSocket requests are walked and large UTF-8 string fields truncated or stubbed; responses still stream.  
**Claude / OpenAI reverse-proxy:** JSON bodies via `--mode anthropic` / `openai` / `reverse`.

---

## 8. Ports & files

| What | Where |
|------|--------|
| Proxy | `127.0.0.1:8080` |
| Dashboard | `127.0.0.1:8081` |
| Alias | `http://tokensaver.local/` after `--install-hostname` |
| Config | `config.yaml` |
| Launcher prefs | `.aiproxy_runtime.env` (saved) / `.aiproxy_session.env` (this run) |
| Stats | `logs/stats.json` |
| Body dumps | `logs/` |
| mitmproxy CA | `~/.mitmproxy/mitmproxy-ca-cert.pem` (Windows: `%USERPROFILE%\.mitmproxy\`) |
| macOS app logs | `~/Library/Logs/TokenSaver/proxy.log` |

`SKIP_SETUP=1` in `.aiproxy_runtime.env` means the launcher opens the dashboard without the setup wizard (set via **Don’t show this again**). Use the dashboard **Setup** button to change that later. Works on macOS Dock and Windows `windows\start.ps1`.

---

## 9. Quick reference

```bash
# macOS
open start-mac.command
open "Install to Applications.app"   # or ./install-to-applications.command
open -a "Token Saver"

.venv/bin/python -m aiproxy --mode mitm --dry-run
.venv/bin/python -m aiproxy --mode anthropic --dry-run
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080 && claude
sudo "$(pwd)/.venv/bin/python" -m aiproxy --install-hostname
```

```powershell
# Windows
.\start-windows.bat
.\.venv\Scripts\python.exe -m aiproxy --dry-run
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8080"; claude
# Cursor BYOK Base URL: http://127.0.0.1:8080/v1
& "$(Get-Location)\.venv\Scripts\python.exe" -m aiproxy --install-hostname
```
