import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import altair as alt
import random

from collections import deque
from streamlit_autorefresh import st_autorefresh
import csv
import json
import sqlite3
from datetime import datetime


# ------------------- Auto-refresh -------------------
st_autorefresh(interval=10000, limit=None, key="refresh")

# ------------------- Settings -------------------
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
MOVING_AVERAGE_PERIOD = 60
price_histories = {symbol: deque(maxlen=MOVING_AVERAGE_PERIOD) for symbol in SYMBOLS}

# ------------------- Functions -------------------
def get_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url)
        data = response.json()
        return float(data['price'])
    except:
        return None

def calculate_sma(prices):
    return sum(prices) / len(prices) if prices else None

def color_signal(val):
    if val == "BUY":
        return "color: green"
    elif val == "SELL":
        return "color: red"
    return ""

# ------------------- Streamlit Layout -------------------
for symbol in SYMBOLS:

    SYMBOL_ICONS = {
    "BTCUSDT": "🟠",
    "ETHUSDT": "🔵",
    "BNBUSDT": "🟡"
}

st.markdown("""
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

.signal-box {
    opacity: 0;
    animation: fadeIn 1s forwards;
}

@keyframes fadeIn {
    to { opacity: 1; }
}
    
    /* Custom Fonts & Layout */
    html, body, [class*="css"]  {
        font-family: 'Segoe UI', sans-serif;
        background-color: #0e0e0e;
        color: #fff;
    }

    /* Title Glow */
    h1, h2, h3 {
        text-shadow: 0 0 10px #00f0ff;
    }

    /* Signal Box */
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

    /* Price Flash */
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

    /* Warning box */
    .stAlert {
        background-color: #d4af37 !important;
        color: black !important;
        font-weight: bold;
        border-radius: 10px;
        padding: 1em;
    }

    /* Emoji headers */
    .stMarkdown h3 {
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    /* 🎯 Signal Card Styles */
    .signal-card {
    background: linear-gradient(145deg, #111, #1a1a1a);
    border: 1px solid #333;
    padding: 1rem;
    margin-bottom: 1.2rem;
    border-radius: 12px;
    box-shadow: 0 0 12px rgba(0, 255, 255, 0.1);
    transition: all 0.3s ease;
    }
    .signal-card:hover {
    box-shadow: 0 0 20px rgba(0, 255, 255, 0.4);
    transform: scale(1.02);
    }

    /* Symbol Style */
    .signal-symbol {
    font-size: 1.3rem;
    font-weight: bold;
    color: #00f2ff;
    }

    /* Price Text */
    .signal-price {
    color: #39ff14;
    }

    /* Meta (history length) */
    .signal-meta {
    color: #999;
    font-size: 0.9rem;
    margin-top: 0.3rem;
    letter-spacing: 0.5px;
    }

    </style>
""", unsafe_allow_html=True)

st.title("📈 Crypto Trade Bot Dashboard")
st.caption("Live Prices & Signals (Auto-refreshes every 10 seconds)")

data = []

# ------------------- Logic -------------------
data = []

for symbol in SYMBOLS:
    price = get_price(symbol)
    price_histories[symbol].append(price)
    st.write(f"{symbol} price history length: {len(price_histories[symbol])}/14")
    
    st.markdown(f"<div class='signal-box'>{symbol} price history length: {len(price_histories[symbol])}/14</div>", unsafe_allow_html=True)
    if price is not None:
        st.markdown(
            f"<div class='price-blink'>{symbol} – Current price: ${price:.2f}</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"<div class='price-blink'>{symbol} – Price unavailable</div>",
            unsafe_allow_html=True
                )


    if price is not None:
        price_histories[symbol].append(price)

    
    st.write(f"{symbol} - Current price: {price}")
    st.write(price_histories[symbol])

    df = pd.DataFrame(list(price_histories[symbol]), columns=["close"])

    ema = None
    rsi = None
    signal = ""

    if len(df) >= 3:
        df["EMA10"] = ta.ema(df["close"], length=10)
        df["RSI14"] = ta.rsi(df["close"], length=14)

        ema = df["EMA10"].iloc[-1] if not df["EMA10"].isnull().all() else None
        rsi = df["RSI14"].iloc[-1] if not df["RSI14"].isnull().all() else None

        if price > ema:
            signal = "BUY"
        elif price < ema:
            signal = "SELL"

        if signal:
            alert_msg = f"💹 {symbol}\nPrice: {price}\nEMA(10): {round(ema,2)}\nRSI(14): {round(rsi,2)}\n📢 Signal: {signal}"
            send_discord_alert("YOUR_DISCORD_WEBHOOK_URL", alert_msg)
            execute_paper_trade(symbol, price, signal)

        data.append({
            "Symbol": symbol,
            "Price": round(price, 2),
            "EMA(10)": round(ema, 2) if ema else None,
            "RSI(14)": round(rsi, 2) if rsi else None,
            "Signal": signal
        })



