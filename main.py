from flask import Flask
from threading import Thread
import requests
import logging
from datetime import datetime, timedelta, time
import asyncio
import pandas as pd
import ta
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- KONFIGURASI ---
BOT_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
CHAT_ID = "-1002883903673"
AUTHORIZED_USER_ID = 1305881282
API_KEY = "841e95162faf457e8d80207a75c3ca2c"
signals_buffer = []
active_signals = []

# === KEEP ALIVE ===
app = Flask('')
@app.route('/')
def home():
    return "Bot is alive!"
def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

def fetch_twelvedata(symbol="EUR/USD", interval="5min", outputsize=100):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={API_KEY}"
    try:
        res = requests.get(url)
        data = res.json()
        if "values" not in data:
            logging.error("Data tidak tersedia: %s", data.get("message", ""))
            return None
        candles = [{
            "datetime": datetime.strptime(d["datetime"], "%Y-%m-%d %H:%M:%S"),
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"])
        } for d in data["values"]]
        return candles
    except Exception as e:
        logging.error(f"Gagal ambil data dari Twelve Data: {e}")
        return None

def prepare_df(candles):
    df = pd.DataFrame(candles)
    df = df.sort_values("datetime").reset_index(drop=True)
    return df

def find_snr(df):
    recent = df.tail(30)
    return recent["low"].min(), recent["high"].max()

def confirm_trend_from_last_3(df):
    candles = df.tail(4)
    if len(candles) < 4:
        return None
    c1, c2, c3 = candles.iloc[-4:-1].to_dict('records')
    uptrend = all(c["close"] > c["open"] for c in [c1, c2, c3])
    downtrend = all(c["close"] < c["open"] for c in [c1, c2, c3])
    return "BUY" if uptrend else "SELL" if downtrend else None

