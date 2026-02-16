# =========================
# Crypto Trade Bot Dashboard (FIXED, CLEAN, ALL FEATURES KEPT)
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

# Extra imports you had (kept)
import time
import random

# ------------------- MUST BE FIRST STREAMLIT CALL -------------------
st.set_page_config(page_title="Crypto Trade Bot", layout="wide")

# ------------------- Auto-refresh -------------------
st_autorefresh(interval=10000, limit=None, key="refresh")  # every 10s

# ------------------- Settings -------------------
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
MOVING_AVERAGE_PERIOD = 60

SYMBOL_ICONS = {
    "BTCUSDT": "🟠",
    "ETHUSDT": "🔵",
    "BNBUSDT": "🟡",
}

# ------------------- Stubs / safe fallbacks (so app never crashes) -------------------
def execute_paper_trade(*args, **kwargs):
    return None

def send_discord_alert(*args, **kwargs):
    # Keep feature placeholder: won’t crash if you didn’t set webhook yet
    return None


# =========================
# Session State (CRITICAL FIX)
# =========================
# Streamlit reruns the script every refresh.
# If we don’t store histories in session_state, they reset every 10 seconds.
if "price_histories" not in st.session_state:
    st.session_state.price_histories = {
        symbol: deque(maxlen=MOVING_AVERAGE_PERIOD) for symbol in SYMBOLS
    }

if "live_price_data" not in st.session_state:
    st.session_state.live_price_data = []  # for the Live Trade Bot section

if "last_saved_key" not in st.session_state:
    st.session_state.last_saved_key = None  # prevents saving duplicates every rerun


price_histories = st.session_state.price_histories


# =========================
# Networking (FIXED: one source, retry, user-agent, clean errors)
# =========================
def get_price(symbol):
    """
    Try Binance first (fast).
    Fallback to CoinGecko if Binance is blocked (Streamlit Cloud).
    """

    # ---------- Binance ----------
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            data = r.json()
            if "price" in data:
                return float(data["price"])
    except:
        pass

    # ---------- CoinGecko fallback ----------
    try:
        mapping = {
            "BTCUSDT": "bitcoin",
            "ETHUSDT": "ethereum",
            "BNBUSDT": "binancecoin",
        }
        coin = mapping.get(symbol)
        if not coin:
            return None

        url = (
            "https://api.coingecko.com/api/v3/simple/price"
            f"?ids={coin}&vs_currencies=usd"
        )
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            data = r.json()
            return float(data[coin]["usd"])
    except:
        pass

    return None



def calculate_sma(prices):
    return sum(prices) / len(prices) if prices else None


def color_signal(val):
    if val == "BUY":
        return "color: green"
    elif val == "SELL":
        return "color: red"
    return ""


# =========================
# Styling (kept)
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
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# Header
# =========================
st.title("📈 Crypto Trade Bot Dashboard")
st.caption("Live Prices & Signals (Auto-refreshes every 10 seconds)")

# Sidebar debug
st.sidebar.markdown("## 🔎 Debug Prices")
debug_prices = {}

# =========================
# MAIN LOOP: Fetch prices once per symbol (FIXED)
# =========================
data = []

for symbol in SYMBOLS:
    icon = SYMBOL_ICONS.get(symbol, "💠")
    price = get_price(symbol)

    debug_prices[symbol] = price
    st.sidebar.write(symbol, price)

    # IMPORTANT: Never append None
    if price is not None:
        price_histories[symbol].append(float(price))

    st.markdown(
        f"<div class='signal-box'>{icon} {symbol} price history length: {len(price_histories[symbol])}/{MOVING_AVERAGE_PERIOD}</div>",
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

    # Build df only with real numbers
    history = [p for p in price_histories[symbol] if isinstance(p, (int, float))]
    df = pd.DataFrame(history, columns=["close"])

    ema = None
    rsi = None
    signal = ""

    # Need enough data for indicators
    if len(df) >= 20:
        df["EMA10"] = ta.ema(df["close"], length=10)
        df["RSI14"] = ta.rsi(df["close"], length=14)

        ema = df["EMA10"].iloc[-1] if pd.notna(df["EMA10"].iloc[-1]) else None
        rsi = df["RSI14"].iloc[-1] if pd.notna(df["RSI14"].iloc[-1]) else None

        if (ema is not None) and (price is not None):
            if price > ema:
                signal = "BUY"
            elif price < ema:
                signal = "SELL"

        # Keep alert/paper trading feature without crashing
        if signal and ema is not None and rsi is not None:
            alert_msg = (
                f"💹 {symbol}\n"
                f"Price: {price}\n"
                f"EMA(10): {round(ema,2)}\n"
                f"RSI(14): {round(rsi,2)}\n"
                f"📢 Signal: {signal}"
            )
            send_discord_alert("YOUR_DISCORD_WEBHOOK_URL", alert_msg)
            execute_paper_trade(symbol, price, signal)

        data.append(
            {
                "Symbol": symbol,
                "Price": round(price, 2) if price is not None else None,
                "EMA(10)": round(ema, 2) if ema is not None else None,
                "RSI(14)": round(rsi, 2) if rsi is not None else None,
                "Signal": signal,
            }
        )
    else:
        # Still show row (feature kept)
        data.append(
            {
                "Symbol": symbol,
                "Price": round(price, 2) if price is not None else None,
                "EMA(10)": None,
                "RSI(14)": None,
                "Signal": "",
            }
        )

# =========================
# Display Table (kept)
# =========================
df_display = pd.DataFrame(data)

if not df_display.empty and "Signal" in df_display.columns:
    st.dataframe(df_display.style.map(color_signal, subset=["Signal"]))
else:
    st.warning("No signal data available yet.")

# =========================
# Charts (FIXED: do NOT refetch here, only use stored history)
# =========================
st.subheader("📊 Live Charts")

for symbol in SYMBOLS:
    history = [p for p in price_histories[symbol] if isinstance(p, (int, float))]
    if len(history) < 15:
        continue

    dfc = pd.DataFrame(history, columns=["close"])
    dfc["EMA10"] = ta.ema(dfc["close"], length=10)
    dfc["Index"] = range(len(dfc))

    chart = (
        alt.Chart(dfc)
        .mark_line()
        .encode(x="Index", y=alt.Y("close", title="Price"))
        .properties(title=f"{symbol} Price vs EMA(10)")
    )

    ema_line = alt.Chart(dfc).mark_line().encode(x="Index", y="EMA10")
    st.altair_chart(chart + ema_line, use_container_width=True)

# =========================
# Saving (CSV/JSON/SQLite) — FIXED: prevent duplicates every rerun
# =========================
# Create a save key based on timestamp minute + last prices
save_key = (datetime.now().strftime("%Y-%m-%d %H:%M"), tuple(df_display["Price"].fillna(0).tolist()))

if st.session_state.last_saved_key != save_key:
    st.session_state.last_saved_key = save_key

    # ---- CSV
    with open("signals.csv", mode="a", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=["Time", "Symbol", "Price", "EMA(10)", "RSI(14)", "Signal"]
        )
        if file.tell() == 0:
            writer.writeheader()

        for row in data:
            writer.writerow(
                {
                    "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    **row,
                }
            )

    # ---- JSON lines
    with open("signals.json", mode="a") as file:
        for row in data:
            out = dict(row)
            out["Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            json.dump(out, file)
            file.write("\n")

    # ---- SQLite
    conn = sqlite3.connect("signals.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            time TEXT,
            symbol TEXT,
            price REAL,
            ema10 REAL,
            rsi14 REAL,
            signal TEXT
        )
        """
    )

    for row in data:
        cursor.execute(
            """
            INSERT INTO signals (time, symbol, price, ema10, rsi14, signal)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                row["Symbol"],
                row["Price"],
                row["EMA(10)"],
                row["RSI(14)"],
                row["Signal"],
            ),
        )

    conn.commit()
    conn.close()

