# main.py

from flask import Flask
from threading import Thread
import requests
from datetime import datetime, time
import pytz
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters
)
from ta.trend import EMAIndicator, SMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
import pandas as pd
from bs4 import BeautifulSoup
import mplfinance as mpf
import matplotlib.pyplot as plt
import io

# Konfigurasi
BOT_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
CHAT_ID = "-1002657952587"
API_KEY = "94a7d766d73f4db4a7ddf877473711c7"

app = Flask(__name__)

def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

@app.route('/')
def home():
    return "Bot is running"

def fetch_twelvedata(symbol="XAU/USD", interval="1h", count=100):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&apikey={API_KEY}&outputsize={count}&format=JSON"
    response = requests.get(url)
    if response.status_code != 200:
        return None
    data = response.json().get("values", [])
    return data[::-1] if data else None

def prepare_df(data):
    df = pd.DataFrame(data)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.astype(float)
    return df

def detect_candle_pattern(df):
    patterns = []
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Bullish Engulfing
    if prev["close"] < prev["open"] and last["close"] > last["open"]:
        if last["close"] > prev["open"] and last["open"] < prev["close"]:
            patterns.append("Bullish Engulfing")

    # Bearish Engulfing
    if prev["close"] > prev["open"] and last["close"] < last["open"]:
        if last["open"] > prev["close"] and last["close"] < prev["open"]:
            patterns.append("Bearish Engulfing")

    # Hammer
    body = abs(last["close"] - last["open"])
    lower_shadow = last["open"] - last["low"] if last["open"] > last["close"] else last["close"] - last["low"]
    upper_shadow = last["high"] - last["close"] if last["close"] > last["open"] else last["high"] - last["open"]
    if lower_shadow > 2 * body and upper_shadow < body:
        patterns.append("Hammer")

    # Doji
    if abs(last["close"] - last["open"]) <= (0.1 * (last["high"] - last["low"])):
        patterns.append("Doji")

    return patterns

async def send_chart_with_pattern(context):
    candles = fetch_twelvedata("XAU/USD", interval="1h", count=50)
    if candles is None:
        await context.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data XAU/USD untuk chart.")
        return

    df = prepare_df(candles)
    patterns = detect_candle_pattern(df)

    # Plot chart
    ap = []
    if patterns:
        ap = [mpf.make_addplot(df["close"], type='scatter', markersize=100, marker='o', color='red')]

    fig, _ = mpf.plot(
        df.tail(50),
        type='candle',
        style='charles',
        title="XAU/USD 1H Chart",
        ylabel='Price',
        addplot=ap,
        returnfig=True
    )

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    caption = "📉 Chart XAU/USD 1H"
    if patterns:
        caption += "\n🔍 Ditemukan pola: " + ", ".join(patterns)
    else:
        caption += "\n❌ Tidak ada pola candlestick yang dikenali."

    await context.bot.send_photo(chat_id=CHAT_ID, photo=buf, caption=caption)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo! Bot sudah aktif.")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pesan diterima.")

async def ignore_bot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error terjadi: {context.error}")

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    jakarta_tz = pytz.timezone("Asia/Jakarta")
    job_queue = application.job_queue

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_user_message))
    application.add_handler(MessageHandler(filters.ALL, ignore_bot_messages))
    application.add_error_handler(error_handler)

    # Kirim chart + pola candlestick setiap 1 jam sekali
    job_queue.run_repeating(send_chart_with_pattern, interval=3600, first=10)

    await application.run_polling()

if __name__ == '__main__':
    keep_alive()
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass

    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
