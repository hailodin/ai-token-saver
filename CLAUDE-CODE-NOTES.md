# Notes on Claude Code, from a review of this proxy (5 October 2026, updated 22 October)

Written for whoever works on the Claude Code path. The Cursor path is not
covered here. The short version: with the shipped defaults the generic
stripper breaks Claude Code, and the dashboard's savings figure is not a
saving. Both are fixed in this copy: anthropic `/v1/messages` requests no
longer go through `stripper.py` at all. They take `aiproxy/claude_path.py`,
which implements the design described below with the three `claude_*.py`
modules in `aiproxy/`. `openai_bridge.handle` uses it in `anthropic` mode and
the mitm addon uses it for `api.anthropic.com`; `count_tokens` is forwarded
untouched. Settings live under `claude:` in `config.yaml`, and the dashboard
shows the result as its own "Claude Code" row.

## What went wrong with the defaults

The generic rules still apply to OpenAI-style traffic; Claude Code traffic
bypasses them, so the first three items below can no longer happen to it.

1. **Multi-block messages lost their blocks.** `_set_content` in `stripper.py`
   rewrote the first text-like part and dropped every other part. A Claude Code
   user turn is a list of `tool_result` blocks; after the rewrite it had none,
   and the API answers 400 ("tool_use ids were found without tool_result
   blocks"). Fixed in this copy (the other parts are kept; a message with no
   text part is left alone). `test_set_content.py` pins it.

2. **The system prompt was cut every turn.** `max_system_chars: 12000` is far
   below Claude Code's system prompt, so `compress_system` truncated it on
   every request - losing tool instructions - and the `cache_control` marker
   on the system block was dropped with it.

3. **Old messages were edited.** Dropping messages past `max_messages`,
   truncating old tool results and compressing the system prompt all change
   the prefix of the conversation. Two consequences:
   - Claude Code depends on prompt caching: the unchanged prefix (tools,
     system, every earlier message) is billed at 0.1x or less, and on the
     newest models 0.05x / 0.025x. Any change to an earlier message is a cache
     miss from that point on, re-billed at the full write rate (1.25x). So the
     strip costs more than it saves, by a wide margin.
   - On Claude Opus 5.5, Sonnet 5.5 and Fable 5.1, editing an earlier turn
     is also "editing history": every later thinking block is invalidated, and
     on accounts enforced for preserved thinking the API returns 400. The docs
     say so explicitly: "deleting old tool results" is listed as an edit that
     breaks it; the sanctioned way to drop old tool results is server-side
     context editing (`context_management`, beta `context-management-2025-06-27`).

4. **The savings number assumed full price.** The dashboard priced removed
   characters at the model's input rate. Most of what was removed was already
   cached content, worth a tenth of that, and the cache misses the stripping
   caused were not counted at all. The word "cache" did not appear in the code.
   The "Claude Code" row is priced from the response's `usage` instead (below).

## What actually works (what `claude_path.py` does)

- **Edit only the newest message.** The newest user message has not been
  reasoned about yet, so changing it is append-only and cache-free. The one
  lossless edit there: a `tool_result` byte-identical to one already in the
  conversation becomes a short stub pointing at the earlier copy
  (`claude_strip.py`). Store the decision by `tool_use_id` and replay it on
  every later request, so the history never changes under the model
  (`claude.state_path` in `config.yaml`).
- **Never touch** `system`, `tools`, `metadata`, `cache_control`, thinking
  blocks, assistant turns, images, or any earlier message.
- **Account from `usage`.** Every response carries `input_tokens`,
  `cache_read_input_tokens`, `cache_creation_input_tokens` (with a 5m/1h
  breakdown under `cache_creation`) and `output_tokens`. Price those with the
  cache multipliers (`claude_usage.py`). For the removed duplicate, convert
  chars to tokens with the chars-per-token ratio measured on the same
  conversation, and price a new stub at the write rate of the response's TTL
  and a replayed one at the read rate (`claude_stats.py`). Label both as
  estimates.
