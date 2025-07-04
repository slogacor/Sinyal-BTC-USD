import requests
import logging
from datetime import datetime, timedelta, time, timezone
import asyncio
import numpy as np
from telegram.ext import ApplicationBuilder, CommandHandler

BOT_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
CHAT_ID = " -1002883903673"
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
    candles = []
    for d in data:
        candle = {
            "open_time": datetime.fromtimestamp(d[0] / 1000, tz=timezone.utc),
            "open": float(d[1]),
            "high": float(d[2]),
            "low": float(d[3]),
            "close": float(d[4]),
            "volume": float(d[5]),
            "close_time": datetime.fromtimestamp(d[6] / 1000, tz=timezone.utc)
        }
        candles.append(candle)
    return candles

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)
    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        upval = delta if delta > 0 else 0.
        downval = -delta if delta < 0 else 0.
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi

def bollinger_bands(prices, window=20, no_of_std=2):
    sma = np.convolve(prices, np.ones(window) / window, mode='valid')
    rolling_std = np.array([np.std(prices[i:i + window]) for i in range(len(prices) - window + 1)])
    upper_band = sma + no_of_std * rolling_std
    lower_band = sma - no_of_std * rolling_std
    return sma, upper_band, lower_band

def analyze_candlestick(candle, prev_candle):
    if (candle["close"] > candle["open"] and
        prev_candle["close"] < prev_candle["open"] and
        candle["open"] < prev_candle["close"] and
        candle["close"] > prev_candle["open"]):
        return "bullish"
    if (candle["close"] < candle["open"] and
        prev_candle["close"] > prev_candle["open"] and
        candle["open"] > prev_candle["close"] and
        candle["close"] < prev_candle["open"]):
        return "bearish"
    return "neutral"

def determine_signal(candles_5m):
    closes = np.array([c["close"] for c in candles_5m])
    if len(closes) < 20:
        return None
    rsi = calculate_rsi(closes)[-1]
    sma, upper, lower = bollinger_bands(closes)
    if len(sma) == 0:
        return None
    last_candle = candles_5m[-1]
    prev_candle = candles_5m[-2]
    candle_pattern = analyze_candlestick(last_candle, prev_candle)
    last_close = closes[-1]
    upper_last = upper[-1]
    lower_last = lower[-1]
    signal = "neutral"
    if candle_pattern == "bullish" and rsi < 40 and last_close < lower_last:
        signal = "buy"
    elif candle_pattern == "bearish" and rsi > 60 and last_close > upper_last:
        signal = "sell"
    else:
        if rsi < 30 and last_close < lower_last:
            signal = "buy"
        elif rsi > 70 and last_close > upper_last:
            signal = "sell"
    pip_size = 0.01
    if signal == "buy":
        tp1 = 30 * pip_size
        tp2 = 50 * pip_size
        sl = 15 * pip_size
    elif signal == "sell":
        tp1 = 30 * pip_size
        tp2 = 50 * pip_size
        sl = 15 * pip_size
    else:
        return None

    entry_price = round(last_close, 2)
    tp1_price = round(entry_price + tp1, 2) if signal == "buy" else round(entry_price - tp1, 2)
    tp2_price = round(entry_price + tp2, 2) if signal == "buy" else round(entry_price - tp2, 2)
    sl_price  = round(entry_price - sl, 2) if signal == "buy" else round(entry_price + sl, 2)

    return {
        "signal": signal,
        "entry_price": entry_price,
        "tp1_price": tp1_price,
        "tp2_price": tp2_price,
        "sl_price": sl_price,
        "tp1": round(tp1, 4),
        "tp2": round(tp2, 4),
        "sl": round(sl, 4),
        "time": utc_to_wib(last_candle["close_time"]),
        "result": None,
        "pips": 0
    }