# ------------------- Display Table -------------------
df_display = pd.DataFrame(data)

if not df_display.empty and "Signal" in df_display.columns:
    st.dataframe(df_display.style.map(color_signal, subset=['Signal']))
else:
    st.warning("No signal data available yet.")

# ------------------- Charts -------------------
st.subheader("📊 Live Charts")

for symbol in SYMBOLS:
    price = get_price(symbol)
    price_histories[symbol].append(price)

    history = list(price_histories[symbol])
    if len(history) < 15:
        continue

    df = pd.DataFrame(history, columns=["close"])
    df["EMA10"] = ta.ema(df["close"], length=10)
    df["Index"] = range(len(df))

    chart = alt.Chart(df).mark_line().encode(
        x="Index",
        y=alt.Y("close", title="Price"),
        color=alt.value("steelblue")
    ).properties(title=f"{symbol} Price vs EMA(10)")

    ema_line = alt.Chart(df).mark_line(color="orange").encode(
        x="Index",
        y="EMA10"
    )

    st.altair_chart(chart + ema_line, use_container_width=True)

# ------------------- Save to CSV -------------------
with open("signals.csv", mode="a", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=["Time", "Symbol", "Price", "EMA(10)", "RSI(14)", "Signal"])
    if file.tell() == 0:
        writer.writeheader()
    for row in data:
        writer.writerow({
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **row
        })

# ------------------- Save to JSON -------------------
with open("signals.json", mode="a") as file:
    for row in data:
        row["Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        json.dump(row, file)
        file.write("\n")

# ------------------- Save to SQLite -------------------
conn = sqlite3.connect("signals.db")
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS signals (
        time TEXT,
        symbol TEXT,
        price REAL,
        ema10 REAL,
        rsi14 REAL,
        signal TEXT
    )
''')

for row in data:
    cursor.execute('''
        INSERT INTO signals (time, symbol, price, ema10, rsi14, signal)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        row["Symbol"],
        row["Price"],
        row["EMA(10)"],
        row["RSI(14)"],
        row["Signal"]
    ))

conn.commit()
conn.close()

# ------------------- Paper Trading -------------------
portfolio_file = "portfolio.json"

# Load or initialize portfolio
try:
    with open(portfolio_file, "r") as f:
        portfolio = json.load(f)
except:
    portfolio = {"USD": 10000, "positions": {}}

# Simulate trades
for row in data:
    symbol = row["Symbol"]
    price = row["Price"]
    signal = row["Signal"]

    # Buy logic
    if signal == "BUY" and portfolio["USD"] >= price:
        quantity = 1  # Buy 1 unit
        cost = price * quantity
        portfolio["USD"] -= cost
        portfolio["positions"][symbol] = portfolio["positions"].get(symbol, 0) + quantity

    # Sell logic
    elif signal == "SELL" and portfolio["positions"].get(symbol, 0) > 0:
        quantity = portfolio["positions"][symbol]
        proceeds = price * quantity
        portfolio["USD"] += proceeds
        portfolio["positions"][symbol] = 0

# Save portfolio
with open(portfolio_file, "w") as f:
    json.dump(portfolio, f, indent=2)

