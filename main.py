import telebot
import requests
import pandas as pd
import plotly.graph_objects as go
import io
import time
from datetime import datetime
import os

# Biar kaleido pakai Chromium di Railway (optional)
os.environ["PLOTLY_RENDERER"] = "kaleido"

# Ambil konfigurasi dari environment
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))
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
        high=df["high
