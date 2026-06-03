"""
=============================================================
  MA Crossover Crypto Trading Bot — v3
  Upgrades over v2:
    ✅ Daily summary report  — emailed to you every morning
    ✅ Dashboard data file   — writes live data for the
                               web dashboard to read
=============================================================

HOW TO RUN:
  1. Install requirements:
       pip install requests

     For SMS also run:
       pip install twilio

  2. Fill in your settings below.

  3. Run the bot:
       python crypto_bot_v3.py

  4. Run the dashboard separately (different terminal window):
       python dashboard.py
       Then open http://localhost:5000 in your browser.
"""

import requests
import time
import json
import os
from datetime import datetime, date


# ─────────────────────────────────────────────
#  SETTINGS
# ─────────────────────────────────────────────

COINS = [
    "XRP_USD",   # 1,749.11 XRP on Ledger
    "HBAR_USD",  # 2,731.04 HBAR on Ledger
    "XLM_USD",   # 612.87 XLM on Ledger
    "DOGE_USD",  # 822.93 DOGE on Ledger
    "BTC_USD",   # Market reference
]

FAST_PERIOD    = 9
SLOW_PERIOD    = 21
TIMEFRAME      = "1h"
CHECK_INTERVAL = 3600

STARTING_CAPITAL   = 1000.00  # GBP
RISK_PER_TRADE_PCT = 10
STOP_LOSS_PCT      = 3.0

# --- GBP conversion ---
# Crypto.com prices are in USD. We convert everything to GBP for display.
# Update USD_TO_GBP if you want a fresher rate — or the bot fetches it automatically.
CURRENCY_SYMBOL = "£"
USD_TO_GBP      = 0.7508  # $1 USD = £0.7508 (live rate 2026-03-22)

# Daily summary — sent every morning at this hour (24h clock)
DAILY_SUMMARY_HOUR = 8   # 8 = 8:00 AM

# File the dashboard reads (keep default unless you change dashboard.py too)
DASHBOARD_DATA_FILE = "data/dashboard_data.json"

