from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .claude_strip import ClaudeConfig


@dataclass
class StripConfig:
    max_messages: int = 24
    max_chars_recent: int = 24000
    max_chars_old: int = 4000
    recent_turn_window: int = 6
    drop_reasoning_parts: bool = True
    dedupe_file_blocks: bool = True
    max_tool_result_chars: int = 2000
    # BidiAppend hex-nested file bodies — stub down to this many chars
    max_bidi_file_chars: int = 256
    drop_keys: list[str] = field(default_factory=list)
    compress_system: bool = True
    max_system_chars: int = 12000
    dry_run: bool = False


@dataclass
class LogConfig:
    level: str = "INFO"
    dump_dir: str = "logs"
    dump_bodies: bool = True
    dump_only_when_stripped: bool = True


@dataclass
class PricingConfig:
    # Cursor sends "default" and resolves the model server-side, so savings are
    # priced at this model's input rate when nothing concrete is detected.
    assume_model: str = ""


@dataclass
class Config:
    listen_host: str = "127.0.0.1"
    listen_port: int = 8080
    dashboard_port: int = 8081
    # Friendly local name for the dashboard (needs --install-hostname once).
    # Install maps hostname → alias IP and forwards :alias_port → dashboard_port
    # so http://tokensaver.local/ works without typing :8081.
    dashboard_hostname: str = "tokensaver.local"
    dashboard_alias_ip: str = "127.0.0.2"
    dashboard_alias_port: int = 80
    mode: str = "mitm"
    openai_upstream: str = "https://api.openai.com"
    anthropic_upstream: str = "https://api.anthropic.com"
    intercept_hosts: list[str] = field(default_factory=list)
    block_hosts: list[str] = field(default_factory=list)
    block_host_suffixes: list[str] = field(default_factory=list)
    strip: StripConfig = field(default_factory=StripConfig)
    logging: LogConfig = field(default_factory=LogConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)
    stats_path: str = "logs/stats.json"
    # Claude Code's own path (claude_path.py): never the strip rules above.
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        raw: dict[str, Any] = {}
        if path.exists():
            # Explicit UTF-8: Windows' default is cp1252, which turns the em
            # dashes in this file's comments into mojibake and raises on any
            # character cp1252 has no byte for. "-sig" also accepts the BOM
            # older Notepad versions add when saving.
            with path.open(encoding="utf-8-sig") as f:
                raw = yaml.safe_load(f) or {}

        strip_raw = raw.get("strip") or {}
        log_raw = raw.get("logging") or {}
        pricing_raw = raw.get("pricing") or {}
        claude_raw = raw.get("claude") or {}
        base = path.parent if path.exists() else Path(__file__).resolve().parent.parent
        claude_defaults = ClaudeConfig()

        return cls(
            listen_host=raw.get("listen_host", "127.0.0.1"),
            listen_port=int(raw.get("listen_port", 8080)),
            dashboard_port=int(raw.get("dashboard_port", 8081)),
            dashboard_hostname=str(
                raw.get("dashboard_hostname", "tokensaver.local") or ""
            ).strip(),
            dashboard_alias_ip=str(
                raw.get("dashboard_alias_ip", "127.0.0.2") or "127.0.0.2"
            ).strip(),
            dashboard_alias_port=int(raw.get("dashboard_alias_port", 80)),
            mode=raw.get("mode", "mitm"),
            openai_upstream=raw.get("openai_upstream", "https://api.openai.com"),
            anthropic_upstream=raw.get(
                "anthropic_upstream", "https://api.anthropic.com"
            ),
            intercept_hosts=list(raw.get("intercept_hosts") or []),
            block_hosts=list(raw.get("block_hosts") or []),
            block_host_suffixes=list(raw.get("block_host_suffixes") or []),
            strip=StripConfig(
                max_messages=int(strip_raw.get("max_messages", 24)),
                max_chars_recent=int(strip_raw.get("max_chars_recent", 24000)),
                max_chars_old=int(strip_raw.get("max_chars_old", 4000)),
                recent_turn_window=int(strip_raw.get("recent_turn_window", 6)),
                drop_reasoning_parts=bool(strip_raw.get("drop_reasoning_parts", True)),
                dedupe_file_blocks=bool(strip_raw.get("dedupe_file_blocks", True)),
                max_tool_result_chars=int(strip_raw.get("max_tool_result_chars", 2000)),
                max_bidi_file_chars=int(strip_raw.get("max_bidi_file_chars", 256)),
                drop_keys=list(strip_raw.get("drop_keys") or []),
                compress_system=bool(strip_raw.get("compress_system", True)),
                max_system_chars=int(strip_raw.get("max_system_chars", 12000)),
                dry_run=bool(strip_raw.get("dry_run", False)),
            ),
            logging=LogConfig(
                level=str(log_raw.get("level", "INFO")),
                dump_dir=_resolve_stats_path(
                    str(log_raw.get("dump_dir", "logs")),
                    base=base,
                ),
                dump_bodies=bool(log_raw.get("dump_bodies", True)),
                dump_only_when_stripped=bool(
                    log_raw.get("dump_only_when_stripped", True)
                ),
            ),
            pricing=PricingConfig(
                assume_model=str(pricing_raw.get("assume_model", "") or ""),
            ),
            stats_path=_resolve_stats_path(
                str(raw.get("stats_path", "logs/stats.json")),
                base=base,
            ),
            claude=ClaudeConfig(
                enabled=bool(claude_raw.get("enabled", claude_defaults.enabled)),
                dedupe_tool_results=bool(
                    claude_raw.get("dedupe_tool_results", claude_defaults.dedupe_tool_results)
                ),
                dedupe_min_chars=int(
                    claude_raw.get("dedupe_min_chars", claude_defaults.dedupe_min_chars)
                ),
                state_path=_resolve_stats_path(
                    str(claude_raw.get("state_path", claude_defaults.state_path)), base=base
                ),
                stats_path=_resolve_stats_path(
                    str(claude_raw.get("stats_path", claude_defaults.stats_path)), base=base
                ),
                drop_tool_prefixes=[
                    str(p).strip() for p in (claude_raw.get("drop_tool_prefixes") or []) if str(p).strip()
                ],
                keep_cache_warm=bool(claude_raw.get("keep_cache_warm", claude_defaults.keep_cache_warm)),
                # Capped below 3600 so the refresh always lands inside the
                # hour, however long the last reply took to stream.
                keep_warm_after_seconds=min(3540, max(60, int(
                    claude_raw.get("keep_warm_after_seconds", claude_defaults.keep_warm_after_seconds)))),
                keep_warm_limit=max(0, int(claude_raw.get("keep_warm_limit", claude_defaults.keep_warm_limit))),
                keep_warm_min_requests=max(1, int(
                    claude_raw.get("keep_warm_min_requests", claude_defaults.keep_warm_min_requests))),
            ),
        )


