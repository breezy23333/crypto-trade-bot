import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import altair as alt
from collections import deque
from streamlit_autorefresh import st_autorefresh

# ------------------- Page config -------------------
st.set_page_config(page_title="Crypto Trade Bot Dashboard", layout="wide")

# ------------------- Auto-refresh -------------------
st_autorefresh(interval=10000, key="refresh")

# ------------------- Settings -------------------
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
WINDOW = 60
price_histories = {s: deque(maxlen=WINDOW) for s in SYMBOLS}

# ------------------- Helpers -------------------
def get_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    r = requests.get(url, timeout=5)
    return float(r.json()["price"])

# ------------------- UI -------------------
st.title("📈 Crypto Trade Bot Dashboard")
st.caption("Live prices • EMA • RSI • Demo version")

rows = []

for symbol in SYMBOLS:
    price = get_price(symbol)
    price_histories[symbol].append(price)

    df = pd.DataFrame(price_histories[symbol], columns=["close"])
    if len(df) > 14:
        df["EMA10"] = ta.ema(df["close"], length=10)
        df["RSI14"] = ta.rsi(df["close"], length=14)

        ema = df["EMA10"].iloc[-1]
        rsi = df["RSI14"].iloc[-1]

        signal = "BUY" if price > ema else "SELL"

        rows.append({
            "Symbol": symbol,
            "Price": round(price, 2),
            "EMA(10)": round(ema, 2),
            "RSI(14)": round(rsi, 2),
            "Signal": signal
        })

        chart = alt.Chart(df.reset_index()).mark_line().encode(
            x="index",
            y="close"
        ).properties(title=symbol)

        st.altair_chart(chart, use_container_width=True)

# ------------------- Table -------------------
if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
