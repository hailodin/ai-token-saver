"""Claude Code's path: forwarded intact, duplicates stubbed and replayed, usage booked.

Runs the real reverse proxy (openai_bridge.create_app) against a stand-in for
api.anthropic.com on loopback, and the MITM addon through mitmproxy's own test
helpers, so nothing leaves the machine and no key is needed.

    python -m aiproxy.test_claude_path
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from aiproxy.claude_path import ClaudePath, ResponseTap, is_messages_request
from aiproxy.claude_strip import STUB_TEXT, conversation_key
from aiproxy.claude_usage import parse_sse
from aiproxy.config import Config
from aiproxy.stats import StatsStore
from aiproxy.stripper import try_strip_bytes

# --- helpers -----------------------------------------------------------------


def _config(tmp: Path, upstream: str = "https://api.anthropic.com") -> Config:
    cfg = Config()
    cfg.mode = "anthropic"
    cfg.anthropic_upstream = upstream
    cfg.claude.state_path = str(tmp / "claude_state.json")
    cfg.claude.stats_path = str(tmp / "claude_stats.json")
    cfg.logging.dump_dir = str(tmp / "dumps")
    cfg.strip.max_messages = 16  # the shipped config.yaml value
    cfg.strip.max_system_chars = 8000
    cfg.strip.drop_keys = ["metadata"]
    return cfg


def _sse(model: str, *, read: int, write_1h: int, out: int) -> bytes:
    """A stream shaped like the real API's: the split in message_start, and
    message_delta repeating the flat cache_creation_input_tokens total."""
    start = {
        "type": "message_start",
        "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": [],
            "usage": {"input_tokens": 3, "cache_read_input_tokens": read,
                      "cache_creation_input_tokens": write_1h,
                      "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                         "ephemeral_1h_input_tokens": write_1h},
                      "output_tokens": 1},
        },
    }
    delta = {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"input_tokens": 3, "cache_read_input_tokens": read,
                       "cache_creation_input_tokens": write_1h, "output_tokens": out}}
    events = [("message_start", start),
              ("content_block_start", {"type": "content_block_start", "index": 0,
                                       "content_block": {"type": "text", "text": ""}}),
              ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                       "delta": {"type": "text_delta", "text": "ok"}}),
              ("content_block_stop", {"type": "content_block_stop", "index": 0}),
              ("message_delta", delta),
              ("message_stop", {"type": "message_stop"})]
    return b"".join(f"event: {n}\ndata: {json.dumps(d)}\n\n".encode() for n, d in events)


def _claude_code_body(turns: int = 11) -> dict:
    """The shape Claude Code sends: long cached system prompt, metadata,
    thinking blocks in history, user turns of several tool_result blocks."""
    msgs = [{"role": "user", "content": [{"type": "text", "text": "Fix the bug in app.py"}]}]
    for i in range(turns):
        msgs.append({"role": "assistant", "content": [
            {"type": "thinking", "thinking": f"step {i}", "signature": "s" * 40},
            {"type": "tool_use", "id": f"toolu_{i}a", "name": "Read", "input": {"file_path": f"f{i}"}},
            {"type": "tool_use", "id": f"toolu_{i}b", "name": "Read", "input": {"file_path": f"g{i}"}},
        ]})
        msgs.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"toolu_{i}a", "content": f"f{i}\n" + "x = 1\n" * 300},
            {"type": "tool_result", "tool_use_id": f"toolu_{i}b", "content": f"g{i}\n" + "y = 2\n" * 300},
        ]})
    return {
        "model": "claude-opus-5-5", "max_tokens": 32000, "stream": True,
        "system": [{"type": "text", "text": "You are Claude Code."},
                   {"type": "text", "text": "instructions " * 1500,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        "messages": msgs,
        "metadata": {"user_id": json.dumps({"session_id": "s1"})},
        "thinking": {"type": "adaptive"},
    }


class Upstream:
    """Stand-in for api.anthropic.com that records every body it receives."""

    def __init__(self) -> None:
        self.bodies: list[tuple[str, dict]] = []

    def app(self) -> web.Application:
        async def messages(request: web.Request) -> web.StreamResponse:
            body = await request.json()
            self.bodies.append((request.path_qs, body))
            if request.path.endswith("count_tokens"):
                return web.json_response({"input_tokens": 1234})
            resp = web.StreamResponse(headers={"content-type": "text/event-stream"})
            await resp.prepare(request)
            await resp.write(_sse(body["model"], read=40_000, write_1h=1_000, out=50))
            await resp.write_eof()
            return resp

        app = web.Application(client_max_size=64 * 1024 * 1024)
        app.router.add_post("/v1/messages", messages)
        app.router.add_post("/v1/messages/count_tokens", messages)
        return app


async def _with_bridge(fn) -> None:  # noqa: ANN001
    from aiproxy.openai_bridge import create_app

    up = Upstream()
    async with TestServer(up.app()) as upstream_srv:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(Path(tmp), upstream=str(upstream_srv.make_url("")).rstrip("/"))
            claude = ClaudePath(cfg)
            proxy = create_app(cfg, StatsStore(persist_path=None), claude)
            async with TestClient(TestServer(proxy)) as client:
                await fn(client, up, claude)


async def _post(client: TestClient, path: str, body: dict) -> bytes:
    r = await client.post(path, data=json.dumps(body).encode(),
                          headers={"content-type": "application/json", "anthropic-version": "2023-06-01"})
    assert r.status == 200, r.status
    return await r.read()


# --- tests -------------------------------------------------------------------


def test_is_messages_request() -> None:
    assert is_messages_request("POST", "/v1/messages")
    assert is_messages_request("POST", "/v1/messages?beta=true")
    assert is_messages_request("post", "v1/messages")
    assert not is_messages_request("POST", "/v1/messages/count_tokens?beta=true")
    assert not is_messages_request("GET", "/v1/messages")
    assert not is_messages_request("POST", "/v1/models")


def test_response_tap_keeps_both_ends() -> None:
    tap = ResponseTap(limit=100)
    tap.feed(b"A" * 30)
    tap.feed(b"B" * 200)
    tap.feed(b"C" * 30)
    data = tap.data()
    assert data.startswith(b"A" * 30) and data.endswith(b"C" * 30)
    assert tap.total == 260 and len(data) <= 100 + 2


def test_usage_cache_write_is_not_counted_twice() -> None:
    u = parse_sse(_sse("claude-opus-5-5", read=40_000, write_1h=1_000, out=50))
    assert (u.cache_write_5m, u.cache_write_1h) == (0, 1_000), (u.cache_write_5m, u.cache_write_1h)
    assert u.output_tokens == 50 and u.cache_read == 40_000
    # 3 in x $4 + 40k read x $0.20 + 1k 1h-write x $8 + 50 out x $20, per million
    assert abs(u.cost_usd() - (3 * 4 + 40_000 * 0.2 + 1_000 * 8 + 50 * 20) / 1e6) < 1e-12


def test_conversation_key_ignores_moving_cache_marker() -> None:
    a = _claude_code_body(1)
    b = json.loads(json.dumps(a))
    b["messages"][0]["content"][0]["cache_control"] = {"type": "ephemeral"}
    assert conversation_key(a) == conversation_key(b)
    c = json.loads(json.dumps(a))
    c["messages"][0]["content"][0]["text"] = "A sub-agent's task"
    assert conversation_key(a) != conversation_key(c)


def test_bridge_forwards_claude_code_untouched() -> None:
    body = _claude_code_body()
    # Sanity: the general strip rules WOULD have rewritten this body.
    _, generic = try_strip_bytes(json.dumps(body).encode(), _config(Path(".")).strip)
    assert generic is not None and generic.changed

    async def run(client, up, claude):  # noqa: ANN001
        await _post(client, "/v1/messages?beta=true", body)
        path, got = up.bodies[-1]
        assert path == "/v1/messages?beta=true"
        assert got == body, "the proxy changed a Claude Code request"
        t = claude.stats.snapshot()["totals"]
        assert t["requests"] == 1 and t["cache_write_1h"] == 1_000 and t["cache_write_5m"] == 0
        assert abs(t["cost_usd"] - (3 * 4 + 40_000 * 0.2 + 1_000 * 8 + 50 * 20) / 1e6) < 1e-12

    asyncio.run(_with_bridge(run))


def test_bridge_stubs_a_duplicate_and_replays_it() -> None:
    same = "def handler():\n" + "    return 42\n" * 60  # > dedupe_min_chars
    turn1 = {
        "model": "claude-opus-5-5", "max_tokens": 1000, "stream": True,
        "system": [{"type": "text", "text": "You are Claude Code."}],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "look at app.py"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": same}]},
        ],
    }
    turn2 = json.loads(json.dumps(turn1))
    turn2["messages"] += [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "Read", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": same}]},
    ]
    turn3 = json.loads(json.dumps(turn2))
    turn3["messages"] += [
        {"role": "assistant", "content": [{"type": "text", "text": "Same file twice."}]},
        {"role": "user", "content": [{"type": "text", "text": "ok"}]},
    ]

    async def run(client, up, claude):  # noqa: ANN001
        await _post(client, "/v1/messages", turn1)
        assert up.bodies[-1][1] == turn1  # first copy: nothing to point at
        await _post(client, "/v1/messages", turn2)
        sent2 = up.bodies[-1][1]
        stub = sent2["messages"][-1]["content"][0]["content"]
        assert stub == STUB_TEXT.format(ref="t1", chars=len(same)), stub
        assert sent2["messages"][:-1] == turn2["messages"][:-1]  # only the newest changed
        await _post(client, "/v1/messages", turn3)
        sent3 = up.bodies[-1][1]
        # The model must see turn 2 exactly as it was sent the first time.
        assert sent3["messages"][: len(sent2["messages"])] == sent2["messages"]
        t = claude.stats.snapshot()["totals"]
        assert t["stubs_new"] == 1 and t["removed_chars_replayed"] == len(same)
        assert t["saved_usd_est"] > 0

    asyncio.run(_with_bridge(run))


def test_bridge_leaves_count_tokens_alone() -> None:
    body = _claude_code_body()
    body.pop("stream")

    async def run(client, up, claude):  # noqa: ANN001
        await _post(client, "/v1/messages/count_tokens?beta=true", body)
        assert up.bodies[-1][1] == body
        assert claude.stats.snapshot()["totals"]["requests"] == 0  # counting is not billed

    asyncio.run(_with_bridge(run))


def test_mitm_addon_claude_flow() -> None:
    from mitmproxy.test import taddons, tflow, tutils

    from aiproxy.addon import CursorStripAddon

    body = _claude_code_body()
    raw = json.dumps(body).encode()
    with tempfile.TemporaryDirectory() as tmp, taddons.context():
        cfg = _config(Path(tmp))
        cfg.intercept_hosts = ["api.anthropic.com"]
        addon = CursorStripAddon(cfg, store=StatsStore(persist_path=None))
        req = tutils.treq(host="api.anthropic.com", port=443, scheme=b"https", method=b"POST",
                          path=b"/v1/messages?beta=true", content=raw,
                          headers=((b"content-type", b"application/json"),
                                   (b"content-length", str(len(raw)).encode())))
        flow = tflow.tflow(req=req)
        addon.requestheaders(flow)
        addon.request(flow)
        assert json.loads(flow.request.raw_content) == body, "MITM mode changed a Claude Code request"
        flow.response = tutils.tresp(status_code=200, content=b"",
                                     headers=((b"content-type", b"text/event-stream"),))
        addon.responseheaders(flow)
        assert callable(flow.response.stream)
        stream = _sse("claude-opus-5-5", read=40_000, write_1h=1_000, out=50)
        for i in range(0, len(stream), 97):  # arrives in pieces
            assert flow.response.stream(stream[i:i + 97]) == stream[i:i + 97]
        addon.response(flow)
        t = addon.claude.stats.snapshot()["totals"]
        assert t["requests"] == 1 and t["output_tokens"] == 50 and t["cache_write_1h"] == 1_000


if __name__ == "__main__":
    test_is_messages_request()
    test_response_tap_keeps_both_ends()
    test_usage_cache_write_is_not_counted_twice()
    test_conversation_key_ignores_moving_cache_marker()
    test_bridge_forwards_claude_code_untouched()
    test_bridge_stubs_a_duplicate_and_replays_it()
    test_bridge_leaves_count_tokens_alone()
    test_mitm_addon_claude_flow()
    print("ok")
