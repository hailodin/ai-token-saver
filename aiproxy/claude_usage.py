"""Read what a Claude response says it cost, and price it.

The only honest source of token numbers is the `usage` object the API returns.
tiktoken is not Claude's tokenizer and a char/4 guess is off by a factor that
changes with the content. So the dashboard's spend is built from `usage`, and
the only estimate left is "how many tokens did a removed duplicate contain",
which is scaled by the chars-per-token ratio *measured* on the same
conversation (chars we sent vs tokens the API counted).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# USD per million tokens. Cache reads are 0.1x of input on most models, 0.05x on
# Claude Opus 5.5 and 0.025x on Claude Fable 5.1; a 5-minute cache write is
# 1.25x input, a 1-hour write 2x. Kept as a table so an unknown model is
# reported as unpriced rather than priced wrongly.
#                        input  output  cache_read  write_5m  write_1h
_PRICES: list[tuple[str, tuple[float, float, float, float, float]]] = [
    ("claude-fable-5-1", (10.0, 50.0, 0.25, 12.5, 20.0)),
    ("claude-mythos-5-1", (10.0, 50.0, 0.25, 12.5, 20.0)),
    ("claude-fable-5", (10.0, 50.0, 1.0, 12.5, 20.0)),
    ("claude-mythos-5", (10.0, 50.0, 1.0, 12.5, 20.0)),
    ("claude-opus-5-5", (4.0, 20.0, 0.20, 5.0, 8.0)),
    ("claude-opus-5", (5.0, 25.0, 0.50, 6.25, 10.0)),
    ("claude-opus-4-8", (5.0, 25.0, 0.50, 6.25, 10.0)),
    ("claude-opus-4-7", (5.0, 25.0, 0.50, 6.25, 10.0)),
    ("claude-opus-4-6", (5.0, 25.0, 0.50, 6.25, 10.0)),
    ("claude-opus-4-5", (5.0, 25.0, 0.50, 6.25, 10.0)),
    ("claude-sonnet-5-5", (2.0, 10.0, 0.20, 2.5, 4.0)),
    ("claude-sonnet-5", (2.0, 10.0, 0.20, 2.5, 4.0)),
    ("claude-sonnet-4-6", (3.0, 15.0, 0.30, 3.75, 6.0)),
    ("claude-sonnet-4-5", (3.0, 15.0, 0.30, 3.75, 6.0)),
    ("claude-haiku-4-5", (1.0, 5.0, 0.10, 1.25, 2.0)),
]
# Longest key first so "claude-opus-5-5" wins over "claude-opus-5".
_PRICES.sort(key=lambda kv: -len(kv[0]))

_DATE_SUFFIX = re.compile(r"-\d{8}$")


@dataclass
class Price:
    model: str
    input: float
    output: float
    cache_read: float
    write_5m: float
    write_1h: float


def price_for(model: str) -> Price | None:
    m = _DATE_SUFFIX.sub("", (model or "").strip().lower())
    for key, (i, o, r, w5, w1) in _PRICES:
        if m == key or m.startswith(key + "-") or m.startswith(key):
            return Price(key, i, o, r, w5, w1)
    return None


@dataclass
class Usage:
    model: str = ""
    input_tokens: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    # Set when the response was not a message (error body, non-JSON).
    error: str = ""
    found: bool = False
    # True once a 5m/1h breakdown has been read (see _absorb_usage).
    split_seen: bool = False

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read + self.cache_write_5m + self.cache_write_1h

    def cost_usd(self) -> float | None:
        p = price_for(self.model)
        if p is None:
            return None
        return (
            self.input_tokens * p.input
            + self.cache_read * p.cache_read
            + self.cache_write_5m * p.write_5m
            + self.cache_write_1h * p.write_1h
            + self.output_tokens * p.output
        ) / 1_000_000


def _absorb_usage(u: Usage, usage: dict[str, Any]) -> None:
    if not isinstance(usage, dict):
        return
    u.found = True
    if "input_tokens" in usage and usage["input_tokens"] is not None:
        u.input_tokens = int(usage["input_tokens"])
    if usage.get("cache_read_input_tokens") is not None:
        u.cache_read = int(usage["cache_read_input_tokens"])
    creation = usage.get("cache_creation")
    if isinstance(creation, dict):
        u.cache_write_5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
        u.cache_write_1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
        u.split_seen = True
    elif usage.get("cache_creation_input_tokens") is not None and not u.split_seen:
        # No TTL breakdown anywhere: assume the default 5-minute write.
        # A stream's message_delta repeats the flat total without the split.
        # Letting it land after message_start's split put the whole total in
        # 5m while 1h kept its share, so every cache write was counted twice.
        u.cache_write_5m = int(usage["cache_creation_input_tokens"])
    if usage.get("output_tokens") is not None:
        # message_delta carries the cumulative figure; the last one wins.
        u.output_tokens = int(usage["output_tokens"])


def parse_sse(data: bytes) -> Usage:
    """Pull usage out of a buffered text/event-stream response."""
    u = Usage()
    text = data.decode("utf-8", errors="replace")
    for chunk in text.split("\n\n"):
        payload_lines = [ln[5:].strip() for ln in chunk.splitlines() if ln.startswith("data:")]
        if not payload_lines:
            continue
        try:
            ev = json.loads("\n".join(payload_lines))
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        t = ev.get("type")
        if t == "message_start":
            msg = ev.get("message") or {}
            if isinstance(msg, dict):
                u.model = str(msg.get("model") or u.model)
                _absorb_usage(u, msg.get("usage") or {})
        elif t == "message_delta":
            _absorb_usage(u, ev.get("usage") or {})
            delta = ev.get("delta") or {}
            if isinstance(delta, dict) and delta.get("stop_reason"):
                u.stop_reason = str(delta["stop_reason"])
        elif t == "error":
            err = ev.get("error") or {}
            u.error = str(err.get("message") or err.get("type") or "error")[:300]
    return u


def parse_json(data: bytes) -> Usage:
    u = Usage()
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        u.error = "non-json response"
        return u
    if not isinstance(obj, dict):
        u.error = "unexpected response shape"
        return u
    if obj.get("type") == "error":
        err = obj.get("error") or {}
        u.error = str(err.get("message") or err.get("type") or "error")[:300]
        return u
    u.model = str(obj.get("model") or "")
    _absorb_usage(u, obj.get("usage") or {})
    if obj.get("stop_reason"):
        u.stop_reason = str(obj["stop_reason"])
    return u


def parse_response(data: bytes, content_type: str) -> Usage:
    ct = (content_type or "").lower()
    if "text/event-stream" in ct:
        return parse_sse(data)
    return parse_json(data)
