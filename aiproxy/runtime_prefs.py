"""Launcher / dashboard runtime preferences (.aiproxy_runtime.env).

Shared by macOS Dock app, Windows start scripts, and the in-browser setup wizard.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PREF_NAME = ".aiproxy_runtime.env"
SESSION_NAME = ".aiproxy_session.env"

APP_CHOICES = {
    1: {
        "label": "Cursor",
        "detail": "Default models — MITM HTTPS proxy",
        "mode": "mitm",
    },
    2: {
        "label": "Claude Code",
        "detail": "ANTHROPIC_BASE_URL — no CA needed",
        "mode": "anthropic",
    },
    3: {
        "label": "Both",
        "detail": "MITM — Cursor + Claude via HTTPS_PROXY",
        "mode": "mitm",
    },
    4: {
        "label": "Quick start",
        "detail": "Use saved settings from last setup",
        "mode": None,  # resolved from saved APP/MODE
    },
}


def platform_name() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def project_root(config: Any | None = None) -> Path:
    cfg_path = getattr(config, "_config_path", None) if config is not None else None
    if cfg_path:
        return Path(cfg_path).resolve().parent
    env = os.environ.get("AIPROXY_CONFIG", "").strip()
    if env:
        return Path(env).expanduser().resolve().parent
    return Path(__file__).resolve().parent.parent


def prefs_path(config: Any | None = None) -> Path:
    return project_root(config) / PREF_NAME


def session_path(config: Any | None = None) -> Path:
    return project_root(config) / SESSION_NAME


def default_prefs() -> dict[str, Any]:
    return {
        "app": 1,
        "mode": "mitm",
        "dry_run": True,
        "exists": False,
        "saved_at": None,
        "skip_setup": False,
    }


def _parse_prefs_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    app, mode, dry = 1, "mitm", True
    skip_setup = False
    saved_at = None
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("APP="):
            try:
                app = int(line.split("=", 1)[1].strip())
            except ValueError:
                app = 1
        elif line.startswith("MODE="):
            mode = line.split("=", 1)[1].strip() or "mitm"
        elif line.startswith("DRY_RUN="):
            dry = line.split("=", 1)[1].strip() == "1"
        elif line.startswith("SKIP_SETUP="):
            skip_setup = line.split("=", 1)[1].strip() == "1"
        elif line.startswith("SAVED_AT="):
            saved_at = line.split("=", 1)[1].strip() or None
    if app == 2:
        mode = "anthropic"
    elif app in (1, 3):
        mode = "mitm"
    elif app == 4:
        app = 1
        mode = "mitm"
    return {
        "app": app,
        "mode": mode,
        "dry_run": dry,
        "exists": True,
        "saved_at": saved_at,
        "skip_setup": skip_setup,
        "path": str(path),
    }


def load_prefs(config: Any | None = None, *, include_session: bool = True) -> dict[str, Any]:
    """Active prefs: session override (if any) else saved quick-start file."""
    if include_session:
        session = _parse_prefs_file(session_path(config))
        if session:
            session["source"] = "session"
            return session
    saved = _parse_prefs_file(prefs_path(config))
    if saved:
        saved["source"] = "saved"
        return saved
    out = default_prefs()
    out["source"] = "default"
    return out


def load_saved_prefs(config: Any | None = None) -> dict[str, Any]:
    """Quick-start file only (ignores session override)."""
    saved = _parse_prefs_file(prefs_path(config))
    if saved:
        saved["source"] = "saved"
        return saved
    return default_prefs()


def mode_for_app(app: int, *, saved: dict[str, Any] | None = None) -> str:
    if app == 4:
        src = saved if saved and saved.get("exists") else None
        if src is None:
            return "mitm"
        return str(src.get("mode") or "mitm")
    info = APP_CHOICES.get(app) or APP_CHOICES[1]
    return str(info["mode"] or "mitm")


def _write_env(
    path: Path,
    *,
    app: int,
    mode: str,
    dry_run: bool,
    skip_setup: bool = False,
) -> None:
    saved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.write_text(
        (
            "# aiproxy launcher preferences (local — not committed)\n"
            f"APP={int(app)}\n"
            f"MODE={mode}\n"
            f"DRY_RUN={1 if dry_run else 0}\n"
            f"SKIP_SETUP={1 if skip_setup else 0}\n"
            f"SAVED_AT={saved_at}\n"
        ),
        encoding="utf-8",
    )


def save_prefs(
    *,
    app: int,
    dry_run: bool,
    config: Any | None = None,
    mode: str | None = None,
    persist_quick_start: bool = True,
    skip_setup: bool | None = None,
) -> dict[str, Any]:
    existing_saved = load_saved_prefs(config)
    if app == 4:
        if not existing_saved.get("exists"):
            raise ValueError("No saved settings yet — pick Cursor, Claude Code, or Both once.")
        app = int(existing_saved["app"])
        mode = str(existing_saved["mode"])
        if skip_setup is None:
            skip_setup = bool(existing_saved.get("skip_setup"))
    resolved_mode = mode or mode_for_app(app)
    if app == 2:
        resolved_mode = "anthropic"
    elif app in (1, 3):
        resolved_mode = "mitm"

    # Preserve prior skip flag unless explicitly set; only meaningful with saved prefs.
    if skip_setup is None:
        skip_setup = bool(existing_saved.get("skip_setup"))
    skip_setup = bool(skip_setup) and (
        persist_quick_start or bool(existing_saved.get("exists"))
    )

    # Session file always — so start scripts / restart pick up this run.
    _write_env(
        session_path(config),
        app=app,
        mode=resolved_mode,
        dry_run=dry_run,
        skip_setup=skip_setup,
    )
    if persist_quick_start:
        _write_env(
            prefs_path(config),
            app=app,
            mode=resolved_mode,
            dry_run=dry_run,
            skip_setup=skip_setup,
        )
    elif skip_setup != bool(existing_saved.get("skip_setup")) and existing_saved.get(
        "exists"
    ):
        # Allow toggling "don't show again" without rewriting the rest via save=false.
        _write_env(
            prefs_path(config),
            app=int(existing_saved["app"]),
            mode=str(existing_saved["mode"]),
            dry_run=bool(existing_saved["dry_run"]),
            skip_setup=skip_setup,
        )
    return load_prefs(config)


def _ca_paths() -> tuple[Path, Path]:
    pem = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
    return pem, pem.with_suffix(".cer")


def _cursor_launch_hint(plat: str, ca: Path) -> str:
    if plat == "windows":
        cursor = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "cursor" / "Cursor.exe"
        return (
            f'$env:NODE_EXTRA_CA_CERTS = "{ca}"\n'
            f'Start-Process "{cursor}"'
        )
    if plat == "darwin":
        return f'export NODE_EXTRA_CA_CERTS="{ca}"\nopen -a Cursor'
    return f'export NODE_EXTRA_CA_CERTS="{ca}"\ncursor  # or your Cursor binary'


def _claude_env_hint(plat: str, proxy_url: str) -> str:
    if plat == "windows":
        return f'$env:ANTHROPIC_BASE_URL = "{proxy_url}"\nclaude'
    return f'export ANTHROPIC_BASE_URL="{proxy_url}"\nclaude'


def _mitm_ca_hint(plat: str, ca: Path, cer: Path) -> str:
    if plat == "windows":
        return (
            "If replies fail with certificate errors, trust the mitmproxy CA once:\n\n"
            f"  # Open the .cer (or .pem) and Install Certificate → Local Machine\n"
            f"  # → Trusted Root Certification Authorities\n"
            f"  start \"{cer if cer.exists() else ca}\"\n\n"
            "Then fully quit Cursor and relaunch from PowerShell with:\n\n"
            f"  {_cursor_launch_hint(plat, ca)}"
        )
    if plat == "darwin":
        return (
            "If replies fail with certificate errors, trust the CA once in Terminal:\n\n"
            "  sudo security add-trusted-cert -d -r trustRoot \\\n"
            "    -k /Library/Keychains/System.keychain \\\n"
            f'    "{ca}"\n\n'
            "Then fully quit Cursor (Cmd+Q) and relaunch with:\n\n"
            f"  {_cursor_launch_hint(plat, ca)}"
        )
    return (
        "If replies fail with certificate errors, trust the mitmproxy CA for your OS, then:\n\n"
        f"  {_cursor_launch_hint(plat, ca)}"
    )


def setup_payload(config: Any | None = None) -> dict[str, Any]:
    prefs = load_prefs(config)
    saved = load_saved_prefs(config)
    can_skip_setup = bool(saved.get("exists"))
    skip_setup = bool(saved.get("skip_setup")) and can_skip_setup
    plat = platform_name()
    ca, cer = _ca_paths()
    proxy_url = (
        f"http://{getattr(config, 'listen_host', '127.0.0.1')}:"
        f"{getattr(config, 'listen_port', 8080)}"
    )
    return {
        "prefs": prefs,
        "saved": saved,
        "can_skip_setup": can_skip_setup,
        "skip_setup": skip_setup,
        "platform": plat,
        "choices": [
            {
                "id": i,
                "label": APP_CHOICES[i]["label"],
                "detail": APP_CHOICES[i]["detail"],
                "mode": APP_CHOICES[i]["mode"],
                "available": True if i != 4 else bool(saved.get("exists")),
            }
            for i in (1, 2, 3, 4)
        ],
        "ca_path": str(ca),
        "ca_cer_path": str(cer),
        "proxy_url": proxy_url,
        "hints": {
            "claude_env": _claude_env_hint(plat, proxy_url),
            "mitm_ca": _mitm_ca_hint(plat, ca, cer),
            "cursor_launch": _cursor_launch_hint(plat, ca),
            "restart_note": (
                "Apply will write launcher prefs and restart the proxy "
                + (
                    "(Dock app stays open)."
                    if plat == "darwin"
                    else "(background process keeps running)."
                )
            ),
        },
    }


def _restart_windows(root: Path) -> tuple[bool, str]:
    start = root / "windows" / "start.ps1"
    stop = root / "windows" / "stop.ps1"
    if not start.is_file() or not stop.is_file():
        # Fall back to repo-root helpers if present.
        start = root / "start-windows-detached.ps1"
        stop = root / "stop-windows.ps1"
    if not start.is_file() or not stop.is_file():
        return (
            False,
            "Saved. Restart manually: .\\windows\\stop.ps1 then .\\windows\\start.ps1 "
            "(or re-run start-windows.bat).",
        )

    # Detached restart so this HTTP handler can finish.
    ps = (
        f"Start-Sleep -Milliseconds 400; "
        f"& '{stop}' -Quiet; "
        f"Start-Sleep -Milliseconds 500; "
        f"& '{start}'"
    )
    # CREATE_NO_WINDOW, not DETACHED_PROCESS: powershell.exe started without a
    # console exits at once with code 0 and runs nothing, so "Apply & restart"
    # reported success and the old proxy kept running. NO_WINDOW gives it a
    # hidden console of its own.
    creationflags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            ps,
        ],
        cwd=str(root),
        start_new_session=True,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True, "Restarting proxy with new settings…"


def _restart_macos(root: Path) -> tuple[bool, str]:
    # Prefer the installed app's Resources scripts (know ProjectRoot), else repo macos/.
    candidates = [
        Path("/Applications/Token Saver.app/Contents/Resources"),
        Path.home() / "Applications/Token Saver.app/Contents/Resources",
        root / "macos" / "Token Saver.app" / "Contents" / "Resources",
        root / "macos",
    ]
    start = stop = None
    for base in candidates:
        s, t = base / "start.sh", base / "stop.sh"
        if s.is_file() and t.is_file():
            start, stop = s, t
            break
    if not start or not stop:
        return (
            False,
            "Saved. Restart the proxy manually to apply "
            "(Quit Token Saver from the Dock, then reopen).",
        )

    script = f"""
sleep 0.4
bash {stop.as_posix()} >/dev/null 2>&1 || true
sleep 0.4
bash {start.as_posix()} >/dev/null 2>&1 || true
"""
    subprocess.Popen(
        ["/bin/bash", "-c", script],
        start_new_session=True,
        cwd=str(root),
    )
    return True, "Restarting proxy with new settings…"


def restart_proxy(config: Any | None = None) -> tuple[bool, str]:
    """Restart via platform start/stop scripts when available."""
    root = project_root(config)
    if sys.platform == "win32":
        return _restart_windows(root)
    if sys.platform == "darwin":
        return _restart_macos(root)
    # Linux: try windows-style names won't work; look for a generic script if present.
    start = root / "start.sh"
    stop = root / "stop.sh"
    if start.is_file() and stop.is_file():
        script = f"""
sleep 0.4
bash {stop.as_posix()} >/dev/null 2>&1 || true
sleep 0.4
bash {start.as_posix()} >/dev/null 2>&1 || true
"""
        subprocess.Popen(
            ["/bin/bash", "-c", script],
            start_new_session=True,
            cwd=str(root),
        )
        return True, "Restarting proxy with new settings…"
    return (
        False,
        "Saved. Restart the proxy manually to apply (stop, then start again).",
    )
