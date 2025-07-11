import os
import telebot
import requests
import pandas as pd
import plotly.graph_objects as go
import io
import time
from datetime import datetime

# Setup environment variable untuk plotly
os.environ["PLOTLY_RENDERER"] = "kaleido"

# Ambil environment variables dengan pengecekan
BOT_TOKEN = os.environ.get("BOT_TOKEN")
group_id_str = os.environ.get("GROUP_ID")

if BOT_TOKEN is None:
    raise ValueError("Environment variable BOT_TOKEN is not set")

if group_id_str is None:
    raise ValueError("Environment variable GROUP_ID is not set")

GROUP_ID = int(group_id_str)

SYMBOL = "BTCUSDT"
INTERVAL = "1m"

bot = telebot.TeleBot(BOT_TOKEN)
BINANCE_URL = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=10"

def fetch_candles():
    res = requests.get(BINANCE_URL)
    raw_data = res.json()
    df = pd.DataFrame(raw_data, columns=[
        "time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base_vol", "taker_buy_quote_vol", "ignore"
    ])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df.set_index("time", inplace=True)
    df = df.astype(float)
    return df

def generate_chart(df):
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color='green',
        decreasing_line_color='red'
    )])
    fig.update_layout(
        title="BTC/USDT - Last 10 Candles (1m)",
        xaxis_title="Time",
        yaxis_title="Price",
        template="plotly_dark",
        height=500,
        margin=dict(l=30, r=30, t=40, b=30)
    )
    buffer = io.BytesIO()
    fig.write_image(buffer, format='png')
    buffer.seek(0)
    return buffer

def get_analysis(df):
    last = df.iloc[-1]
    open_ = last["open"]
    close = last["close"]
    high = last["high"]
    low = last["low"]

    direction = "Bullish 📈" if close > open_ else "Bearish 📉"
    change = round(((close - open_) / open_) * 100, 2)

    body = abs(close - open_)
    shadow_top = high - max(open_, close)
    shadow_bottom = min(open_, close) - low

    if body < (shadow_top + shadow_bottom) * 0.3:
        pola = "Doji ⚖️"
    elif close > open_ and body > shadow_top and shadow_bottom > body * 0.5:
        pola = "Hammer 🛠️"
    elif open_ > close and body > shadow_bottom and shadow_top > body * 0.5:
        pola = "Inverted Hammer 🔃"
    else:
        pola = "—"

    return (
        f"📊 *BTC/USDT (10m snapshot)*\n"
        f"🕒 Time: {df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"💰 Open: {open_:.2f}\n"
        f"🔚 Close: {close:.2f}\n"
        f"🔼 High: {high:.2f}\n"
        f"🔽 Low: {low:.2f}\n"
        f"🧠 Pola: {pola}\n"
        f"📈 Status: *{direction}* ({change}%)"
    )

def send_update():
    df = fetch_candles()
    chart = generate_chart(df)
    caption = get_analysis(df)
    bot.send_photo(GROUP_ID, photo=chart, caption=caption, parse_mode="Markdown")

if __name__ == "__main__":
    while True:
        try:
            print(f"[{datetime.now()}] Sending update to Telegram...")
            send_update()
            time.sleep(600)
        except Exception as e:
            print("❌ Error:", e)
            time.sleep(60)
