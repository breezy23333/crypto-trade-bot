# =========================
# Crypto Trade Bot Dashboard (FULL, LONG, FIXED, ALL FEATURES KEPT + ADDED)
# - Live prices (Binance + CoinGecko fallback)
# - EMA / RSI / MACD
# - Signals + Buy/Sell markers
# - Live charts (Altair)
# - Auto-refresh (10s)
# - CSV / JSONL / SQLite saving (no duplicate spam)
# - Paper trading + trade log
# - Optional Discord alerts (safe fallback)
# - Session-state persistence (CRITICAL)
# =========================

import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import altair as alt
from collections import deque
from streamlit_autorefresh import st_autorefresh
import csv
import json
import sqlite3
from datetime import datetime
import time
import random

# ------------------- MUST BE FIRST STREAMLIT CALL -------------------
st.set_page_config(page_title="Crypto Trade Bot", layout="wide")

# ------------------- Auto-refresh -------------------
st_autorefresh(interval=10_000, limit=None, key="refresh")  # every 10 seconds

# =========================
# SETTINGS / CONTROLS
# =========================
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
DEFAULT_MAXLEN = 240  # keep enough for indicators + smooth charts (about 40 min at 10s refresh)

SYMBOL_ICONS = {
    "BTCUSDT": "🟠",
    "ETHUSDT": "🔵",
    "BNBUSDT": "🟡",
    "SOLUSDT": "🟣",
    "XRPUSDT": "⚪",
    "ADAUSDT": "🔷",
}

# =========================
# SAFE FALLBACKS (NO CRASH)
# =========================
def send_discord_alert(webhook_url: str, message: str) -> bool:
    """
    Optional Discord alert. Safe: returns False if not configured or fails.
    """
    if not webhook_url or webhook_url.strip() == "" or "http" not in webhook_url:
        return False
    try:
        r = requests.post(webhook_url, json={"content": message}, timeout=6)
        return (200 <= r.status_code < 300)
    except Exception:
        return False


def execute_paper_trade(*args, **kwargs):
    # Kept as a placeholder in case you later split into modules
    return None


# =========================
# SESSION STATE (CRITICAL)
# =========================
if "symbols" not in st.session_state:
    st.session_state.symbols = DEFAULT_SYMBOLS.copy()

if "maxlen" not in st.session_state:
    st.session_state.maxlen = DEFAULT_MAXLEN

if "price_histories" not in st.session_state:
    st.session_state.price_histories = {
        sym: deque(maxlen=st.session_state.maxlen) for sym in st.session_state.symbols
    }

if "last_signal" not in st.session_state:
    st.session_state.last_signal = {sym: "" for sym in st.session_state.symbols}

if "live_price_data" not in st.session_state:
    st.session_state.live_price_data = []  # for the BTC live section

if "last_saved_key" not in st.session_state:
    st.session_state.last_saved_key = None

if "trade_log" not in st.session_state:
    st.session_state.trade_log = []  # [{time, symbol, side, price, qty, reason}]

if "portfolio" not in st.session_state:
    st.session_state.portfolio = {"USD": 10_000.0, "positions": {}}

if "db_initialized" not in st.session_state:
    st.session_state.db_initialized = False

if "last_alert_key" not in st.session_state:
    st.session_state.last_alert_key = None  # prevent alert spam every rerun

