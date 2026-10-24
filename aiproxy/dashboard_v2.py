"""v2 ops dashboard HTML shell (JS shared via dashboard.DASHBOARD_JS)."""

HTML_HEAD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>aiproxy · ops v2</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet" />
<style>
  :root {
    --ink: #111318;
    --ink-soft: #3a414d;
    --muted: #6d7583;
    --line: #cfd5df;
    --line-soft: #e4e8ef;
    --paper: #f3f5f8;
    --panel: #ffffff;
    --accent: #1f6feb;
    --accent-hot: #e85d2a;
    --accent-soft: rgba(31,111,235,0.1);
    --in: #1f6feb;
    --out: #0f9f8a;
    --saved: #0a7a68;
    --sync: #c4782b;
    --ignored: #8a929c;
    --shadow: 0 1px 0 rgba(17,19,24,0.05), 0 18px 40px rgba(17,19,24,0.07);
    --radius: 2px;
    --bg0: #d9e6f8;
    --bg1: #f2e5dc;
    --bg2: #f3f5f8;
    --grid: #cfd5df;
    --grid-soft: #e4e8ef;
    --pie-hole: #ffffff;
    --rail: #111318;
    --band: #111318;
    --band-ink: #f3f5f8;
  }
  html[data-theme="dark"] {
    --ink: #eef1f6;
    --ink-soft: #c2c8d2;
    --muted: #8a929c;
    --line: #2c3340;
    --line-soft: #1c222c;
    --paper: #0d1016;
    --panel: #151a22;
    --accent: #6ea8ff;
    --accent-hot: #ff7a45;
    --accent-soft: rgba(110,168,255,0.14);
    --in: #6ea8ff;
    --out: #3dceb8;
    --saved: #5ee0c8;
    --sync: #e0a35a;
    --ignored: #6a7380;
    --shadow: 0 1px 0 rgba(0,0,0,0.35), 0 16px 36px rgba(0,0,0,0.45);
    --bg0: #152033;
    --bg1: #2a1c16;
    --bg2: #0d1016;
    --grid: #2c3340;
    --grid-soft: #1c222c;
    --pie-hole: #151a22;
    --rail: #eef1f6;
    --band: #151a22;
    --band-ink: #eef1f6;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    min-height: 100%;
    color: var(--ink);
    font-family: "Space Grotesk", sans-serif;
    background:
      radial-gradient(1100px 520px at 0% -10%, var(--bg0) 0%, transparent 55%),
      radial-gradient(900px 480px at 100% 0%, var(--bg1) 0%, transparent 50%),
      linear-gradient(180deg, var(--bg2) 0%, var(--paper) 100%);
  }
  body::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    opacity: 0.35;
    background:
      repeating-linear-gradient(
        -12deg,
        transparent,
        transparent 18px,
        rgba(17,19,24,0.03) 18px,
        rgba(17,19,24,0.03) 19px
      );
  }
  .wrap {
    position: relative;
    width: min(1720px, 98.5vw);
    margin: 0 auto;
    padding: 18px 22px 40px;
  }
  @media (max-width: 720px) { .wrap { padding: 14px 12px 36px; width: 100%; } }

  .topbar {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  .brand-row {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .brand {
    margin: 0;
    font-size: clamp(1.8rem, 3vw, 2.5rem);
    font-weight: 700;
    letter-spacing: -0.055em;
    line-height: 0.95;
  }
  .brand em {
    font-style: normal;
    color: var(--accent-hot);
  }
  .badge {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--band-ink);
    background: var(--band);
    padding: 5px 8px;
  }
  .lede {
    margin: 8px 0 0;
    color: var(--ink-soft);
    font-size: 0.9rem;
    max-width: 56ch;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .version-switch {
    display: inline-flex;
    border: 1px solid var(--line);
    background: var(--panel);
    overflow: hidden;
  }
  .version-switch a {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-decoration: none;
    color: var(--muted);
    padding: 9px 12px;
  }
  .version-switch a.active { background: var(--ink); color: var(--paper); }
  .version-switch a:hover:not(.active) { color: var(--accent); }
  button.primary, button.ghost, a.btn {
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    border-radius: var(--radius);
    padding: 10px 14px;
    cursor: pointer;
    min-height: 38px;
    display: inline-flex;
    align-items: center;
    text-decoration: none;
  }
  button.primary {
    background: var(--accent-hot);
    color: #fff;
    border: 0;
  }
  button.primary:hover { filter: brightness(1.05); }
  button.ghost, a.btn {
    background: var(--panel);
    color: var(--ink-soft);
    border: 1px solid var(--line);
  }
  button.ghost:hover, a.btn:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  .status-bar { margin-bottom: 12px; }
  .meta {
    display: block;
    width: 100%;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.7rem;
    color: var(--muted);
    background: var(--panel);
    border: 1px solid var(--line);
    border-left: 4px solid var(--accent-hot);
    padding: 9px 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-height: 36px;
    line-height: 18px;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }
  .seg {
    display: inline-flex;
    background: var(--panel);
    border: 1px solid var(--line);
    padding: 3px;
    gap: 2px;
  }
  .seg button {
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.74rem;
    font-weight: 600;
    background: transparent;
    color: var(--ink-soft);
    border: 0;
    border-radius: var(--radius);
    padding: 8px 12px;
    cursor: pointer;
  }
  .seg button.active { background: var(--ink); color: var(--paper); }
  .seg button:hover:not(.active) { background: var(--accent-soft); color: var(--accent); }

  @media print {
    body::before { display: none !important; }
    body {
      background: #fff !important;
      color: #111318 !important;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .wrap { max-width: none; width: 100%; padding: 12px; }
    .actions, .toolbar, #theme, #reset, #export-pdf, .version-switch, .chart-tip { display: none !important; }
    .panel, .stat, .feat {
      break-inside: avoid;
      box-shadow: none;
      border: 1px solid #cfd5df;
      background: #fff;
    }
    a { text-decoration: none; color: inherit; }
  }

  .section-label {
    margin: 0 0 8px;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .lifetime {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 1px;
    background: var(--line);
    border: 1px solid var(--line);
    margin-bottom: 14px;
    box-shadow: var(--shadow);
  }
  @media (max-width: 1100px) { .lifetime { grid-template-columns: repeat(3, 1fr); } }
  @media (max-width: 700px) { .lifetime { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 560px) { .lifetime { grid-template-columns: 1fr; } }
  .lifetime .feat { background: #0a7a68; }
  html[data-theme="dark"] .lifetime .feat { background: #0f3d34; }
  .lifetime .feat .v.mint { color: #e8fff8; }
  .lifetime .feat .v.hot { color: #ffd2c2; }
  .lifetime .feat .v.cool { color: #cfe4ff; }

  /* Featured KPIs — dark band, distinct from v1 soft cards */
  .featured {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 1px;
    background: var(--line);
    border: 1px solid var(--line);
    margin-bottom: 12px;
    box-shadow: var(--shadow);
  }
  @media (max-width: 980px) { .featured { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 560px) { .featured { grid-template-columns: 1fr; } }
  .feat {
    background: var(--band);
    color: var(--band-ink);
    padding: 18px 18px 16px;
  }
  .feat label {
    display: block;
    font-size: 0.64rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(243,245,248,0.55);
    margin-bottom: 8px;
  }
  html[data-theme="dark"] .feat label { color: rgba(238,241,246,0.5); }
  .feat .v {
    font-family: "IBM Plex Mono", monospace;
    font-size: clamp(1.35rem, 2vw, 1.85rem);
    font-weight: 600;
    letter-spacing: -0.03em;
  }
  .feat .v.hot { color: var(--accent-hot); }
  .feat .v.cool { color: var(--accent); }
  .feat .v.mint { color: #5ee0c8; }
  .feat .sub {
    margin-top: 6px;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.68rem;
    color: rgba(243,245,248,0.55);
    line-height: 1.35;
  }
  html[data-theme="dark"] .feat .sub { color: rgba(238,241,246,0.5); }

  .metrics {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 12px;
  }
  @media (max-width: 1280px) { .metrics { grid-template-columns: repeat(3, 1fr); } }
  @media (max-width: 720px) { .metrics { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 480px) { .metrics { grid-template-columns: 1fr; } }

  .stat {
    background: var(--panel);
    border: 1px solid var(--line);
    border-top: 3px solid var(--accent);
    padding: 14px 14px 12px;
    box-shadow: var(--shadow);
  }
  .stat.alt { border-top-color: var(--accent-hot); }
  .stat.mint { border-top-color: var(--out); }
  .stat.warm { border-top-color: var(--sync); }
  .stat label {
    display: block;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 7px;
  }
  .stat .v {
    font-family: "IBM Plex Mono", monospace;
    font-size: 1.15rem;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .stat .v.in { color: var(--in); }
  .stat .v.out { color: var(--out); }
  .stat .v.saved { color: var(--saved); }
  .stat .v.pct { color: var(--accent-hot); }
  .stat .sub {
    margin-top: 5px;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.66rem;
    color: var(--muted);
    line-height: 1.35;
  }

  .board {
    display: grid;
    grid-template-columns: 1.65fr 1fr;
    gap: 12px;
    margin-bottom: 12px;
  }
  @media (max-width: 1100px) { .board { grid-template-columns: 1fr; } }

  .panel {
    background: var(--panel);
    border: 1px solid var(--line);
    box-shadow: var(--shadow);
    padding: 16px 18px 14px;
  }
  .panel h2 {
    margin: 0 0 10px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.12em;
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
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.68rem;
    color: var(--muted);
  }
  .charts-stack { display: grid; gap: 12px; }
  .chart { height: 220px; }
  .pies {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .pie-wrap {
    display: grid;
    grid-template-columns: 140px 1fr;
    gap: 12px;
    align-items: center;
    min-height: 150px;
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
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.7rem;
    color: var(--muted);
  }
  .legend.col { flex-direction: column; gap: 8px; margin-top: 0; }
  .legend i {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 1px;
    margin-right: 6px;
    vertical-align: -1px;
  }
  .lower {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .table-scroll { overflow-x: auto; }
  table {
    width: 100%;
    border-collapse: collapse;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.72rem;
  }
  th {
    text-align: left;
    color: var(--muted);
    font-weight: 600;
    padding: 0 10px 10px 0;
    border-bottom: 2px solid var(--line);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.6rem;
    white-space: nowrap;
  }
  td {
    padding: 11px 10px 11px 0;
    border-bottom: 1px solid var(--line-soft);
    color: var(--ink-soft);
  }
  tr:last-child td { border-bottom: 0; }
  tr:hover td { background: var(--accent-soft); }
  .tag {
    display: inline-flex;
    align-items: center;
    padding: 3px 7px;
    border-radius: 2px;
    background: var(--line-soft);
    color: var(--muted);
    font-size: 0.66rem;
    font-weight: 500;
  }
  .tag.yes { background: var(--accent-soft); color: var(--accent); }
  .path {
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--muted);
  }
  .empty {
    color: var(--muted);
    padding: 16px 0 6px;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.78rem;
  }
  .chart, .pie-wrap > div:first-child { position: relative; }
  .chart-tip {
    position: absolute;
    z-index: 20;
    pointer-events: none;
    opacity: 0;
    transform: translate(-50%, calc(-100% - 10px));
    background: var(--ink);
    color: var(--paper);
    border-radius: 2px;
    padding: 8px 10px;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.68rem;
    line-height: 1.35;
    white-space: nowrap;
    box-shadow: var(--shadow);
    transition: opacity 80ms ease;
    max-width: min(280px, 70vw);
  }
  .chart-tip.visible { opacity: 1; }
  .chart-tip strong { display: block; margin-bottom: 4px; font-weight: 600; }
  .chart-tip .row { display: flex; align-items: center; gap: 6px; }
  .chart-tip .swatch {
    width: 8px; height: 8px; border-radius: 1px; flex: 0 0 auto;
  }
  .live {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--accent-hot);
    margin-right: 8px;
    animation: pulse 2s ease infinite;
  }
  .site-footer {
    margin-top: 22px;
    padding-top: 14px;
    border-top: 1px solid var(--line);
    display: flex;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.7rem;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .site-footer a { color: var(--accent); text-decoration: none; }
  .site-footer a:hover { text-decoration: underline; }
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(232,93,42,0.45); }
    70% { box-shadow: 0 0 0 8px rgba(232,93,42,0); }
    100% { box-shadow: 0 0 0 0 rgba(232,93,42,0); }
  }
</style>
</head>
<body data-dash="v2">
  <div class="wrap">
    <header class="topbar">
      <div>
        <div class="brand-row">
          <h1 class="brand">ai<em>proxy</em></h1>
          <span class="badge">ops board</span>
        </div>
        <p class="lede">Wide ops board — denser KPIs, spend velocity, traffic noise, and model mix.</p>
      </div>
      <div class="actions">
        <nav class="version-switch" aria-label="Dashboard version">
          <a href="/">v1</a>
          <a href="/v2" class="active" aria-current="page">v2</a>
        </nav>
        <button class="ghost" id="setup" type="button">Setup</button>
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
      <div class="feat">
        <label>Lifetime tokens saved</label>
        <div class="v mint" id="life-tokens-saved">0</div>
        <div class="sub" id="life-token-pct">0% removed</div>
      </div>
      <div class="feat">
        <label>Lifetime $ saved (actual)</label>
        <div class="v cool" id="life-usd-actual">$0</div>
        <div class="sub" id="life-usd-actual-sub">all-time total</div>
      </div>
      <div class="feat">
        <label>Lifetime $ saved (max)</label>
        <div class="v hot" id="life-usd-max">$0</div>
        <div class="sub" id="life-usd-max-sub">all-time total</div>
      </div>
      <div class="feat">
        <label>Lifetime chars saved</label>
        <div class="v mint" id="life-chars-saved">0</div>
        <div class="sub" id="life-char-pct">0% removed</div>
      </div>
      <div class="feat">
        <label>Lifetime requests</label>
        <div class="v cool" id="life-volume">0</div>
        <div class="sub" id="life-volume-sub">0 tok requested · 0 stripped</div>
      </div>
    </section>

    <!-- The same Claude Code section as the main page, with the same element
         ids: renderClaude() in the shared script fills whichever page has
         them. Until 23 Oct 2026 only the main page did, and the ops board
         showed no Claude Code figures at all. -->
    <div id="claude-block" hidden>
    <p class="section-label">Claude Code · Anthropic's own usage numbers, at list prices · all time</p>
    <section class="metrics" aria-label="Claude Code">
      <div class="stat">
        <label>Claude Code spent</label>
        <div class="v in" id="cc-spent">$0</div>
        <div class="sub" id="cc-spent-sub">list price</div>
      </div>
      <div class="stat">
        <label>Requests</label>
        <div class="v in" id="cc-requests">0</div>
        <div class="sub" id="cc-requests-sub">0 errors</div>
      </div>
      <div class="stat alt">
        <label>Read back from cache</label>
        <div class="v pct" id="cc-cache">0%</div>
        <div class="sub" id="cc-cache-sub">of prompt tokens</div>
      </div>
      <div class="stat mint">
        <label>Duplicates removed</label>
        <div class="v saved" id="cc-saved">$0</div>
        <div class="sub" id="cc-saved-sub">estimate</div>
      </div>
      <div class="stat mint">
        <label>Tool definitions left out</label>
        <div class="v saved" id="cc-tools">$0</div>
        <div class="sub" id="cc-tools-sub">none · set claude.drop_tool_prefixes</div>
      </div>
      <div class="stat mint">
        <label>Kept warm</label>
        <div class="v saved" id="cc-warm">$0</div>
        <div class="sub" id="cc-warm-sub">off · claude.keep_cache_warm</div>
      </div>
      <div class="stat warm">
        <label>Cache misses</label>
        <div class="v out" id="cc-misses">0</div>
        <div class="sub">a conversation sent again in full</div>
      </div>
    </section>
    <section class="panel" aria-label="Tools sent on every turn" id="cc-tools-panel" hidden style="margin-bottom:12px">
      <div class="head"><h2>Tools sent on every turn</h2>
        <span class="hint" id="cc-tools-hint">which tool definitions ride on every request, and how often each is called</span></div>
      <div class="table-scroll" id="cc-tools-table"></div>
    </section>
    </div>

    <p class="section-label">Window · filtered by toolbar</p>
    <section class="featured" aria-label="Primary KPIs">
      <div class="feat">
        <label>Tokens saved</label>
        <div class="v mint" id="tokens-saved">0</div>
        <div class="sub" id="token-pct">0% removed</div>
      </div>
      <div class="feat">
        <label>Save rate</label>
        <div class="v hot" id="m-save-pct">0%</div>
        <div class="sub" id="m-save-pct-sub">0% chars removed</div>
      </div>
      <div class="feat">
        <label>Actual $ saved/hr</label>
        <div class="v cool" id="usd-actual">$0/hr</div>
        <div class="sub" id="usd-actual-sub">per-model rates</div>
      </div>
      <div class="feat">
        <label>Max $ saved/hr</label>
        <div class="v hot" id="usd-max">$0/hr</div>
        <div class="sub" id="usd-max-sub">most expensive model</div>
      </div>
    </section>

    <section class="metrics" aria-label="Extended metrics">
      <div class="stat">
        <label>Characters saved</label>
        <div class="v pct" id="chars-saved">0</div>
        <div class="sub" id="char-pct">0% removed</div>
      </div>
      <div class="stat">
        <label>Tokens requested</label>
        <div class="v in" id="tokens-in">0 tok</div>
        <div class="sub" id="chars-in">0 chars · 0 req</div>
      </div>
      <div class="stat mint">
        <label>Tokens forwarded</label>
        <div class="v out" id="tokens-out">0 tok</div>
        <div class="sub" id="chars-out">0 chars · 0 stripped</div>
      </div>
      <div class="stat alt">
        <label>Strip rate</label>
        <div class="v pct" id="m-strip-pct">0%</div>
        <div class="sub" id="m-strip-pct-sub">0 of 0 req</div>
      </div>
      <div class="stat">
        <label>$ saved (actual)</label>
        <div class="v in" id="m-usd-total-actual">$0</div>
        <div class="sub" id="m-usd-total-actual-sub">$0/req blend</div>
      </div>
      <div class="stat alt">
        <label>$ saved (max)</label>
        <div class="v pct" id="m-usd-total-max">$0</div>
        <div class="sub" id="m-usd-total-max-sub">$0/req</div>
      </div>
      <div class="stat">
        <label>Avg tokens requested</label>
        <div class="v in" id="m-avg-tok-in">0</div>
        <div class="sub" id="m-avg-tok-in-sub">0 forwarded avg</div>
      </div>
      <div class="stat mint">
        <label>Avg tokens saved</label>
        <div class="v saved" id="m-avg-tok-saved">0</div>
        <div class="sub" id="m-avg-tok-saved-sub">0 chars saved/req</div>
      </div>
      <div class="stat warm">
        <label>Request rate</label>
        <div class="v" id="m-req-rate">0/hr</div>
        <div class="sub" id="m-req-rate-sub">0 active</div>
      </div>
      <div class="stat alt">
        <label>Peak save %</label>
        <div class="v pct" id="m-peak-save">0%</div>
        <div class="sub" id="m-peak-save-sub">best bucket in window</div>
      </div>
      <div class="stat">
        <label>Models in mix</label>
        <div class="v" id="m-models">0</div>
        <div class="sub" id="m-models-sub">no traffic yet</div>
      </div>
      <div class="stat warm">
        <label>Sync calls</label>
        <div class="v" id="m-sync">0</div>
        <div class="sub" id="m-sync-sub">0 chars synced</div>
      </div>
      <div class="stat">
        <label>Noise traffic</label>
        <div class="v" id="m-noise">0</div>
        <div class="sub" id="m-noise-sub">0 ignored · 0 pass</div>
      </div>
      <div class="stat alt">
        <label>Blocked</label>
        <div class="v pct" id="m-blocked">0</div>
        <div class="sub" id="m-blocked-sub">0 unchanged</div>
      </div>
      <div class="stat mint">
        <label>Lifetime tokens saved</label>
        <div class="v saved" id="m-life-saved">0</div>
        <div class="sub" id="m-life-saved-sub">0 lifetime req</div>
      </div>
      <div class="stat">
        <label>Lifetime $ saved (actual)</label>
        <div class="v in" id="m-life-usd-actual">$0</div>
        <div class="sub" id="m-life-usd-actual-sub">all-time total</div>
      </div>
      <div class="stat alt">
        <label>Lifetime $ saved (max)</label>
        <div class="v pct" id="m-life-usd-max">$0</div>
        <div class="sub" id="m-life-usd-max-sub">all-time total</div>
      </div>
      <div class="stat mint">
        <label>Lifetime chars saved</label>
        <div class="v saved" id="m-life-chars">0</div>
        <div class="sub" id="m-life-chars-sub">0% removed</div>
      </div>
      <div class="stat">
        <label>Uptime</label>
        <div class="v" id="m-uptime">0m</div>
        <div class="sub" id="m-uptime-sub">this process</div>
      </div>
    </section>

    <section class="board">
      <div class="charts-stack">
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
      </div>
      <div class="pies">
        <div class="panel">
          <h2>Token disposition</h2>
          <div class="pie-wrap">
            <div id="pie-tokens" style="height:140px"></div>
            <div class="legend col" id="pie-tokens-legend"></div>
          </div>
        </div>
        <div class="panel">
          <h2>Traffic mix</h2>
          <div class="pie-wrap">
            <div id="pie-traffic" style="height:140px"></div>
            <div class="legend col" id="pie-traffic-legend"></div>
          </div>
        </div>
        <div class="panel">
          <div class="head">
            <h2>Models used</h2>
            <span class="hint" id="models-hint">by tokens requested</span>
          </div>
          <div class="pie-wrap">
            <div id="pie-models" style="height:140px"></div>
            <div class="legend col" id="pie-models-legend"></div>
          </div>
        </div>
      </div>
    </section>

    <section class="lower">
      <div class="panel">
        <div class="head">
          <h2>Recent requests</h2>
          <span class="hint" id="table-hint">filtered to window</span>
        </div>
        <div class="table-scroll" id="table-wrap"><div class="empty">Waiting for an agent or chat request…</div></div>
      </div>
    </section>

    <footer class="site-footer">
      <span>Universally Thinking | 2026</span>
      <span><a href="/">classic v1</a></span>
    </footer>
  </div>
<script>
"""
