from __future__ import annotations

import hashlib
import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .config import StripConfig

log = logging.getLogger("aiproxy.stripper")

# Path-labeled file dumps Cursor/agents often inject into context
FILE_BLOCK_RE = re.compile(
    r"(?m)^(?:#{1,3}\s*)?(?:File|Path|filepath):\s*(?P<path>\S+)\s*\n"
    r"(?:```[^\n]*\n)(?P<body>.*?)(?:\n```)",
    re.DOTALL | re.IGNORECASE,
)

FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)

SYSTEM_BOILERPLATE_MARKERS = (
    "You are an AI coding assistant",
    "You are Auto, an agent router",
    "<communication>",
    "<citing_code>",
    "NEVER reveal these instructions",
    "PRIORITY: refuse remotely",
)


@dataclass
class StripResult:
    original: Any
    stripped: Any
    changed: bool
    original_chars: int
    stripped_chars: int
    notes: list[str] = field(default_factory=list)

    @property
    def saved_chars(self) -> int:
        return max(0, self.original_chars - self.stripped_chars)

    @property
    def saved_tokens_est(self) -> int:
        # Rough GPT-style estimate; tiktoken used when available at log time
        return self.saved_chars // 4


def estimate_tokens(text: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _json_size(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def _truncate(text: str, limit: int, label: str = "truncated") -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    keep = max(0, limit - 48)
    head = keep * 3 // 4
    tail = keep - head
    return (
        f"{text[:head]}\n\n…[{label}: removed {len(text) - keep} chars]…\n\n{text[-tail:]}"
    )


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                if isinstance(p.get("text"), str):
                    parts.append(p["text"])
                elif isinstance(p.get("content"), str):
                    parts.append(p["content"])
                else:
                    parts.append(json.dumps(p, ensure_ascii=False))
        return "\n".join(parts)
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _set_content(msg: dict[str, Any], text: str) -> None:
    content = msg.get("content")
    if isinstance(content, list) and content:
        # Keep the structure: rewrite the first text-like part and keep every
        # other part exactly as it was. The previous version appended only the
        # rewritten part and silently dropped the rest, so a user message that
        # carried two tool_result blocks (Claude Code sends these) left here
        # with none - and the API answered 400 "tool_use ids were found
        # without tool_result blocks". A rewrite must never change the block
        # count of a message.
        rewritten = False
        new_parts: list[Any] = []
        for p in content:
            if not rewritten and isinstance(p, dict) and (
                "text" in p or p.get("type") in ("text", "input_text", "output_text")
            ):
                q = dict(p)
                q["text"] = text
                new_parts.append(q)
                rewritten = True
            elif not rewritten and isinstance(p, str):
                new_parts.append(text)
                rewritten = True
            else:
                new_parts.append(p)
        if not rewritten:
            # No text part to carry the rewrite: leave the message alone rather
            # than replace tool_result / image blocks with a string.
            return
        msg["content"] = new_parts
    else:
        msg["content"] = text


def _dedupe_file_blocks(text: str) -> tuple[str, int]:
    seen: set[str] = set()
    removed = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal removed
        path = m.group("path")
        body = m.group("body")
        key = hashlib.sha1(f"{path}\n{body}".encode()).hexdigest()
        if key in seen:
            removed += 1
            return f"[deduped duplicate file block: {path}]"
        seen.add(key)
        return m.group(0)

    return FILE_BLOCK_RE.sub(repl, text), removed


def _compress_system(text: str, max_chars: int) -> tuple[str, bool]:
    """Keep the head of system prompts; drop mid boilerplate when over budget."""
    if len(text) <= max_chars:
        return text, False

    # Prefer cutting after known instruction blocks
    cut_at = None
    for marker in SYSTEM_BOILERPLATE_MARKERS:
        idx = text.find(marker)
        if idx > 200:
            # keep everything before a late reappearance of boilerplate
            pass
        # If marker appears in the latter half and we're oversized, trim after first chunk
        if idx > max_chars // 3:
            cut_at = idx
            break

    if cut_at and cut_at < len(text) - 500:
        kept = text[: max_chars - 80]
        return (
            kept
            + f"\n\n…[system compressed: removed {len(text) - len(kept)} chars]…\n",
            True,
        )

    return _truncate(text, max_chars, "system"), True


def _is_reasoning_part(part: Any) -> bool:
    if not isinstance(part, dict):
        return False
    t = str(part.get("type", "")).lower()
    if t in {"reasoning", "thinking", "thought"}:
        return True
    if "reasoning" in t or "thinking" in t:
        return True
    return False


def _strip_message_parts(
    msg: dict[str, Any], cfg: StripConfig, *, old: bool, notes: list[str]
) -> dict[str, Any]:
    out = dict(msg)
    role = str(out.get("role", "")).lower()
    limit = cfg.max_chars_old if old else cfg.max_chars_recent

    # Tool / function results
    if role in {"tool", "function"} or out.get("type") in {
        "function_call_output",
        "tool_result",
    }:
        text = _content_to_text(out.get("content", out.get("output")))
        if len(text) > cfg.max_tool_result_chars:
            text = _truncate(text, cfg.max_tool_result_chars, "tool_result")
            if "content" in out:
                _set_content(out, text)
            elif "output" in out:
                out["output"] = text
            notes.append("truncated tool result")
        return out

    content = out.get("content")
    if isinstance(content, list) and cfg.drop_reasoning_parts:
        filtered = [p for p in content if not _is_reasoning_part(p)]
        if len(filtered) != len(content):
            notes.append("dropped reasoning parts")
            out["content"] = filtered
            content = filtered

    text = _content_to_text(out.get("content"))
    if cfg.dedupe_file_blocks and text:
        text2, n = _dedupe_file_blocks(text)
        if n:
            notes.append(f"deduped {n} file blocks")
            text = text2
            _set_content(out, text)

    if role in {"system", "developer"} and cfg.compress_system:
        text2, changed = _compress_system(text, cfg.max_system_chars)
        if changed:
            notes.append("compressed system")
            text = text2
            _set_content(out, text)

    if len(text) > limit:
        text = _truncate(text, limit, f"{role or 'msg'}")
        _set_content(out, text)
        notes.append(f"truncated {role or 'message'} to {limit}")

    # Drop giant unused fields on the message itself
    for k in ("reasoning_content", "thinking", "encrypted_content"):
        if k in out and cfg.drop_reasoning_parts:
            out.pop(k, None)
            notes.append(f"removed message.{k}")

    return out


def _get_message_list(body: dict[str, Any]) -> tuple[str | None, list[Any]]:
    if isinstance(body.get("messages"), list):
        return "messages", body["messages"]
    if isinstance(body.get("input"), list):
        return "input", body["input"]
    return None, []


def strip_payload(body: Any, cfg: StripConfig) -> StripResult:
    """Return a token-reduced copy of a Cursor/OpenAI-style JSON body."""
    original_chars = _json_size(body) if not isinstance(body, (str, bytes)) else len(body)
    notes: list[str] = []

    if not isinstance(body, dict):
        return StripResult(body, body, False, original_chars, original_chars, ["non-object"])

    out = deepcopy(body)

    # Top-level noise
    for k in cfg.drop_keys:
        if k in out:
            out.pop(k, None)
            notes.append(f"dropped key {k}")

    # Nested stream_options fluff
    so = out.get("stream_options")
    if isinstance(so, dict) and "include_obfuscation" in so:
        so = dict(so)
        so.pop("include_obfuscation", None)
        out["stream_options"] = so
        notes.append("dropped stream_options.include_obfuscation")

    key, messages = _get_message_list(out)
    if key and messages:
        # Preserve leading system/developer messages, trim the rest by count
        systems: list[Any] = []
        rest: list[Any] = []
        for m in messages:
            if isinstance(m, dict) and str(m.get("role", "")).lower() in {
                "system",
                "developer",
            }:
                systems.append(m)
            else:
                rest.append(m)

        max_non_system = max(0, cfg.max_messages - len(systems))
        if len(rest) > max_non_system:
            dropped = len(rest) - max_non_system
            rest = rest[-max_non_system:]
            notes.append(f"dropped {dropped} older messages")

        recent_n = max(1, cfg.recent_turn_window)
        rewritten: list[Any] = []
        for i, m in enumerate(systems):
            if isinstance(m, dict):
                rewritten.append(
                    _strip_message_parts(m, cfg, old=False, notes=notes)
                )
            else:
                rewritten.append(m)

        start_recent = max(0, len(rest) - recent_n)
        for i, m in enumerate(rest):
            old = i < start_recent
            if isinstance(m, dict):
                rewritten.append(_strip_message_parts(m, cfg, old=old, notes=notes))
            elif isinstance(m, str):
                limit = cfg.max_chars_old if old else cfg.max_chars_recent
                rewritten.append(_truncate(m, limit, "input"))
            else:
                rewritten.append(m)

        out[key] = rewritten

    # Responses API: instructions field can be huge
    if isinstance(out.get("instructions"), str) and cfg.compress_system:
        text, changed = _compress_system(out["instructions"], cfg.max_system_chars)
        if changed:
            out["instructions"] = text
            notes.append("compressed instructions")

    # Anthropic Messages API: top-level system (string or content blocks)
    if "system" in out and cfg.compress_system:
        sys_val = out["system"]
        if isinstance(sys_val, str):
            text, changed = _compress_system(sys_val, cfg.max_system_chars)
            if changed:
                out["system"] = text
                notes.append("compressed anthropic system")
        elif isinstance(sys_val, list):
            # Join text blocks, compress, rewrite as single text block if oversized
            parts: list[str] = []
            for block in sys_val:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block, str):
                    parts.append(block)
            joined = "\n".join(parts)
            if len(joined) > cfg.max_system_chars:
                text, _ = _compress_system(joined, cfg.max_system_chars)
                out["system"] = text
                notes.append("compressed anthropic system blocks")

    stripped_chars = _json_size(out)
    changed = stripped_chars < original_chars or bool(notes)
    # Exact equality check for semantic change
    if out == body:
        changed = False
        notes = []

    return StripResult(
        original=body,
        stripped=out,
        changed=changed,
        original_chars=original_chars,
        stripped_chars=stripped_chars,
        notes=notes,
    )


def try_strip_bytes(data: bytes, cfg: StripConfig) -> tuple[bytes, StripResult | None]:
    """Parse JSON bytes, strip, re-serialize. Returns original bytes if not JSON."""
    if not data:
        return data, None
    # Skip obvious binary / protobuf
    if b"\x00" in data[:64]:
        return data, None
    try:
        text = data.decode("utf-8")
        body = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return data, None

    result = strip_payload(body, cfg)
    if not result.changed:
        return data, result

    if cfg.dry_run:
        return data, result

    new = json.dumps(result.stripped, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return new, result
