import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import altair as alt
from collections import deque
import json
import csv
import sqlite3
from datetime import datetime

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
st.set_page_config(page_title="Crypto Trade Bot Dashboard", layout="wide")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
COIN_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
}
MAX_HISTORY = 60

# --------------------------------------------------
# STATE
# --------------------------------------------------
if "price_histories" not in st.session_state:
    st.session_state.price_histories = {
        s: deque(maxlen=MAX_HISTORY) for s in SYMBOLS
    }

# --------------------------------------------------
# PRICE FETCH (FIXED)
# --------------------------------------------------
@st.cache_data(ttl=60)
def get_price(symbol):
    coin = COIN_MAP[symbol]
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()[coin]["usd"]
    except:
        return None

# --------------------------------------------------
# UI STYLE
# --------------------------------------------------
st.markdown("""
<style>
body { background:#0e0e0e; color:white; }
.price { color:#00f2ff; font-size:1.2rem; font-weight:bold; }
.buy { color:#39ff14; font-weight:bold; }
.sell { color:#ff4d4d; font-weight:bold; }
.card {
    background:#1e1e1e; padding:1rem; border-radius:10px;
    margin-bottom:1rem; box-shadow:0 0 15px rgba(0,255,255,0.2);
}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# HEADER
# --------------------------------------------------
st.title("📈 Crypto Trade Bot Dashboard")
st.caption("Live prices • EMA(10) • RSI(14)")

# --------------------------------------------------
# MAIN LOGIC
# --------------------------------------------------
rows = []

for symbol in SYMBOLS:
    price = get_price(symbol)
    history = st.session_state.price_histories[symbol]

    if price is not None:
        history.append(price)

    df = pd.DataFrame(history, columns=["close"])

    ema = ta.ema(df["close"], length=10).iloc[-1] if len(df) >= 10 else None
    rsi = ta.rsi(df["close"], length=14).iloc[-1] if len(df) >= 14 else None

    signal = ""
    if ema is not None:
        signal = "BUY" if price > ema else "SELL"

    rows.append({
        "Symbol": symbol,
        "Price": round(price, 2) if price else None,
        "EMA(10)": round(ema, 2) if ema else None,
        "RSI(14)": round(rsi, 2) if rsi else None,
        "Signal": signal
    })

    st.markdown(f"""
    <div class="card">
        <div class="price">{symbol}: ${price if price else "N/A"}</div>
        EMA(10): {ema if ema else "—"} | RSI(14): {rsi if rsi else "—"}<br>
        Signal: <span class="{signal.lower()}">{signal}</span>
    </div>
    """, unsafe_allow_html=True)

# --------------------------------------------------
# TABLE
# --------------------------------------------------
df_display = pd.DataFrame(rows)
st.subheader("📋 Signals")
st.dataframe(df_display, use_container_width=True)

# --------------------------------------------------
# CHARTS
# --------------------------------------------------
st.subheader("📊 Charts")

for symbol in SYMBOLS:
    history = list(st.session_state.price_histories[symbol])
    if len(history) < 15:
        continue

    df = pd.DataFrame(history, columns=["Price"])
    df["EMA10"] = ta.ema(df["Price"], length=10)
    df["Index"] = range(len(df))

    price_line = alt.Chart(df).mark_line(color="#00f2ff").encode(
        x="Index", y="Price"
    )

    ema_line = alt.Chart(df).mark_line(color="orange").encode(
        x="Index", y="EMA10"
    )

    st.altair_chart(price_line + ema_line, use_container_width=True)

# --------------------------------------------------
# PAPER TRADING (SAFE)
# --------------------------------------------------
portfolio_file = "portfolio.json"

try:
    with open(portfolio_file, "r") as f:
        portfolio = json.load(f)
except:
    portfolio = {"USD": 10000, "positions": {}}

for row in rows:
    if row["Signal"] == "BUY" and portfolio["USD"] >= row["Price"]:
        portfolio["USD"] -= row["Price"]
        portfolio["positions"][row["Symbol"]] = \
            portfolio["positions"].get(row["Symbol"], 0) + 1

with open(portfolio_file, "w") as f:
    json.dump(portfolio, f, indent=2)

st.subheader("💼 Paper Portfolio")
st.json(portfolio)


