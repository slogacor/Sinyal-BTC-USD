from flask import Flask
from threading import Thread
import requests
from datetime import datetime
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

def fetch_twelvedata(symbol="XAU/USD", interval="5min", count=100):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&apikey={API_KEY}&outputsize={count}&format=JSON"
    response = requests.get(url)
    print(f"Request URL: {url}")
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.text}")
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
    prev2 = df.iloc[-3] if len(df) >= 3 else None

    body_last = abs(last["close"] - last["open"])
    upper_shadow_last = last["high"] - max(last["close"], last["open"])
    lower_shadow_last = min(last["close"], last["open"]) - last["low"]

    body_prev = abs(prev["close"] - prev["open"])
    upper_shadow_prev = prev["high"] - max(prev["close"], prev["open"])
    lower_shadow_prev = min(prev["close"], prev["open"]) - prev["low"]

    # Bullish Engulfing
    if prev["close"] < prev["open"] and last["close"] > last["open"]:
        if last["close"] > prev["open"] and last["open"] < prev["close"]:
            patterns.append("Bullish Engulfing")

    # Bearish Engulfing
    if prev["close"] > prev["open"] and last["close"] < last["open"]:
        if last["open"] > prev["close"] and last["close"] < prev["open"]:
            patterns.append("Bearish Engulfing")

    # Hammer
    if lower_shadow_last > 2 * body_last and upper_shadow_last < body_last:
        patterns.append("Hammer")

    # Hanging Man (Hammer at top of uptrend)
    # Simple check: if prev candle uptrend (close > open) and last candle hammer shape bearish
    if prev["close"] > prev["open"] and \
       lower_shadow_last > 2 * body_last and upper_shadow_last < body_last and \
       last["close"] < last["open"]:
        patterns.append("Hanging Man")

    # Inverted Hammer
    if upper_shadow_last > 2 * body_last and lower_shadow_last < body_last:
        patterns.append("Inverted Hammer")

    # Shooting Star (Inverted hammer at top of uptrend)
    if prev["close"] > prev["open"] and \
       upper_shadow_last > 2 * body_last and lower_shadow_last < body_last and \
       last["close"] < last["open"]:
        patterns.append("Shooting Star")

    # Doji
    if body_last <= (0.1 * (last["high"] - last["low"])):
        patterns.append("Doji")

    # Morning Star (3 candle pattern, bullish reversal)
    # Prev2: bearish, Prev: small body (could be doji), Last: bullish and close > midpoint prev2 body
    if prev2 is not None:
        is_prev2_bearish = prev2["close"] < prev2["open"]
        is_prev_small_body = abs(prev["close"] - prev["open"]) < abs(prev2["close"] - prev2["open"]) * 0.5
        is_last_bullish = last["close"] > last["open"]
        last_close_above_mid_prev2 = last["close"] > (prev2["open"] + prev2["close"]) / 2
        if is_prev2_bearish and is_prev_small_body and is_last_bullish and last_close_above_mid_prev2:
            patterns.append("Morning Star")

    # Evening Star (3 candle pattern, bearish reversal)
    if prev2 is not None:
        is_prev2_bullish = prev2["close"] > prev2["open"]
        is_prev_small_body = abs(prev["close"] - prev["open"]) < abs(prev2["close"] - prev2["open"]) * 0.5
        is_last_bearish = last["close"] < last["open"]
        last_close_below_mid_prev2 = last["close"] < (prev2["open"] + prev2["close"]) / 2
        if is_prev2_bullish and is_prev_small_body and is_last_bearish and last_close_below_mid_prev2:
            patterns.append("Evening Star")

    # Tweezer Top (two candles with equal highs at top, bearish reversal)
    if prev["high"] == last["high"] and prev["close"] > prev["open"] and last["close"] < last["open"]:
        patterns.append("Tweezer Top")

    # Tweezer Bottom (two candles with equal lows at bottom, bullish reversal)
    if prev["low"] == last["low"] and prev["close"] < prev["open"] and last["close"] > last["open"]:
        patterns.append("Tweezer Bottom")

    return patterns

async def send_chart_with_pattern(context):
    candles = fetch_twelvedata("XAU/USD", interval="5min", count=50)
    if candles is None:
        await context.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data XAU/USD untuk chart.")
        return

    df = prepare_df(candles)
    patterns = detect_candle_pattern(df)

    ap = []
    if patterns:
        ap = [mpf.make_addplot(df["close"], type='scatter', markersize=100, marker='o', color='red')]

    fig, _ = mpf.plot(
        df.tail(50),
        type='candle',
        style='charles',
        title="XAU/USD 5min Chart",
        ylabel='Price',
        addplot=ap,
        returnfig=True
    )

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    caption = "📉 Chart XAU/USD 5min"
    if patterns:
        caption += "\n🔍 Ditemukan pola: " + ", ".join(patterns)
    else:
        caption += "\n❌ Tidak ada pola candlestick yang dikenali."

    await context.bot.send_photo(chat_id=CHAT_ID, photo=buf, caption=caption)

async def send_chart_if_on_hour(context):
    jakarta_tz = pytz.timezone("Asia/Jakarta")
    now = datetime.now(jakarta_tz)
    if now.minute == 0:
        await send_chart_with_pattern(context)

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
    job_queue = application.job_queue

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_user_message))
    application.add_handler(MessageHandler(filters.ALL, ignore_bot_messages))
    application.add_error_handler(error_handler)

    # Cek tiap menit, jika menit == 0 kirim chart 5min
    job_queue.run_repeating(send_chart_if_on_hour, interval=60, first=0)

    await application.run_polling()

if __name__ == '__main__':
    keep_alive()
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
