from flask import Flask
from threading import Thread
import requests
from datetime import datetime, time, timedelta
import pytz
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from ta.trend import EMAIndicator, SMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import pandas as pd

# === CONFIGURASI ===
BOT_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
CHAT_ID = "-1002883903673"
AUTHORIZED_USER_ID = 1305881282
API_KEY = "841e95162faf457e8d80207a75c3ca2c"
signals_buffer = []

# === KEEP ALIVE SERVER ===
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running"
def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

# === FUNGSI DATA & TEKNIKAL ===
def fetch_twelvedata(symbol="EUR/USD", interval="5min", count=100):
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

def find_snr(df):
    highs = df["high"].tail(30)
    lows = df["low"].tail(30)
    return highs.max(), lows.min()

def confirm_trend_from_last_3(df):
    last_3 = df.tail(3)
    return all(last_3["close"] > last_3["open"]) or all(last_3["close"] < last_3["open"])

def generate_signal(df):
    rsi = RSIIndicator(df["close"], window=14).rsi()
    ema = EMAIndicator(df["close"], window=9).ema_indicator()
    sma = SMAIndicator(df["close"], window=50).sma_indicator()
    atr = AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()
    df["rsi"] = rsi
    df["ema"] = ema
    df["sma"] = sma
    df["atr"] = atr
    df.dropna(inplace=True)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    snr_res, snr_sup = find_snr(df)

    score = 0
    note = ""

    if last["rsi"] < 30 and last["close"] > last["ema"]:
        score += 1
        note += "✅ RSI oversold + harga di atas EMA\n"
    if last["ema"] > last["sma"]:
        score += 1
        note += "✅ EMA > SMA (tren naik)\n"
    if confirm_trend_from_last_3(df):
        score += 1
        note += "✅ Tiga candle mendukung arah\n"

    signal = None
    if score == 3:
        signal = "BUY" if last["close"] > prev["close"] else "SELL"
    elif score == 2:
        signal = "BUY" if last["close"] > last["open"] else "SELL"

    return signal, score, note, last, snr_res, snr_sup

def calculate_tp_sl(signal, price, score, atr):
    atr_pips = round(atr * 10000)
    buffer = 5
    if signal == "BUY":
        tp1 = round(price + (atr * (1 + score / 2)), 5)
        tp2 = round(price + (atr * (1.5 + score / 2)), 5)
        sl = round(price - (atr * (0.8)), 5)
    else:
        tp1 = round(price - (atr * (1 + score / 2)), 5)
        tp2 = round(price - (atr * (1.5 + score / 2)), 5)
        sl = round(price + (atr * (0.8)), 5)
    return tp1, tp2, sl

def format_status(score):
    return "🟢 KUAT" if score == 3 else "🟡 MODERAT" if score == 2 else "🔴 LEMAH"

# === FUNGSI PENGIRIM SINYAL ===
async def send_signal(context):
    candles = fetch_twelvedata()
    if candles is None:
        await context.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data EUR/USD.")
        return

    df = prepare_df(candles)
    signal, score, note, last, res, sup = generate_signal(df)
    if not signal:
        await context.bot.send_message(chat_id=CHAT_ID, text="⏳ Tidak ada sinyal valid saat ini.")
        return

    price = last["close"]
    tp1, tp2, sl = calculate_tp_sl(signal, price, score, last["atr"])
    time_now = datetime.now(pytz.timezone("Asia/Jakarta")).strftime("%H:%M:%S")

    alert = ""
    if score < 3:
        alert = "\n⚠️ *Hati-hati*, sinyal tidak terlalu kuat.\n"

    msg = (
        f"📡 *Sinyal EUR/USD*\n"
        f"🕒 Waktu: {time_now} WIB\n"
        f"📈 Arah: *{signal}*\n"
        f"💰 Entry: `{price}`\n"
        f"🎯 TP1: `{tp1}` | TP2: `{tp2}`\n"
        f"🛑 SL: `{sl}`\n"
        f"{alert}"
        f"📊 Status: {format_status(score)}\n"
        f"🔍 Analisa:\n{note}"
    )

    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
    signals_buffer.append({"signal": signal, "price": price})

# === REKAP HARIAN ===
async def rekap_harian(context):
    jakarta = pytz.timezone("Asia/Jakarta")
    now = datetime.now(jakarta)
    if now.weekday() >= 5:
        return

    candles = fetch_twelvedata("EUR/USD", "5min", 60)
    if candles is None:
        await context.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data untuk rekap harian.")
        return

    df = prepare_df(candles).tail(60)
    tp_total = sum(20 for i in df.itertuples() if i.close > i.open)
    sl_total = sum(10 for i in df.itertuples() if i.close <= i.open)

    msg = (
        f"📊 *Rekap Harian EUR/USD - {now.strftime('%A, %d %B %Y')}*\n"
        f"🕙 Waktu: {now.strftime('%H:%M')} WIB\n"
        f"🎯 Total TP: {tp_total} pips\n"
        f"🛑 Total SL: {sl_total} pips\n"
        f"📈 Berdasarkan 5-menit candle terakhir 5 jam\n"
        f"📌 Sinyal ini sebagai evaluasi dan referensi trading harian."
    )

    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')

# === PERINTAH /start & /price ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("❌ Anda tidak diizinkan menjalankan bot ini.")
        return

    await update.message.reply_text("✅ Bot aktif. Sinyal akan dikirim setiap 45 menit.")

    async def sinyal_job():
        while True:
            await send_signal(context)
            await asyncio.sleep(45 * 60)

    async def jadwal_rekap():
        while True:
            jakarta = pytz.timezone("Asia/Jakarta")
            now = datetime.now(jakarta)
            next_22 = datetime.combine(now.date(), time(22, 0, 0))
            if now > next_22:
                next_22 += timedelta(days=1)
            delay = (next_22 - now).total_seconds()
            await asyncio.sleep(delay)
            await rekap_harian(context)

    asyncio.create_task(sinyal_job())
    asyncio.create_task(jadwal_rekap())

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    candles = fetch_twelvedata("EUR/USD", "1min", 1)
    if candles:
        price = candles[-1]["close"]
        await update.message.reply_text(f"Harga EUR/USD sekarang: {price}")
    else:
        await update.message.reply_text("❌ Tidak bisa mengambil harga.")

# === MAIN BOT ===
if __name__ == "__main__":
    keep_alive()
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("price", price))
    app_bot.run_polling()
