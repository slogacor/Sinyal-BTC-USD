import time
import pandas as pd
import yfinance as yf
import talib
import mplfinance as mpf
import matplotlib.pyplot as plt
from telegram.ext import Updater, CommandHandler
from telegram import Bot
from datetime import datetime

# Token dan Chat ID
TELEGRAM_TOKEN = "7678173969:AAEUvVsRqbsHV-oUeky54CVytf_9nU9Fi5c"
TELEGRAM_CHAT_ID = "-1002657952587"

bot = Bot(token=TELEGRAM_TOKEN)

SYMBOL = "GC=F"  # Gold futures (XAU/USD)
INTERVAL_MINUTES = 15
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

def generate_analysis(df):
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()
    df['RSI'] = talib.RSI(df['close'].values, timeperiod=14)

    latest_close = df['close'].iloc[-1]
    sma20 = df['SMA20'].iloc[-1]
    sma50 = df['SMA50'].iloc[-1]
    rsi = df['RSI'].iloc[-1]

    trend = "Bullish 📈" if sma20 > sma50 else "Bearish 📉"
    rsi_signal = "Overbought 🔴" if rsi > 70 else "Oversold 🟢" if rsi < 30 else "Neutral ⚪"

    return f"📉 Current Price: {latest_close:.2f}\n📊 Trend: {trend}\n💡 RSI: {rsi:.2f} → {rsi_signal}"

def plot_chart(df, detected_patterns):
    df_plot = df.set_index('Datetime')

    apds = [mpf.make_addplot(df['SMA20'], color='blue'),
            mpf.make_addplot(df['SMA50'], color='orange')]

    mc = mpf.make_marketcolors(up='g', down='r', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc)

    fig, _ = mpf.plot(df_plot, type='candle', style=s, addplot=apds,
                      title='XAU/USD - 15 Min Chart',
                      ylabel='Price',
                      returnfig=True)

    filename = "chart.png"
    fig.savefig(filename)
    plt.close(fig)
    return filename

def