def generate_signal(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    df["ma"] = ta.trend.SMAIndicator(df["close"], window=50).sma_indicator()
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["atr"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()

    support, resistance = find_snr(df)
    last_close = df["close"].iloc[-1]
    rsi_now = df["rsi"].iloc[-1]
    ma = df["ma"].iloc[-1]
    ema = df["ema"].iloc[-1]
    atr = df["atr"].iloc[-1]

    trend = confirm_trend_from_last_3(df)
    if not trend:
        if atr > 0.2:
            return ("LEMAH", last_close, rsi_now, atr, ma, ema), 1, support, resistance
        else:
            return None, 0, support, resistance

    score = 0
    if atr > 0.2:
        score += 1
    if trend == "BUY" and last_close > ma and last_close > ema and rsi_now < 70:
        score += 2
    elif trend == "SELL" and last_close < ma and last_close < ema and rsi_now > 30:
        score += 2

    if score >= 1:
        return (trend, last_close, rsi_now, atr, ma, ema), score, support, resistance
    return None, score, support, resistance

def calculate_tp_sl(signal, entry, score):
    if score >= 3:
        tp1_pips, tp2_pips, sl_pips = 30, 55, 20
    elif score == 2:
        tp1_pips, tp2_pips, sl_pips = 25, 40, 20
    else:
        tp1_pips, tp2_pips, sl_pips = 15, 25, 15

    tp1 = entry + tp1_pips * 0.0001 if signal == "BUY" else entry - tp1_pips * 0.0001
    tp2 = entry + tp2_pips * 0.0001 if signal == "BUY" else entry - tp2_pips * 0.0001
    sl = entry - sl_pips * 0.0001 if signal == "BUY" else entry + sl_pips * 0.0001

    return tp1, tp2, sl, tp1_pips, tp2_pips, sl_pips

def adjust_entry(signal, entry, last_close):
    if signal == "BUY" and entry >= last_close:
        entry = last_close - 0.0001
    elif signal == "SELL" and entry <= last_close:
        entry = last_close + 0.0001
    return round(entry, 5)

def format_status(score):
    return "GOLDEN MOMENT 🌟" if score >= 3 else "MODERATE ⚠️" if score == 2 else "LEMAH ⚠️ Harap berhati-hati"

def is_weekend(now):
    return now.weekday() in [5, 6]

async def send_signal(context):
    global signals_buffer, active_signals
    application = context.application
    jakarta = pytz.timezone("Asia/Jakarta")
    now = datetime.now(jakarta)
    now_minus3 = now - timedelta(hours=3)

    if is_weekend(now) or (now.weekday() == 0 and now.time() < time(8, 0)):
        return

    if now.minute % 45 != 0:
        return

    candles = fetch_twelvedata("EUR/USD", "5min", 9)
    if candles is None or len(candles) < 9:
        await application.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data EUR/USD (kurang dari 9 candle)")
        return
    df = prepare_df(candles)
    df_analyze = df.iloc[0:8]

    result, score, support, resistance = generate_signal(df_analyze)
    if result:
        signal, entry, rsi, atr, ma, ema = result
        last_close = df_analyze["close"].iloc[-1]
        entry = adjust_entry(signal, entry, last_close)
        tp1, tp2, sl, tp1_pips, tp2_pips, sl_pips = calculate_tp_sl(signal, entry, score)
        status_text = format_status(score)
        entry_note = "Entry di bawah harga sinyal" if signal == "BUY" else "Entry di atas harga sinyal"
        msg = (
            f"🚨 *Sinyal {signal}* {'⬆️' if signal=='BUY' else '⬇️'} _EUR/USD_ @ {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📊 Status: {status_text}\n"
            f"⏳ RSI: {rsi:.2f}, ATR: {atr:.2f}\n"
            f"⚖️ Support: {support:.5f}, Resistance: {resistance:.5f}\n"
            f"💰 Entry: {entry:.5f} ({entry_note})\n"
            f"🌟 TP1: {tp1:.5f} (+{tp1_pips} pips), TP2: {tp2:.5f} (+{tp2_pips} pips)\n"
            f"🛑 SL: {sl:.5f} (-{sl_pips} pips)"
        )
        await application.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
        active_signals.append({"signal": signal, "entry": entry, "tp1": tp1, "tp2": tp2, "sl": sl, "status": "active"})

async def monitor_active_signals(application):
    global active_signals
    while True:
        if not active_signals:
            await asyncio.sleep(60)
            continue

        candles = fetch_twelvedata("EUR/USD", "1min", 1)
        if candles:
            price = candles[0]["close"]
            remove_list = []
            for signal in active_signals:
                if signal["status"] != "active":
                    continue

                if signal["signal"] == "BUY":
                    if price >= signal["tp2"]:
                        msg = f"🌟 *TP2 HIT!* Harga: {price:.5f} ✅"
                        remove_list.append(signal)
                    elif price >= signal["tp1"]:
                        msg = f"🌟 *TP1 HIT!* Harga: {price:.5f} ✅"
                        signal["status"] = "tp1_hit"
                    elif price <= signal["sl"]:
                        msg = f"🛑 *SL HIT!* Harga: {price:.5f} ❌"
                        remove_list.append(signal)
                    else:
                        continue
                else:  # SELL
                    if price <= signal["tp2"]:
                        msg = f"🌟 *TP2 HIT!* Harga: {price:.5f} ✅"
                        remove_list.append(signal)
                    elif price <= signal["tp1"]:
                        msg = f"🌟 *TP1 HIT!* Harga: {price:.5f} ✅"
                        signal["status"] = "tp1_hit"
                    elif price >= signal["sl"]:
                        msg = f"🛑 *SL HIT!* Harga: {price:.5f} ❌"
                        remove_list.append(signal)
                    else:
                        continue

                await application.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')

            for s in remove_list:
                active_signals.remove(s)

        await asyncio.sleep(60)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("❌ Anda tidak diizinkan menjalankan bot ini.")
        return
    await update.message.reply_text("Bot dimulai dan akan memantau sinyal.")
    asyncio.create_task(send_signal(context))
    asyncio.create_task(monitor_active_signals(context.application))

if __name__ == "__main__":
    keep_alive()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.run_polling()
