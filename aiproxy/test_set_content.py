"""A rewrite must never change the block count of a message.

Claude Code sends user messages whose content is a list of several
tool_result blocks. The old _set_content kept only the first text-like part,
so those messages left the proxy with every tool_result gone and Anthropic
answered 400. These tests pin the fix.
"""

from __future__ import annotations

from aiproxy.config import StripConfig
from aiproxy.stripper import _set_content, strip_payload


def test_set_content_keeps_every_other_block():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "old"},
            {"type": "tool_result", "tool_use_id": "t1", "content": "r1"},
            {"type": "image", "source": {"type": "base64", "data": "..."}},
        ],
    }
    _set_content(msg, "new")
    assert [b["type"] for b in msg["content"]] == ["text", "tool_result", "image"]
    assert msg["content"][0]["text"] == "new"
    assert msg["content"][1]["tool_use_id"] == "t1"


def test_set_content_leaves_a_message_with_no_text_part_alone():
    msg = {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "r1"},
            {"type": "tool_result", "tool_use_id": "t2", "content": "r2"},
        ],
    }
    _set_content(msg, "new")
    assert len(msg["content"]) == 2
    assert all(b["type"] == "tool_result" for b in msg["content"])


def test_anthropic_tool_results_survive_the_dedupe_rule():
    blk = "File: a.py\n```python\nprint(1)\n```\n"
    body = {
        "model": "claude-sonnet-5-5",
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "go"}]},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
                {"type": "tool_use", "id": "t2", "name": "Read", "input": {}}]},
            {"role": "user", "content": [
                {"type": "text", "text": blk + blk},
                {"type": "tool_result", "tool_use_id": "t1", "content": "one"},
                {"type": "tool_result", "tool_use_id": "t2", "content": "two"}]},
        ],
    }
    result = strip_payload(body, StripConfig(compress_system=False))
    last = result.stripped["messages"][-1]["content"]
    assert [b["type"] for b in last] == ["text", "tool_result", "tool_result"]
    assert [b.get("tool_use_id") for b in last[1:]] == ["t1", "t2"]


if __name__ == "__main__":
    test_set_content_keeps_every_other_block()
    test_set_content_leaves_a_message_with_no_text_part_alone()
    test_anthropic_tool_results_survive_the_dedupe_rule()
    print("ok")