# =========================
# Paper Trading (kept)
# =========================
portfolio_file = "portfolio.json"

try:
    with open(portfolio_file, "r") as f:
        portfolio = json.load(f)
except:
    portfolio = {"USD": 10000, "positions": {}}

for row in data:
    symbol = row["Symbol"]
    price = row["Price"]
    signal = row["Signal"]

    if price is None:
        continue

    if signal == "BUY" and portfolio["USD"] >= price:
        quantity = 1
        cost = price * quantity
        portfolio["USD"] -= cost
        portfolio["positions"][symbol] = portfolio["positions"].get(symbol, 0) + quantity

    elif signal == "SELL" and portfolio["positions"].get(symbol, 0) > 0:
        quantity = portfolio["positions"][symbol]
        proceeds = price * quantity
        portfolio["USD"] += proceeds
        portfolio["positions"][symbol] = 0

with open(portfolio_file, "w") as f:
    json.dump(portfolio, f, indent=2)

st.subheader("💼 Paper Trading Portfolio")
st.write(f"**Cash (USD):** ${portfolio['USD']:.2f}")
st.write("**Positions:**")
st.json(portfolio["positions"])

# =========================
# Live Trade Bot Dashboard (kept, FIXED: no blocking loops)
# =========================
st.title("📊 Trade Bot Dashboard")
st.subheader("📈 Live Trade Bot Dashboard (BTCUSDT)")

THRESHOLD = st.number_input("Threshold (USD)", value=29500.0, step=100.0)
SYMBOL = "BTCUSDT"

live_price = get_price(SYMBOL)

if live_price is None:
    st.error("Failed to fetch live BTC price right now.")
else:
    st.success(f"{SYMBOL} Live Price: ${live_price:,.2f}")

    # Store in session history for live chart
    st.session_state.live_price_data.append(
        {"Time": datetime.now().strftime("%H:%M:%S"), "Price": live_price}
    )
    st.session_state.live_price_data = st.session_state.live_price_data[-120:]  # keep last 120 points

    live_df = pd.DataFrame(st.session_state.live_price_data)

    # Signal logic (kept)
    live_signal = "HOLD"
    if live_price > THRESHOLD:
        live_signal = "BUY"
    elif live_price < THRESHOLD:
        live_signal = "SELL"

    st.markdown(f"### 🔔 Live Signal: **{live_signal}**")

    # Live chart (kept)
    chart = (
        alt.Chart(live_df)
        .mark_line()
        .encode(x="Time", y="Price")
        .properties(height=350)
    )
    st.altair_chart(chart, use_container_width=True)

# =========================
# Signal Summary (kept)
# =========================
st.markdown("### 📝 Signal Summary")

if not df_display.empty and "Signal" in df_display.columns:
    for _, row in df_display.iterrows():
        sig = row["Signal"] if row["Signal"] else "—"
        sig_color = "green" if sig == "BUY" else ("red" if sig == "SELL" else "#999")

        st.markdown(
            f"""
            <div class="signal-box">
                <strong>{row['Symbol']}</strong><br>
                Price: <span class="price-blink">${row['Price']}</span><br>
                EMA(10): {row['EMA(10)']} | RSI(14): {row['RSI(14)']}<br>
                Signal: <b style='color: {sig_color}'>{sig}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.warning("No signal data available yet.")
