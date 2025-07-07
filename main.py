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
signals_log = []

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
            return None
        candles = [
            {
                "datetime": datetime.strptime(d["datetime"], "%Y-%m-%d %H:%M:%S"),
                "open": float(d["open"]),
                "high": float(d["high"]),
                "low": float(d["low"]),
                "close": float(d["close"]),
            } for d in data["values"]
        ]
        return candles
    except:
        return None

def prepare_df(candles):
    df = pd.DataFrame(candles)
    return df.sort_values("datetime").reset_index(drop=True)

def find_snr(df):
    recent = df.tail(30)
    return recent["low"].min(), recent["high"].max()

def confirm_trend(df):
    candles = df.tail(4)
    if len(candles) < 4:
        return None
    c1, c2, c3 = candles.iloc[-4:-1].to_dict("records")
    up = all(c["close"] > c["open"] for c in [c1, c2, c3])
    down = all(c["close"] < c["open"] for c in [c1, c2, c3])
    return "BUY" if up else "SELL" if down else None

def generate_signal(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    df["ma"] = ta.trend.SMAIndicator(df["close"], window=50).sma_indicator()
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["atr"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()

    support, resistance = find_snr(df)
    last_close = df["close"].iloc[-1]
    rsi = df["rsi"].iloc[-1]
    ma = df["ma"].iloc[-1]
    ema = df["ema"].iloc[-1]
    atr = df["atr"].iloc[-1]
    trend = confirm_trend(df)

    score = 0
    if atr > 0.1:
        score += 1
    if trend == "BUY" and last_close > ma and last_close > ema and rsi < 70:
        score += 2
    elif trend == "SELL" and last_close < ma and last_close < ema and rsi > 30:
        score += 2

    if trend:
        return (trend, last_close, rsi, atr, ma, ema), score, support, resistance
    return None, score, support, resistance

def calculate_tp_sl(signal, entry):
    tp1 = entry + 0.0030 if signal == "BUY" else entry - 0.0030
    tp2 = entry + 0.0060 if signal == "BUY" else entry - 0.0060
    sl = entry - 0.0025 if signal == "BUY" else entry + 0.0025
    return round(tp1, 5), round(tp2, 5), round(sl, 5)

def candle_hit(candles, signal, entry, sl, tp1, tp2):
    hit_tp1 = hit_tp2 = hit_sl = False
    for c in candles:
        high, low = c.high, c.low
        if signal == "BUY":
            if low <= sl: hit_sl = True
            if high >= tp1: hit_tp1 = True
            if high >= tp2: hit_tp2 = True
        else:
            if high >= sl: hit_sl = True
            if low <= tp1: hit_tp1 = True
            if low <= tp2: hit_tp2 = True
    return hit_tp1, hit_tp2, hit_sl

def format_signal_message(signal, entry, tp1, tp2, sl, rsi, atr, support, resistance, status):
    return (
        f"📢 *Sinyal {signal} EUR/USD*
        f"\n💰 Entry: {entry}\n🎯 TP1: {tp1}, TP2: {tp2}\n🛑 SL: {sl}"
        f"\n📊 RSI: {rsi:.2f}, ATR: {atr:.2f}"
        f"\n⚖️ Support: {support:.5f}, Resistance: {resistance:.5f}"
        f"\n📈 Status: {status}\n⏳ Evaluasi dalam 3 candle ke depan."
    )

def format_status(score):
    return "GOLDEN 🌟" if score >= 3 else "MODERATE ⚠️" if score == 2 else "LEMAH ⚠️"

def is_market_open():
    now = datetime.now(pytz.timezone("Asia/Jakarta"))
    if now.weekday() in [5, 6]: return False
    if now.weekday() == 0 and now.time() < time(8, 0): return False
    return True

async def send_signal(context):
    global signals_log
    if not is_market_open(): return

    candles = fetch_twelvedata("EUR/USD", "5min", 20)
    if not candles or len(candles) < 15: return
    df = prepare_df(candles)
    df_analyze = df.iloc[0:12]
    result, score, support, resistance = generate_signal(df_analyze)

    if result:
        signal, entry, rsi, atr, ma, ema = result
        tp1, tp2, sl = calculate_tp_sl(signal, entry)
        msg = format_signal_message(signal, round(entry, 5), tp1, tp2, sl, rsi, atr, support, resistance, format_status(score))
        await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

        # Save signal
        signals_log.append({
            "datetime": datetime.now(pytz.timezone("Asia/Jakarta")),
            "signal": signal,
            "entry": entry,
            "tp1": tp1,
            "tp2": tp2,
            "sl": sl,
            "eval_candles": df.iloc[12:15],
        })

        # Evaluate hits after 3 candles
        await asyncio.sleep(15 * 60)
        eval_candles = fetch_twelvedata("EUR/USD", "5min", 5)
        df_eval = prepare_df(eval_candles)
        hit_tp1, hit_tp2, hit_sl = candle_hit(df_eval.tail(3).itertuples(), signal, entry, sl, tp1, tp2)
        result_msg = f"🎯 *Evaluasi Sinyal*
        f"\nTP1: {'✅' if hit_tp1 else '❌'}, TP2: {'✅' if hit_tp2 else '❌'}, SL: {'✅' if hit_sl else '❌'}"
        await context.bot.send_message(chat_id=CHAT_ID, text=result_msg, parse_mode='Markdown')

async def daily_summary(context):
    jakarta = pytz.timezone("Asia/Jakarta")
    today = datetime.now(jakarta).date()
    summary = [s for s in signals_log if s["datetime"].date() == today]
    if not summary: return

    total = len(summary)
    tp1_hit = sum(1 for s in summary if s.get("hit_tp1"))
    tp2_hit = sum(1 for s in summary if s.get("hit_tp2"))
    sl_hit = sum(1 for s in summary if s.get("hit_sl"))

    msg = (
        f"📊 *Rekap Sinyal Hari Ini*
        f"\nJumlah sinyal: {total}\nTP1 Hit: {tp1_hit}\nTP2 Hit: {tp2_hit}\nSL Hit: {sl_hit}"
    )
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("⛔ Anda tidak diizinkan.")
        return
    await update.message.reply_text("✅ Bot aktif.")

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    candles = fetch_twelvedata("EUR/USD", "1min", 1)
    if candles:
        last = candles[0]
        msg = (
            f"💱 *EUR/USD Price*
            f"\nOpen: {last['open']:.5f}, Close: {last['close']:.5f}, High: {last['high']:.5f}, Low: {last['low']:.5f}"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Gagal ambil harga.")

if __name__ == "__main__":
    keep_alive()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("price", cmd_price))
    application.job_queue.run_repeating(send_signal, interval=2700, first=10)
    application.job_queue.run_daily(daily_summary, time=time(22, 0, 0), days=(0, 1, 2, 3, 4))
    application.run_polling()