# =========================
# HELPERS (DB, SAVE, PORTFOLIO)
# =========================
DB_FILE = "signals.db"
CSV_FILE = "signals.csv"
JSONL_FILE = "signals.json"
PORTFOLIO_FILE = "portfolio.json"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            time TEXT,
            symbol TEXT,
            price REAL,
            ema_fast REAL,
            ema_slow REAL,
            rsi REAL,
            macd REAL,
            macd_signal REAL,
            macd_hist REAL,
            signal TEXT
        )
        """ 
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            time TEXT,
            symbol TEXT,
            side TEXT,
            price REAL,
            qty REAL,
            reason TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def reset_signals_table():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS signals")
    cur.execute("DROP TABLE IF EXISTS trades")
    conn.commit()
    conn.close()


def append_trade_db(trade_row: dict):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO trades (time, symbol, side, price, qty, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            trade_row["time"],
            trade_row["symbol"],
            trade_row["side"],
            float(trade_row["price"]),
            float(trade_row["qty"]),
            trade_row.get("reason", ""),
        ),
    )
    conn.commit()
    conn.close()


def save_signals_rows(rows: list[dict]):
    """
    Save to CSV + JSONL + SQLite. Safe and consistent.
    """
    # ---- CSV
    with open(CSV_FILE, mode="a", newline="") as f:
        fieldnames = [
            "Time", "Symbol", "Price",
            "EMA_Fast", "EMA_Slow", "RSI",
            "MACD", "MACD_Signal", "MACD_Hist",
            "Signal"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if f.tell() == 0:
            writer.writeheader()
        for r in rows:
    cur.execute(
        """
        INSERT INTO signals (
            time, symbol, price,
            ema_fast, ema_slow, rsi,
            macd, macd_signal, macd_hist,
            signal
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            r["Time"],
            r["Symbol"],
            float(r["Price"]) if r["Price"] is not None else None,
            float(r["EMA_Fast"]) if r["EMA_Fast"] is not None else None,
            float(r["EMA_Slow"]) if r["EMA_Slow"] is not None else None,
            float(r["RSI"]) if r["RSI"] is not None else None,
            float(r["MACD"]) if r["MACD"] is not None else None,
            float(r["MACD_Signal"]) if r["MACD_Signal"] is not None else None,
            float(r["MACD_Hist"]) if r["MACD_Hist"] is not None else None,
            r["Signal"],
        ),
    )


    # ---- JSONL
    with open(JSONL_FILE, mode="a") as f:
        for r in rows:
            json.dump(r, f)
            f.write("\n")

    # ---- SQLite
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """
            INSERT INTO signals (time, symbol, price, ema_fast, ema_slow, rsi, macd, macd_signal, macd_hist, signal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["Time"],
                r["Symbol"],
                r["Price"],
                r["EMA_Fast"],
                r["EMA_Slow"],
                r["RSI"],
                r["MACD"],
                r["MACD_Signal"],
                r["MACD_Hist"],
                r["Signal"],
            ),
        )
    conn.commit()
    conn.close()


def load_portfolio_from_disk():
    try:
        with open(PORTFOLIO_FILE, "r") as f:
            st.session_state.portfolio = json.load(f)
    except Exception:
        # keep defaults
        pass


def save_portfolio_to_disk():
    try:
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(st.session_state.portfolio, f, indent=2)
    except Exception:
        pass


def apply_paper_trade(symbol: str, price: float, side: str, qty: float, reason: str):
    """
    Simple paper-trading rules:
    - BUY: spend USD, add qty to positions
    - SELL: sell full qty or specified qty if available
    """
    pf = st.session_state.portfolio
    pf["positions"].setdefault(symbol, 0.0)

    if side == "BUY":
        cost = price * qty
        if pf["USD"] >= cost:
            pf["USD"] -= cost
            pf["positions"][symbol] += qty
            trade = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "side": "BUY",
                "price": float(price),
                "qty": float(qty),
                "reason": reason,
            }
            st.session_state.trade_log.append(trade)
            append_trade_db(trade)
            save_portfolio_to_disk()

    elif side == "SELL":
        available = pf["positions"].get(symbol, 0.0)
        sell_qty = min(qty, available)
        if sell_qty > 0:
            proceeds = price * sell_qty
            pf["USD"] += proceeds
            pf["positions"][symbol] = max(0.0, available - sell_qty)
            trade = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "side": "SELL",
                "price": float(price),
                "qty": float(sell_qty),
                "reason": reason,
            }
            st.session_state.trade_log.append(trade)
            append_trade_db(trade)
            save_portfolio_to_disk()


# =========================
# NETWORKING (BINANCE + COINGECKO FALLBACK)
# =========================
def _requests_get(url: str, timeout: float = 6.0):
    # A tiny wrapper to keep a consistent UA (helps some hosts)
    headers = {"User-Agent": "Mozilla/5.0"}
    return requests.get(url, headers=headers, timeout=timeout)


def get_price(symbol: str):
    """
    Try Binance first.
    Fallback to CoinGecko if Binance is blocked.
    Returns float or None.
    """

    # ---- Binance
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        r = _requests_get(url, timeout=6)
        if r.status_code == 200:
            data = r.json()
            if "price" in data:
                return float(data["price"])
    except Exception:
        pass

    # ---- CoinGecko fallback
    try:
        mapping = {
            "BTCUSDT": "bitcoin",
            "ETHUSDT": "ethereum",
            "BNBUSDT": "binancecoin",
            "SOLUSDT": "solana",
            "XRPUSDT": "ripple",
            "ADAUSDT": "cardano",
        }
        coin = mapping.get(symbol)
        if not coin:
            return None

        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"
        r = _requests_get(url, timeout=6)
        if r.status_code == 200:
            data = r.json()
            return float(data[coin]["usd"])
    except Exception:
        pass

    return None


# =========================
# INDICATORS / SIGNALS
# =========================
def compute_indicators(close_series: pd.Series, ema_fast_len=10, ema_slow_len=30, rsi_len=14):
    df = pd.DataFrame({"close": close_series})

    df["EMA_FAST"] = ta.ema(df["close"], length=ema_fast_len)
    df["EMA_SLOW"] = ta.ema(df["close"], length=ema_slow_len)
    df["RSI"] = ta.rsi(df["close"], length=rsi_len)

    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    # macd columns: MACD_12_26_9, MACDs_12_26_9, MACDh_12_26_9
    if macd is not None and not macd.empty:
        df["MACD"] = macd.iloc[:, 0]
        df["MACD_SIGNAL"] = macd.iloc[:, 1]
        df["MACD_HIST"] = macd.iloc[:, 2]
    else:
        df["MACD"] = None
        df["MACD_SIGNAL"] = None
        df["MACD_HIST"] = None

    return df


def generate_signal(latest_row: pd.Series, rsi_buy=45.0, rsi_sell=55.0):
    """
    A stable signal rule:
    - BUY when EMA_FAST > EMA_SLOW and RSI < rsi_sell and MACD_HIST >= 0
    - SELL when EMA_FAST < EMA_SLOW and RSI > rsi_buy and MACD_HIST <= 0
    - else HOLD
    """
    try:
        ema_fast = latest_row["EMA_FAST"]
        ema_slow = latest_row["EMA_SLOW"]
        rsi = latest_row["RSI"]
        macd_hist = latest_row["MACD_HIST"]

        if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(rsi) or pd.isna(macd_hist):
            return ""

        if (ema_fast > ema_slow) and (rsi <= rsi_sell) and (macd_hist >= 0):
            return "BUY"

        if (ema_fast < ema_slow) and (rsi >= rsi_buy) and (macd_hist <= 0):
            return "SELL"

        return "HOLD"
    except Exception:
        return ""


def color_signal(val):
    if val == "BUY":
        return "color: green"
    if val == "SELL":
        return "color: red"
    if val == "HOLD":
        return "color: #999"
    return ""


# =========================
# UI / STYLING (Kept + extra classes)
# =========================
st.markdown(
    """
