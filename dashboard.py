"""
=============================================================
  Crypto Bot — Web Dashboard
  Reads dashboard_data.json written by crypto_bot_v3.py
=============================================================

HOW TO RUN:
  1. Install Flask:
       pip install flask

  2. Make sure crypto_bot_v3.py is running (in another terminal)

  3. Run the dashboard:
       python dashboard.py

  4. Open your browser:
       http://localhost:5000

  The dashboard auto-refreshes every 60 seconds.
"""

from flask import Flask, render_template_string
import json
import os
from datetime import datetime

app = Flask(__name__)

DASHBOARD_DATA_FILE = "dashboard_data.json"

# ─────────────────────────────────────────────
#  HTML TEMPLATE
#  The full dashboard UI — single file, no external CSS
# ─────────────────────────────────────────────

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>Crypto Bot Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    font-size: 14px;
    line-height: 1.6;
    padding: 24px;
  }

  h1 { font-size: 20px; font-weight: 600; color: #f8fafc; }
  h2 { font-size: 14px; font-weight: 500; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid #1e293b;
  }

  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: {% if data %}#22c55e{% else %}#ef4444{% endif %};
    display: inline-block; margin-right: 6px;
  }

  .updated { font-size: 12px; color: #64748b; }

  /* ── Stat cards ── */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 24px;
  }

  .stat-card {
    background: #1e293b;
    border-radius: 10px;
    padding: 16px;
    border: 1px solid #334155;
  }

  .stat-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
  .stat-value { font-size: 22px; font-weight: 600; color: #f8fafc; }
  .stat-value.positive { color: #22c55e; }
  .stat-value.negative { color: #ef4444; }
  .stat-value.neutral  { color: #f8fafc; }

  /* ── Sections ── */
  .section {
    background: #1e293b;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 20px;
    border: 1px solid #334155;
  }

  /* ── Coin cards ── */
  .coins-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
  }

  .coin-card {
    background: #0f1117;
    border-radius: 8px;
    padding: 14px;
    border: 1px solid #334155;
  }

  .coin-card.bull { border-left: 3px solid #22c55e; }
  .coin-card.bear { border-left: 3px solid #ef4444; }

  .coin-name  { font-size: 13px; font-weight: 600; color: #f8fafc; margin-bottom: 6px; }
  .coin-price { font-size: 18px; font-weight: 600; color: #f8fafc; margin-bottom: 8px; }

  .coin-meta {
    display: flex; flex-direction: column; gap: 3px;
    font-size: 11px; color: #64748b;
  }

  .signal-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 99px;
    font-size: 11px;
    font-weight: 600;
    margin-top: 8px;
  }

  .signal-badge.BUY  { background: #14532d; color: #4ade80; }
  .signal-badge.SELL { background: #450a0a; color: #f87171; }
  .signal-badge.HOLD { background: #1e293b; color: #64748b; border: 1px solid #334155; }

  /* ── Positions table ── */
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    text-align: left;
    padding: 8px 12px;
    font-size: 11px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #334155;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid #1e293b;
    color: #cbd5e1;
  }
  tr:last-child td { border-bottom: none; }
  td.positive { color: #22c55e; }
  td.negative { color: #ef4444; }
  td.neutral  { color: #94a3b8; }

  .empty-state {
    text-align: center;
    padding: 24px;
    color: #475569;
    font-size: 13px;
  }

  /* ── Chart ── */
  .chart-wrap { position: relative; height: 220px; margin-top: 8px; }

  /* ── Settings pills ── */
  .settings-row { display: flex; flex-wrap: wrap; gap: 8px; }
  .pill {
    background: #0f1117;
    border: 1px solid #334155;
    border-radius: 99px;
    padding: 4px 12px;
    font-size: 12px;
    color: #94a3b8;
  }
  .pill span { color: #f8fafc; font-weight: 500; }

  /* ── Two-col layout ── */
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
  @media (max-width: 768px) { .two-col { grid-template-columns: 1fr; } }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1><span class="status-dot"></span>Crypto Bot Dashboard</h1>
    <div class="updated">
      {% if data %}
        Last update: {{ data.updated_at }} &nbsp;·&nbsp; Auto-refreshes every 60s
      {% else %}
        Waiting for bot data — is crypto_bot_v3.py running?
      {% endif %}
    </div>
  </div>
  <div class="updated">Paper trading mode</div>
</div>

{% if data %}

<!-- ── Summary stats ── -->
{% set pnl = data.total_pnl %}
{% set pnl_pct = (pnl / data.starting_capital * 100) %}
{% set all_sells = data.trade_log | selectattr("action", "equalto", "SELL") | list %}
{% set wins = all_sells | selectattr("pnl", "gt", 0) | list | length %}
{% set total_trades = all_sells | length %}
{% set win_rate = (wins / total_trades * 100) if total_trades > 0 else 0 %}

<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-label">Portfolio value</div>
    <div class="stat-value neutral">£{{ "%.2f"|format(data.cash + data.positions.values()|sum(attribute='position_value')) }}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Total P&L</div>
    <div class="stat-value {{ 'positive' if pnl >= 0 else 'negative' }}">
      {{ '+' if pnl >= 0 else '' }}£{{ "%.2f"|format(pnl) }}
      ({{ '+' if pnl_pct >= 0 else '' }}{{ "%.1f"|format(pnl_pct) }}%)
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Cash available</div>
    <div class="stat-value neutral">£{{ "%.2f"|format(data.cash) }}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Win rate</div>
    <div class="stat-value {{ 'positive' if win_rate >= 50 else 'negative' }}">
      {{ "%.0f"|format(win_rate) }}%
      <span style="font-size:13px;font-weight:400;color:#64748b">({{ wins }}W / {{ total_trades - wins }}L)</span>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Open positions</div>
    <div class="stat-value neutral">{{ data.positions | length }}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Trades completed</div>
    <div class="stat-value neutral">{{ total_trades }}</div>
  </div>
</div>

<!-- ── Coin monitor ── -->
<div class="section">
  <h2>Live coin monitor</h2>
  <div class="coins-grid">
    {% for coin, stats in data.coin_stats.items() %}
    <div class="coin-card {{ stats.trend | lower }}">
      <div class="coin-name">{{ coin }}</div>
      <div class="coin-price">£{{ "%.4f"|format(stats.price) }}</div>
      <div class="coin-meta">
        <span>Fast MA (9):  £{{ "%.4f"|format(stats.fast_ma) if stats.fast_ma else '—' }}</span>
        <span>Slow MA (21): £{{ "%.4f"|format(stats.slow_ma) if stats.slow_ma else '—' }}</span>
        <span>MA gap: {{ '+' if stats.ma_gap >= 0 else '' }}{{ "%.3f"|format(stats.ma_gap) }}%</span>
      </div>
      <span class="signal-badge {{ stats.signal }}">{{ stats.signal }}</span>
    </div>
    {% endfor %}
  </div>
</div>

<div class="two-col">

  <!-- ── Open positions ── -->
  <div class="section">
    <h2>Open positions</h2>
    {% if data.positions %}
    <table>
      <thead>
        <tr>
          <th>Coin</th>
          <th>Buy price</th>
          <th>Current</th>
          <th>Unrealised</th>
          <th>Stop</th>
        </tr>
      </thead>
      <tbody>
        {% for coin, pos in data.positions.items() %}
        <tr>
          <td style="font-weight:600;color:#f8fafc">{{ coin }}</td>
          <td>£{{ "%.4f"|format(pos.buy_price) }}</td>
          <td>£{{ "%.4f"|format(pos.current_price) if pos.current_price else '—' }}</td>
          <td class="{{ 'positive' if pos.unrealised_pnl >= 0 else 'negative' }}">
            {{ '+' if pos.unrealised_pnl >= 0 else '' }}£{{ "%.2f"|format(pos.unrealised_pnl) }}
          </td>
          <td class="neutral">£{{ "%.4f"|format(pos.stop_loss_price) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty-state">No open positions</div>
    {% endif %}
  </div>

  <!-- ── P&L chart ── -->
  <div class="section">
    <h2>Cumulative P&L</h2>
    <div class="chart-wrap">
      <canvas id="pnlChart"></canvas>
    </div>
  </div>

</div>

<!-- ── Trade log ── -->
<div class="section">
  <h2>Recent trades</h2>
  {% if data.trade_log %}
  <table>
    <thead>
      <tr><th>Time</th><th>Action</th><th>Coin</th><th>Price</th><th>P&L</th></tr>
    </thead>
    <tbody>
      {% for trade in data.trade_log | reverse | list %}
      <tr>
        <td class="neutral">{{ trade.time }}</td>
        <td>
          <span class="signal-badge {{ trade.action }}">{{ trade.action }}</span>
        </td>
        <td style="font-weight:500;color:#f8fafc">{{ trade.coin }}</td>
        <td>£{{ "%.4f"|format(trade.price) }}</td>
        <td class="{{ 'positive' if trade.pnl > 0 else ('negative' if trade.pnl < 0 else 'neutral') }}">
          {% if trade.action == 'SELL' %}
            {{ '+' if trade.pnl >= 0 else '' }}£{{ "%.2f"|format(trade.pnl) }}
          {% else %}
            —
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty-state">No trades yet — waiting for signals</div>
  {% endif %}
</div>

<!-- ── Settings ── -->
<div class="section">
  <h2>Bot settings</h2>
  <div class="settings-row">
    <div class="pill">Strategy: <span>MA({{ data.settings.fast_period }}) / MA({{ data.settings.slow_period }})</span></div>
    <div class="pill">Currency: <span>GBP (£)</span></div>
    <div class="pill">Risk per trade: <span>{{ data.settings.risk_per_trade }}%</span></div>
    <div class="pill">Stop-loss: <span>{{ data.settings.stop_loss_pct }}%</span></div>
    <div class="pill">Coins: <span>{{ data.settings.coins | join(', ') }}</span></div>
  </div>
</div>

<!-- ── P&L Chart Script ── -->
<script>
const trades = {{ data.trade_log | tojson }};
const sells  = trades.filter(t => t.action === 'SELL');

let cumPnl = 0;
const labels = [];
const values = [];

sells.forEach(t => {
  cumPnl += t.pnl;
  labels.push(t.time);
  values.push(parseFloat(cumPnl.toFixed(2)));
});

if (labels.length === 0) {
  labels.push('Start');
  values.push(0);
}

const positive = values[values.length - 1] >= 0;

new Chart(document.getElementById('pnlChart'), {
  type: 'line',
  data: {
    labels,
    datasets: [{
      data: values,
      borderColor:     positive ? '#22c55e' : '#ef4444',
      backgroundColor: positive ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
      borderWidth: 2,
      pointRadius: 3,
      fill: true,
      tension: 0.3,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: ctx => ' £' + ctx.parsed.y.toFixed(2) } }
    },
    scales: {
      x: {
        ticks: { maxTicksLimit: 6, color: '#475569', font: { size: 11 } },
        grid:  { color: 'rgba(51,65,85,0.5)' }
      },
      y: {
        ticks: { callback: v => '£' + v.toFixed(2), color: '#475569', font: { size: 11 } },
        grid:  { color: 'rgba(51,65,85,0.5)' }
      }
    }
  }
});
</script>

{% else %}

<!-- No data state -->
<div class="section">
  <div class="empty-state" style="padding: 48px">
    <div style="font-size:32px;margin-bottom:16px">⏳</div>
    <div style="font-size:16px;color:#94a3b8;margin-bottom:8px">Waiting for bot data</div>
    <div>Make sure <strong>crypto_bot_v3.py</strong> is running in another terminal window.</div>
    <div style="margin-top:8px;color:#475569">This page refreshes automatically every 60 seconds.</div>
  </div>
</div>

{% endif %}

</body>
</html>
"""


# ─────────────────────────────────────────────
#  FLASK ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Serves the main dashboard page."""
    data = None
    if os.path.exists(DASHBOARD_DATA_FILE):
        try:
            with open(DASHBOARD_DATA_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = None
    return render_template_string(TEMPLATE, data=data)


@app.route("/api/data")
def api_data():
    """Returns raw JSON data — useful for building your own frontend later."""
    if os.path.exists(DASHBOARD_DATA_FILE):
        try:
            with open(DASHBOARD_DATA_FILE, "r") as f:
                return f.read(), 200, {"Content-Type": "application/json"}
        except IOError:
            pass
    return '{"error": "No data yet"}', 404, {"Content-Type": "application/json"}


# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 45)
    print("  Crypto Bot Dashboard")
    print("=" * 45)
    print(f"  Reading data from: {DASHBOARD_DATA_FILE}")
    print(f"  Open in browser:   http://localhost:5000")
    print(f"  Auto-refreshes:    every 60 seconds")
    print("=" * 45 + "\n")
    app.run(debug=False, port=5000)