# Show portfolio
st.subheader("💼 Paper Trading Portfolio")
st.write(f"**Cash (USD):** ${portfolio['USD']:.2f}")
st.write("**Positions:**")
st.json(portfolio["positions"])

# Store history
price_history = []
signal_history = []

st.title("📊 Trade Bot Dashboard")

# Settings
threshold = 29500.0
moving_average = 29500.0
last_signal = None

price_placeholder = st.empty()
chart_placeholder = st.empty()

price_data = []

for i in range(300):  # adjust how long it runs
    mock_price = random.uniform(-1, 1)
    moving_average += mock_price

    # Add to history
    price_data.append({"Time": i, "Price": moving_average})
    df = pd.DataFrame(price_data)

    # Show latest price
    price_placeholder.markdown(f"### Current Price: **{moving_average:.2f}**")

    # Determine signal
    signal = None
    if moving_average > threshold and last_signal != "BUY":
        signal = "BUY"
        last_signal = "BUY"
    elif moving_average < threshold and last_signal != "SELL":
        signal = "SELL"
        last_signal = "SELL"

    # Plot chart
    chart = alt.Chart(df).mark_line().encode(
        x="Time",
        y="Price"
    ).properties(height=300)

    chart_placeholder.altair_chart(chart, use_container_width=True)

    time.sleep(0.5)
    
# Set symbol and threshold
SYMBOL = "BTCUSDT"
THRESHOLD = 29500.0 # You’ll adjust this based on real price later
last_signal = None
price_data = []

# Binance price fetcher
def get_binance_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url)
        data = response.json()
        return float(data["price"])
    except:
        return None

st.set_page_config(page_title="Live Trade Bot", layout="wide")
st.title("📈 Live Trade Bot Dashboard")

price_placeholder = st.empty()
chart_placeholder = st.empty()
log_placeholder = st.empty()

for i in range(300):  # limit to 300 steps for now
    price = get_binance_price(SYMBOL)
    if price is None:
        st.error("Failed to fetch price.")
        time.sleep(2)
        continue

    price_data.append({"Time": i, "Price": price})
    df = pd.DataFrame(price_data)

    # Live price display
    price_placeholder.markdown(f"### {SYMBOL} Price: **${price:.2f}**")

    # Signal logic
    signal = None
    if price > THRESHOLD and last_signal != "BUY":
        signal = "BUY"
        last_signal = "BUY"
        price_data[-1]["Signal"] = "BUY"
    elif price < THRESHOLD and last_signal != "SELL":
        signal = "SELL"
        last_signal = "SELL"
        price_data[-1]["Signal"] = "SELL"
    else:
        price_data[-1]["Signal"] = "HOLD"

    # Chart
    base = alt.Chart(df).encode(x="Time", y="Price")

    line = base.mark_line(color="blue")
    markers = base.mark_point(filled=True, size=80).encode(
        color=alt.condition(
            alt.datum.Signal == "BUY", alt.value("green"),
            alt.condition(alt.datum.Signal == "SELL", alt.value("red"), alt.value("gray"))
        ),
        tooltip=["Signal", "Price"]
    )

    chart = (line + markers).properties(height=400)
    chart_placeholder.altair_chart(chart, use_container_width=True)

    # Log
    if signal:
        log_placeholder.markdown(f"**🔔 {signal} at ${price:.2f}**")

    time.sleep(3)
    
# Signal Summary Section
st.markdown("### 📝 Signal Summary")

if not df_display.empty and "Signal" in df_display.columns:
    for _, row in df_display.iterrows():
        st.markdown(f"""
        <div class="signal-box">
            <strong>{row['Symbol']}</strong><br>
            Price: <span class="price-blink">${row['Price']}</span><br>
            EMA(10): {row['EMA(10)']} | RSI(14): {row['RSI(14)']}<br>
            Signal: <b style='color: {"green" if row["Signal"]=="BUY" else "red"}'>{row["Signal"]}</b>
        </div>
        """, unsafe_allow_html=True)
else:
    st.warning("No signal data available yet.") 

