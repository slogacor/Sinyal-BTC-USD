import time
import pandas as pd
import yfinance as yf
import talib
import mplfinance as mpf
import matplotlib.pyplot as plt
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from datetime import datetime
import logging

# Setup logging biar kelihatan error/debug
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Konfigurasi Telegram
TELEGRAM_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
TELEGRAM_CHAT_ID = "-1002657952587"

bot = Bot(token=TELEGRAM_TOKEN)

# Config chart
SYMBOL = "GC=F"
INTERVAL_MINUTES = 15
CANDLE_LIMIT = 50

# Ambil data dari Yahoo Finance
def fetch_data():
    df = yf.download(tickers=SYMBOL, period="2d", interval="15m")
    df = df.tail(CANDLE_LIMIT)
    df.reset_index(inplace=True)
    df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
    df['Datetime'] = pd.to_datetime(df['Datetime'])
    return df

# Deteksi pola candlestick
def detect_patterns(df):
    openp = df['open'].values
    highp = df['high'].values
    lowp = df['low'].values
    closep = df['close'].values

    patterns = {
        "Hammer": talib.CDLHAMMER(openp, highp, lowp, closep),
        "Engulfing": talib.CDLENGULFING(openp, highp, lowp, closep),
        "Doji": talib.CDLDOJI(openp, highp, lowp, closep),
        "ShootingStar": talib.CDLSHOOTINGSTAR(openp, highp, lowp, closep),
        "MorningStar": talib.CDLMORNINGSTAR(openp, highp, lowp, closep),
        "EveningStar": talib.CDLEVENINGSTAR(openp, highp, lowp, closep),
    }
    latest = len(closep) - 1
    detected = {}
    for name, values in patterns.items():
        val = values[latest]
        if val != 0:
            detected[name] = val
    return detected

# Bikin chart dan tandai candle terakhir
def plot_and_mark(df, detected_patterns):
    mc = mpf.make_marketcolors(up='g', down='r', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc)
    df_plot = df.set_index('Datetime')
    latest_idx = len(df_plot) - 1
    fig, axlist = mpf.plot(df_plot, type='candle', style=s, returnfig=True)
    ax = axlist[0]
    candle = df.iloc[latest_idx]
    x = latest_idx
    low = candle['low']
    high = candle['high']
    circle = plt.Circle((x, (high + low) / 2), 0.3, color='red', fill=False, linewidth=2)
    ax.add_patch(circle)
    filename = "chart.png"
    fig.savefig(filename)
    plt.close(fig)
    return filename

# Kirim pesan ke grup
def send_telegram_message(text, photo_path):
    bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=open(photo_path, 'rb'), caption=text)

# Handler untuk /start
def start_command(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Bot sedang berjalan dan akan mengirim sinyal jika pola candlestick terdeteksi.")

# Handler untuk pesan biasa yang mengandung "start"
def message_handler(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    if 'start' in text:
        update.message.reply_text("✅ Bot aktif dan siap memantau sinyal candlestick.")

# Fungsi utama analisis data
def pattern_loop():
    while True:
        try:
            df = fetch_data()
            patterns = detect_patterns(df)
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

            if patterns:
                msg = f"📊 XAU/USD M15 Candlestick Pattern Detected at {now}\n"
                for pat, val in patterns.items():
                    direction = "📈 Bullish" if val > 0 else "📉 Bearish"
                    msg += f"→ {pat}: {direction}\n"
                chart_file = plot_and_mark(df, patterns)
                send_telegram_message(msg, chart_file)
                print(f"[{now}] Sinyal terkirim.")
            else:
                print(f"[{now}] Tidak ada pola terdeteksi.")
        except Exception as e:
            print("Terjadi kesalahan:", e)
        time.sleep(INTERVAL_MINUTES * 60)

# Jalankan bot Telegram
def run_telegram_bot():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, message_handler))
    updater.start_polling()
    print("🤖 Telegram bot aktif dan polling...")
    updater.idle()

# Menjalankan bot & analisis secara paralel
if __name__ == "__main__":
    import threading
    # Jalankan bot Telegram di thread terpisah
    telegram_thread = threading.Thread(target=run_telegram_bot)
    telegram_thread.start()

    # Jalankan loop analisis
    pattern_loop()
