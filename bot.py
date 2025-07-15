import time
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import mplfinance as mpf
import matplotlib.pyplot as plt
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from datetime import datetime

# Token dan Chat ID langsung ditulis di sini
TELEGRAM_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
TELEGRAM_CHAT_ID = "-1002657952587"  

bot = Bot(token=TELEGRAM_TOKEN)

SYMBOL = "GC=F"  # XAU/USD Yahoo Finance ticker
INTERVAL_MINUTES = 30
CANDLE_LIMIT = 50

def fetch_data():
    df = yf.download(tickers=SYMBOL, period="2d", interval="15m")
    df = df.tail(CANDLE_LIMIT)
    df.reset_index(inplace=True)
    df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
    return df

def detect_patterns(df):
    df['doji'] = ta.cdl_doji(df['open'], df['high'], df['low'], df['close'])
    df['engulfing'] = ta.cdl_engulfing(df['open'], df['high'], df['low'], df['close'])
    df['hammer'] = ta.cdl_hammer(df['open'], df['high'], df['low'], df['close'])
    df['shooting'] = ta.cdl_shootingstar(df['open'], df['high'], df['low'], df['close'])

    latest = df.iloc[-1]
    patterns = {}

    if latest['doji'] != 0:
        patterns['Doji'] = int(latest['doji'])
    if latest['engulfing'] != 0:
        patterns['Engulfing'] = int(latest['engulfing'])
    if latest['hammer'] != 0:
        patterns['Hammer'] = int(latest['hammer'])
    if latest['shooting'] != 0:
        patterns['ShootingStar'] = int(latest['shooting'])

    return patterns

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

    radius = 0.2
    circle = plt.Circle((x, (high + low)/2), radius, color='red', fill=False, linewidth=2)
    ax.add_patch(circle)

    filename = "chart.png"
    fig.savefig(filename)
    plt.close(fig)
    return filename

def send_telegram_message(text, photo_path):
    bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=open(photo_path, 'rb'), caption=text)

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Bot aktif! Saya akan mengirim chart XAU/USD M15 dan analisa setiap 30 menit.")

def main_loop(context: CallbackContext):
    try:
        df = fetch_data()
        patterns = detect_patterns(df)
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        msg = f"📊 XAU/USD M15 Candlestick Pattern at {now}\n"
        if patterns:
            for pat, val in patterns.items():
                direction = "📈 Bullish" if val > 0 else "📉 Bearish"
                msg += f"→ {pat}: {direction}\n"
        else:
            msg += "No significant patterns detected."

        chart_file = plot_and_mark(df, patterns)
        send_telegram_message(msg, chart_file)
        print(f"Sent update at {now}")

    except Exception as e:
        print("Error in main loop:", e)

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))

    updater.start_polling()
    print("Bot started. Waiting for /start command.")

    # Jalankan main_loop setiap 30 menit
    job_queue = updater.job_queue
    job_queue.run_repeating(main_loop, interval=INTERVAL_MINUTES * 60, first=10)

    updater.idle()

if __name__ == "__main__":
    main()