<style>
body {
  background: radial-gradient(ellipse at center, #1c1c1c 0%, #000000 100%);
  animation: backgroundPulse 30s infinite;
}
@keyframes backgroundPulse {
  0% { background-color: #0e0e0e; }
  50% { background-color: #141414; }
  100% { background-color: #0e0e0e; }
}
html, body, [class*="css"]  {
  font-family: 'Segoe UI', sans-serif;
  background-color: #0e0e0e;
  color: #fff;
}
h1, h2, h3 { text-shadow: 0 0 10px #00f0ff; }

.signal-box {
  background-color: #1e1e1e;
  padding: 1rem;
  border-radius: 10px;
  margin-bottom: 1rem;
  box-shadow: 0 0 15px rgba(0,255,255,0.2);
  transition: 0.3s ease-in-out;
}
.signal-box:hover {
  transform: scale(1.02);
  box-shadow: 0 0 20px rgba(0,255,255,0.4);
}

.price-blink {
  animation: pulse 2s infinite;
  color: #0ff;
  font-weight: bold;
}
@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.4; }
  100% { opacity: 1; }
}

.stAlert {
  background-color: #d4af37 !important;
  color: black !important;
  font-weight: bold;
  border-radius: 10px;
  padding: 1em;
}

.badge {
  display:inline-block;
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  background: rgba(0,255,255,0.12);
  border: 1px solid rgba(0,255,255,0.25);
  margin-left: .4rem;
  font-size: .85rem;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# SIDEBAR CONTROLS
# =========================
st.sidebar.markdown("## ⚙️ Controls")

symbols_input = st.sidebar.text_input(
    "Symbols (comma-separated, Binance style)",
    value=",".join(st.session_state.symbols),
    help="Example: BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT",
)
maxlen = st.sidebar.slider("History Length", min_value=60, max_value=600, value=st.session_state.maxlen, step=20)

ema_fast_len = st.sidebar.slider("EMA Fast", 5, 30, 10, 1)
ema_slow_len = st.sidebar.slider("EMA Slow", 10, 80, 30, 1)
rsi_len = st.sidebar.slider("RSI Length", 7, 28, 14, 1)

rsi_buy = st.sidebar.slider("RSI Buy Threshold", 10.0, 60.0, 45.0, 1.0)
rsi_sell = st.sidebar.slider("RSI Sell Threshold", 40.0, 90.0, 55.0, 1.0)

paper_trade_on = st.sidebar.toggle("Enable Paper Trading", value=True)
trade_qty = st.sidebar.number_input("Paper Trade Qty (units)", value=1.0, step=0.5, min_value=0.1)

discord_webhook = st.sidebar.text_input("Discord Webhook (optional)", value="", type="password")
alerts_on = st.sidebar.toggle("Enable Discord Alerts", value=False)

st.sidebar.markdown("---")
st.sidebar.markdown("## 🔎 Debug Prices")

# Apply sidebar changes safely (rebuild histories only if needed)
parsed = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
if parsed != st.session_state.symbols or maxlen != st.session_state.maxlen:
    st.session_state.symbols = parsed if parsed else DEFAULT_SYMBOLS.copy()
    st.session_state.maxlen = maxlen

    # rebuild histories preserving what we can
    new_hist = {}
    for sym in st.session_state.symbols:
        old = st.session_state.price_histories.get(sym)
        dq = deque(maxlen=st.session_state.maxlen)
        if old:
            for v in list(old)[-st.session_state.maxlen :]:
                dq.append(v)
        new_hist[sym] = dq
    st.session_state.price_histories = new_hist

    # rebuild last_signal for new symbols
    for sym in st.session_state.symbols:
        st.session_state.last_signal.setdefault(sym, "")
    # remove last_signal entries for removed symbols
    for sym in list(st.session_state.last_signal.keys()):
        if sym not in st.session_state.symbols:
            del st.session_state.last_signal[sym]

# convenience locals
SYMBOLS = st.session_state.symbols
price_histories = st.session_state.price_histories

# Init DB once
if not st.session_state.db_initialized:
    reset_signals_table()   # ✅ wipes old broken schema
    init_db()               # ✅ recreates correct schema
    st.session_state.db_initialized = True


# Load portfolio once (if not loaded yet)
if "portfolio_loaded" not in st.session_state:
    load_portfolio_from_disk()
    st.session_state.portfolio_loaded = True

# =========================
# HEADER
# =========================
st.title("📈 Crypto Trade Bot Dashboard")
st.caption("Live Prices, Indicators, Signals, Charts, Storage, Paper Trading (Auto-refresh every 10 seconds)")

# =========================
# MAIN LOOP (FETCH ONCE PER SYMBOL)
# =========================
rows_for_table = []
rows_for_save = []
marker_rows = []  # for buy/sell markers on charts

now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

for symbol in SYMBOLS:
    icon = SYMBOL_ICONS.get(symbol, "💠")
    price = get_price(symbol)

    # debug sidebar
    st.sidebar.write(symbol, price)

    # store only numeric prices (never None)
    if isinstance(price, (int, float)):
        price_histories[symbol].append(float(price))

    # UI header card
    st.markdown(
        f"<div class='signal-box'>{icon} <b>{symbol}</b> "
        f"<span class='badge'>history {len(price_histories[symbol])}/{st.session_state.maxlen}</span></div>",
        unsafe_allow_html=True,
    )

    if price is not None:
        st.markdown(
            f"<div class='price-blink'>{symbol} – Current price: ${price:,.2f}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div class='price-blink'>{symbol} – Price unavailable</div>",
            unsafe_allow_html=True,
        )

    # build df
    history = [p for p in price_histories[symbol] if isinstance(p, (int, float))]
    df = pd.DataFrame(history, columns=["close"])

    ema_fast = ema_slow = rsi = macd_v = macd_s = macd_h = None
    signal = ""

    # indicators need enough points
    min_points = max(ema_slow_len + 5, 35)

    if len(df) >= min_points:
        ind = compute_indicators(df["close"], ema_fast_len=ema_fast_len, ema_slow_len=ema_slow_len, rsi_len=rsi_len)
        latest = ind.iloc[-1]

        ema_fast = float(latest["EMA_FAST"]) if pd.notna(latest["EMA_FAST"]) else None
        ema_slow = float(latest["EMA_SLOW"]) if pd.notna(latest["EMA_SLOW"]) else None
        rsi = float(latest["RSI"]) if pd.notna(latest["RSI"]) else None

        macd_v = float(latest["MACD"]) if pd.notna(latest["MACD"]) else None
        macd_s = float(latest["MACD_SIGNAL"]) if pd.notna(latest["MACD_SIGNAL"]) else None
        macd_h = float(latest["MACD_HIST"]) if pd.notna(latest["MACD_HIST"]) else None

        signal = generate_signal(latest, rsi_buy=rsi_buy, rsi_sell=rsi_sell)

        # BUY/SELL marker only when signal CHANGES into BUY/SELL
        prev = st.session_state.last_signal.get(symbol, "")
        if signal in ("BUY", "SELL") and signal != prev and isinstance(price, (int, float)):
            marker_rows.append(
                {
                    "Symbol": symbol,
                    "Index": len(history) - 1,
                    "Price": float(price),
                    "Marker": signal,
                }
            )

            # Optional alerts (no spam)
            alert_key = (symbol, signal, now_ts[:16], round(float(price), 2))
            if alerts_on and st.session_state.last_alert_key != alert_key:
                st.session_state.last_alert_key = alert_key
                msg = (
                    f"💹 {symbol} {signal}\n"
                    f"Price: {price}\n"
                    f"EMA({ema_fast_len}): {round(ema_fast,2) if ema_fast is not None else None}\n"
                    f"EMA({ema_slow_len}): {round(ema_slow,2) if ema_slow is not None else None}\n"
                    f"RSI({rsi_len}): {round(rsi,2) if rsi is not None else None}\n"
                    f"MACD_H: {round(macd_h,4) if macd_h is not None else None}\n"
                )
                send_discord_alert(discord_webhook, msg)

            # Paper trade
            if paper_trade_on:
                reason = f"Signal flip -> {signal} (EMA/RSI/MACD)"
                apply_paper_trade(symbol, float(price), signal, float(trade_qty), reason)

        st.session_state.last_signal[symbol] = signal

    # table row
    rows_for_table.append(
        {
            "Symbol": symbol,
            "Price": round(price, 4) if isinstance(price, (int, float)) else None,
            f"EMA({ema_fast_len})": round(ema_fast, 4) if isinstance(ema_fast, (int, float)) else None,
            f"EMA({ema_slow_len})": round(ema_slow, 4) if isinstance(ema_slow, (int, float)) else None,
            f"RSI({rsi_len})": round(rsi, 3) if isinstance(rsi, (int, float)) else None,
            "MACD": round(macd_v, 6) if isinstance(macd_v, (int, float)) else None,
            "MACD_Signal": round(macd_s, 6) if isinstance(macd_s, (int, float)) else None,
            "MACD_Hist": round(macd_h, 6) if isinstance(macd_h, (int, float)) else None,
            "Signal": signal,
        }
    )

    # save row (normalized columns)
    rows_for_save.append(
        {
            "Time": now_ts,
            "Symbol": symbol,
            "Price": float(price) if isinstance(price, (int, float)) else None,
            "EMA_Fast": float(ema_fast) if isinstance(ema_fast, (int, float)) else None,
            "EMA_Slow": float(ema_slow) if isinstance(ema_slow, (int, float)) else None,
            "RSI": float(rsi) if isinstance(rsi, (int, float)) else None,
            "MACD": float(macd_v) if isinstance(macd_v, (int, float)) else None,
            "MACD_Signal": float(macd_s) if isinstance(macd_s, (int, float)) else None,
            "MACD_Hist": float(macd_h) if isinstance(macd_h, (int, float)) else None,
            "Signal": signal,
        }
    )

# =========================
# TABLE
# =========================
st.subheader("📋 Live Table")
df_display = pd.DataFrame(rows_for_table)

if not df_display.empty:
    st.dataframe(df_display.style.map(color_signal, subset=["Signal"]), use_container_width=True)
else:
    st.warning("No data yet.")

# =========================
# CHARTS (NO REFETCH, USE HISTORY)
# =========================
st.subheader("📊 Live Charts (Price + EMA + Markers)")
marker_df = pd.DataFrame(marker_rows) if marker_rows else pd.DataFrame(columns=["Symbol", "Index", "Price", "Marker"])

for symbol in SYMBOLS:
    history = [p for p in price_histories[symbol] if isinstance(p, (int, float))]
    if len(history) < 20:
        st.info(f"{symbol}: waiting for more data ({len(history)}/20)…")
        continue

    dfc = pd.DataFrame({"close": history})
    dfc["Index"] = range(len(dfc))

    dfc["EMA_FAST"] = ta.ema(dfc["close"], length=ema_fast_len)
    dfc["EMA_SLOW"] = ta.ema(dfc["close"], length=ema_slow_len)

    base = alt.Chart(dfc).encode(x="Index")

    price_line = base.mark_line().encode(
        y=alt.Y("close", title="Price")
    ).properties(title=f"{symbol} • Price + EMA({ema_fast_len}/{ema_slow_len})")

    ema_fast_line = base.mark_line().encode(y="EMA_FAST")
    ema_slow_line = base.mark_line().encode(y="EMA_SLOW")

    # markers
    m = marker_df[marker_df["Symbol"] == symbol].copy()
    if not m.empty:
        markers = alt.Chart(m).mark_point(filled=True, size=110).encode(
            x="Index",
            y="Price",
            shape=alt.Shape("Marker", scale=alt.Scale(domain=["BUY", "SELL"], range=["triangle-up", "triangle-down"])),
            tooltip=["Marker", "Price", "Index"],
        )
        st.altair_chart(price_line + ema_fast_line + ema_slow_line + markers, use_container_width=True)
    else:
        st.altair_chart(price_line + ema_fast_line + ema_slow_line, use_container_width=True)

# =========================
# SAVE (CSV/JSONL/SQLITE) - NO DUPLICATE SPAM
# =========================
# Save key: minute + last prices snapshot
save_key = (
    datetime.now().strftime("%Y-%m-%d %H:%M"),
    tuple(pd.DataFrame(rows_for_save)["Price"].fillna(0).round(6).tolist()),
)

if st.session_state.last_saved_key != save_key:
    st.session_state.last_saved_key = save_key
    save_signals_rows(rows_for_save)

# =========================
# PAPER TRADING PORTFOLIO
# =========================
st.subheader("💼 Paper Trading Portfolio")

pf = st.session_state.portfolio
colA, colB = st.columns([1, 2])

with colA:
    st.metric("Cash (USD)", f"${pf['USD']:.2f}")
    if st.button("Reset Portfolio to $10,000"):
        st.session_state.portfolio = {"USD": 10_000.0, "positions": {}}
        st.session_state.trade_log = []
        save_portfolio_to_disk()
        st.success("Portfolio reset.")

with colB:
    st.write("**Positions**")
    st.json(pf.get("positions", {}))

st.write("**Trade Log (latest first)**")
if st.session_state.trade_log:
    tdf = pd.DataFrame(st.session_state.trade_log[::-1])
    st.dataframe(tdf, use_container_width=True)
else:
    st.info("No trades yet. Enable Paper Trading and wait for BUY/SELL flips.")

# =========================
# LIVE TRADE BOT SECTION (BTC LIVE + THRESHOLD) - NO BLOCKING LOOP
# =========================
st.subheader("📡 Live Trade Bot (BTCUSDT)")

THRESHOLD = st.number_input("Threshold (USD)", value=29500.0, step=100.0)
SYMBOL = "BTCUSDT"

live_price = get_price(SYMBOL)
if live_price is None:
    st.error("Failed to fetch live BTC price right now.")
else:
    st.success(f"{SYMBOL} Live Price: ${live_price:,.2f}")

    # store in session for live chart
    st.session_state.live_price_data.append(
        {"Time": datetime.now().strftime("%H:%M:%S"), "Price": float(live_price)}
    )
    st.session_state.live_price_data = st.session_state.live_price_data[-180:]  # keep last 180 points

    live_df = pd.DataFrame(st.session_state.live_price_data)

    # ✅ FIX: drop bad rows BEFORE charting
    live_df = live_df.dropna()
    live_df = live_df[
        live_df["Price"].apply(lambda x: isinstance(x, (int, float)))
    ]


    live_signal = "HOLD"
    if live_price > THRESHOLD:
        live_signal = "BUY"
    elif live_price < THRESHOLD:
        live_signal = "SELL"

    st.markdown(f"### 🔔 Live Signal: **{live_signal}**")

    live_chart = alt.Chart(live_df).mark_line().encode(
        x="Time",
        y="Price",
        tooltip=["Time", "Price"]
    ).properties(height=330, title=f"{SYMBOL} Live Price (last {len(live_df)} points)")

    if len(live_df) >= 2:
        st.altair_chart(live_chart, use_container_width=True)
    else:
        st.info("Waiting for valid live price data…")


# =========================
# SIGNAL SUMMARY CARDS
# =========================
st.subheader("📝 Signal Summary")

if not df_display.empty and "Signal" in df_display.columns:
    for _, row in df_display.iterrows():
        sig = row["Signal"] if row["Signal"] else "—"
        sig_color = "green" if sig == "BUY" else ("red" if sig == "SELL" else "#999")
        price_txt = row["Price"] if row["Price"] is not None else "—"

        st.markdown(
            f"""
            <div class="signal-box">
                <strong>{row['Symbol']}</strong><br>
                Price: <span class="price-blink">${price_txt}</span><br>
                EMA({ema_fast_len}): {row.get(f"EMA({ema_fast_len})")} |
                EMA({ema_slow_len}): {row.get(f"EMA({ema_slow_len})")}<br>
                RSI({rsi_len}): {row.get(f"RSI({rsi_len})")} |
                MACD_Hist: {row.get("MACD_Hist")}<br>
                Signal: <b style="color:{sig_color}">{sig}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.warning("No signal data available yet.")

# =========================
# DATA EXPORT + DB VIEW (BONUS)
# =========================
st.subheader("📦 Data Export & Database Peek")

col1, col2, col3 = st.columns(3)

with col1:
    try:
        with open(CSV_FILE, "rb") as f:
            st.download_button("⬇️ Download signals.csv", f, file_name="signals.csv")
    except Exception:
        st.info("CSV not created yet (wait one refresh).")

with col2:
    try:
        with open(JSONL_FILE, "rb") as f:
            st.download_button("⬇️ Download signals.json (jsonl)", f, file_name="signals.json")
    except Exception:
        st.info("JSONL not created yet (wait one refresh).")

with col3:
    try:
        with open(DB_FILE, "rb") as f:
            st.download_button("⬇️ Download signals.db", f, file_name="signals.db")
    except Exception:
        st.info("DB not created yet.")

# Quick DB peek
with st.expander("🔍 View latest 25 DB rows (signals)", expanded=False):
    conn = sqlite3.connect(DB_FILE)
    try:
        sdf = pd.read_sql_query(
            "SELECT * FROM signals ORDER BY time DESC LIMIT 25",
            conn
        )
        st.dataframe(sdf, use_container_width=True)
    finally:
        conn.close()

with st.expander("🔍 View latest 25 DB rows (trades)", expanded=False):
    conn = sqlite3.connect(DB_FILE)
    try:
        tdf = pd.read_sql_query(
            "SELECT * FROM trades ORDER BY time DESC LIMIT 25",
            conn
        )
        st.dataframe(tdf, use_container_width=True)
    finally:
        conn.close()

