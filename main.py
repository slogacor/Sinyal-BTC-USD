from flask import Flask
from threading import Thread
import requests
from datetime import datetime
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
API_KEY = "94a7d766d73f4db4a7ddf877473711c7"

signals_buffer = []
last_signal_price = None
last_failed = False  # Flag untuk status error terakhir

# === SERVER KEEP ALIVE ===
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running"
def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

# === DATA & ANALISA TEKNIKAL ===
def fetch_twelvedata(symbol="XAU/USD", interval="5min", count=100):
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

    signal = None
    reason = ""

    if last["rsi"] <= 30 and last["close"] > last["ema"] and last["ema"] > last["sma"]:
        signal = "BUY"
        reason = (
            "RSI menunjukkan oversold (<=30), harga menembus EMA9 ke atas, dan EMA9 di atas SMA50.\n"
            "Ini sinyal kuat pembalikan ke atas (bullish reversal)."
        )
    elif last["rsi"] >= 70 and last["close"] < last["ema"] and last["ema"] < last["sma"]:
        signal = "SELL"
        reason = (
            "RSI menunjukkan overbought (>=70), harga menembus EMA9 ke bawah, dan EMA9 di bawah SMA50.\n"
            "Ini sinyal kuat pembalikan ke bawah (bearish reversal)."
        )

    return signal, reason, last

def calculate_tp_sl(signal, price, atr):
    if signal == "BUY":
        tp1 = round(price + (atr * 2.5), 2)
        tp2 = round(price + (atr * 4), 2)
        sl = round(price - (atr * 1.2), 2)
    else:
        tp1 = round(price - (atr * 2.5), 2)
        tp2 = round(price - (atr * 4), 2)
        sl = round(price + (atr * 1.2), 2)
    return tp1, tp2, sl

def format_status():
    return "✨ *Golden Moment* - Sinyal sangat akurat dan kuat."

# === PENGIRIM SINYAL ===
async def send_signal(context):
    global last_failed

    candles = fetch_twelvedata("XAU/USD")
    if candles is None:
        if not last_failed:
            last_failed = True
            await context.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data XAU/USD. Bot akan mencoba lagi dalam 1 jam.")
        await asyncio.sleep(3600)  # Jika gagal, tunggu 1 jam sebelum lanjut
        return

    last_failed = False  # Reset error flag kalau berhasil

    df = prepare_df(candles)
    signal, reason, last = generate_signal(df)
    if signal is None:
        return  # Tidak ada sinyal, tidak kirim apa-apa

    price = last["close"]
    tp1, tp2, sl = calculate_tp_sl(signal, price, last["atr"])
    time_now = datetime.now(pytz.timezone("Asia/Jakarta")).strftime("%H:%M:%S")

    msg = (
        f"📡 *Sinyal XAU/USD*\n"
        f"🕒 Waktu: {time_now} WIB\n"
        f"📈 Arah: *{signal}*\n"
        f"💰 Harga entry: `{price}`\n"
        f"🎯 TP1: `{tp1}` | TP2: `{tp2}`\n"
        f"🛑 SL: `{sl}`\n"
        f"{format_status()}\n"
        f"🔍 *Alasan sinyal:*\n{reason}"
    )

    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')

# === REKAP HARIAN ===
async def rekap_harian(context):
    jakarta = pytz.timezone("Asia/Jakarta")
    now = datetime.now(jakarta)

    candles = fetch_twelvedata("XAU/USD", "5min", 60)
    if candles is None:
        await context.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data untuk rekap harian.")
        return

    df = prepare_df(candles).tail(60)
    bullish = sum(1 for i in df.itertuples() if i.close > i.open)
    bearish = sum(1 for i in df.itertuples() if i.close < i.open)

    msg = (
        f"📊 *Rekap Harian XAU/USD - {now.strftime('%A, %d %B %Y')}*\n"
        f"🕙 Waktu: {now.strftime('%H:%M')} WIB\n"
        f"📈 Candle Bullish: {bullish}\n"
        f"📉 Candle Bearish: {bearish}\n"
        f"📌 Sinyal ini sebagai evaluasi dan referensi trading harian."
    )

    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')

# === JADWAL & HANDLER ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("❌ Anda tidak diizinkan menjalankan bot ini.")
        return

    await update.message.reply_text("✅ Bot aktif. Sinyal akan dikirim saat golden moment ditemukan.")

    async def sinyal_job():
        while True:
            await send_signal(context)
            await asyncio.sleep(300)  # Cek setiap 5 menit

    async def jadwal_rekap():
        while True:
            jakarta = pytz.timezone("Asia/Jakarta")
            now = datetime.now(jakarta)

            if now.weekday() < 5 and now.hour == 21 and now.minute == 59:
                await rekap_harian(context)

            if now.weekday() == 4 and now.hour == 22 and now.minute == 0:
                await context.bot.send_message(chat_id=CHAT_ID, text=(
                    "📴 *Market Close*\n"
                    "Hari ini Jumat pukul 22:00 WIB, pasar forex telah tutup.\n"
                    "🔕 Bot berhenti mengirim sinyal akhir pekan.\n"
                    "📅 Bot aktif kembali Senin pukul 09:00 WIB."
                ))
                await asyncio.sleep(60 * 60 * 24 * 2)

            if now.weekday() == 0 and now.hour == 9 and now.minute == 0:
                await context.bot.send_message(chat_id=CHAT_ID, text=(
                    "✅ *Bot Aktif Kembali*\n"
                    "Hari ini Senin, pasar telah dibuka kembali.\n"
                    "🤖 Bot siap mengirim sinyal saat golden moment ditemukan.\n"
                    "Selamat trading!"
                ))

            await asyncio.sleep(60)

    asyncio.create_task(sinyal_job())
    asyncio.create_task(jadwal_rekap())

# === RUN BOT ===
if __name__ == "__main__":
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot started...")
    app.run_polling()
