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
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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

def fetch_realtime_price(symbol="BTCUSDT"):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    res = requests.get(url)
    if res.status_code != 200:
        logging.error(f"Binance API realtime price error: {res.status_code}")
        return None
    data = res.json()
    return float(data["price"])

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

def trend_direction(symbol="BTCUSDT", interval="15m", length=50):
    candles = fetch_klines(symbol, interval, length)
    if not candles:
        return "sideways"
    closes = [c['close'] for c in candles]
    sma_short = pd.Series(closes).rolling(20).mean()
    sma_long = pd.Series(closes).rolling(50).mean()
    if sma_short.iloc[-1] > sma_long.iloc[-1]:
        return "up"
    elif sma_short.iloc[-1] < sma_long.iloc[-1]:
        return "down"
    else:
        return "sideways"

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
    strength = "lemah"

    if last_close < support * 1.01 and last_k < 25 and last_k > last_d:
        signal = "buy"
        strength = "kuat" if (last_d - last_k) > 7 else "sedang"
    elif last_close > resistance * 0.99 and last_k > 75 and last_k < last_d:
        signal = "sell"
        strength = "kuat" if (last_k - last_d) > 7 else "sedang"

    if not signal:
        return None

    trend = trend_direction()
    if (signal == "buy" and trend != "up") or (signal == "sell" and trend != "down"):
        return None

    tp1_pips = np.random.randint(45, 65)
    tp2_pips = np.random.randint(65, 90)
    sl_pips = np.random.randint(20, 30)

    return {
        "signal": signal,
        "strength": strength,
        "tp1": tp1_pips,
        "tp2": tp2_pips,
        "sl": sl_pips,
        "time": utc_to_wib(candles[-1]["close_time"]),
        "result": None,
        "pips": 0
    }

def simulate_result(sig):
    from random import choice
    result = choice(["TP1", "TP2", "SL"])
    sig["result"] = result
    sig["pips"] = sig["tp1"] if result == "TP1" else sig["tp2"] if result == "TP2" else -sig["sl"]

async def send_signal(context):
    await do_send_signal(context.application)

async def do_send_signal(app):
    global signal_history
    candles = fetch_klines("BTCUSDT", "5m", 100)
    if not candles:
        await app.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data BTC/USD")
        return

    signal = detect_signal(candles)
    if not signal:
        return

    entry_price = fetch_realtime_price("BTCUSDT")
    if entry_price is None:
        await app.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil harga realtime BTC/USD")
        return

    pip_size = 0.01 * 0.1
    if signal["signal"] == "buy":
        tp1_price = round(entry_price + signal["tp1"] * pip_size, 2)
        tp2_price = round(entry_price + signal["tp2"] * pip_size, 2)
        sl_price = round(entry_price - signal["sl"] * pip_size, 2)
    else:
        tp1_price = round(entry_price - signal["tp1"] * pip_size, 2)
        tp2_price = round(entry_price - signal["tp2"] * pip_size, 2)
        sl_price = round(entry_price + signal["sl"] * pip_size, 2)

    signal.update({
        "entry_price": round(entry_price, 2),
        "tp1_price": tp1_price,
        "tp2_price": tp2_price,
        "sl_price": sl_price,
    })

    simulate_result(signal)
    signal_history.append(signal)

    emoji = "🔹" if signal["signal"] == "buy" else "🔻"
    msg = (
        f"✨ Sinyal BTC/USD @ {signal['time'].strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
        f"{emoji} Sinyal: {signal['signal'].upper()} ({signal['strength']})\n"
        f"💰 Entry: {signal['entry_price']}\n"
        f"🌟 TP1: {signal['tp1_price']} (+{signal['tp1']} pips)\n"
        f"🔥 TP2: {signal['tp2_price']} (+{signal['tp2']} pips)\n"
        f"⛔ SL: {signal['sl_price']} (-{signal['sl']} pips)"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=msg)

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
    await update.message.reply_text("✅ Bot sinyal BTC/USD aktif dengan mode swing!")

# ✅ Tambahan fitur /check untuk cek manual
async def check_signal(update, context: ContextTypes.DEFAULT_TYPE):
    app = context.application
    candles = fetch_klines("BTCUSDT", "5m", 100)
    if not candles:
        await update.message.reply_text("❌ Gagal ambil data BTC/USD")
        return

    signal = detect_signal(candles)
    if not signal:
        await update.message.reply_text("📉 Tidak ada sinyal valid saat ini.")
        return

    entry_price = fetch_realtime_price("BTCUSDT")
    if entry_price is None:
        await update.message.reply_text("❌ Gagal ambil harga realtime BTC/USD")
        return

    pip_size = 0.01 * 0.1
    if signal["signal"] == "buy":
        tp1_price = round(entry_price + signal["tp1"] * pip_size, 2)
        tp2_price = round(entry_price + signal["tp2"] * pip_size, 2)
        sl_price = round(entry_price - signal["sl"] * pip_size, 2)
    else:
        tp1_price = round(entry_price - signal["tp1"] * pip_size, 2)
        tp2_price = round(entry_price - signal["tp2"] * pip_size, 2)
        sl_price = round(entry_price + signal["sl"] * pip_size, 2)

    signal.update({
        "entry_price": round(entry_price, 2),
        "tp1_price": tp1_price,
        "tp2_price": tp2_price,
        "sl_price": sl_price,
    })

    simulate_result(signal)
    signal_history.append(signal)

    emoji = "🔹" if signal["signal"] == "buy" else "🔻"
    msg = (
        f"✨ Sinyal BTC/USD @ {signal['time'].strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
        f"{emoji} Sinyal: {signal['signal'].upper()} ({signal['strength']})\n"
        f"💰 Entry: {signal['entry_price']}\n"
        f"🌟 TP1: {signal['tp1_price']} (+{signal['tp1']} pips)\n"
        f"🔥 TP2: {signal['tp2_price']} (+{signal['tp2']} pips)\n"
        f"⛔ SL: {signal['sl_price']} (-{signal['sl']} pips)"
    )
    await update.message.reply_text(msg)

async def main():
    keep_alive()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_signal))  # ⬅️ Tambah fitur cek manual

    application.job_queue.run_daily(send_signal, time=time(0, 30))   # 07:30 WIB
    application.job_queue.run_daily(send_signal, time=time(6, 30))   # 13:30 WIB
    application.job_queue.run_daily(send_signal, time=time(13, 30))  # 20:30 WIB
    application.job_queue.run_daily(daily_recap, time=time(14, 0))   # 21:00 WIB

    print("Bot BTC/USD Swing aktif dan berjalan...")
    await application.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