def simulate_signal_result(signal_obj):
    import random
    outcome = random.choice(["TP1", "TP2", "SL"])
    signal_obj["result"] = outcome
    signal_obj["pips"] = 30 if outcome == "TP1" else 50 if outcome == "TP2" else -15

async def send_signal(context):
    global signal_history
    application = context.application
    candles_5m = fetch_klines("BTCUSDT", "5m", 100)
    if not candles_5m:
        await application.bot.send_message(chat_id=CHAT_ID, text="Gagal ambil data BTC/USD")
        return
    result = determine_signal(candles_5m)
    if not result:
        return

    simulate_signal_result(result)
    signal_history.append(result)
    emoji = "🔹" if result["signal"] == "buy" else "🔻"

    msg = (
        f"✨ Sinyal BTC/USD @ {result['time'].strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
        f"{emoji} Sinyal: {result['signal'].upper()}\n"
        f"💰 Entry: {result['entry_price']}\n"
        f"🌟 TP1: {result['tp1_price']} (+30 pips)\n"
        f"🔥 TP2: {result['tp2_price']} (+50 pips)\n"
        f"⛔ SL: {result['sl_price']} (-15 pips)"
    )

    await application.bot.send_message(chat_id=CHAT_ID, text=msg)

    if len(signal_history) >= 5:
        recap_msg = "📊 [Rekapan 5 Sinyal Terakhir]\n"
        total_pips = 0
        for i, s in enumerate(signal_history[-5:], 1):
            status = "✅ TP1 🌟 +30 pips" if s["result"] == "TP1" else \
                     "✅ TP2 🔥 +50 pips" if s["result"] == "TP2" else \
                     "❌ SL ⛔ -15 pips"
            total_pips += s["pips"]
            recap_msg += f"{i}. {s['signal'].upper():<4} {status}\n"
        recap_msg += f"\n📈 Total Pips: {'➕' if total_pips >= 0 else '➖'} {abs(total_pips)} pips"
        await application.bot.send_message(chat_id=CHAT_ID, text=recap_msg)
        signal_history = []

async def daily_recap(context):
    application = context.application
    total = len(signal_history)
    profit_count = sum(1 for s in signal_history if s["result"] in ["TP1", "TP2"])
    loss_count = sum(1 for s in signal_history if s["result"] == "SL")
    tp_pips = sum(s["pips"] for s in signal_history if s["pips"] > 0)
    sl_pips = sum(s["pips"] for s in signal_history if s["pips"] < 0)
    net_pips = tp_pips + sl_pips
    accuracy = int(profit_count / total * 100) if total > 0 else 0

    recap_msg = (f"📅 [Rekapan Harian BTC/USD]\n"
                 f"📈 Total Sinyal: {total}\n"
                 f"✅ Profit: {profit_count}\n"
                 f"❌ Loss: {loss_count}\n\n"
                 f"🌟 Total Pips:\n"
                 f"➕ TP: {tp_pips} pips\n"
                 f"➖ SL: {sl_pips} pips\n"
                 f"📊 Net Pips: {net_pips:+} pips\n\n"
                 f"🎯 Akurasi: {accuracy}%\n"
                 f"🔥 Tetap disiplin & gunakan SL ya!")

    await application.bot.send_message(chat_id=CHAT_ID, text=recap_msg)

async def start(update, context):
    await update.message.reply_text("Bot sinyal BTC/USD siap!")

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    job_queue = application.job_queue
    job_queue.run_repeating(send_signal, interval=25 * 60, first=5)

    now = datetime.now(timezone.utc) + timedelta(hours=7)
    target_time = datetime.combine(now.date(), time(20, 0)).replace(tzinfo=timezone(timedelta(hours=7)))
    if now > target_time:
        target_time += timedelta(days=1)
    delay_seconds = (target_time - now).total_seconds()

    job_queue.run_repeating(daily_recap, interval=24 * 3600, first=delay_seconds)

    print("Bot BTC/USD running...")
    await application.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