- **Honest expectations.** The real saving for Claude Code is the prompt cache
  it already uses. A proxy's job is to not break it, to measure it, and to
  remove the one thing it can remove losslessly. A context-window saver (old
  tool results) belongs server-side, and the platform docs say it is a window
  tool, not a savings lever.
- **The dedupe is correctness, not the saving.** Measured on one user's
  traffic (15,728 real requests, 19-23 October 2026, $2,068 at list prices):
  7 new stubs, $0.11 saved over the proxy's lifetime. Keep it, because it is
  lossless and it is replayed exactly; do not describe it as what the proxy
  saves.

## What saves money (measured on one user's traffic, October 2026)

Two levers, both under `claude:` in `config.yaml`, both off by default, both
applied to every request alike so the cached prefix is never disturbed
mid-conversation.

- **Tool definitions left out** (`drop_tool_prefixes`). Claude Code sends
  every tool's definition on every request, and the set sits in the cached
  prefix: written once per session, read back every turn. On the measured
  traffic 99 definitions came to 225,000 chars, about 78,000 tokens at the
  measured 2.87 chars per token - a third of a median Opus 5.5 prompt of
  234,000 tokens - and 48 of them were never called once in 21,260 requests
  (Artifact alone 37,000 chars). The cache reads of those unused definitions
  were about 7% of the spend. `claude_path.prepare` removes the named families
  from every request (`claude_strip.drop_tools`); `claude_stats` books the
  saving at the read rate when the response read from cache and at the
  response's write rate when it wrote, and keeps a `tool_usage` table (name,
  size, times sent, times called, from the reply's own `tool_use` blocks) that
  the dashboard shows so the user can choose. The list is changed between
  sessions, never during one.
- **The keep-warm, 1-hour plan only** (`keep_cache_warm`). Claude Code writes
  1-hour cache entries. On the measured traffic, four pauses of one to four
  hours with no refresh were full rewrites (about $20 together); three with
  one refresh came back writing a median 873 tokens, a normal turn. A refresh
  at 55 minutes is the conversation's own last request with `max_tokens: 0`
  and `stream: false`: the API runs prefill, resets the entry's timer and
  bills a cache read. Up to `keep_warm_limit` (3) refreshes a pause, only
  once the conversation has made `keep_warm_min_requests` (2) real requests,
  so a one-shot subagent's conversation is not kept. The 5-minute plan the
  Longship gateway also had was measured and dropped: 1,052 of its 1,125
  refreshes were 5-minute ones, and a pause of 5 minutes to an hour with none
  came back to a cache read anyway. The replayed request is held in memory
  with its headers (`claude_path.KeepWarm`) and is never written. Booked on
  the dashboard as refreshes sent and what they cost, and as rewrites avoided:
  a real request after a pause longer than the entry's hour that still read
  from cache, priced at write minus read.
- **Not ported: the effort cap.** Longship's gateway can lower
  `output_config.effort`. On the measured traffic the user raised effort to
  max on 2,455 requests and lowered it on none, and output per turn at max
  was no larger than as asked. It saves only by trading quality; it is not a
  lever this proxy offers.
- **What no proxy can avoid.** 89% of Opus 5.5 cache writes (69% on Fable
  5.1) were ordinary new content per turn. The largest thing entering a
  conversation is command output (30.7M chars over the lifetime), then file
  reads (17.5M). Those are the user's to shorten.

## Pricing used (USD per million tokens, list)

| model | input | output | cache read | 5m write | 1h write |
|---|---|---|---|---|---|
| claude-fable-5-1 | 10 | 50 | 0.25 | 12.5 | 20 |
| claude-opus-5-5 | 4 | 20 | 0.20 | 5 | 8 |
| claude-opus-5 / 4.8 / 4.7 / 4.6 | 5 | 25 | 0.50 | 6.25 | 10 |
| claude-sonnet-5-5 / 5 | 2 | 10 | 0.20 | 2.5 | 4 |
| claude-sonnet-4-6 | 3 | 15 | 0.30 | 3.75 | 6 |
| claude-haiku-4-5 | 1 | 5 | 0.10 | 1.25 | 2 |

Models not in the table should be shown as unpriced rather than guessed.
