import requests
import logging
from datetime import datetime, timedelta, time
import asyncio
import numpy as np
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
    candles = []
    for d in data:
        candle = {
            "open_time": datetime.utcfromtimestamp(d[0]/1000),
            "open": float(d[1]),
            "high": float(d[2]),
            "low": float(d[3]),
            "close": float(d[4]),
            "volume": float(d[5]),
            "close_time": datetime.utcfromtimestamp(d[6]/1000)
        }
        candles.append(candle)
    return candles

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum()/period
    down = -seed[seed < 0].sum()/period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100./(1.+rs)

    for i in range(period, len(prices)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
        up = (up*(period-1) + upval)/period
        down = (down*(period-1) + downval)/period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100./(1.+rs)
    return rsi

def bollinger_bands(prices, window=20, no_of_std=2):
    sma = np.convolve(prices, np.ones(window)/window, mode='valid')
    rolling_std = np.array([np.std(prices[i:i+window]) for i in range(len(prices)-window+1)])
    upper_band = sma + no_of_std*rolling_std
    lower_band = sma - no_of_std*rolling_std
    return sma, upper_band, lower_band

def analyze_candlestick(candle, prev_candle):
    # Bullish Engulfing
    if (candle["close"] > candle["open"] and
        prev_candle["close"] < prev_candle["open"] and
        candle["open"] < prev_candle["close"] and
        candle["close"] > prev_candle["open"]):
        return "bullish"

    # Bearish Engulfing
    if (candle["close"] < candle["open"] and
        prev_candle["close"] > prev_candle["open"] and
        candle["open"] > prev_candle["close"] and
        candle["close"] < prev_candle["open"]):
        return "bearish"

    return "neutral"

def determine_signal(candles_15m, candles_5m):
    closes_15 = np.array([c["close"] for c in candles_15m])
    closes_5 = np.array([c["close"] for c in candles_5m])

    if len(closes_15) < 20 or len(closes_5) < 20:
        return None

    rsi = calculate_rsi(closes_15)[-1]
    sma, upper, lower = bollinger_bands(closes_15)
    if len(sma) == 0:
        return None

    last_candle_15 = candles_15m[-1]
    prev_candle_15 = candles_15m[-2]
    candle_pattern = analyze_candlestick(last_candle_15, prev_candle_15)

    last_close = closes_15[-1]
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

    # Tentukan TP dan SL (pip = 0.01 USD pada BTC/USD)
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

    return {
        "signal": signal,
        "tp1": round(tp1, 4),
        "tp2": round(tp2, 4),
        "sl": round(sl, 4),
        "time": utc_to_wib(last_candle_15["close_time"])
    }

async def send_signal(application):
    global signal_history
    candles_15m = fetch_klines("BTCUSDT", "15m", 100)
    candles_5m = fetch_klines("BTCUSDT", "5m", 100)
    if not candles_15m or not candles_5m:
        await application.bot.send_message(chat_id=CHAT_ID, text="Gagal ambil data BTC/USD")
        return

    result = determine_signal(candles_15m, candles_5m)
    if not result:
        return

    signal_history.append(result)

    msg = (f"Sinyal BTC/USD @ {result['time'].strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
           f"Sinyal: {result['signal'].upper()}\n"
           f"TP1: {result['tp1']} USD\n"
           f"TP2: {result['tp2']} USD\n"
           f"SL: {result['sl']} USD\n")

    await application.bot.send_message(chat_id=CHAT_ID, text=msg)

    # Kirim rekapan setiap 5 sinyal
    if len(signal_history) >= 5:
        recap_msg = "Rekapan 5 sinyal terakhir:\n"
        buy_tp1 = []
        buy_tp2 = []
        buy_sl = []
        sell_tp1 = []
        sell_tp2 = []
        sell_sl = []

        for s in signal_history:
            if s["signal"] == "buy":
                buy_tp1.append(s["tp1"])
                buy_tp2.append(s["tp2"])
                buy_sl.append(s["sl"])
            elif s["signal"] == "sell":
                sell_tp1.append(s["tp1"])
                sell_tp2.append(s["tp2"])
                sell_sl.append(s["sl"])

            recap_msg += f"{s['signal'].upper()} TP1:{s['tp1']} TP2:{s['tp2']} SL:{s['sl']}\n"

        await application.bot.send_message(chat_id=CHAT_ID, text=recap_msg)
        signal_history = []

async def daily_recap(application):
    recap_msg = "Rekapan harian sinyal BTC/USD:\n"
    # Simple daily recap: bisa dikembangkan simpan ke DB/ file
    # Disini contoh dummy karena histori hanya 5 sinyal per batch
    await application.bot.send_message(chat_id=CHAT_ID, text=recap_msg)

async def start(update, context):
    await update.message.reply_text("Bot sinyal BTC/USD siap!")

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    # Kirim sinyal tiap 45 menit, mulai 10 detik setelah bot jalan
    application.job_queue.run_repeating(send_signal, interval=45*60, first=10)

    # Rekapan harian jam 8 malam WIB (13:00 UTC)
    def schedule_daily_recap(context):
        asyncio.create_task(daily_recap(context.job.application))

    now = datetime.utcnow() + timedelta(hours=7)
    target_time = datetime.combine(now.date(), time(20, 0))  # 20:00 WIB
    if now > target_time:
        target_time += timedelta(days=1)
    delay_seconds = (target_time - now).total_seconds()

    application.job_queue.run_repeating(
        schedule_daily_recap,
        interval=24*3600,
        first=delay_seconds
    )

    print("Bot BTC/USD running...")
    await application.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    asyncio.run(main())
