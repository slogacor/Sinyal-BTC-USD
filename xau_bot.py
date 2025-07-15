import time
import pandas as pd
import yfinance as yf
import talib
import mplfinance as mpf
import matplotlib.pyplot as plt
from telegram import Bot
from datetime import datetime

# === GANTI SESUAI MILIKMU ===
TELEGRAM_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
TELEGRAM_CHAT_ID = "-1002657952587" 
bot = Bot(token=TELEGRAM_TOKEN)

SYMBOL = "GC=F"  # Emas (XAU/USD)
INTERVAL_MINUTES = 30
CANDLE_LIMIT = 50

def fetch_data():
    df = yf.download(tickers=SYMBOL, period="2d", interval="15m")
    df = df.tail(CANDLE_LIMIT)
    df.reset_index(inplace=True)
    df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
    df['Datetime'] = pd.to_datetime(df['Datetime'])
    return df

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
    circle = plt.Circle((x, (high + low)/2), 0.2, color='red', fill=False, linewidth=2)
    ax.add_patch(circle)

    filename = "chart.png"
    fig.savefig(filename)
    plt.close(fig)
    return filename

def send_telegram_message(text, photo_path):
    bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=open(photo_path, 'rb'), caption=text)

def main():
    while True:
        try:
            df = fetch_data()
            patterns = detect_patterns(df)
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

            if patterns:
                msg = f"📊 XAU/USD M15 Candlestick Pattern at {now}\n"
                for pat, val in patterns.items():
                    direction = "📈 Bullish" if val > 0 else "📉 Bearish"
                    msg += f"→ {pat}: {direction}\n"
                chart_file = plot_and_mark(df, patterns)
                send_telegram_message(msg, chart_file)
                print(f"✅ Sent message at {now}")
            else:
                print(f"ℹ️ No pattern detected at {now}")

        except Exception as e:
            print("❌ Error:", e)

        time.sleep(INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
