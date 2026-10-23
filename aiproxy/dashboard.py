from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

from aiohttp import web

from .claude_stats import get_claude_store
from .stats import StatsStore
from .dashboard_v2 import HTML_HEAD as DASHBOARD_HTML_V2_HEAD
from .setup_modal import SETUP_MODAL_ASSETS

if TYPE_CHECKING:
    from .config import Config

log = logging.getLogger("aiproxy.dashboard")

DASHBOARD_HTML_HEAD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>aiproxy</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Sora:wght@400;500;600;700&display=swap" rel="stylesheet" />
<style>
  :root {
    --ink: #12201c;
    --ink-soft: #3a4a44;
    --muted: #6b7a73;
    --line: #d7e0db;
    --line-soft: #e8efeb;
    --paper: #f4f7f5;
    --panel: rgba(255,255,255,0.82);
    --accent: #0f7a5f;
    --accent-soft: #d8f0e8;
    --in: #1f6feb;
    --out: #2a9d8f;
    --saved: #0b5c47;
    --sync: #c4782b;
    --ignored: #8a968a;
    --shadow: 0 1px 0 rgba(18,32,28,0.04), 0 14px 36px rgba(18,32,28,0.07);
    --radius: 14px;
    --bg0: #dff3ea;
    --bg1: #e7eef8;
    --bg2: #f7faf8;
    --grid: #d7e0db;
    --grid-soft: #e8efeb;
    --pie-hole: #f7faf8;
  }
  html[data-theme="dark"] {
    --ink: #e8f0eb;
    --ink-soft: #b7c4bc;
    --muted: #8a968a;
    --line: #2a3530;
    --line-soft: #1f2824;
    --paper: #0f1412;
    --panel: rgba(22,28,25,0.88);
    --accent: #7dcca8;
    --accent-soft: rgba(125,204,168,0.14);
    --in: #6eb6ff;
    --out: #5ec4b2;
    --saved: #9be7c0;
    --sync: #e0a35a;
    --ignored: #7a8680;
    --shadow: 0 1px 0 rgba(0,0,0,0.25), 0 16px 40px rgba(0,0,0,0.35);
    --bg0: #163028;
    --bg1: #152030;
    --bg2: #0f1412;
    --grid: #2a3530;
    --grid-soft: #1f2824;
    --pie-hole: #161c19;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    min-height: 100%;
    color: var(--ink);
    font-family: "Sora", sans-serif;
    background:
      radial-gradient(900px 520px at 0% -10%, var(--bg0) 0%, transparent 55%),
      radial-gradient(700px 420px at 100% 0%, var(--bg1) 0%, transparent 50%),
      linear-gradient(180deg, var(--bg2) 0%, var(--paper) 100%);
  }
  body::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    opacity: 0.32;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cpath d='M120 0H0V120' fill='none' stroke='%2312201c' stroke-opacity='0.04' stroke-width='1'/%3E%3C/svg%3E");
  }
  .wrap {
    position: relative;
    max-width: 1180px;
    margin: 0 auto;
    padding: 32px 22px 64px;
  }
  header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 18px;
    margin-bottom: 12px;
    flex-wrap: nowrap;
  }
  .brand-block { min-width: 0; flex: 1 1 auto; }
  .brand {
    font-size: clamp(1.9rem, 3.6vw, 2.6rem);
    font-weight: 700;
    letter-spacing: -0.05em;
    line-height: 0.95;
    margin: 0 0 8px;
  }
  .brand span { color: var(--accent); }
  .lede {
    margin: 0;
    color: var(--ink-soft);
    font-size: 0.92rem;
    line-height: 1.4;
    max-width: 46ch;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 0 0 auto;
    flex-wrap: nowrap;
  }
  .actions button {
    flex: 0 0 auto;
    white-space: nowrap;
    box-sizing: border-box;
    min-height: 40px;
  }
  #theme { min-width: 4.6rem; }
  #export-pdf { min-width: 7.2rem; }
  #goto-v2 {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 4.6rem;
    text-decoration: none;
    background: var(--accent);
    color: #fff;
    border: 0;
    border-radius: 10px;
    padding: 10px 14px;
    font-family: "Sora", sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
  }
  #goto-v2:hover { background: var(--saved); color: #fff; }
  .status-bar {
    margin-bottom: 16px;
  }
  .meta {
    display: block;
    width: 100%;
    box-sizing: border-box;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.7rem;
    color: var(--muted);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 8px 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-height: 34px;
    line-height: 18px;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .seg {
    display: inline-flex;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 4px;
    gap: 2px;
    box-shadow: var(--shadow);
  }
  .seg button {
    font-family: "Sora", sans-serif;
    font-size: 0.74rem;
    font-weight: 600;
    background: transparent;
    color: var(--ink-soft);
    border: 0;
    border-radius: 9px;
    padding: 8px 12px;
    cursor: pointer;
  }
  .seg button.active {
    background: var(--ink);
    color: var(--paper);
  }
  .seg button:hover:not(.active) { background: var(--accent-soft); color: var(--accent); }
  button.primary {
    font-family: "Sora", sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    background: var(--ink);
    color: var(--paper);
    border: 0;
    border-radius: 10px;
    padding: 10px 14px;
    cursor: pointer;
  }
  button.primary:hover { background: var(--saved); color: var(--paper); }
  button.ghost {
    font-family: "Sora", sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    background: var(--panel);
    color: var(--ink-soft);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 10px 14px;
    cursor: pointer;
  }
  button.ghost:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
  @media print {
    body::before { display: none !important; }
    body {
      background: #fff !important;
      color: #12201c !important;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .wrap { max-width: none; padding: 12px; }
    .actions button,
    .actions a,
    .toolbar,
    #theme,
    #reset,
    #export-pdf,
    #goto-v2,
    .chart-tip { display: none !important; }
    .panel {
      break-inside: avoid;
      box-shadow: none;
      border: 1px solid #d7e0db;
      background: #fff;
      backdrop-filter: none;
    }
    .meta { border: 1px solid #d7e0db; }
    .chart, .pie-wrap { break-inside: avoid; }
    a { text-decoration: none; color: inherit; }
  }
  .lifetime {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin-bottom: 12px;
  }
  @media (max-width: 1100px) { .lifetime { grid-template-columns: repeat(3, 1fr); } }
  @media (max-width: 700px) { .lifetime { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 560px) { .lifetime { grid-template-columns: 1fr; } }
  .lifetime .stat {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .section-label {
    margin: 0 0 8px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .hero {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 12px;
    margin-bottom: 14px;
  }
  @media (max-width: 1200px) { .hero { grid-template-columns: repeat(3, 1fr); } }
  @media (max-width: 700px) { .hero { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 560px) { .hero { grid-template-columns: 1fr; } }
  .panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    backdrop-filter: blur(10px);
    padding: 18px 18px 16px;
  }
  .panel h2 {
    margin: 0 0 10px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .panel .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
  }
  .panel .head h2 { margin: 0; }
  .hint {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.68rem;
    color: var(--muted);
  }
  .stat label {
    display: block;
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 8px;
  }
  .stat .v {
    font-family: "JetBrains Mono", monospace;
    font-size: 1.45rem;
    font-weight: 600;
    letter-spacing: -0.03em;
  }
  .stat .v.in { color: var(--in); }
  .stat .v.out { color: var(--out); }
  .stat .v.saved { color: var(--saved); }
  .stat .v.pct { color: var(--accent); }
  .stat .sub {
    margin-top: 6px;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.72rem;
    color: var(--muted);
  }
  .charts {
    display: grid;
    grid-template-columns: 1.45fr 1fr;
    gap: 12px;
    margin-bottom: 14px;
  }
  @media (max-width: 900px) { .charts { grid-template-columns: 1fr; } }
  .pies {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
    margin-bottom: 14px;
  }
  @media (max-width: 1000px) { .pies { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 700px) { .pies { grid-template-columns: 1fr; } }
  .chart { height: 220px; }
  .pie-wrap {
    display: grid;
    grid-template-columns: 150px 1fr;
    gap: 12px;
    align-items: center;
    min-height: 170px;
  }
  @media (max-width: 520px) {
    .pie-wrap { grid-template-columns: 1fr; justify-items: center; }
  }
  .chart svg, .pie-wrap svg { width: 100%; height: 100%; display: block; }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 14px;
    margin-top: 10px;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.7rem;
    color: var(--muted);
  }
  .legend.col { flex-direction: column; gap: 8px; margin-top: 0; }
  .legend i {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 2px;
    margin-right: 6px;
    vertical-align: -1px;
  }
  .table-scroll { overflow-x: auto; }
  table {
    width: 100%;
    border-collapse: collapse;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.72rem;
  }
  th {
    text-align: left;
    color: var(--muted);
    font-weight: 600;
    padding: 0 10px 10px 0;
    border-bottom: 1px solid var(--line);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.62rem;
    white-space: nowrap;
  }
  td {
    padding: 11px 10px 11px 0;
    border-bottom: 1px solid var(--line-soft);
    color: var(--ink-soft);
  }
  tr:last-child td { border-bottom: 0; }
  tr:hover td { background: rgba(15,122,95,0.03); }
  .tag {
    display: inline-flex;
    align-items: center;
    padding: 3px 8px;
    border-radius: 6px;
    background: var(--line-soft);
    color: var(--muted);
    font-size: 0.66rem;
    font-weight: 500;
  }
  .tag.yes { background: var(--accent-soft); color: var(--accent); }
  .path {
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--muted);
  }
  .empty {
    color: var(--muted);
    padding: 16px 0 6px;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.78rem;
  }
  .chart, .pie-wrap > div:first-child {
    position: relative;
  }
  .chart-tip {
    position: absolute;
    z-index: 20;
    pointer-events: none;
    opacity: 0;
    transform: translate(-50%, calc(-100% - 10px));
    background: var(--ink);
    color: var(--paper);
    border-radius: 8px;
    padding: 8px 10px;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.68rem;
    line-height: 1.35;
    white-space: nowrap;
    box-shadow: var(--shadow);
    transition: opacity 80ms ease;
    max-width: min(280px, 70vw);
  }
  .chart-tip.visible { opacity: 1; }
  .chart-tip strong {
    display: block;
    margin-bottom: 4px;
    font-weight: 600;
  }
  .chart-tip .row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .chart-tip .swatch {
    width: 8px;
    height: 8px;
    border-radius: 2px;
    flex: 0 0 auto;
  }
  .live {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
    margin-right: 8px;
    animation: pulse 2s ease infinite;
  }
  .site-footer {
    margin-top: 28px;
    padding-top: 16px;
    border-top: 1px solid var(--line);
    text-align: center;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(15,122,95,0.4); }
    70% { box-shadow: 0 0 0 8px rgba(15,122,95,0); }
    100% { box-shadow: 0 0 0 0 rgba(15,122,95,0); }
  }
</style>
</head>
<body data-dash="v1">
  <div class="wrap">
    <header>
      <div class="brand-block">
        <h1 class="brand">ai<span>proxy</span></h1>
        <p class="lede">Classic view — token savings, trends, and mix charts.</p>
      </div>
      <div class="actions">
        <button class="ghost" id="setup" type="button">Setup</button>
        <a class="ghost" id="goto-v2" href="/v2">v2 →</a>
        <button class="ghost" id="theme" type="button" aria-label="Toggle dark theme">Dark</button>
        <button class="ghost" id="export-pdf" type="button">Export PDF</button>
        <button class="primary" id="reset" type="button">Reset</button>
      </div>
    </header>
    <div class="status-bar">
      <div class="meta" id="meta"><span class="live"></span>connecting…</div>
    </div>

    <div class="toolbar">
      <div class="seg" id="window-seg" role="group" aria-label="Time window">
        <button type="button" data-mins="15">15m</button>
        <button type="button" data-mins="60" class="active">1h</button>
        <button type="button" data-mins="360">6h</button>
        <button type="button" data-mins="0">All</button>
      </div>
      <div class="seg" id="bucket-seg" role="group" aria-label="Bucket size">
        <button type="button" data-bucket="1" class="active">1m buckets</button>
        <button type="button" data-bucket="5">5m</button>
        <button type="button" data-bucket="15">15m</button>
      </div>
    </div>

    <p class="section-label">Lifetime totals · all time (persisted)</p>
    <section class="lifetime" aria-label="Lifetime savings">
      <div class="panel stat">
        <label>Lifetime tokens saved</label>
        <div class="v saved" id="life-tokens-saved">0</div>
        <div class="sub" id="life-token-pct">0% removed</div>
      </div>
      <div class="panel stat">
        <label>Lifetime $ saved (actual)</label>
        <div class="v pct" id="life-usd-actual">$0</div>
        <div class="sub" id="life-usd-actual-sub">all-time total</div>
      </div>
      <div class="panel stat">
        <label>Lifetime $ saved (max)</label>
        <div class="v saved" id="life-usd-max">$0</div>
        <div class="sub" id="life-usd-max-sub">all-time total</div>
      </div>
      <div class="panel stat">
        <label>Lifetime chars saved</label>
        <div class="v pct" id="life-chars-saved">0</div>
        <div class="sub" id="life-char-pct">0% removed</div>
      </div>
      <div class="panel stat">
        <label>Lifetime requests</label>
        <div class="v in" id="life-volume">0</div>
        <div class="sub" id="life-volume-sub">0 tok requested · 0 stripped</div>
      </div>
    </section>

    <div id="claude-block" hidden>
    <p class="section-label">Claude Code · Anthropic's own usage numbers, at list prices · all time</p>
    <section class="lifetime" aria-label="Claude Code">
      <div class="panel stat">
        <label>Claude Code spent</label>
        <div class="v in" id="cc-spent">$0</div>
        <div class="sub" id="cc-spent-sub">list price</div>
      </div>
      <div class="panel stat">
        <label>Requests</label>
        <div class="v in" id="cc-requests">0</div>
        <div class="sub" id="cc-requests-sub">0 errors</div>
      </div>
      <div class="panel stat">
        <label>Read back from cache</label>
        <div class="v pct" id="cc-cache">0%</div>
        <div class="sub" id="cc-cache-sub">of prompt tokens</div>
      </div>
      <div class="panel stat">
        <label>Duplicates removed</label>
        <div class="v saved" id="cc-saved">$0</div>
        <div class="sub" id="cc-saved-sub">estimate</div>
      </div>
      <div class="panel stat">
        <label>Cache misses</label>
        <div class="v out" id="cc-misses">0</div>
        <div class="sub">a conversation sent again in full</div>
      </div>
    </section>
    </div>

    <p class="section-label">Window · filtered by toolbar</p>
    <section class="hero">
      <div class="panel stat">
        <label>Tokens saved</label>
        <div class="v saved" id="tokens-saved">0</div>
        <div class="sub" id="token-pct">0% removed</div>
      </div>
      <div class="panel stat">
        <label>Actual $ saved/hr</label>
        <div class="v pct" id="usd-actual">$0/hr</div>
        <div class="sub" id="usd-actual-sub">per-model rates</div>
      </div>
      <div class="panel stat">
        <label>Max $ saved/hr</label>
        <div class="v saved" id="usd-max">$0/hr</div>
        <div class="sub" id="usd-max-sub">most expensive model</div>
      </div>
      <div class="panel stat">
        <label>Characters saved</label>
        <div class="v pct" id="chars-saved">0</div>
        <div class="sub" id="char-pct">0% removed</div>
      </div>
      <div class="panel stat">
        <label>Tokens requested</label>
        <div class="v in" id="tokens-in">0 tok</div>
        <div class="sub" id="chars-in">0 chars · 0 req</div>
      </div>
      <div class="panel stat">
        <label>Tokens forwarded</label>
        <div class="v out" id="tokens-out">0 tok</div>
        <div class="sub" id="chars-out">0 chars · 0 stripped</div>
      </div>
    </section>

    <section class="charts">
      <div class="panel">
        <div class="head">
          <h2>Tokens over time</h2>
          <span class="hint" id="line-hint">1h · 1m buckets</span>
        </div>
        <div class="chart" id="line-chart"></div>
        <div class="legend">
          <span><i style="background:var(--in)"></i>requested</span>
          <span><i style="background:var(--saved)"></i>saved</span>
          <span><i style="background:var(--out)"></i>forwarded</span>
        </div>
      </div>
      <div class="panel">
        <div class="head">
          <h2>Save rate</h2>
          <span class="hint" id="rate-hint">% tokens removed</span>
        </div>
        <div class="chart" id="rate-chart"></div>
        <div class="legend">
          <span><i style="background:var(--accent)"></i>save %</span>
        </div>
      </div>
    </section>

    <section class="pies">
      <div class="panel">
        <h2>Token disposition</h2>
        <div class="pie-wrap">
          <div id="pie-tokens" style="height:150px"></div>
          <div class="legend col" id="pie-tokens-legend"></div>
        </div>
      </div>
      <div class="panel">
        <h2>Traffic mix</h2>
        <div class="pie-wrap">
          <div id="pie-traffic" style="height:150px"></div>
          <div class="legend col" id="pie-traffic-legend"></div>
        </div>
      </div>
      <div class="panel">
        <div class="head">
          <h2>Models used</h2>
          <span class="hint" id="models-hint">by tokens requested</span>
        </div>
        <div class="pie-wrap">
          <div id="pie-models" style="height:150px"></div>
          <div class="legend col" id="pie-models-legend"></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="head">
        <h2>Recent requests</h2>
        <span class="hint" id="table-hint">filtered to window</span>
      </div>
      <div class="table-scroll" id="table-wrap"><div class="empty">Waiting for an agent or chat request…</div></div>
    </section>

    <footer class="site-footer">Universally Thinking | 2026 · <a href="/v2" style="color:var(--accent)">v2</a></footer>
  </div>
<script>
"""

DASHBOARD_JS = r"""
const WINDOWS = {15: "15m", 60: "1h", 360: "6h", 0: "all"};
let windowMins = 60;
let bucketMins = 1;
let lastPayload = null;

const THEME_KEY = document.body && document.body.dataset.dash === "v2"
  ? "aiproxy.dashboard.v2.theme"
  : "aiproxy.dashboard.theme";

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function applyTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  const btn = document.getElementById("theme");
  if (btn) btn.textContent = dark ? "Light" : "Dark";
  try { localStorage.setItem(THEME_KEY, dark ? "dark" : "light"); } catch (_) {}
  if (lastPayload) applyView(lastPayload);
}

function initTheme() {
  let theme = null;
  try { theme = localStorage.getItem(THEME_KEY); } catch (_) {}
  if (!theme && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    theme = "dark";
  }
  applyTheme(theme || "light");
}

const fmt = (n) => {
  n = Number(n) || 0;
  if (Math.abs(n) >= 1e6) return (n/1e6).toFixed(2) + "M";
  if (Math.abs(n) >= 1e3) return (n/1e3).toFixed(1) + "k";
  return String(Math.round(n));
};
const fmtFull = (n) => (Number(n)||0).toLocaleString();
const fmtUsd = (n) => {
  n = Number(n) || 0;
  if (n >= 100) return "$" + n.toFixed(0);
  if (n >= 1) return "$" + n.toFixed(2);
  if (n >= 0.01) return "$" + n.toFixed(2);
  if (n > 0) return "$" + n.toFixed(4);
  return "$0";
};

/**
 * Active minute buckets for $/hr — only minutes with model-token traffic.
 * Idle gaps are excluded (no first→last wall-clock span).
 */
function savingsActiveBuckets(d) {
  const now = d.now || (Date.now() / 1000);
  const cut = windowCutoff(now);
  return (d.series || []).filter((s) => {
    if ((s.t || 0) < cut) return false;
    return (Number(s.tokens_in) || 0) > 0 || (Number(s.n) || 0) > 0;
  });
}
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const MODEL_COLORS = ["#1f6feb","#0f7a5f","#2a9d8f","#c4782b","#8b5cf6","#db6b5a","#0b5c47","#6b7a73","#3b82f6","#d97706"];

function shortModel(name) {
  const s = String(name || "unknown");
  return s.length > 22 ? s.slice(0, 20) + "…" : s;
}

function modelsFromRecent(recent) {
  const map = {};
  for (const r of recent || []) {
    const m = r.model || "unknown";
    const st = map[m] || {tokens_in: 0, tokens_saved: 0, n: 0};
    st.tokens_in += Number(r.tokens_in || 0);
    st.tokens_saved += Number(r.tokens_saved || 0);
    st.n += 1;
    map[m] = st;
  }
  return map;
}

function windowCutoff(now) {
  if (!windowMins) return 0;
  return now - windowMins * 60;
}

function filterSeries(series, now) {
  const cut = windowCutoff(now);
  const filtered = (series || []).filter(s => (s.t || 0) >= cut);
  if (bucketMins <= 1) return filtered;
  const step = bucketMins * 60;
  const map = new Map();
  for (const s of filtered) {
    const key = Math.floor((s.t || 0) / step) * step;
    const b = map.get(key) || {
      t: key, tokens_in: 0, tokens_out: 0, tokens_saved: 0,
      chars_in: 0, chars_out: 0, chars_saved: 0, n: 0, stripped: 0
    };
    for (const k of ["tokens_in","tokens_out","tokens_saved","chars_in","chars_out","chars_saved","n","stripped"]) {
      b[k] += Number(s[k] || 0);
    }
    map.set(key, b);
  }
  return [...map.values()].sort((a,b) => a.t - b.t);
}

function sumSeries(series) {
  const out = {
    tokens_in: 0, tokens_out: 0, tokens_saved: 0,
    chars_in: 0, chars_out: 0, chars_saved: 0,
    n: 0, stripped: 0
  };
  for (const s of series) {
    for (const k of Object.keys(out)) out[k] += Number(s[k] || 0);
  }
  return out;
}

function filterRecent(recent, now) {
  const cut = windowCutoff(now);
  return (recent || []).filter(r => (r.ts || 0) >= cut);
}

function ensureTip(el) {
  let tip = el.querySelector(".chart-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "chart-tip";
    tip.setAttribute("role", "tooltip");
    el.appendChild(tip);
  }
  return tip;
}

function placeTip(el, tip, clientX, clientY) {
  const rect = el.getBoundingClientRect();
  let left = clientX - rect.left;
  let top = clientY - rect.top;
  tip.classList.add("visible");
  // Keep tooltip inside the chart box.
  const tw = tip.offsetWidth || 120;
  const th = tip.offsetHeight || 40;
  left = Math.max(tw/2 + 4, Math.min(rect.width - tw/2 - 4, left));
  top = Math.max(th + 14, top);
  tip.style.left = left + "px";
  tip.style.top = top + "px";
}

function renderLineChart(el, series, keys, colors, labels, {areaKey=null, yFmt=fmt} = {}) {
  if (!series.length) {
    el.innerHTML = '<div class="empty">No time series in this window</div>';
    return;
  }
  const w = el.clientWidth || 640, h = 220;
  const pad = {t: 12, r: 12, b: 28, l: 44};
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const maxY = Math.max(1, ...series.flatMap(s => keys.map(k => Number(s[k] || 0))));
  const x = (i) => pad.l + (series.length === 1 ? iw/2 : (i/(series.length-1))*iw);
  const y = (v) => pad.t + ih - (v/maxY)*ih;
  const line = (key, color) => {
    const pts = series.map((s,i) => `${x(i)},${y(s[key]||0)}`).join(" ");
    return `<polyline fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" points="${pts}" />`;
  };
  const grid = cssVar("--grid") || "#d7e0db";
  const gridSoft = cssVar("--grid-soft") || "#e8efeb";
  const muted = cssVar("--muted") || "#6b7a73";
  const ink = cssVar("--ink") || "#12201c";
  const areaFill = currentTheme() === "dark" ? "rgba(155,231,192,0.14)" : "rgba(11,92,71,0.12)";
  const t0 = new Date((series[0].t||0)*1000).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"});
  const t1 = new Date((series[series.length-1].t||0)*1000).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"});
  const dots = keys.map((k, ki) => series.map((s,i) =>
    `<circle class="pt" data-i="${i}" data-k="${k}" cx="${x(i)}" cy="${y(s[k]||0)}" r="3.5" fill="${colors[ki]}" opacity="0" />`
  ).join("")).join("");
  el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <line x1="${pad.l}" y1="${y(0)}" x2="${w-pad.r}" y2="${y(0)}" stroke="${grid}" />
    <line x1="${pad.l}" y1="${y(maxY/2)}" x2="${w-pad.r}" y2="${y(maxY/2)}" stroke="${gridSoft}" stroke-dasharray="4 4" />
    ${areaKey ? `<polygon fill="${areaFill}" points="${x(0)},${y(0)} ${series.map((s,i) => `${x(i)},${y(s[areaKey]||0)}`).join(" ")} ${x(series.length-1)},${y(0)}" />` : ""}
    ${keys.map((k,i) => line(k, colors[i])).join("")}
    ${dots}
    <line class="guide" x1="0" y1="${pad.t}" x2="0" y2="${pad.t+ih}" stroke="${ink}" stroke-opacity="0.25" stroke-dasharray="3 3" opacity="0" />
    <rect class="hit" x="${pad.l}" y="${pad.t}" width="${iw}" height="${ih}" fill="transparent" />
    <text x="${pad.l}" y="${h-8}" fill="${muted}" font-size="10" font-family="JetBrains Mono">${t0}</text>
    <text x="${w-pad.r}" y="${h-8}" fill="${muted}" font-size="10" font-family="JetBrains Mono" text-anchor="end">${t1}</text>
    <text x="${w-pad.r}" y="${pad.t+10}" fill="${muted}" font-size="10" font-family="JetBrains Mono" text-anchor="end">${yFmt(maxY)}</text>
  </svg>`;
  const tip = ensureTip(el);
  const svg = el.querySelector("svg");
  const guide = svg.querySelector(".guide");
  const hit = svg.querySelector(".hit");
  const nearestIndex = (clientX) => {
    const rect = svg.getBoundingClientRect();
    const px = ((clientX - rect.left) / rect.width) * w;
    let best = 0, bestDist = Infinity;
    for (let i = 0; i < series.length; i++) {
      const d = Math.abs(x(i) - px);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
  };
  const showAt = (i, clientX, clientY) => {
    const s = series[i];
    const when = new Date((s.t||0)*1000).toLocaleString([], {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"});
    const rows = keys.map((k, ki) => {
      const label = (labels && labels[ki]) || k;
      const val = k === "save_pct" ? (Math.round((s[k]||0)*10)/10) + "%" : fmtFull(s[k]||0);
      return `<div class="row"><span class="swatch" style="background:${colors[ki]}"></span>${label}: <strong style="display:inline;margin:0">${val}</strong></div>`;
    }).join("");
    tip.innerHTML = `<strong>${when}</strong>${rows}`;
    guide.setAttribute("x1", x(i));
    guide.setAttribute("x2", x(i));
    guide.setAttribute("opacity", "1");
    svg.querySelectorAll(".pt").forEach(c => {
      c.setAttribute("opacity", c.getAttribute("data-i") === String(i) ? "1" : "0");
    });
    placeTip(el, tip, clientX, clientY);
  };
  const hide = () => {
    tip.classList.remove("visible");
    guide.setAttribute("opacity", "0");
    svg.querySelectorAll(".pt").forEach(c => c.setAttribute("opacity", "0"));
  };
  hit.addEventListener("mousemove", (e) => showAt(nearestIndex(e.clientX), e.clientX, e.clientY));
  hit.addEventListener("mouseleave", hide);
}

function renderPie(el, legendEl, slices) {
  const total = slices.reduce((a,s) => a + Math.max(0, s.value), 0);
  if (total <= 0) {
    el.innerHTML = '<div class="empty">No data</div>';
    legendEl.innerHTML = "";
    return;
  }
  const size = 150, r = 58, cx = 75, cy = 75;
  let angle = -Math.PI / 2;
  const paths = [];
  const meta = [];
  for (const s of slices) {
    const v = Math.max(0, s.value);
    if (!v) continue;
    const sweep = (v / total) * Math.PI * 2;
    const a2 = angle + sweep;
    const x1 = cx + r * Math.cos(angle), y1 = cy + r * Math.sin(angle);
    const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
    const large = sweep > Math.PI ? 1 : 0;
    const pct = Math.round(100 * v / total);
    const idx = meta.length;
    meta.push({...s, value: v, pct});
    paths.push(`<path data-i="${idx}" d="M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z" fill="${s.color}" style="cursor:pointer">
      <title>${s.label}: ${fmtFull(v)} (${pct}%)</title>
    </path>`);
    angle = a2;
  }
  const hole = cssVar("--pie-hole") || "#f7faf8";
  const inkSoft = cssVar("--ink-soft") || "#3a4a44";
  el.innerHTML = `<svg viewBox="0 0 ${size} ${size}">${paths.join("")}<circle cx="${cx}" cy="${cy}" r="30" fill="${hole}"/><text x="${cx}" y="${cy+4}" text-anchor="middle" font-size="11" font-family="JetBrains Mono" fill="${inkSoft}">${fmt(total)}</text></svg>`;
  legendEl.innerHTML = slices.map(s => {
    const pct = total ? Math.round(100 * s.value / total) : 0;
    return `<span title="${s.label}: ${fmtFull(s.value)} (${pct}%)"><i style="background:${s.color}"></i>${s.label} · ${fmt(s.value)} (${pct}%)</span>`;
  }).join("");
  const tip = ensureTip(el);
  el.querySelectorAll("path[data-i]").forEach(path => {
    path.addEventListener("mouseenter", (e) => {
      const m = meta[Number(path.getAttribute("data-i"))];
      if (!m) return;
      tip.innerHTML = `<strong>${m.label}</strong><div class="row"><span class="swatch" style="background:${m.color}"></span>${fmtFull(m.value)} · ${m.pct}% of total</div>`;
      placeTip(el, tip, e.clientX, e.clientY);
      path.setAttribute("opacity", "0.85");
    });
    path.addEventListener("mousemove", (e) => placeTip(el, tip, e.clientX, e.clientY));
    path.addEventListener("mouseleave", () => {
      tip.classList.remove("visible");
      path.setAttribute("opacity", "1");
    });
  });
}

function renderTable(recent) {
  const wrap = document.getElementById("table-wrap");
  if (!recent.length) {
    wrap.innerHTML = '<div class="empty">No requests in this time window.</div>';
    return;
  }
  const rows = recent.slice(0, 40).map(r => {
    const t = new Date(r.ts*1000).toLocaleTimeString();
    const model = shortModel(r.model || "unknown");
    return `<tr>
      <td>${t}</td>
      <td class="path" title="${r.model||""}">${model}</td>
      <td class="path" title="${r.path||""}">${r.path||""}</td>
      <td>${fmtFull(r.tokens_in)} / ${fmtFull(r.chars_in)}</td>
      <td>${fmtFull(r.tokens_out)} / ${fmtFull(r.chars_out)}</td>
      <td style="color:var(--saved);font-weight:600">${fmtFull(r.tokens_saved)} / ${fmtFull(r.chars_saved)}</td>
      <td><span class="tag ${r.stripped?'yes':''}">${r.stripped?(r.dry_run?'dry-run':'stripped'):((r.notes&&r.notes[0])||'same')}</span></td>
    </tr>`;
  }).join("");
  wrap.innerHTML = `<table>
    <thead><tr>
      <th>time</th><th>model</th><th>path</th>
      <th>requested tok/char</th><th>forwarded tok/char</th><th>saved tok/char</th><th></th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function applyView(d) {
  const now = d.now || (Date.now()/1000);
  const series = filterSeries(d.series || [], now);
  const sum = sumSeries(series);
  const recent = filterRecent(d.recent || [], now);
  const tAll = d.totals || {};

  // "All" uses lifetime totals (persisted across launches). Time windows use series only.
  const use = windowMins === 0 ? {
    tokens_in: tAll.tokens_in || 0,
    tokens_out: tAll.tokens_out || 0,
    tokens_saved: tAll.tokens_saved || 0,
    chars_in: tAll.chars_in || 0,
    chars_out: tAll.chars_out || 0,
    chars_saved: tAll.chars_saved || 0,
    n: tAll.requests || 0,
    stripped: tAll.stripped || 0,
  } : sum;

  const tokPct = use.tokens_in ? round2(100 * use.tokens_saved / use.tokens_in) : 0;
  const charPct = use.chars_in ? round2(100 * use.chars_saved / use.chars_in) : 0;

  document.getElementById("tokens-saved").textContent = fmtFull(use.tokens_saved);
  document.getElementById("chars-saved").textContent = fmtFull(use.chars_saved);
  document.getElementById("token-pct").textContent = tokPct + "% of requested tokens removed";
  document.getElementById("char-pct").textContent = charPct + "% of requested characters removed";
  document.getElementById("tokens-in").textContent = fmtFull(use.tokens_in) + " tok";
  document.getElementById("chars-in").textContent = fmtFull(use.chars_in) + " chars · " + fmtFull(use.n) + (windowMins === 0 ? " req" : " buckets");
  document.getElementById("tokens-out").textContent = fmtFull(use.tokens_out) + " tok";
  document.getElementById("chars-out").textContent = fmtFull(use.chars_out) + " chars · " + fmtFull(use.stripped) + " stripped";

  // Cost cards: actual (per-model) then max (most expensive). $/hr = active minutes only.
  const lifeTok = Number(tAll.tokens_saved || 0);
  const tokSaved = Number(use.tokens_saved || 0);
  const scale = lifeTok > 0 ? tokSaved / lifeTok : 0;
  const lifeActual = Number(d.usd_saved_actual != null ? d.usd_saved_actual : d.usd_saved_est || 0);
  const lifeMax = Number(d.usd_saved_max != null ? d.usd_saved_max : d.usd_saved_est || 0);
  const usdActual = lifeActual * scale;
  const usdMax = lifeMax * scale;
  const activeBuckets = savingsActiveBuckets(d);
  const activeTokSaved = sumSeries(activeBuckets).tokens_saved || 0;
  const activeScale = lifeTok > 0 ? activeTokSaved / lifeTok : 0;
  const hours = Math.max(activeBuckets.length, 1) / 60;
  const usdPerHourActual = (lifeActual * activeScale) / hours;
  const usdPerHourMax = (lifeMax * activeScale) / hours;
  const reqs = Number(use.n || 0);
  const usdPerReqActual = reqs > 0 ? usdActual / reqs : 0;
  const usdPerReqMax = reqs > 0 ? usdMax / reqs : 0;
  const activeMin = Math.max(1, activeBuckets.length);
  const rateNote = activeMin < 60 ? `${activeMin}m active` : `${Math.round(hours)}h active`;
  const rateModel = shortModel(d.usd_rate_model || d.assumed_model || "est");
  const rateActual = Number(d.usd_per_mtok_actual || d.usd_per_mtok || 3);
  const rateMax = Number(d.usd_per_mtok_max || d.usd_per_mtok || 3);
  document.getElementById("usd-actual").textContent = fmtUsd(usdPerHourActual) + "/hr";
  document.getElementById("usd-actual-sub").textContent =
    fmtUsd(usdActual) + " total · " + fmtUsd(usdPerReqActual) + "/req · @$" + rateActual.toFixed(2) + "/MTok blend · " + rateNote;
  document.getElementById("usd-max").textContent = fmtUsd(usdPerHourMax) + "/hr";
  document.getElementById("usd-max-sub").textContent =
    fmtUsd(usdMax) + " total · " + fmtUsd(usdPerReqMax) + "/req · @$" + rateMax.toFixed(2) + "/MTok (" + rateModel + ") · " + rateNote;

  const mins = Math.floor((d.uptime_s||0)/60);
  const lifeDays = Math.floor((d.lifetime_s||0) / 86400);
  const lifeNote = lifeDays > 0 ? ` · since ${lifeDays}d` : "";
  document.getElementById("meta").innerHTML =
    `<span class="live"></span>up ${mins}m${lifeNote} · window ${WINDOWS[windowMins]} · sync ${fmt(tAll.sync_chars||0)} chars · ignored ${tAll.ignored||0}`
    + (d.persisted ? " · cached" : "");
  document.getElementById("line-hint").textContent = `${WINDOWS[windowMins]} · ${bucketMins}m buckets`;
  document.getElementById("rate-hint").textContent = `${series.length} points`;
  document.getElementById("table-hint").textContent = `${recent.length} in window`;

  const rateSeries = series.map(s => ({
    t: s.t,
    save_pct: s.tokens_in ? (100 * (s.tokens_saved||0) / s.tokens_in) : 0
  }));

  renderLineChart(
    document.getElementById("line-chart"),
    series,
    ["tokens_in", "tokens_saved", "tokens_out"],
    [cssVar("--in") || "#1f6feb", cssVar("--saved") || "#0b5c47", cssVar("--out") || "#2a9d8f"],
    ["Requested tokens", "Saved tokens", "Forwarded tokens"],
    {areaKey: "tokens_saved"}
  );
  renderLineChart(
    document.getElementById("rate-chart"),
    rateSeries,
    ["save_pct"],
    [cssVar("--accent") || "#0f7a5f"],
    ["Save rate"],
    {yFmt: (v) => Math.round(v) + "%"}
  );

  renderPie(
    document.getElementById("pie-tokens"),
    document.getElementById("pie-tokens-legend"),
    [
      {label: "saved", value: use.tokens_saved, color: cssVar("--saved") || "#0b5c47"},
      {label: "forwarded", value: Math.max(0, use.tokens_out), color: cssVar("--out") || "#2a9d8f"},
    ]
  );
  renderPie(
    document.getElementById("pie-traffic"),
    document.getElementById("pie-traffic-legend"),
    [
      {label: "model req", value: use.n || tAll.requests || 0, color: cssVar("--in") || "#1f6feb"},
      {label: "stripped", value: use.stripped || tAll.stripped || 0, color: cssVar("--accent") || "#0f7a5f"},
      {label: "sync calls", value: tAll.sync || 0, color: cssVar("--sync") || "#c4782b"},
      {label: "ignored", value: tAll.ignored || 0, color: cssVar("--ignored") || "#8a968a"},
      {label: "passthrough", value: tAll.passthrough || 0, color: cssVar("--muted") || "#6b7a73"},
    ]
  );

  const byModel = windowMins === 0
    ? (d.by_model || {})
    : modelsFromRecent(recent);
  const modelEntries = Object.entries(byModel)
    .map(([name, st]) => ({name, tokens_in: Number(st.tokens_in || 0), n: Number(st.n || 0)}))
    .filter(x => x.tokens_in > 0 || x.n > 0)
    .sort((a, b) => b.tokens_in - a.tokens_in)
    .slice(0, 10);
  document.getElementById("models-hint").textContent =
    modelEntries.length
      ? `${modelEntries.length} model${modelEntries.length===1?"":"s"} · ${windowMins===0?"lifetime":WINDOWS[windowMins]}`
      : "no model traffic yet";
  renderPie(
    document.getElementById("pie-models"),
    document.getElementById("pie-models-legend"),
    modelEntries.length
      ? modelEntries.map((m, i) => ({
          label: shortModel(m.name),
          value: m.tokens_in || m.n,
          color: MODEL_COLORS[i % MODEL_COLORS.length],
        }))
      : [{label: "none", value: 0, color: cssVar("--muted") || "#6b7a73"}]
  );
  renderTable(recent);

  // Optional denser metrics (v2). Safe no-ops when elements are absent.
  const activeSum = sumSeries(activeBuckets);
  const activeReqs = Number(activeSum.n || 0);
  const reqPerHour = activeReqs / hours;
  const stripPct = reqs > 0 ? round2(100 * Number(use.stripped || 0) / reqs) : 0;
  const avgTokIn = reqs > 0 ? Math.round(use.tokens_in / reqs) : 0;
  const avgTokOut = reqs > 0 ? Math.round(use.tokens_out / reqs) : 0;
  const avgTokSaved = reqs > 0 ? Math.round(use.tokens_saved / reqs) : 0;
  const avgCharsSaved = reqs > 0 ? Math.round(use.chars_saved / reqs) : 0;
  const peakSave = rateSeries.length
    ? round2(Math.max(...rateSeries.map((s) => Number(s.save_pct) || 0)))
    : 0;
  const topModel = modelEntries.length ? shortModel(modelEntries[0].name) : "—";
  const topShare = modelEntries.length && use.tokens_in
    ? round2(100 * modelEntries[0].tokens_in / use.tokens_in)
    : (modelEntries.length && modelEntries[0].n
        ? round2(100 * modelEntries[0].n / Math.max(reqs, 1))
        : 0);
  setText("m-save-pct", tokPct + "%");
  setText("m-save-pct-sub", charPct + "% chars removed");
  setText("m-strip-pct", stripPct + "%");
  setText("m-strip-pct-sub", fmtFull(use.stripped || 0) + " of " + fmtFull(reqs) + " req");
  setText("m-usd-total-actual", fmtUsd(usdActual));
  setText("m-usd-total-actual-sub", fmtUsd(usdPerReqActual) + "/req blend");
  setText("m-usd-total-max", fmtUsd(usdMax));
  setText("m-usd-total-max-sub", fmtUsd(usdPerReqMax) + "/req @" + rateModel);
  setText("m-avg-tok-in", fmtFull(avgTokIn));
  setText("m-avg-tok-in-sub", fmtFull(avgTokOut) + " forwarded avg");
  setText("m-avg-tok-saved", fmtFull(avgTokSaved));
  setText("m-avg-tok-saved-sub", fmtFull(avgCharsSaved) + " chars saved/req");
  setText("m-req-rate", round2(reqPerHour) + "/hr");
  setText("m-req-rate-sub", fmtFull(activeReqs) + " active · " + rateNote);
  setText("m-peak-save", peakSave + "%");
  setText("m-peak-save-sub", "best bucket in window");
  setText("m-models", String(modelEntries.length));
  setText("m-models-sub", topModel === "—" ? "no traffic yet" : "top " + topModel + " · " + topShare + "%");
  setText("m-sync", fmtFull(tAll.sync || 0));
  setText("m-sync-sub", fmt(tAll.sync_chars || 0) + " chars synced");
  setText("m-noise", fmtFull((tAll.ignored || 0) + (tAll.passthrough || 0)));
  setText("m-noise-sub", fmtFull(tAll.ignored || 0) + " ignored · " + fmtFull(tAll.passthrough || 0) + " pass");
  setText("m-blocked", fmtFull(tAll.blocked || 0));
  setText("m-blocked-sub", fmtFull(tAll.unchanged || 0) + " unchanged");
  // Lifetime aggregate totals (persisted all-time — never rates/averages).
  const lifeTokIn = Number(tAll.tokens_in || 0);
  const lifeTokSaved = Number(tAll.tokens_saved || 0);
  const lifeCharIn = Number(tAll.chars_in || 0);
  const lifeCharSaved = Number(tAll.chars_saved || 0);
  const lifeTokPct = lifeTokIn ? round2(100 * lifeTokSaved / lifeTokIn) : 0;
  const lifeCharPct = lifeCharIn ? round2(100 * lifeCharSaved / lifeCharIn) : 0;
  const lifeReqs = Number(tAll.requests || 0);
  const lifeStripped = Number(tAll.stripped || 0);
  const lifeSpan = lifeDays > 0
    ? lifeDays + "d tracked"
    : (Math.floor((d.lifetime_s || 0) / 3600) + "h tracked");
  setText("life-tokens-saved", fmtFull(lifeTokSaved));
  setText("life-token-pct", lifeTokPct + "% of " + fmtFull(lifeTokIn) + " tok requested · " + lifeSpan);
  setText("life-chars-saved", fmtFull(lifeCharSaved));
  setText("life-char-pct", lifeCharPct + "% of " + fmtFull(lifeCharIn) + " chars requested");
  setText("life-usd-actual", fmtUsd(lifeActual));
  setText("life-usd-actual-sub", "all-time total · " + lifeSpan);
  setText("life-usd-max", fmtUsd(lifeMax));
  setText("life-usd-max-sub", "all-time total · ceiling @" + rateModel);
  setText("life-volume", fmtFull(lifeReqs));
  setText("life-volume-sub",
    fmtFull(lifeTokIn) + " tok requested · " + fmtFull(lifeStripped) + " stripped · " + lifeSpan);
  setText("m-life-saved", fmtFull(lifeTokSaved));
  setText("m-life-saved-sub", fmtFull(lifeReqs) + " req · " + lifeSpan);
  setText("m-life-usd-actual", fmtUsd(lifeActual));
  setText("m-life-usd-actual-sub", "all-time total · " + lifeSpan);
  setText("m-life-usd-max", fmtUsd(lifeMax));
  setText("m-life-usd-max-sub", "all-time total · ceiling @" + rateModel);
  setText("m-life-chars", fmtFull(lifeCharSaved));
  setText("m-life-chars-sub", lifeCharPct + "% of " + fmtFull(lifeCharIn) + " chars requested");
  setText("m-uptime", mins + "m");
  setText("m-uptime-sub", lifeDays > 0 ? lifeDays + "d lifetime span" : "this process");
}

function round2(n) { return Math.round(n * 100) / 100; }

// Claude Code is measured from the API's usage numbers (cache reads, cache
// writes, output), not estimated from characters like the rest of the page:
// most of a Claude Code prompt is a cache read at a tenth of the input price
// or less, so a character-based figure overstates it many times over.
function renderClaude(c) {
  const block = document.getElementById("claude-block");
  if (!block) return;
  const t = c && c.totals;
  if (!t || !Number(t.requests)) { block.hidden = true; return; }
  block.hidden = false;
  const prompt = Number(c.prompt_tokens || 0);
  setText("cc-spent", fmtUsd(t.cost_usd));
  setText("cc-spent-sub", fmt(prompt) + " prompt tok · " + fmt(t.output_tokens) + " out"
    + (Number(t.unpriced) ? " · " + t.unpriced + " unpriced" : ""));
  setText("cc-requests", fmtFull(t.requests));
  setText("cc-requests-sub", fmtFull(t.errors) + " errors");
  setText("cc-cache", (c.cache_hit_pct || 0) + "%");
  setText("cc-cache-sub", fmt(t.cache_read) + " of " + fmt(prompt) + " prompt tok");
  setText("cc-saved", fmtUsd(t.saved_usd_est));
  setText("cc-saved-sub", "estimate · " + fmtFull(t.stubs_new) + " duplicate tool results · ~"
    + fmt(t.removed_tokens_est) + " tok");
  setText("cc-misses", fmtFull(t.cache_misses));
}

function bindSeg(id, attr, onPick) {
  const root = document.getElementById(id);
  root.querySelectorAll("button").forEach(btn => {
    btn.addEventListener("click", () => {
      root.querySelectorAll("button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      onPick(Number(btn.dataset[attr]));
    });
  });
}

bindSeg("window-seg", "mins", (v) => {
  windowMins = v;
  if (lastPayload) applyView(lastPayload);
});
bindSeg("bucket-seg", "bucket", (v) => {
  bucketMins = v;
  if (lastPayload) applyView(lastPayload);
});

async function refresh() {
  try {
    document.getElementById("meta").innerHTML = `<span class="live"></span>loading…`;
    const res = await fetch("/api/stats", {cache:"no-store"});
    if (!res.ok) throw new Error("stats " + res.status);
    lastPayload = await res.json();
    applyView(lastPayload);
    renderClaude(lastPayload.claude);
  } catch (e) {
    console.error(e);
    document.getElementById("meta").textContent = "dashboard offline";
  }
}

document.getElementById("theme").onclick = () => {
  applyTheme(currentTheme() === "dark" ? "light" : "dark");
};
const setupBtn = document.getElementById("setup");
if (setupBtn) {
  setupBtn.onclick = () => {
    if (window.TokenSaverSetup) window.TokenSaverSetup.open();
    else location.search = "setup=1";
  };
}
document.getElementById("export-pdf").onclick = async () => {
  const btn = document.getElementById("export-pdf");
  const prev = btn.textContent;
  btn.textContent = "Preparing…";
  btn.disabled = true;
  try {
    // Refresh charts at print width, then open system print → Save as PDF.
    if (lastPayload) applyView(lastPayload);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const title = document.title;
    document.title = `aiproxy-${WINDOWS[windowMins]}-${new Date().toISOString().slice(0,19).replace(/[:T]/g,"-")}`;
    window.print();
    document.title = title;
  } finally {
    btn.textContent = prev;
    btn.disabled = false;
  }
};
document.getElementById("reset").onclick = async () => {
  if (!confirm("Reset all dashboard totals?")) return;
  await fetch("/api/reset", {method:"POST"});
  refresh();
};
initTheme();
refresh();
setInterval(refresh, 2000);
window.addEventListener("resize", () => { if (lastPayload) applyView(lastPayload); });
"""

DASHBOARD_HTML = DASHBOARD_HTML_HEAD + DASHBOARD_JS + r"""
</script>
""" + SETUP_MODAL_ASSETS + r"""
</body>
</html>
"""

DASHBOARD_HTML_V2 = DASHBOARD_HTML_V2_HEAD + DASHBOARD_JS + r"""
</script>
""" + SETUP_MODAL_ASSETS + r"""
</body>
</html>
"""


def create_dashboard_app(store: StatsStore, config: "Config | None" = None) -> web.Application:
    app = web.Application()
    app["store"] = store
    app["config"] = config

    async def index(_: web.Request) -> web.Response:
        return web.Response(text=DASHBOARD_HTML, content_type="text/html")

    async def index_v2(_: web.Request) -> web.Response:
        return web.Response(text=DASHBOARD_HTML_V2, content_type="text/html")

    async def api_stats(request: web.Request) -> web.Response:
        payload = request.app["store"].snapshot()
        claude = get_claude_store()
        if claude is not None:
            snap = claude.snapshot()
            payload["claude"] = {
                k: snap[k] for k in ("totals", "prompt_tokens", "cache_hit_pct", "by_model")
            }
        return web.json_response(payload)

    async def api_reset(request: web.Request) -> web.Response:
        request.app["store"].reset()
        claude = get_claude_store()
        if claude is not None:
            claude.reset()
        return web.json_response({"ok": True})

    async def api_setup(request: web.Request) -> web.Response:
        from .runtime_prefs import restart_proxy, save_prefs, setup_payload

        cfg = request.app.get("config")
        if request.method == "GET":
            return web.json_response(setup_payload(cfg))

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

        app_id = int(data.get("app") or 1)
        dry_run = bool(data.get("dry_run", True))
        do_save = bool(data.get("save", True))
        do_restart = bool(data.get("restart", False))
        skip_setup = data.get("skip_setup", None)
        if skip_setup is not None:
            skip_setup = bool(skip_setup)
        if bool(data.get("quick_start", False)):
            app_id = 4

        try:
            prefs = save_prefs(
                app=app_id,
                dry_run=dry_run,
                config=cfg,
                persist_quick_start=do_save,
                skip_setup=skip_setup,
            )
        except ValueError as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        except OSError as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

        message = "Settings saved."
        restarted = False
        if do_restart:
            restarted, message = restart_proxy(cfg)
        return web.json_response(
            {"ok": True, "prefs": prefs, "restarted": restarted, "message": message}
        )

    app.router.add_get("/", index)
    app.router.add_get("/v2", index_v2)
    app.router.add_get("/api/stats", api_stats)
    app.router.add_post("/api/reset", api_reset)
    app.router.add_get("/api/setup", api_setup)
    app.router.add_post("/api/setup", api_setup)
    return app


def start_dashboard_background(config: "Config", store: StatsStore) -> threading.Thread:
    from .config import dashboard_bind_host, dashboard_origin

    host = dashboard_bind_host(config)
    port = getattr(config, "dashboard_port", 8081)
    public = dashboard_origin(config)

    def runner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = create_dashboard_app(store, config)

        async def _start() -> None:
            runner_ = web.AppRunner(app)
            await runner_.setup()
            site = web.TCPSite(runner_, host, port)
            await site.start()
            log.info("dashboard on %s/ (v2: %s/v2)", public, public)
            await asyncio.Event().wait()

        try:
            loop.run_until_complete(_start())
        except OSError as e:
            log.error("dashboard failed to bind %s:%s — %s", host, port, e)

    t = threading.Thread(target=runner, name="aiproxy-dashboard", daemon=True)
    t.start()
    return t
