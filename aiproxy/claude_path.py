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
import threading
import time
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from .claude_stats import ClaudeEvent, ClaudeStats, init_claude_store
from .claude_strip import ClaudeStripResult, DecisionState, drop_tools, serialize, strip_claude
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
    # For the keep-warm: the request as it went upstream, with its headers.
    # Held in memory until the reply is booked and then, if the conversation
    # is kept warm, in the warmer's state. Written nowhere.
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    sent: bytes = b""

    def remember(self, url: str, headers: Any, sent: bytes) -> None:
        self.url = url
        self.headers = {str(k): str(v) for k, v in dict(headers).items()}
        self.sent = sent


# Headers that belong to one hop and are set afresh for the refresh.
_HOP_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "accept-encoding", "keep-alive",
                "proxy-connection", "proxy-authorization"}


def _post_direct(url: str, headers: dict[str, str], payload: bytes, timeout: float = 600.0) -> tuple[int, str, bytes]:
    """POST without any system proxy: in mitm mode HTTPS_PROXY points at this
    very process, and a refresh that went through it would be booked twice."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("content-type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("content-type", "") if exc.headers else "", exc.read()


class KeepWarm:
    """Replays a conversation's last request just before its 1-hour cache
    entry expires, asking for no output (max_tokens 0, stream off): the API
    runs prefill, resets the entry's timer and bills a cache read. Without
    it, the first message after a pause of over an hour rewrites the whole
    context at the write rate.

    1-hour entries only. Measured on one user's five days: 1,052 of 1,125
    refreshes were 5-minute ones, and a pause of 5 minutes to an hour with no
    refresh came back to a cache read anyway, because Claude Code writes
    1-hour entries. The 1-hour refreshes were the ones that paid.

    The stored bodies are whole conversations with their headers. They live
    here and nowhere else: never logged, never persisted.
    """

    MAX_CONVERSATIONS = 8

    def __init__(self, cfg: Any, stats: ClaudeStats, post: Callable[..., tuple[int, str, bytes]] = _post_direct):
        self.cfg = cfg
        self.stats = stats
        self._post = post
        self._lock = threading.Lock()
        self._state: dict[str, dict[str, Any]] = {}

    def planned(self) -> int:
        with self._lock:
            return len(self._state)

    def plan(self, conversation: str, url: str, headers: dict[str, str], sent: bytes, *,
             ttl: str, started_at: float) -> bool:
        """After a real request: plan a refresh for just before its entry
        would expire. A later real request supersedes it (the sequence number
        moves on); a refresh that finds the conversation quiet re-plans itself
        up to keep_warm_limit times, then lets the entry go."""
        if not self.cfg.keep_cache_warm or self.cfg.dry_run or ttl != "1h" or not url or not sent:
            return False
        if self.cfg.keep_warm_limit <= 0:
            return False
        with self._lock:
            state = self._state.setdefault(conversation, {"seq": 0})
            state["seq"] += 1
            # The hour runs from when the request STARTED (the prefill), not
            # from when its reply finished streaming.
            state.update({"url": url, "headers": dict(headers), "sent": sent, "refreshes": 0,
                          "last": started_at or time.time()})
            if len(self._state) > self.MAX_CONVERSATIONS:
                # Evict the conversation with the FEWEST real requests: under
                # a fan-out the parent's last request is the oldest, and
                # evicting by age threw out the one worth keeping warm.
                victim = min(self._state, key=lambda k: (
                    self.stats.conversations.get(k).requests if k in self.stats.conversations else 0,
                    self._state[k].get("last", 0)))
                if victim != conversation:
                    del self._state[victim]
            seq = state["seq"]
            delay = max(1.0, self.cfg.keep_warm_after_seconds - (time.time() - float(state["last"])))
            self._arm(conversation, seq, delay)
        log.info("claude %s: keep-alive planned in %ds", conversation, int(delay))
        return True

    def _arm(self, conversation: str, seq: int, delay: float) -> None:
        timer = threading.Timer(delay, self._fire, args=(conversation, seq))
        timer.daemon = True
        timer.start()

    def _fire(self, conversation: str, seq: int) -> None:
        with self._lock:
            state = self._state.get(conversation)
            if state is None or state["seq"] != seq:
                return  # a real request came through since; its own refresh is planned
            if not self.cfg.keep_cache_warm or state["refreshes"] >= self.cfg.keep_warm_limit:
                self._state.pop(conversation, None)
                return
            url, headers, sent = state["url"], dict(state["headers"]), state["sent"]
        try:
            body = json.loads(sent.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            with self._lock:
                self._state.pop(conversation, None)
            return
        body["max_tokens"] = 0
        body["stream"] = False
        payload = serialize(body)
        headers = {k: v for k, v in headers.items() if k.lower() not in _HOP_HEADERS}
        headers["content-length"] = str(len(payload))
        started = time.perf_counter()
        try:
            status, content_type, data = self._post(url, headers, payload)
        except (urllib.error.URLError, OSError) as exc:
            log.warning("claude %s: keep-alive failed: %s", conversation, exc)
            self.stats.count_keep_alive_failure()
            with self._lock:
                self._state.pop(conversation, None)
            return
        usage = parse_response(data, content_type)
        elapsed = int((time.perf_counter() - started) * 1000)
        ev = self.stats.record_keep_alive(conversation=conversation, usage=usage, status=status,
                                          duration_ms=elapsed)
        log.info("claude %s: keep-alive status=%s cached=%d written=%d cost=%s %dms%s", conversation, status,
                 ev.cache_read, ev.cache_write_5m + ev.cache_write_1h,
                 f"${ev.cost_usd:.4f}" if ev.cost_usd is not None else "unpriced", elapsed,
                 f" error={ev.error}" if ev.error else "")
        with self._lock:
            state = self._state.get(conversation)
            if state is None or state["seq"] != seq:
                return
            if status != 200 or usage.error:
                # Whatever the API objected to, it will object to again.
                self._state.pop(conversation, None)
                return
            state["refreshes"] += 1
            state["last"] = time.time()
            self._arm(conversation, seq, max(1.0, float(self.cfg.keep_warm_after_seconds)))


class ClaudePath:
    def __init__(self, config: Any):  # noqa: ANN401 - aiproxy.config.Config
        self.cfg = config.claude
        self.state = DecisionState(self.cfg.state_path, self.cfg.state_max_entries)
        self.stats: ClaudeStats = init_claude_store(self.cfg.stats_path)
        self.warmer = KeepWarm(self.cfg, self.stats)

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
        if cfg.drop_tool_prefixes and isinstance(result.body, dict):
            # On a copy when the dedupe made none: `body` is what the
            # dashboard's request row is sized from.
            target = result.body if result.changed else deepcopy(body)
            dropped, dropped_chars = drop_tools(target, cfg.drop_tool_prefixes)
            if dropped:
                result.tools_dropped, result.tools_dropped_chars = dropped, dropped_chars
                result.notes.append(f"left out {dropped} tool definition(s) (~{dropped_chars:,} chars)")
                if cfg.dry_run:
                    if "dry-run: body forwarded unchanged" not in result.notes:
                        result.notes.append("dry-run: body forwarded unchanged")
                else:
                    result.body = target
                    result.changed = True
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
        ev = self.stats.record(
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
            tools_dropped=r.tools_dropped if r else 0,
            tools_dropped_chars=r.tools_dropped_chars if r else 0,
            tools_sent=r.tools_sent if r else None,
        )
        conv = self.stats.conversations.get(r.conversation) if r else None
        if (r is not None and status == 200 and usage.found and usage.prompt_tokens >= 1024
                and conv is not None and conv.requests >= self.cfg.keep_warm_min_requests):
            self.warmer.plan(r.conversation, prep.url, prep.headers, prep.sent,
                             ttl=conv.write_ttl, started_at=prep.started)
        return ev


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