# Email
EMAIL_ENABLED  = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_FROM     = os.environ.get("EMAIL_FROM", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_TO       = os.environ.get("EMAIL_TO", "")

# SMS (Twilio)
SMS_ENABLED        = False
TWILIO_ACCOUNT_SID = "ACxxxxxxxxxxxxxxxx"
TWILIO_AUTH_TOKEN  = "your_auth_token"
TWILIO_FROM_NUMBER = "+15005550006"
SMS_TO_NUMBER      = "+447700000000"


# ─────────────────────────────────────────────
#  GOOGLE DRIVE STATE PERSISTENCE
#  Saves and loads portfolio state to Google Drive
#  so positions survive Railway restarts
# ─────────────────────────────────────────────

STATE_FILENAME = "crypto_bot_state.json"

def get_drive_service():
    """Authenticates with Google Drive using credentials from Railway env vars."""
    import pickle, base64
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_b64 = os.environ.get("GDRIVE_TOKEN_B64", "")
    client_b64 = os.environ.get("GDRIVE_CLIENT_B64", "")
    folder_id = os.environ.get("GDRIVE_FOLDER_ID", "")

    if not token_b64 or not folder_id:
        print("  [DRIVE] Env vars missing — state persistence disabled")
        return None, None

    token_data = base64.b64decode(token_b64.encode("utf-8"))
    creds = pickle.loads(token_data)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("drive", "v3", credentials=creds)
    return service, folder_id


def save_state_to_drive():
    """Saves the current portfolio state to Google Drive as a JSON file."""
    try:
        service, folder_id = get_drive_service()
        if not service:
            return

        from googleapiclient.http import MediaInMemoryUpload
        state = {
            "cash": paper_portfolio["cash"],
            "positions": paper_portfolio["positions"],
            "trade_log": paper_portfolio["trade_log"],
            "total_pnl": paper_portfolio["total_pnl"],
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        content = json.dumps(state, indent=2).encode("utf-8")
        media = MediaInMemoryUpload(content, mimetype="application/json")

        results = service.files().list(
            q=f"name='{STATE_FILENAME}' and '{folder_id}' in parents and trashed=false",
            fields="files(id)"
        ).execute()
        existing = results.get("files", [])

        if existing:
            service.files().update(fileId=existing[0]["id"], media_body=media).execute()
            print(f"  [DRIVE] State updated in Google Drive")
        else:
            metadata = {"name": STATE_FILENAME, "parents": [folder_id]}
            service.files().create(body=metadata, media_body=media).execute()
            print(f"  [DRIVE] State saved to Google Drive (new file)")

    except Exception as e:
        print(f"  [DRIVE ERROR] {e}")


def load_state_from_drive():
    """Loads portfolio state from Google Drive on startup."""
    try:
        service, folder_id = get_drive_service()
        if not service:
            return

        results = service.files().list(
            q=f"name='{STATE_FILENAME}' and '{folder_id}' in parents and trashed=false",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])

        if not files:
            print("  [DRIVE] No saved state found — starting fresh")
            return

        content = service.files().get_media(fileId=files[0]["id"]).execute()
        state = json.loads(content.decode("utf-8"))

        paper_portfolio["cash"] = state["cash"]
        paper_portfolio["positions"] = state["positions"]
        paper_portfolio["trade_log"] = state["trade_log"]
        paper_portfolio["total_pnl"] = state["total_pnl"]
        print(f"  [DRIVE] State loaded — cash: £{to_gbp(paper_portfolio['cash']):.2f}, positions: {len(paper_portfolio['positions'])}, trades: {len(paper_portfolio['trade_log'])}")

    except Exception as e:
        print(f"  [DRIVE ERROR] {e}")

# ─────────────────────────────────────────────
#  GBP CONVERSION
# ─────────────────────────────────────────────

def fetch_gbp_rate():
    """Fetches the latest USD to GBP rate from a free API. Falls back to hardcoded rate."""
    global USD_TO_GBP
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        rate = r.json()["rates"]["GBP"]
        USD_TO_GBP = rate
        print(f"  [FX] Live rate fetched: $1 USD = £{rate:.4f}")
    except Exception:
        print(f"  [FX] Could not fetch live rate — using £{USD_TO_GBP:.4f}")

def to_gbp(usd_amount):
    """Converts a USD amount to GBP."""
    return usd_amount * USD_TO_GBP

def gbp(usd_amount):
    """Formats a USD amount as GBP string e.g. £1,234.56"""
    return f"£{to_gbp(usd_amount):,.4f}" if usd_amount < 100 else f"£{to_gbp(usd_amount):,.2f}"


# ─────────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────────

paper_portfolio = {
    "cash":      STARTING_CAPITAL,
    "positions": {},
    "trade_log": [],
    "total_pnl": 0.0,
}

# Tracks whether we've sent today's summary already
_last_summary_date = None


# ─────────────────────────────────────────────
#  PRICE DATA
# ─────────────────────────────────────────────

def fetch_candles(instrument_name, timeframe="1h"):
    url = "https://api.crypto.com/exchange/v1/public/get-candlestick"
    params = {"instrument_name": instrument_name, "timeframe": timeframe, "count": 50}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        candles = sorted(r.json()["result"]["data"], key=lambda x: x["t"])
        return [float(c["c"]) for c in candles]
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] {instrument_name}: {e}")
        return None


# ─────────────────────────────────────────────
#  MOVING AVERAGES & SIGNALS
# ─────────────────────────────────────────────

def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def check_signal(prices):
    if len(prices) < SLOW_PERIOD + 1:
        return "HOLD"
    fast_now  = calculate_sma(prices,      FAST_PERIOD)
    slow_now  = calculate_sma(prices,      SLOW_PERIOD)
    fast_prev = calculate_sma(prices[:-1], FAST_PERIOD)
    slow_prev = calculate_sma(prices[:-1], SLOW_PERIOD)
    if None in (fast_now, slow_now, fast_prev, slow_prev):
        return "HOLD"
    if fast_now > slow_now and fast_prev <= slow_prev:
        return "BUY"
    if fast_now < slow_now and fast_prev >= slow_prev:
        return "SELL"
    return "HOLD"


