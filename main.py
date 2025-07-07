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
API_KEY = "841e95162faf457e8d80207a75c3ca2c"

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

    score = 0
    reasons = []

    if last["rsi"] < 30 and last["close"] > last["ema"]:
        score += 1
        reasons.append("RSI menunjukkan kondisi oversold (<30), menandakan potensi pembalikan ke atas, dan harga menutup di atas EMA9 sebagai sinyal bullish.")
    if last["ema"] > last["sma"]:
        score += 1
        reasons.append("EMA9 lebih tinggi dari SMA50, menandakan tren jangka pendek sedang naik.")
    if confirm_trend_from_last_3(df):
        score += 1
        reasons.append("Tiga candle terakhir menunjukkan konsistensi arah yang sama, menguatkan sinyal tren.")

    if score == 3:
        signal = "BUY" if last["close"] > prev["close"] else "SELL"
    else:
        signal = None

    return signal, score, reasons, last

def calculate_tp_sl(signal, price, atr):
    if signal == "BUY":
        tp1 = round(price + (atr * 3), 2)
        tp2 = round(price + (atr * 4), 2)
        sl = round(price - (atr * 1.5), 2)
    elif signal == "SELL":
        tp1 = round(price - (atr * 3), 2)
        tp2 = round(price - (atr * 4), 2)
        sl = round(price + (atr * 1.5), 2)
    else:
        tp1 = tp2 = sl = None
    return tp1, tp2, sl

def format_status(score):
    return "🟢 GOLDEN MOMENT" if score == 3 else "🔴 NO SIGNAL"

# === PENGIRIM SINYAL ===
async def send_signal(context):
    candles = fetch_twelvedata("XAU/USD")
    if candles is None:
        await context.bot.send_message(chat_id=CHAT_ID, text="❌ Gagal ambil data XAU/USD.")
        return

    df = prepare_df(candles)
    signal, score, reasons, last = generate_signal(df)
    if signal is None:
        return

    price = last["close"]
    tp1, tp2, sl = calculate_tp_sl(signal, price, last["atr"])
    time_now = datetime.now(pytz.timezone("Asia/Jakarta")).strftime("%H:%M:%S")

    reasons_text = "\n".join(f"• {r}" for r in reasons)

    msg = (
        f"📡 *Sinyal XAU/USD*\n"
        f"🕒 Waktu: {time_now} WIB\n"
        f"📈 Arah: *{signal}*\n"
        f"💰 Harga entry: `{price}`\n"
        f"🎯 TP1: `{tp1}` | TP2: `{tp2}`\n"
        f"🛑 SL: `{sl}`\n"
        f"📊 Status: {format_status(score)}\n"
        f"🔍 *Alasan sinyal:*\n{reasons_text}"
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
    tp_total = sum(20 for i in df.itertuples() if i.close > i.open)
    sl_total = sum(10 for i in df.itertuples() if i.close <= i.open)

    msg = (
        f"📊 *Rekap Harian XAU/USD - {now.strftime('%A, %d %B %Y')}*\n"
        f"🕙 Waktu: {now.strftime('%H:%M')} WIB\n"
        f"🎯 Total TP: {tp_total} pips\n"
        f"🛑 Total SL: {sl_total} pips\n"
        f"📈 Berdasarkan 5-menit candle terakhir 5 jam\n"
        f"📌 Sinyal ini sebagai evaluasi dan referensi trading harian."
    )

    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')

# === JADWAL & HANDLER ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("❌ Anda tidak diizinkan menjalankan bot ini.")
        return

    await update.message.reply_text("✅ Bot aktif. Sinyal akan dikirim setiap 2 jam sekali jika golden moment.")

    async def sinyal_job():
        while True:
            await context.bot.send_message(chat_id=CHAT_ID, text="📣 *Ready signal 5 menit lagi!* Bersiap entry.")
            await asyncio.sleep(5 * 60)
            await send_signal(context)
            await asyncio.sleep(2 * 60 * 60 - 5 * 60)

    async def jadwal_rekap():
        while True:
            jakarta = pytz.timezone("Asia/Jakarta")
            now = datetime.now(jakarta)

            if now.weekday() < 5 and now.hour == 21 and now.minute == 59:
                await rekap_harian(context)

            if now.weekday() == 4 and now.hour == 22 and now.minute == 0:
                await context.bot.send_message(chat_id=CHAT_ID, text=
                    "📴 *Market Close*\n"
                    "Hari ini Jumat pukul 22:00 WIB, pasar forex telah tutup.\n"
                    "🔕 Bot berhenti mengirim sinyal akhir pekan.\n"
                    "📅 Bot aktif kembali Senin pukul 09:00 WIB."
                )
                await asyncio.sleep(60 * 60 * 24 * 2)

            if now.weekday() == 0 and now.hour == 9 and now.minute == 0:
                await context.bot.send_message(chat_id=CHAT_ID, text=
                    "✅ *Bot Aktif Kembali*\n"
                    "Hari ini Senin, pasar telah dibuka kembali.\n"
                    "🤖 Bot siap mengirim sinyal setiap 2 jam.\n"
                    "Selamat trading!"
                )

            await asyncio.sleep(60)

    asyncio.create_task(sinyal_job())
    asyncio.create_task(jadwal_rekap())

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    candles = fetch_twelvedata("XAU/USD", "1min", 1)
    if candles:
        price = candles[-1]["close"]
        await update.message.reply_text(f"Harga XAU/USD sekarang: {price}")
    else:
        await update.message.reply_text("❌ Tidak bisa mengambil harga.")

# === MAIN ===
if __name__ == "__main__":
    keep_alive()

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("price", price))

    app_bot.run_polling()
