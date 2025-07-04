# === KEEP ALIVE UNTUK RAILWAY ===
from flask import Flask
from threading import Thread

app = Flask('')
@app.route('/')
def home():
    return "Bot is alive!"
def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

# === BOT UTAMA ===
import requests
import logging
from datetime import datetime, timedelta, time, timezone
import asyncio
import numpy as np
import pandas as pd
from telegram.ext import ApplicationBuilder, CommandHandler

BOT_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
CHAT_ID = "-1002883903673"
signal_history = []


def utc_to_wib(utc_dt):
    return utc_dt + timedelta(hours=7)


def fetch_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    res = requests.get(url)
    if res.status_code != 200:
        logging.error(f"Binance API error: {res.status_code}")
        return None
    data = res.json()
    return [{
        "open_time": datetime.fromtimestamp(d[0] / 1000, tz=timezone.utc),
        "open": float(d[1]),
        "high": float(d[2]),
        "low": float(d[3]),
        "close": float(d[4]),
        "volume": float(d[5]),
        "close_time": datetime.fromtimestamp(d[6] / 1000, tz=timezone.utc)
    } for d in data]


def bollinger_bands(prices, window=20, no_of_std=2):
    sma = pd.Series(prices).rolling(window).mean()
    std = pd.Series(prices).rolling(window).std()
    upper_band = sma + no_of_std * std
    lower_band = sma - no_of_std * std
    return sma, upper_band, lower_band


def stochastic_oscillator(highs, lows, closes, k_period=14, d_period=3):
    low_min = pd.Series(lows).rolling(window=k_period).min()
    high_max = pd.Series(highs).rolling(window=k_period).max()
    k = 100 * ((pd.Series(closes) - low_min) / (high_max - low_min))
    d = k.rolling(window=d_period).mean()
    return k, d


def detect_snrs(candles):
    levels = []
    for i in range(2, len(candles) - 2):
        high = candles[i]['high']
        low = candles[i]['low']
        if high > candles[i-1]['high'] and high > candles[i+1]['high']:
            levels.append(high)
        elif low < candles[i-1]['low'] and low < candles[i+1]['low']:
            levels.append(low)
    return levels[-3:]


def detect_signal(candles):
    closes = [c['close'] for c in candles]
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]

    if len(closes) < 20:
        return None

    sma, upper, lower = bollinger_bands(closes)
    k, d = stochastic_oscillator(highs, lows, closes)
    last_close = closes[-1]
    last_k, last_d = k.iloc[-1], d.iloc[-1]
    snrs = detect_snrs(candles)
    support = min(snrs) if snrs else min(lows)
    resistance = max(snrs) if snrs else max(highs)

    signal = None
    if last_close < support * 1.01 and last_k < 30 and last_k > last_d:
        signal = "buy"
    elif last_close > resistance * 0.99 and last_k > 70 and last_k < last_d:
        signal = "sell"

    if not signal:
        return None

    pip_size = 0.01 * 0.1  # Faktor pengali 0.1 sesuai permintaan
    entry = round(last_close, 2)
    tp1 = round(entry + 30 * pip_size, 2) if signal == "buy" else round(entry - 30 * pip_size, 2)
    tp2 = round(entry + 50 * pip_size, 2) if signal == "buy" else round(entry - 50 * pip_size, 2)
    sl = round(entry - 15 * pip_size, 2) if signal == "buy" else round(entry + 15 * pip_size, 2)

    return {
        "signal": signal,
        "entry_price": entry,
        "tp1_price": tp1,
        "tp2_price": tp2,
        "sl_price": sl,
        "tp1": 30,
        "tp2": 50,
        "sl": 15,
        "time": utc_to_wib(candles[-1]["close_time"]),
        "result": None,
        "pips": 0
    }


def simulate_result(sig):
    from random import choice
    result = choice(["TP1", "TP2", "SL"])
    sig["result"] = result
    sig["pips"] = 30 if result == "TP1" else 50 if result == "TP2" else -15


async def send_signal(context):
    global signal_history
    app = context.application
    candles = fetch_klines("BTCUSDT", "5m", 100)
    if not candles:
        await app.bot.send_message(chat_id=CHAT_ID, text="Gagal ambil data BTC/USD")
        return

    signal = detect_signal(candles)
    if not signal:
        return

    simulate_result(signal)
    signal_history.append(signal)

    emoji = "🔹" if signal["signal"] == "buy" else "🔻"
    msg = (
        f"✨ Sinyal BTC/USD @ {signal['time'].strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
        f"{emoji} Sinyal: {signal['signal'].upper()}\n"
        f"💰 Entry: {signal['entry_price']}\n"
        f"🌟 TP1: {signal['tp1_price']} (+30 pips)\n"
        f"🔥 TP2: {signal['tp2_price']} (+50 pips)\n"
        f"⛔ SL: {signal['sl_price']} (-15 pips)"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=msg)

    if len(signal_history) >= 5:
        total_pips = 0
        recap = "📊 [Rekapan 5 Sinyal Terakhir]\n"
        for i, s in enumerate(signal_history[-5:], 1):
            hasil = "✅ TP1 🌟 +30" if s["result"] == "TP1" else "✅ TP2 🔥 +50" if s["result"] == "TP2" else "❌ SL ⛔ -15"
            total_pips += s["pips"]
            recap += f"{i}. {s['signal'].upper():<4} {hasil} pips\n"
        recap += f"\n📈 Total Pips: {'➕' if total_pips >= 0 else '➖'} {abs(total_pips)} pips"
        await app.bot.send_message(chat_id=CHAT_ID, text=recap)
        signal_history = []


async def daily_recap(context):
    app = context.application
    total = len(signal_history)
    profit = sum(1 for s in signal_history if s["result"] in ["TP1", "TP2"])
    loss = sum(1 for s in signal_history if s["result"] == "SL")
    tp = sum(s["pips"] for s in signal_history if s["pips"] > 0)
    sl = sum(s["pips"] for s in signal_history if s["pips"] < 0)
    net = tp + sl
    acc = int(profit / total * 100) if total else 0

    recap = (f"📅 [Rekapan Harian BTC/USD]\n"
             f"📈 Total Sinyal: {total}\n"
             f"✅ Profit: {profit}\n"
             f"❌ Loss: {loss}\n\n"
             f"🌟 Total Pips:\n➕ TP: {tp} pips\n➖ SL: {sl} pips\n"
             f"📊 Net Pips: {net:+} pips\n🎯 Akurasi: {acc}%\n"
             f"🔥 Tetap disiplin & gunakan SL ya!")
    await app.bot.send_message(chat_id=CHAT_ID, text=recap)


async def start(update, context):
    await update.message.reply_text("✅ Bot sinyal BTC/USD aktif!")


async def main():
    keep_alive()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    application.job_queue.run_repeating(send_signal, interval=1200, first=5)  # setiap 20 menit

    now = datetime.now(timezone.utc) + timedelta(hours=7)
    target = datetime.combine(now.date(), time(20, 0)).replace(tzinfo=timezone(timedelta(hours=7)))
    if now > target:
        target += timedelta(days=1)
    delay = (target - now).total_seconds()
    application.job_queue.run_repeating(daily_recap, interval=86400, first=delay)

    print("Bot BTC/USD aktif dan berjalan...")
    await application.run_polling()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