# ─────────────────────────────────────────────
#  STOP-LOSS
# ─────────────────────────────────────────────

def check_stop_losses(current_prices):
    coins_to_stop = []
    for coin, pos in paper_portfolio["positions"].items():
        if coin in current_prices and current_prices[coin] <= pos["stop_loss_price"]:
            print(f"  [STOP-LOSS] {coin} hit stop at {gbp(pos['stop_loss_price'])} "
                  f"(current: {gbp(current_prices[coin])})")
            coins_to_stop.append((coin, current_prices[coin]))
    for coin, price in coins_to_stop:
        paper_sell(coin, price, reason="STOP-LOSS")


# ─────────────────────────────────────────────
#  POSITION SIZING
# ─────────────────────────────────────────────

def calculate_position_size():
    position_usd = STARTING_CAPITAL * (RISK_PER_TRADE_PCT / 100)
    return min(position_usd, paper_portfolio["cash"])


# ─────────────────────────────────────────────
#  PAPER TRADE EXECUTION
# ─────────────────────────────────────────────

def paper_buy(coin, price):
    if coin in paper_portfolio["positions"]:
        print(f"  [SKIP] Already holding {coin}")
        return
    position_usd = calculate_position_size()
    if position_usd < 1:
        print(f"  [SKIP] Not enough cash (${paper_portfolio['cash']:.2f})")
        return

    coins_bought      = position_usd / price
    stop_loss_price   = price * (1 - STOP_LOSS_PCT / 100)

    paper_portfolio["positions"][coin] = {
        "coins_held":      coins_bought,
        "buy_price":       price,
        "stop_loss_price": stop_loss_price,
        "position_value":  position_usd,
        "buy_time":        datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    paper_portfolio["cash"] -= position_usd
    log_trade("BUY", coin, price, 0, position_usd)

    print(f"  [PAPER BUY]  {coin} @ {gbp(price)} | "
          f"Spent: £{to_gbp(position_usd):.2f} | Stop: {gbp(stop_loss_price)}")

    send_alert(
        subject=f"BUY: {coin}",
        message=(f"BUY signal fired.\n\nCoin: {coin}\nPrice: {gbp(price)}\n"
                 f"Spent: £{to_gbp(position_usd):.2f}\nStop-loss: {gbp(stop_loss_price)}\n"
                 f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    )


def paper_sell(coin, price, reason="MA SIGNAL"):
    if coin not in paper_portfolio["positions"]:
        return
    pos      = paper_portfolio["positions"][coin]
    proceeds = pos["coins_held"] * price
    pnl      = proceeds - pos["position_value"]
    pnl_pct  = (pnl / pos["position_value"]) * 100

    paper_portfolio["cash"]      += proceeds
    paper_portfolio["total_pnl"] += pnl
    del paper_portfolio["positions"][coin]
    log_trade("SELL", coin, price, pnl, proceeds)

    outcome = "PROFIT" if pnl >= 0 else "LOSS"
    print(f"  [PAPER SELL] {coin} @ {gbp(price)} [{reason}] | "
          f"{outcome}: £{to_gbp(pnl):+.2f} ({pnl_pct:+.1f}%) | "
          f"Total P&L: £{to_gbp(paper_portfolio['total_pnl']):+.2f}")

    send_alert(
        subject=f"SELL: {coin} ({outcome} £{to_gbp(pnl):+.2f})",
        message=(f"SELL signal fired.\n\nCoin: {coin}\nReason: {reason}\n"
                 f"Price: {gbp(price)}\nP&L: £{to_gbp(pnl):+.2f} ({pnl_pct:+.1f}%)\n"
                 f"Total P&L: £{to_gbp(paper_portfolio['total_pnl']):+.2f}\n"
                 f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    )


def log_trade(action, coin, price, pnl, value):
    paper_portfolio["trade_log"].append({
        "time":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action": action,
        "coin":   coin,
        "price":  price,
        "pnl":    round(pnl, 4),
        "value":  round(value, 4),
    })


# ─────────────────────────────────────────────
#  ALERTS
# ─────────────────────────────────────────────

def send_email(subject, message):
    if not EMAIL_ENABLED:
        return
    try:
        import resend
        resend.api_key = os.environ.get("RESEND_API_KEY", "")
        resend.Emails.send({
            "from": "Crypto Bot <bot@senalai.com>",
            "to": [EMAIL_TO],
            "subject": f"[Crypto Bot] {subject}",
            "text": message,
        })
        print(f"  [EMAIL] Sent via Resend: {subject}")
    except Exception as e:
        print(f"  [EMAIL ERROR] {e}")


def send_sms(message):
    if not SMS_ENABLED:
        return
    try:
        from twilio.rest import Client
        Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN).messages.create(
            body=f"[Crypto Bot] {message}",
            from_=TWILIO_FROM_NUMBER,
            to=SMS_TO_NUMBER,
        )
        print(f"  [SMS] Sent to {SMS_TO_NUMBER}")
    except Exception as e:
        print(f"  [SMS ERROR] {e}")


def send_alert(subject, message):
    send_email(subject, message)
    send_sms(f"{subject}\n{message}")


# ─────────────────────────────────────────────
#  DAILY SUMMARY REPORT
#  Fires once per day at DAILY_SUMMARY_HOUR
# ─────────────────────────────────────────────

def build_daily_summary(current_prices):
    """Compiles today's trading activity into a readable report."""
    today_str = date.today().strftime("%Y-%m-%d")

    # Filter today's trades only
    today_trades = [
        t for t in paper_portfolio["trade_log"]
        if t["time"].startswith(today_str)
    ]
    sells_today  = [t for t in today_trades if t["action"] == "SELL"]
    buys_today   = [t for t in today_trades if t["action"] == "BUY"]
    pnl_today    = sum(t["pnl"] for t in sells_today)
    wins_today   = len([t for t in sells_today if t["pnl"] > 0])
    losses_today = len([t for t in sells_today if t["pnl"] <= 0])

    # All-time stats
    all_sells    = [t for t in paper_portfolio["trade_log"] if t["action"] == "SELL"]
    total_wins   = len([t for t in all_sells if t["pnl"] > 0])
    total_losses = len([t for t in all_sells if t["pnl"] <= 0])
    win_rate     = (total_wins / len(all_sells) * 100) if all_sells else 0

    # Unrealised P&L on open positions
    unrealised = 0
    open_positions_lines = []
    for coin, pos in paper_portfolio["positions"].items():
        curr = current_prices.get(coin)
        if curr:
            unr = (curr - pos["buy_price"]) * pos["coins_held"]
            unrealised += unr
            open_positions_lines.append(
                f"  • {coin}: bought @ {gbp(pos['buy_price'])} | "
                f"now {gbp(curr)} | unrealised £{to_gbp(unr):+.2f}"
            )

    # Build the report text
    lines = [
        f"Daily Summary — {today_str}",
        "=" * 40,
        "",
        "TODAY",
        f"  Trades:        {len(today_trades)} ({len(buys_today)} buys, {len(sells_today)} sells)",
        f"  P&L today:     £{to_gbp(pnl_today):+.2f}",
        f"  Wins / Losses: {wins_today}W / {losses_today}L",
        "",
        "ALL TIME",
        f"  Total P&L:     £{to_gbp(paper_portfolio['total_pnl']):+.2f}",
        f"  Win rate:      {win_rate:.0f}% ({total_wins}W / {total_losses}L)",
        f"  Cash left:     £{to_gbp(paper_portfolio['cash']):,.2f}",
        f"  Unrealised:    £{to_gbp(unrealised):+.2f}",
        "",
    ]

    if open_positions_lines:
        lines.append("OPEN POSITIONS")
        lines.extend(open_positions_lines)
        lines.append("")

    if today_trades:
        lines.append("TODAY'S TRADES")
        for t in today_trades:
            pnl_str = f"P&L: £{to_gbp(t['pnl']):+.2f}" if t["action"] == "SELL" else "entry"
            lines.append(f"  {t['time']} | {t['action']} {t['coin']} @ {gbp(t['price'])} | {pnl_str}")
        lines.append("")

    lines += [
        "─" * 40,
        "Bot is running. Next check in 1 hour.",
    ]

    return "\n".join(lines)


def maybe_send_daily_summary(current_prices):
    """Checks if it's time to send the daily summary and sends it if so."""
    global _last_summary_date

    now = datetime.now()
    today = date.today()

    # Only send once per day, at the configured hour
    if now.hour == DAILY_SUMMARY_HOUR and _last_summary_date != today:
        _last_summary_date = today
        report = build_daily_summary(current_prices)

        print("\n" + report)  # Always print to terminal

        send_email(
            subject=f"Daily Summary — {today.strftime('%Y-%m-%d')}",
            message=report
        )
        send_sms(
            f"Daily summary: P&L today £{to_gbp(sum(t['pnl'] for t in paper_portfolio['trade_log'] if t['time'].startswith(str(today)) and t['action'] == 'SELL')):+.2f} | "
            f"Total P&L £{to_gbp(paper_portfolio['total_pnl']):+.2f}"
        )


# ─────────────────────────────────────────────
#  DASHBOARD DATA FILE
#  Written every cycle — dashboard.py reads this
# ─────────────────────────────────────────────

def write_dashboard_data(current_prices, coin_stats):
    """
    Writes a JSON snapshot of the current bot state.
    The web dashboard reads this file and displays it.
    Updated every hour (or whenever the bot runs a cycle).
    """
    data = {
        "updated_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cash":             round(to_gbp(paper_portfolio["cash"]), 2),
        "total_pnl":        round(to_gbp(paper_portfolio["total_pnl"]), 4),
        "starting_capital": round(to_gbp(STARTING_CAPITAL), 2),
        "currency":         "GBP",
        "usd_to_gbp":       USD_TO_GBP,
        "positions":        {},
        "trade_log":        paper_portfolio["trade_log"][-50:],
        "coin_stats":       coin_stats,
        "settings": {
            "coins":             COINS,
            "fast_period":       FAST_PERIOD,
            "slow_period":       SLOW_PERIOD,
            "risk_per_trade":    RISK_PER_TRADE_PCT,
            "stop_loss_pct":     STOP_LOSS_PCT,
        }
    }

    # Add open positions with unrealised P&L
    for coin, pos in paper_portfolio["positions"].items():
        curr      = current_prices.get(coin)
        unrealised = ((curr - pos["buy_price"]) * pos["coins_held"]) if curr else 0
        data["positions"][coin] = {
            "buy_price":       round(to_gbp(pos["buy_price"]), 6),
            "current_price":   round(to_gbp(curr), 6) if curr else None,
            "coins_held":      round(pos["coins_held"], 6),
            "stop_loss_price": round(to_gbp(pos["stop_loss_price"]), 6),
            "position_value":  round(to_gbp(pos["position_value"]), 2),
            "unrealised_pnl":  round(to_gbp(unrealised), 4),
            "buy_time":        pos.get("buy_time", ""),
        }

    with open(DASHBOARD_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────
#  STATUS PRINT
# ─────────────────────────────────────────────

def print_status(current_prices=None):
    print("\n" + "─" * 55)
    print(f"  Portfolio — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("─" * 55)
    print(f"  Cash:           £{to_gbp(paper_portfolio['cash']):>10,.2f}")
    print(f"  Realised P&L:   £{to_gbp(paper_portfolio['total_pnl']):>+10,.2f}")
    if paper_portfolio["positions"]:
        print(f"  Open positions: {len(paper_portfolio['positions'])}")
        for coin, pos in paper_portfolio["positions"].items():
            curr = current_prices.get(coin) if current_prices else None
            unr  = ((curr - pos["buy_price"]) * pos["coins_held"]) if curr else 0
            curr_str = f"now {gbp(curr)} | unrealised £{to_gbp(unr):+.2f}" if curr else ""
            print(f"    • {coin:<12} bought @ {gbp(pos['buy_price'])} | {curr_str} | stop @ {gbp(pos['stop_loss_price'])}")
    print(f"  Trades done:    {len([t for t in paper_portfolio['trade_log'] if t['action'] == 'SELL'])}")
    print("─" * 55 + "\n")


def save_trade_log():
    filename = f"trade_log_{datetime.now().strftime('%Y%m%d')}.json"
    with open(filename, "w") as f:
        json.dump(paper_portfolio["trade_log"], f, indent=2)


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────

def run_bot():
    print("\n" + "=" * 55)
    print("  MA Crossover Bot v3 — PAPER TRADING MODE")
    print("─" * 55)
    print(f"  Coins:          {', '.join(COINS)}")
    print(f"  Strategy:       MA({FAST_PERIOD}) / MA({SLOW_PERIOD})")
    print(f"  Capital:        £{STARTING_CAPITAL:,.2f}")
    print(f"  Risk per trade: {RISK_PER_TRADE_PCT}%")
    print(f"  Stop-loss:      {STOP_LOSS_PCT}%")
    print(f"  Currency:       GBP (£)")
    print(f"  Daily summary:  {DAILY_SUMMARY_HOUR:02d}:00 daily")
    print(f"  Dashboard:      run dashboard.py → http://localhost:5000")
    print("=" * 55 + "\n")

    # Fetch live GBP rate on startup
    fetch_gbp_rate()
    load_state_from_drive()

    while True:
        print(f"[{datetime.now().strftime('%H:%M')}] Scanning {len(COINS)} coins...\n")

        current_prices = {}
        coin_stats     = {}

        for coin in COINS:
            print(f"  Checking {coin}...")
            prices = fetch_candles(coin, TIMEFRAME)
            if not prices:
                continue

            current_price = prices[-1]
            current_prices[coin] = current_price

            fast_ma = calculate_sma(prices, FAST_PERIOD)
            slow_ma = calculate_sma(prices, SLOW_PERIOD)
            signal  = check_signal(prices)
            trend   = "BULL" if (fast_ma and slow_ma and fast_ma > slow_ma) else "BEAR"
            ma_gap  = ((fast_ma - slow_ma) / slow_ma * 100) if fast_ma and slow_ma else 0

            coin_stats[coin] = {
                "price":    round(to_gbp(current_price), 6),
                "fast_ma":  round(to_gbp(fast_ma), 6) if fast_ma else None,
                "slow_ma":  round(to_gbp(slow_ma), 6) if slow_ma else None,
                "signal":   signal,
                "trend":    trend,
                "ma_gap":   round(ma_gap, 4),
            }

            print(f"  {gbp(current_price):>12} | Fast: {gbp(fast_ma)} | Slow: {gbp(slow_ma)} "
                  f"| Gap: {ma_gap:+.3f}% | {trend} | Signal: {signal}")

            if signal == "BUY":
                paper_buy(coin, current_price)
            elif signal == "SELL":
                paper_sell(coin, current_price)

        # Stop-loss check
        if paper_portfolio["positions"]:
            print("\n  Checking stop-losses...")
            check_stop_losses(current_prices)

        # Daily summary check
        maybe_send_daily_summary(current_prices)

        # Write dashboard data
        write_dashboard_data(current_prices, coin_stats)
        print(f"  [DASHBOARD] Data written to {DASHBOARD_DATA_FILE}")
        save_state_to_drive()

        print_status(current_prices)

        if paper_portfolio["trade_log"]:
            save_trade_log()

        print(f"  Next check in {CHECK_INTERVAL // 60} minutes. Press Ctrl+C to stop.\n")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n[STOPPED] Bot stopped.")
        print_status()
        save_trade_log()
