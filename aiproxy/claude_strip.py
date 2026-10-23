"""Claude Code request rewriting that is safe under prompt caching and preserved thinking.

Why this file exists instead of reusing stripper.py
---------------------------------------------------
Claude Code sends the *whole* conversation on every request and relies on
prompt caching: the unchanged prefix (tools, system, every earlier message) is
billed at 0.1x or less. Two consequences shape everything here:

1. Any change to an earlier message is a cache miss from that point on, and on
   Claude Opus 5.5 / Sonnet 5.5 / Fable 5.1 it is also an *edit of history*
   that invalidates every later thinking block - on accounts enforced for
   preserved thinking the API answers with a 400. So history is never edited.
   Not truncated, not compacted, not reordered. Only the newest user message -
   the one nothing has reasoned about yet - may be changed.

2. Whatever we send once must be sent identically forever after, because the
   model's next thinking block binds to the conversation *as it was sent*. So
   every rewrite is a stored decision keyed by tool_use_id and replayed on
   every later request, byte for byte.

What is actually rewritten
--------------------------
Exactly one thing: a tool_result in the newest message whose content is
byte-identical to a tool_result already in the conversation becomes a short
stub pointing at the earlier copy. This is lossless (the model still has the
content, once), and the saving is real money: the duplicate would have been
billed at full input price, then written to cache (1.25x), then read back on
every later turn.

Everything else - system, tools, metadata, cache_control markers, thinking
blocks, assistant turns, images, non-duplicate results - passes through
untouched. The old stripper.py flattened multi-block messages, which dropped
tool_result blocks and produced 400s; this module never changes the block
structure of a message, only the `content` of a block it has decided to stub.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("aiproxy.claude")

STUB_TEXT = (
    "[token saver] This result is byte-identical to the result of tool call "
    "{ref} earlier in this conversation ({chars} characters). Refer to that one."
)

@dataclass
class ClaudeConfig:
    enabled: bool = True
    dedupe_tool_results: bool = True
    # A stub is ~150 chars; stubbing anything smaller than this saves nothing.
    dedupe_min_chars: int = 300
    dry_run: bool = False
    state_path: str = "logs/claude_state.json"
    # What Claude Code actually spent, from the API's usage numbers.
    stats_path: str = "logs/claude_stats.json"
    # Decisions are kept this long after their last use. A Claude Code session
    # rarely lives longer than a day; the cap just keeps the file bounded.
    state_max_entries: int = 20000


@dataclass
class StubRecord:
    """One stored decision: tool_use_id -> stub pointing at ref."""

    ref: str
    chars: int
    conv: str
    ts: float


@dataclass
class ClaudeStripResult:
    body: Any
    changed: bool
    notes: list[str] = field(default_factory=list)
    # Chars removed by stubs created on this request (content the model has
    # never seen in this position: would have been billed at full price).
    removed_chars_new: int = 0
    # Chars removed by stubs replayed from earlier requests (would have been
    # a cache read).
    removed_chars_replayed: int = 0
    stubs_new: int = 0
    stubs_replayed: int = 0
    conversation: str = ""


class DecisionState:
    """Persisted tool_use_id -> stub decisions, shared by every request.

    Persisted so a proxy restart mid-conversation does not change what the
    model sees: a stub that was sent once must be sent on every later request.
    """

    def __init__(self, path: str | Path | None, max_entries: int = 20000):
        self._lock = threading.Lock()
        self.path = Path(path).expanduser().resolve() if path else None
        self.max_entries = max_entries
        self.stubs: dict[str, StubRecord] = {}
        if self.path and self.path.exists():
            self._load()

    def get(self, tool_use_id: str) -> StubRecord | None:
        with self._lock:
            rec = self.stubs.get(tool_use_id)
            if rec is not None:
                rec.ts = time.time()
            return rec

    def put(self, tool_use_id: str, rec: StubRecord) -> None:
        with self._lock:
            self.stubs[tool_use_id] = rec
            if len(self.stubs) > self.max_entries:
                # Drop least recently used; never drop anything used in the
                # last hour - a live conversation must keep its decisions.
                cutoff = time.time() - 3600
                victims = sorted(
                    (k for k, r in self.stubs.items() if r.ts < cutoff),
                    key=lambda k: self.stubs[k].ts,
                )
                for k in victims[: len(self.stubs) - self.max_entries]:
                    del self.stubs[k]
            self._persist_unlocked()

    def __len__(self) -> int:
        with self._lock:
            return len(self.stubs)

    def _persist_unlocked(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "stubs": {
                    k: {"ref": r.ref, "chars": r.chars, "conv": r.conv, "ts": r.ts}
                    for k, r in self.stubs.items()
                },
            }
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("claude state persist failed (%s): %s", self.path, e)

    def _load(self) -> None:
        assert self.path is not None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in (data.get("stubs") or {}).items():
                self.stubs[str(k)] = StubRecord(
                    ref=str(v["ref"]),
                    chars=int(v.get("chars", 0)),
                    conv=str(v.get("conv", "")),
                    ts=float(v.get("ts", 0)),
                )
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning("claude state load failed (%s): %s", self.path, e)


# ---------------------------------------------------------------------------


def _without_cache_control(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_cache_control(v) for k, v in value.items() if k != "cache_control"}
    if isinstance(value, list):
        return [_without_cache_control(v) for v in value]
    return value


def conversation_key(body: dict[str, Any]) -> str:
    """A stable id for 'this conversation' across its requests.

    The system prompt plus the first message: Claude Code keeps both
    byte-identical for the life of a conversation, because its prompt cache
    depends on it. The session id in metadata.user_id is not used - one
    session sends the main conversation and every sub-agent's under the same
    id, and lumping them together made each small sub-agent request look like
    a cache miss of the main one. cache_control markers are left out of the
    hash because Claude Code moves them forward as a conversation grows.
    """
    h = hashlib.sha1()
    sys_val = _without_cache_control(body.get("system"))
    h.update(json.dumps(sys_val, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    msgs = body.get("messages")
    if isinstance(msgs, list) and msgs:
        first = _without_cache_control(msgs[0])
        h.update(json.dumps(first, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return "conv_" + h.hexdigest()[:16]


def _content_hash(content: Any) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _content_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        n = 0
        for b in content:
            if isinstance(b, dict) and isinstance(b.get("text"), str):
                n += len(b["text"])
            elif isinstance(b, str):
                n += len(b)
        return n
    return 0


def _is_text_only(content: Any) -> bool:
    """Only text results are stubbed; an image or document is never a duplicate
    we can safely describe in words."""
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return all(
            isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
            for b in content
        )
    return False


def _tool_results(message: Any):
    """Yield (block_index, block) for every tool_result block in a user message."""
    if not isinstance(message, dict) or message.get("role") != "user":
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for i, block in enumerate(content):
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tid = block.get("tool_use_id")
            if isinstance(tid, str) and tid:
                yield i, block


def strip_claude(body: Any, cfg: ClaudeConfig, state: DecisionState) -> ClaudeStripResult:
    """Apply stored stub decisions, then make new ones for the newest message."""
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return ClaudeStripResult(body=body, changed=False, notes=["not a messages request"])

    messages = body["messages"]
    conv = conversation_key(body)
    result = ClaudeStripResult(body=body, changed=False, conversation=conv)
    last_idx = len(messages) - 1

    # (message index, block index) -> stub text to apply
    edits: dict[tuple[int, int], str] = {}
    # content hash -> tool_use_id of the first *kept* (unstubbed) occurrence
    seen: dict[str, str] = {}

    for mi, msg in enumerate(messages):
        for bi, block in _tool_results(msg):
            tid = block["tool_use_id"]
            content = block.get("content")

            rec = state.get(tid)
            if rec is not None:
                # Already stubbed on an earlier request: replay identically.
                # If the client already sends the stub (it echoes what it
                # got back from us? no - it sends its own copy), rewrite anyway.
                edits[(mi, bi)] = STUB_TEXT.format(ref=rec.ref, chars=rec.chars)
                result.removed_chars_replayed += rec.chars
                result.stubs_replayed += 1
                continue

            if not _is_text_only(content):
                continue
            h = _content_hash(content)
            chars = _content_chars(content)

            if mi == last_idx and cfg.dedupe_tool_results and chars >= cfg.dedupe_min_chars:
                ref = seen.get(h)
                if ref is not None and ref != tid:
                    stub = STUB_TEXT.format(ref=ref, chars=chars)
                    edits[(mi, bi)] = stub
                    result.removed_chars_new += chars - len(stub)
                    result.stubs_new += 1
                    if not cfg.dry_run:
                        state.put(tid, StubRecord(ref=ref, chars=chars, conv=conv, ts=time.time()))
                    continue

            # Kept: it is the copy later duplicates will point at.
            seen.setdefault(h, tid)

    if not edits:
        return result

    if result.stubs_new:
        result.notes.append(f"stubbed {result.stubs_new} duplicate tool result(s)")
    if result.stubs_replayed:
        result.notes.append(f"replayed {result.stubs_replayed} earlier stub(s)")

    if cfg.dry_run:
        result.notes.append("dry-run: body forwarded unchanged")
        return result

    out = deepcopy(body)
    for (mi, bi), stub in edits.items():
        block = out["messages"][mi]["content"][bi]
        # Only `content` changes. tool_use_id, is_error and cache_control stay.
        block["content"] = stub
    result.body = out
    result.changed = True
    return result


def serialize(body: Any) -> bytes:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
