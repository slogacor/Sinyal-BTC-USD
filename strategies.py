import requests
import pandas as pd
import ta
from config import TWELVE_DATA_API_KEY

# --- Ambil Harga Terakhir XAU/USD ---
def get_xauusd_price():
    url = f"https://api.twelvedata.com/quote?symbol=XAU/USD&apikey={TWELVE_DATA_API_KEY}"

    try:
        res = requests.get(url).json()

        if 'error' in res:
            print(f"API Error: {res['error']}")
            return None

        if 'close' not in res:
            print("Harga tidak tersedia dalam respons API")
            print("Respons API:", res)
            return None

        return float(res['close'])

    except Exception as e:
        print(f"Terjadi kesalahan saat mengambil harga: {e}")
        return None


# --- Hitung Pivot Points sederhana ---
def calculate_pivot_points(df):
    last = df.iloc[-2]  # candle sebelumnya
    pivot = (last['high'] + last['low'] + last['close']) / 3
    r1 = 2 * pivot - last['low']
    s1 = 2 * pivot - last['high']
    return pivot, r1, s1


# --- Deteksi Pola Candlestick sederhana ---
def detect_candlestick_pattern(df):
    df['body'] = abs(df['close'] - df['open'])
    df['range'] = df['high'] - df['low']
    df['upper_shadow'] = df['high'] - df[['close', 'open']].max(axis=1)
    df['lower_shadow'] = df[['close', 'open']].min(axis=1) - df['low']

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Hammer
    if last['lower_shadow'] > 2 * last['body'] and last['upper_shadow'] < last['body']:
        return "Hammer"

    # Bullish Engulfing
    if (prev['close'] < prev['open'] and  # candle merah sebelumnya
        last['close'] > last['open'] and  # candle hijau sekarang
        last['close'] > prev['open'] and
        last['open'] < prev['close']):
        return "Bullish Engulfing"

    # Bearish Engulfing
    if (prev['close'] > prev['open'] and  # candle hijau sebelumnya
        last['close'] < last['open'] and  # candle merah sekarang
        last['open'] > prev['close'] and
        last['close'] < prev['open']):
        return "Bearish Engulfing"

    return None


# --- Hitung Sinyal Scalping Berdasarkan RSI, MACD, SNR, dan Pola Candlestick ---
def get_scalping_signal():
    try:
        # Ambil data historis XAU/USD (interval 5 menit, 100 candles)
        url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=5min&outputsize=100&apikey={TWELVE_DATA_API_KEY}"
        response = requests.get(url).json()

        if 'values' not in response:
            return {"error": "Gagal mengambil data historis untuk analisis."}

        # Ubah ke DataFrame dan urutkan
        df = pd.DataFrame(response['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime')
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)

        # Hitung RSI (window 9) dan MACD
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=9).rsi()
        macd = ta.trend.MACD(close=df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()

        # Hitung pivot points (SNR)
        pivot, r1, s1 = calculate_pivot_points(df)

        # Deteksi pola candlestick
        pattern = detect_candlestick_pattern(df)

        last = df.iloc[-1]
        price = last['close']
        rsi = last['rsi']
        macd_val = last['macd']
        macd_sig = last['macd_signal']

        sl_pips = 10
        tp_pips = 30

        signal = "JANGAN ENTRY DULU !!"
        reason = "Sinyal lemah, tidak cocok untuk scalping"

        # Logika sinyal dengan longgar + konfirmasi pola dan SNR
        if rsi < 40 and (macd_val - macd_sig) > 0.1:
            signal = "BUY"
            reason = "RSI oversold (40) + MACD Bullish Crossover"

            # Konfirmasi pola candlestick bullish
            if pattern in ["Hammer", "Bullish Engulfing"]:
                reason += f" + Konfirmasi pola candlestick {pattern}"

            # Konfirmasi harga dekat support (s1)
            if abs(price - s1) / s1 < 0.002:  # dalam 0.2%
                reason += " + Harga dekat Support (S1)"

        elif rsi > 60 and (macd_sig - macd_val) > 0.1:
            signal = "SELL"
            reason = "RSI overbought (60) + MACD Bearish Crossover"

            # Konfirmasi pola candlestick bearish
            if pattern in ["Bearish Engulfing"]:
                reason += f" + Konfirmasi pola candlestick {pattern}"

            # Konfirmasi harga dekat resistance (r1)
            if abs(price - r1) / r1 < 0.002:  # dalam 0.2%
                reason += " + Harga dekat Resistance (R1)"

        return {
            "signal": signal,
            "price": round(price, 2),
            "tp_pips": tp_pips if signal in ['BUY', 'SELL'] else "-",
            "sl_pips": sl_pips if signal in ['BUY', 'SELL'] else "-",
            "rsi": round(rsi, 2),
            "macd": round(macd_val, 4),
            "pattern": pattern if pattern else "-",
            "pivot": round(pivot, 2),
            "support1": round(s1, 2),
            "resistance1": round(r1, 2),
            "reason": reason
        }

    except Exception as e:
        return {"error": f"Gagal menganalisis data: {e}"}