def _resolve_stats_path(stats_path: str, *, base: Path) -> str:
    """Make a config path absolute relative to the config file (not cwd)."""
    p = Path(stats_path).expanduser()
    if not p.is_absolute():
        p = base / p
    return str(p.resolve())


def dashboard_bind_host(config: Config) -> str:
    """Interface address the dashboard socket binds to."""
    return config.listen_host


def _alias_installed(config: Config) -> bool:
    """True once --install-hostname has put the alias in the hosts file.

    The alias is set in config.yaml by default, but it only resolves after the
    one-time admin install. Advertising it before then sent every new user to
    a page that does not load.
    """
    alias = (config.dashboard_hostname or "").strip()
    if not alias:
        return False
    from .local_hostname import hostname_configured

    return hostname_configured(alias, alias_ip=config.dashboard_alias_ip)


def dashboard_public_host(config: Config) -> str:
    """Hostname shown in URLs / banners (alias once installed, else loopback)."""
    if _alias_installed(config):
        return (config.dashboard_hostname or "").strip()
    host = config.listen_host
    if host in ("0.0.0.0", "::", "[::]"):
        return "127.0.0.1"
    return host


def dashboard_public_port(config: Config) -> int:
    """Port shown in public URLs (80 via alias once installed)."""
    if _alias_installed(config):
        return int(config.dashboard_alias_port or 80)
    return int(config.dashboard_port)


def dashboard_origin(config: Config) -> str:
    host = dashboard_public_host(config)
    port = dashboard_public_port(config)
    if port == 80:
        return f"http://{host}"
    if port == 443:
        return f"https://{host}"
    return f"http://{host}:{port}"


def dashboard_direct_origin(config: Config) -> str:
    """Loopback URL that always hits the dashboard socket (includes port)."""
    host = config.listen_host
    if host in ("0.0.0.0", "::", "[::]"):
        host = "127.0.0.1"
    return f"http://{host}:{config.dashboard_port}"


def host_matches(host: str, patterns: list[str]) -> bool:
    host = host.lower().split(":")[0]
    for pat in patterns:
        pat = pat.lower().strip()
        if not pat:
            continue
        if pat.startswith("*."):
            suffix = pat[1:]  # .example.com
            if host.endswith(suffix) or host == pat[2:]:
                return True
        elif host == pat or host.endswith("." + pat):
            return True
    return False