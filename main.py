import logging
import asyncio
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
from telegram.ext import ApplicationBuilder, CommandHandler
from tradingview_ta import TA_Handler, Interval

# === KONFIGURASI ===
BOT_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
CHAT_ID = "-1002883903673"
signal_history = []

# === FLASK KEEP ALIVE UNTUK RAILWAY ===
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is alive!"

def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True)
    t.start()

# === UTILITAS WAKTU ===
def utc_to_wib(utc_dt):
    return utc_dt + timedelta(hours=7)

# === AMBIL HARGA REAL-TIME TRADINGVIEW ===
async def fetch_tv_price(symbol="BTCUSD"):
    def get_price():
        handler = TA_Handler(
            symbol=symbol,
            screener="forex",
            exchange="EXNESS",  # Ubah sesuai provider harga real-time kamu
            interval=Interval.INTERVAL_1_MINUTE
        )
        analysis = handler.get_analysis()
        return analysis.indicators['close']
    return await asyncio.to_thread(get_price)

# === DUMMY CANDLE GENERATOR (simulasi data 5m) ===
def fetch_klines_dummy(symbol="BTCUSD", interval="5m", limit=100):
    now = datetime.now(tz=timezone.utc)
    price = 60000
    candles = []
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

# === TEKNIKAL ANALISA ===
def bollinger_bands(prices, window=20, no_of_std=2):
    series = pd.Series(prices)
    sma = series.rolling(window).mean()
    std = series.rolling(window).std()
    return sma, sma + no_of_std * std, sma - no_of_std * std

def stochastic_oscillator(highs, lows, closes, k_period=14, d_period=3):
    low_min = pd.Series(lows).rolling(k_period).min()
    high_max = pd.Series(highs).rolling(k_period).max()
    k = 100 * ((pd.Series(closes) - low_min) / (high_max - low_min))
    d = k.rolling(d_period).mean()
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

    if not signal or (signal == "buy" and trend_direction(candles) != "up") or (signal == "sell" and trend_direction(candles) != "down"):
        return None

    return {
        "signal": signal,
        "strength": strength,
        "tp1": np.random.randint(45, 65),
        "tp2": np.random.randint(65, 90),
        "sl": np.random.randint(20, 30),
        "time": utc_to_wib(candles[-1]["close_time"]),
    }

def simulate_result(sig):
    from random import choice
    result = choice(["TP1", "TP2", "SL"])
    sig["result"] = result
    sig["pips"] = sig["tp1"] if result == "TP1" else sig["tp2"] if result == "TP2" else -sig["sl"]

# === EXECUTE & KIRIM SIGNAL ===
async def do_send_signal(app):
    global signal_history
    candles = fetch_klines_dummy()
    signal = detect_signal(candles)
    if not signal:
        return

    price = await fetch_tv_price()
    pip_size = 0.01 * 0.1

    if signal["signal"] == "buy":
        signal.update({
            "entry_price": round(price, 2),
            "tp1_price": round(price + signal["tp1"] * pip_size, 2),
            "tp2_price": round(price + signal["tp2"] * pip_size, 2),
            "sl_price": round(price - signal["sl"] * pip_size, 2),
        })
    else:
        signal.update({
            "entry_price": round(price, 2),
            "tp1_price": round(price - signal["tp1"] * pip_size, 2),
            "tp2_price": round(price - signal["tp2"] * pip_size, 2),
            "sl_price": round(price + signal["sl"] * pip_size, 2),
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

# === COMMANDS ===
async def cmd_start(update, context):
    await update.message.reply_text("✅ Bot sinyal BTC/USD aktif!")

async def cmd_price(update, context):
    price = await fetch_tv_price()
    await update.message.reply_text(f"Harga BTC/USD saat ini: {price}")

async def cmd_last_signal(update, context):
    if not signal_history:
        await update.message.reply_text("Belum ada sinyal.")
        return
    s = signal_history[-1]
    emoji = "🔹" if s["signal"] == "buy" else "🔻"
    await update.message.reply_text(
        f"Sinyal terakhir:\n{emoji} {s['signal'].upper()} ({s['strength']})\n"
        f"Entry: {s['entry_price']}\nTP1: {s['tp1_price']}, TP2: {s['tp2_price']}, SL: {s['sl_price']}\n"
        f"Hasil: {s['result']} ({s['pips']} pips)\nWaktu: {s['time'].strftime('%Y-%m-%d %H:%M:%S WIB')}"
    )

# === MAIN BOT ===
async def main():
    keep_alive()
    logging.basicConfig(level=logging.INFO)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("last_signal", cmd_last_signal))

    async def loop_signal():
        while True:
            try:
                await do_send_signal(app)
            except Exception as e:
                logging.error(f"❌ Error signal: {e}")
            await asyncio.sleep(300)  # setiap 5 menit

    asyncio.create_task(loop_signal())
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
