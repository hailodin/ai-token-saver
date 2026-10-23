"""Accounting for the Claude Code path: what was spent, what was removed, and
whether the cache held.

Spend is taken from the API's own usage numbers, priced per model with the
cache multipliers (claude_usage.py). The one estimate is the token count of a
removed duplicate, converted from chars at the chars-per-token ratio measured
on that same conversation. Both are labelled as such on the dashboard; the
old dashboard priced removed chars at full input rate and called it savings,
which overstated the figure by up to 10x on cached content.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .claude_usage import Usage, price_for

log = logging.getLogger("aiproxy.claude.stats")

# Before the first measured response in a conversation.
DEFAULT_CHARS_PER_TOKEN = 3.6
_RECENT_PERSIST = 300
_CONV_RETENTION_S = 3 * 24 * 3600


@dataclass
class ClaudeEvent:
    ts: float
    conversation: str
    model: str
    path: str
    status: int
    streamed: bool
    duration_ms: int
    chars_in: int
    chars_out: int
    input_tokens: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    output_tokens: int
    cost_usd: float | None
    # Duplicate content removed on this request
    removed_chars_new: int
    removed_chars_replayed: int
    removed_tokens_est: int
    saved_usd_est: float | None
    cache_miss: bool
    chars_per_token: float
    stop_reason: str = ""
    error: str = ""
    notes: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read + self.cache_write_5m + self.cache_write_1h


@dataclass
class ConvState:
    last_prompt_tokens: int = 0
    chars_per_token: float = 0.0
    requests: int = 0
    last_ts: float = 0.0
    # "5m" or "1h": the cache lifetime this conversation's writes used last.
    write_ttl: str = ""


def _write_rate(price, usage: Usage, conv: ConvState) -> float:  # noqa: ANN001
    """The cache-write price this conversation actually pays.

    Claude Code writes its cache with a 1-hour lifetime, which costs 2x input
    against 1.25x for 5 minutes. Pricing every avoided write at the 5-minute
    rate valued that part of the saving 37% low on Claude Code traffic.
    """
    if usage.cache_write_1h > usage.cache_write_5m:
        conv.write_ttl = "1h"
    elif usage.cache_write_5m > 0:
        conv.write_ttl = "5m"
    return price.write_1h if conv.write_ttl == "1h" else price.write_5m


def _empty_totals() -> dict[str, Any]:
    return {
        "requests": 0,
        "errors": 0,
        "passthrough": 0,
        "unpriced": 0,
        "input_tokens": 0,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "removed_chars_new": 0,
        "removed_chars_replayed": 0,
        "removed_tokens_est": 0,
        "saved_usd_est": 0.0,
        "stubs_new": 0,
        "cache_misses": 0,
    }


class ClaudeStats:
    def __init__(self, persist_path: str | Path | None = None, history_limit: int = 500):
        self._lock = threading.Lock()
        self.persist_path = Path(persist_path).expanduser().resolve() if persist_path else None
        self.first_started_at = time.time()
        self.started_at = time.time()
        self.totals = _empty_totals()
        self.by_model: dict[str, dict[str, Any]] = {}
        self.recent: deque[ClaudeEvent] = deque(maxlen=history_limit)
        self.conversations: dict[str, ConvState] = {}
        if self.persist_path and self.persist_path.exists():
            self._load()

    # -- recording -----------------------------------------------------------

    def record_passthrough(self, *, path: str, status: int) -> None:
        with self._lock:
            self.totals["passthrough"] += 1
            self._persist_unlocked()

    def record(
        self,
        *,
        conversation: str,
        path: str,
        status: int,
        streamed: bool,
        duration_ms: int,
        chars_in: int,
        chars_out: int,
        usage: Usage,
        removed_chars_new: int,
        removed_chars_replayed: int,
        stubs_new: int,
        notes: list[str],
        dry_run: bool,
    ) -> ClaudeEvent:
        with self._lock:
            conv = self.conversations.setdefault(conversation, ConvState())
            prompt = usage.prompt_tokens

            # Measure chars/token on this response; fall back to the last
            # measurement for this conversation, then the default.
            if usage.found and prompt > 0 and chars_out > 0:
                conv.chars_per_token = chars_out / prompt
            cpt = conv.chars_per_token or DEFAULT_CHARS_PER_TOKEN

            # A cache miss: the conversation had a previous request and this
            # one read back less than half of what that request's prompt was.
            cache_miss = bool(
                usage.found
                and conv.requests > 0
                and conv.last_prompt_tokens > 0
                and usage.cache_read < conv.last_prompt_tokens // 2
            )

            removed_chars = removed_chars_new + removed_chars_replayed
            removed_tokens = int(round(removed_chars / cpt)) if removed_chars else 0
            price = price_for(usage.model)
            saved: float | None = None
            if price is not None:
                # New stubs: the duplicate would have been written to cache
                # this turn. Replayed stubs: it would have been read back from
                # cache. Both are what the API would have billed.
                new_tok = removed_chars_new / cpt
                rep_tok = removed_chars_replayed / cpt
                write = _write_rate(price, usage, conv)
                saved = (new_tok * write + rep_tok * price.cache_read) / 1_000_000
                if not usage.found:
                    saved = None

            cost = usage.cost_usd() if usage.found else None
            ev = ClaudeEvent(
                ts=time.time(),
                conversation=conversation,
                model=usage.model or "unknown",
                path=path,
                status=status,
                streamed=streamed,
                duration_ms=duration_ms,
                chars_in=chars_in,
                chars_out=chars_out,
                input_tokens=usage.input_tokens,
                cache_read=usage.cache_read,
                cache_write_5m=usage.cache_write_5m,
                cache_write_1h=usage.cache_write_1h,
                output_tokens=usage.output_tokens,
                cost_usd=cost,
                removed_chars_new=removed_chars_new,
                removed_chars_replayed=removed_chars_replayed,
                removed_tokens_est=removed_tokens,
                saved_usd_est=saved,
                cache_miss=cache_miss,
                chars_per_token=round(cpt, 2),
                stop_reason=usage.stop_reason,
                error=usage.error,
                notes=list(notes),
                dry_run=dry_run,
            )

            t = self.totals
            t["requests"] += 1
            if status >= 400 or usage.error:
                t["errors"] += 1
            t["input_tokens"] += usage.input_tokens
            t["cache_read"] += usage.cache_read
            t["cache_write_5m"] += usage.cache_write_5m
            t["cache_write_1h"] += usage.cache_write_1h
            t["output_tokens"] += usage.output_tokens
            if cost is not None:
                t["cost_usd"] += cost
            elif usage.found:
                t["unpriced"] += 1
            t["removed_chars_new"] += removed_chars_new
            t["removed_chars_replayed"] += removed_chars_replayed
            t["removed_tokens_est"] += removed_tokens
            if saved is not None:
                t["saved_usd_est"] += saved
            t["stubs_new"] += stubs_new
            if cache_miss:
                t["cache_misses"] += 1

            m = self.by_model.setdefault(
                ev.model,
                {
                    "requests": 0,
                    "input_tokens": 0,
                    "cache_read": 0,
                    "cache_write": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "saved_usd_est": 0.0,
                    "priced": price is not None,
                },
            )
            m["requests"] += 1
            m["input_tokens"] += usage.input_tokens
            m["cache_read"] += usage.cache_read
            m["cache_write"] += usage.cache_write_5m + usage.cache_write_1h
            m["output_tokens"] += usage.output_tokens
            if cost is not None:
                m["cost_usd"] += cost
            if saved is not None:
                m["saved_usd_est"] += saved

            if usage.found:
                conv.last_prompt_tokens = prompt
            conv.requests += 1
            conv.last_ts = ev.ts
            self._prune_conversations_unlocked()
            self.recent.appendleft(ev)
            self._persist_unlocked()
            return ev

    # -- reading -------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            t = dict(self.totals)
            prompt_total = t["input_tokens"] + t["cache_read"] + t["cache_write_5m"] + t["cache_write_1h"]
            hit = (100.0 * t["cache_read"] / prompt_total) if prompt_total else 0.0
            recent = [asdict(e) | {"prompt_tokens": e.prompt_tokens} for e in list(self.recent)[:80]]
            convs = sorted(self.conversations.items(), key=lambda kv: -kv[1].last_ts)[:20]
            return {
                "now": time.time(),
                "started_at": self.started_at,
                "first_started_at": self.first_started_at,
                "totals": t,
                "prompt_tokens": prompt_total,
                "cache_hit_pct": round(hit, 1),
                "by_model": self.by_model,
                "recent": recent,
                "conversations": [
                    {
                        "id": k,
                        "requests": v.requests,
                        "last_prompt_tokens": v.last_prompt_tokens,
                        "chars_per_token": round(v.chars_per_token, 2) if v.chars_per_token else None,
                        "last_ts": v.last_ts,
                    }
                    for k, v in convs
                ],
                "persist_path": str(self.persist_path) if self.persist_path else None,
            }

    def reset(self) -> None:
        with self._lock:
            self.totals = _empty_totals()
            self.by_model.clear()
            self.recent.clear()
            self.conversations.clear()
            self.first_started_at = self.started_at = time.time()
            self._persist_unlocked()

    # -- persistence ---------------------------------------------------------

    def _prune_conversations_unlocked(self) -> None:
        cutoff = time.time() - _CONV_RETENTION_S
        for k in [k for k, v in self.conversations.items() if v.last_ts < cutoff]:
            del self.conversations[k]

    def _persist_unlocked(self) -> None:
        if not self.persist_path:
            return
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "first_started_at": self.first_started_at,
                "totals": self.totals,
                "by_model": self.by_model,
                "recent": [asdict(e) for e in list(self.recent)[:_RECENT_PERSIST]],
                "conversations": {k: asdict(v) for k, v in self.conversations.items()},
            }
            tmp = self.persist_path.with_suffix(self.persist_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, self.persist_path)
        except OSError as e:
            log.warning("claude stats persist failed (%s): %s", self.persist_path, e)

    def _load(self) -> None:
        assert self.persist_path is not None
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("claude stats load failed (%s): %s", self.persist_path, e)
            return
        try:
            self.first_started_at = float(data.get("first_started_at") or self.first_started_at)
            for k, v in (data.get("totals") or {}).items():
                if k in self.totals:
                    self.totals[k] = type(self.totals[k])(v)
            for k, v in (data.get("by_model") or {}).items():
                if isinstance(v, dict):
                    self.by_model[str(k)] = v
            restored = []
            for item in data.get("recent") or []:
                try:
                    restored.append(ClaudeEvent(**item))
                except TypeError:
                    continue
            for ev in reversed(restored):
                self.recent.appendleft(ev)
            for k, v in (data.get("conversations") or {}).items():
                if isinstance(v, dict):
                    self.conversations[str(k)] = ConvState(**v)
            self._prune_conversations_unlocked()
        except (TypeError, ValueError) as e:
            log.warning("claude stats partially restored: %s", e)


_STORE: ClaudeStats | None = None
_STORE_LOCK = threading.Lock()


def init_claude_store(persist_path: str | Path | None) -> ClaudeStats:
    global _STORE
    with _STORE_LOCK:
        _STORE = ClaudeStats(persist_path=persist_path)
        return _STORE


def get_claude_store() -> ClaudeStats | None:
    return _STORE
