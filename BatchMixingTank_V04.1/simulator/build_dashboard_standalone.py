"""Build an offline copy of the VC_ARG_04 analytics dashboard.

The published dashboard runs inside claude.ai (Dashboard artifact type), which supplies the `dash` runtime.
This script wraps the same page (dashboard/index.html, calcs.js, charts.js) and the same data files with a
small stand-in for that runtime, so the dashboard can be opened in any browser without a connection.

Usage (from the repository root, after run_scenario.py):  python simulator/build_dashboard_standalone.py
"""
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / 'dashboard'
page = (D / 'index.html').read_text(encoding='utf-8')
calcs = (D / 'calcs.js').read_text(encoding='utf-8')
charts = (D / 'charts.js').read_text(encoding='utf-8')
d3 = (D / 'vendor' / 'd3.v7.min.js').read_text(encoding='utf-8')
report = json.loads((D / 'data' / 'VC_ARG_04_report_rows.json').read_text())
events = json.loads((D / 'data' / 'VC_ARG_04_events.json').read_text())
log = list(csv.DictReader(open(D / 'data' / 'VC_ARG_04_sim_log_5s.csv', encoding='utf-8')))

body = page.replace('<meta name="dash-one-writer">', '')
body = body.replace('<script src="calcs.js"></script>', '').replace('<script src="charts.js"></script>', '')

SHIM = r"""
window.dash = (() => {
  const raw = window.DASH_DATA, calcs = {}, cache = {}, draws = [];
  const api = {
    colors: ['#2f6fdf', '#e8862a', '#1aa39a', '#8b5cf6', '#d9488f', '#6b8e23', '#a0522d', '#4b5563'],
    calc(id, o) { calcs[id] = o; },
    data(id) {
      if (raw[id]) return { status: 'ok', data: raw[id], columns: Object.keys(raw[id][0] || {}) };
      if (calcs[id]) {
        if (!cache[id]) cache[id] = calcs[id].fn(...calcs[id].inputs.map((i) => api.data(i).data));
        return { status: 'ok', data: cache[id] };
      }
      return { status: 'missing', data: [] };
    },
    draw(name, fn) { draws.push([name, fn]); },
    onData(fn) { fn(); }, params() { return {}; }, setParams() {}, resetParams() {}, setLink() {}, refresh() {},
    _run() { for (const [n, fn] of draws) document.querySelectorAll(`[data-draw="${n}"]`).forEach((el) => { if (typeof fn === 'function') fn(el); }); },
  };
  return api;
})();
"""

CSS = """
:root { --color-fg: #172433; --color-fg-muted: #5b6878; --color-bg: #eef2f6; --color-panel: #ffffff; --color-border-line: #d6dee8;
  --color-ok: #1e8e3e; --color-warn: #b45309; --color-bad: #c62828;
  --font-anthropic-sans: Roboto, "Segoe UI", Arial, sans-serif; --font-anthropic-serif: Georgia, "Times New Roman", serif;
  --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 16px; --cds-gap-lg: 24px; --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 12px; --cds-pad-lg: 18px;
  --cds-radius: 8px; --cds-font-size-caption: 12px; --cds-font-size-body: 14px; --cds-font-size-heading: 16px; --cds-font-size-title: 30px;
  --cds-font-weight-medium: 500; --cds-chart-grid: #e6ebf1; --cds-chart-axis: #9aa6b4; --cds-chart-muted: #c3ccd7; --cds-chart-status-critical: #d6332a;
  --cds-chart-reference: #9aa6b4; --cds-surface-popover: #ffffff; --cds-border: #d6dee8; --cds-shadow-popover: 0 4px 14px rgba(20,40,70,.15);
  --cds-text-secondary: #5b6878; --cds-dur-slow: .3s; }
html, body { margin: 0; background: var(--color-bg); color: var(--color-fg); font-family: var(--font-anthropic-sans); font-size: 14px; }
#dash-root { padding: 24px; max-width: 1800px; margin: 0 auto; }
"""

html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VC_ARG_04 analytics (offline copy)</title>
<style>{CSS}</style></head>
<body><div id="dash-root">{body}</div>
<script>{d3}</script>
<script>window.DASH_DATA = {json.dumps(dict(report=report, events=events, log=log), separators=(',', ':'))};</script>
<script>{SHIM}</script>
<script>{calcs}</script>
<script>{charts}</script>
<script>dash._run(); let rt; addEventListener('resize', () => {{ clearTimeout(rt); rt = setTimeout(() => dash._run(), 150); }});</script>
</body></html>
"""
out = D / 'VC_ARG_04_dashboard_offline.html'
out.write_text(html, encoding='utf-8')
print('written', out, len(html))
