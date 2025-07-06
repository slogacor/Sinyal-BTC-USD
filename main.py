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
import logging
import asyncio
import json
import time as t
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time, timezone
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Tambahan import untuk tradingview_ta async wrapper
from tradingview_ta import TA_Handler, Interval


BOT_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
CHAT_ID = "-1002883903673"
signal_history = []


# === UTILITY ===
def utc_to_wib(utc_dt):
    return utc_dt + timedelta(hours=7)


# === FETCH PRICE pakai tradingview_ta (async-friendly) ===
async def fetch_tv_price(symbol="BTCUSD"):
    def get_price():
        handler = TA_Handler(
            symbol=symbol,
            screener="forex",
            exchange="EXNESS",
            interval=Interval.INTERVAL_1_MINUTE
        )
        analysis = handler.get_analysis()
        return analysis.indicators['close']
    price = await asyncio.to_thread(get_price)
    return price


# === ANALISIS DAN SINYAL ===
def fetch_klines_dummy(symbol="BTCUSD", interval="5m", limit=100):
    # Dummy data generator — ganti kalau sudah punya API untuk candle dari OANDA
    now = datetime.now(tz=timezone.utc)
    candles = []
    price = 60000
    for i in range(limit):
        ts = now - timedelta(minutes=5 * (limit - i))
        candles.append({
            "open_time": ts,
            "open": price + np.random.uniform(-100, 100),
            "high": price + np.random.uniform(50, 150),
            "low": price - np.random.uniform(50, 150),
            "close": price + np.random.uniform(-100, 100),
            "volume": np.random.uniform(10, 100),
            "close_time": ts + timedelta(minutes=5)
        })
    return candles

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

def trend_direction(candles):
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

    trend = trend_direction(candles)
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


# === SIGNAL EXECUTION ===
async def do_send_signal(app):
    global signal_history
    candles = fetch_klines_dummy("BTCUSD", "5m", 100)
    signal = detect_signal(candles)
    if not signal:
        return

    price = await fetch_tv_price("BTCUSD")
    if not price:
        await app.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil harga BTC/USD dari TradingView")
        return

    pip_size = 0.01 * 0.1
    if signal["signal"] == "buy":
        tp1_price = round(price + signal["tp1"] * pip_size, 2)
        tp2_price = round(price + signal["tp2"] * pip_size, 2)
        sl_price = round(price - signal["sl"] * pip_size, 2)
    else:
        tp1_price = round(price - signal["tp1"] * pip_size, 2)
        tp2_price = round(price - signal["tp2"] * pip_size, 2)
        sl_price = round(price + signal["sl"] * pip_size, 2)

    signal.update({
        "entry_price": round(price, 2),
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


# === COMMAND HANDLERS ===
async def start(update, context):
    await update.message.reply_text("✅ Bot sinyal BTC/USD aktif!")

async def last_signal(update, context):
    if not signal_history:
        await update.message.reply_text("Belum ada sinyal.")
        return
    last = signal_history[-1]
    emoji = "🔹" if last["signal"] == "buy" else "🔻"
    msg = (
        f"Sinyal terakhir:\n"
        f"{emoji} {last['signal'].upper()} ({last['strength']})\n"
        f"Entry: {last['entry_price']}\n"
        f"TP1: {last['tp1_price']} (+{last['tp1']} pips)\n"
        f"TP2: {last['tp2_price']} (+{last['tp2']} pips)\n"
        f"SL: {last['sl_price']} (-{last['sl']} pips)\n"
        f"Waktu: {last['time'].strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
        f"Hasil: {last['result']} ({last['pips']} pips)"
    )
    await update.message.reply_text(msg)

# Tambahan command baru /price
async def price(update, context):
    price = await fetch_tv_price("BTCUSD")
    if price:
        await update.message.reply_text(f"Harga BTC/USD saat ini: {price}")
    else:
        await update.message.reply_text("Gagal mendapatkan harga BTC/USD saat ini.")


# === MAIN ===
if __name__ == "__main__":
    keep_alive()
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
    )
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("last_signal", last_signal))
    application.add_handler(CommandHandler("price", price))  # Daftarkan command /price

    # Schedule kirim sinyal setiap 5 menit
    async def periodic_signal():
        while True:
            try:
                await do_send_signal(application)
            except Exception as e:
                print(f"Error saat kirim sinyal: {e}")
            await asyncio.sleep(300)  # 5 menit

    loop = asyncio.get_event_loop()
    loop.create_task(periodic_signal())

    application.run_polling()
