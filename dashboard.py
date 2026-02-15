import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import altair as alt
from collections import deque
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# ------------------- Page config -------------------
st.set_page_config(page_title="Crypto Trade Bot Dashboard", layout="wide")

# ------------------- Auto-refresh -------------------
st_autorefresh(interval=10000, key="refresh")

# ------------------- Settings -------------------
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
WINDOW = 60

if "price_histories" not in st.session_state:
    st.session_state.price_histories = {
        s: deque(maxlen=WINDOW) for s in SYMBOLS
    }

# ------------------- Helpers -------------------
def get_price(symbol):
    try:
        r = requests.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
            timeout=5
        )
        return float(r.json()["price"])
    except:
        return None

def color_signal(val):
    if val == "BUY":
        return "color: green"
    if val == "SELL":
        return "color: red"
    return ""

# ------------------- UI -------------------
st.title("📈 Crypto Trade Bot Dashboard")
st.caption("Live prices • Auto-refresh every 10 seconds")

data = []

# ------------------- Logic -------------------
for symbol in SYMBOLS:
    price = get_price(symbol)
    if price is None:
        continue

    st.session_state.price_histories[symbol].append(price)
    history = list(st.session_state.price_histories[symbol])

    df = pd.DataFrame(history, columns=["close"])

    ema = rsi = signal = None

    if len(df) >= 14:
        df["EMA10"] = ta.ema(df["close"], length=10)
        df["RSI14"] = ta.rsi(df["close"], length=14)

        ema = df["EMA10"].iloc[-1]
        rsi = df["RSI14"].iloc[-1]

        if price > ema:
            signal = "BUY"
        elif price < ema:
            signal = "SELL"

    data.append({
        "Symbol": symbol,
        "Price": round(price, 2),
        "EMA(10)": round(ema, 2) if ema else None,
        "RSI(14)": round(rsi, 2) if rsi else None,
        "Signal": signal
    })

# ------------------- Table -------------------
df_display = pd.DataFrame(data)

if not df_display.empty:
    st.dataframe(df_display.style.map(color_signal, subset=["Signal"]))

# ------------------- Charts -------------------
st.subheader("📊 Price Charts")

for row in data:
    symbol = row["Symbol"]
    history = list(st.session_state.price_histories[symbol])

    if len(history) < 15:
        continue

    df = pd.DataFrame(history, columns=["Price"])
    df["Index"] = range(len(df))
    df["EMA10"] = ta.ema(df["Price"], length=10)

    price_line = alt.Chart(df).mark_line().encode(
        x="Index",
        y="Price"
    )

    ema_line = alt.Chart(df).mark_line(color="orange").encode(
        x="Index",
        y="EMA10"
    )

    st.altair_chart(price_line + ema_line, use_container_width=True)

