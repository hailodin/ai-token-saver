"""Claude Code's requests, end to end: the one path that must not use stripper.py.

stripper.py is built for Cursor and OpenAI bodies. It keeps the last N
messages, shortens the system prompt and drops thinking blocks. Claude Code
depends on its prompt cache and, on the current models, on every earlier turn
arriving exactly as it was first sent: each of those edits turns a cache read
into a full re-write, and editing an earlier turn can be refused outright
(CLAUDE-CODE-NOTES.md). Measured on a 23-message Claude Code request, the
stripper dropped 7 messages, every thinking block, and 62% of the system
prompt along with its cache marker.

So a POST to Anthropic's /v1/messages comes here instead: claude_strip.py
makes the one lossless edit (a duplicate tool result in the newest message
becomes a pointer to the earlier copy), and the response's own usage numbers
are booked in claude_stats.py. Everything else goes to Anthropic untouched.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any

from .claude_stats import ClaudeEvent, ClaudeStats, init_claude_store
from .claude_strip import ClaudeStripResult, DecisionState, serialize, strip_claude
from .claude_usage import parse_response

log = logging.getLogger("aiproxy.claude")

ANTHROPIC_HOST = "api.anthropic.com"


def is_messages_request(method: str, path: str) -> bool:
    """POST /v1/messages, with or without a query string (Claude Code sends
    ?beta=true). Not /v1/messages/count_tokens: that only counts, and is
    forwarded untouched like every other Anthropic path."""
    p = (path or "").split("?", 1)[0].rstrip("/")
    if not p.startswith("/"):
        p = "/" + p
    return method.upper() == "POST" and p == "/v1/messages"


class ResponseTap:
    """Keeps enough of a response to read its usage numbers at the end.

    A stream's usage sits in its first event (message_start) and its last
    ones (message_delta), so past the limit the middle is dropped and the
    head and tail kept. A non-streamed reply is one JSON object and is kept
    whole; replies that size are far below the limit.
    """

    def __init__(self, limit: int = 4 * 1024 * 1024):
        self.half = limit // 2
        self.head = bytearray()
        self.tail = bytearray()
        self.total = 0

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        self.total += len(chunk)
        room = self.half - len(self.head)
        if room > 0:
            self.head += chunk[:room]
            chunk = chunk[room:]
        if chunk:
            self.tail += chunk
            if len(self.tail) > self.half:
                del self.tail[: len(self.tail) - self.half]

    def data(self) -> bytes:
        if not self.tail:
            return bytes(self.head)
        # A blank line between the halves, so a cut event stays one bad event
        # (skipped by the parser) instead of gluing itself to its neighbour.
        return bytes(self.head) + b"\n\n" + bytes(self.tail)


@dataclass
class Prepared:
    """What happened to one request on its way out, for booking the reply."""

    result: ClaudeStripResult | None
    chars_in: int
    chars_out: int
    dry_run: bool
    started: float = field(default_factory=time.time)


class ClaudePath:
    def __init__(self, config: Any):  # noqa: ANN401 - aiproxy.config.Config
        self.cfg = config.claude
        self.state = DecisionState(self.cfg.state_path, self.cfg.state_max_entries)
        self.stats: ClaudeStats = init_claude_store(self.cfg.stats_path)

    def prepare(self, raw: bytes, *, dry_run: bool) -> tuple[bytes, Prepared]:
        """The body to send upstream, and what to remember until the reply."""
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw, Prepared(None, len(raw), len(raw), dry_run)
        if not self.cfg.enabled:
            return raw, Prepared(None, len(raw), len(raw), dry_run)
        cfg = replace(self.cfg, dry_run=self.cfg.dry_run or dry_run)
        result = strip_claude(body, cfg, self.state)
        out = serialize(result.body) if result.changed else raw
        if result.notes and result.notes != ["not a messages request"]:
            log.info("claude %s: %s", result.conversation, "; ".join(result.notes))
        return out, Prepared(result, len(raw), len(out), cfg.dry_run)

    def finish(
        self,
        prep: Prepared,
        *,
        path: str,
        status: int,
        content_type: str,
        response: bytes,
    ) -> ClaudeEvent:
        usage = parse_response(response, content_type)
        if status >= 400 and not usage.error:
            usage.error = f"HTTP {status}"
        r = prep.result
        return self.stats.record(
            conversation=r.conversation if r else "",
            path=path,
            status=status,
            streamed="text/event-stream" in (content_type or "").lower(),
            duration_ms=int((time.time() - prep.started) * 1000),
            chars_in=prep.chars_in,
            chars_out=prep.chars_out,
            usage=usage,
            removed_chars_new=r.removed_chars_new if r else 0,
            removed_chars_replayed=r.removed_chars_replayed if r else 0,
            stubs_new=r.stubs_new if r else 0,
            notes=r.notes if r else [],
            dry_run=prep.dry_run,
        )


def record_request(store, host: str, path: str, raw: bytes, sent: bytes, prep: Prepared, model: str) -> None:  # noqa: ANN001
    """Count the request on the main dashboard too, the way other traffic is.

    Token counts there are tiktoken estimates, as for every other request; the
    Claude Code card shows the API's own numbers.
    """
    from .stripper import estimate_tokens

    r = prep.result
    before = raw.decode("utf-8", errors="ignore")
    tokens_in = estimate_tokens(before)
    chars_in = len(before)
    chars_out, tokens_out = chars_in, tokens_in
    # In a dry run nothing is sent changed, but the would-be saving is shown,
    # as the main dashboard does for every other kind of request.
    would_change = bool(r and (r.stubs_new or r.stubs_replayed))
    if r is not None and r.changed:
        after = sent.decode("utf-8", errors="ignore")
        chars_out, tokens_out = len(after), estimate_tokens(after)
    elif would_change and r is not None:
        removed = r.removed_chars_new + r.removed_chars_replayed
        chars_out = max(0, chars_in - removed)
        tokens_out = int(tokens_in * chars_out / chars_in) if chars_in else 0
    store.record(
        host=host,
        path=path,
        chars_in=chars_in,
        chars_out=chars_out,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        stripped=would_change,
        notes=["claude-code", *(r.notes if r else [])],
        dry_run=prep.dry_run,
        model=model,
    )
