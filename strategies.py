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


# --- Hitung Sinyal Scalping Berdasarkan RSI & MACD ---
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
        df = df.sort_values('datetime')  # Urutkan dari lama ke terbaru
        df['close'] = df['close'].astype(float)

        # Hitung RSI dan MACD
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
        macd = ta.trend.MACD(close=df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()

        # Ambil bar terakhir
        last = df.iloc[-1]
        price = last['close']
        rsi = last['rsi']
        macd_val = last['macd']
        macd_sig = last['macd_signal']

        # Atur SL dan TP untuk scalping (30 pips = $3.0)
        sl_pips = 10  # 10 pips = $1.0 (asumsi 1 pip = $0.1 untuk emas)
        tp_pips = 30  # 30 pips = $3.0

        # Logika sinyal
        if rsi < 30 and macd_val > macd_sig:
            signal = "BUY"
            reason = "RSI Oversold + MACD Bullish Crossover"
        elif rsi > 70 and macd_val < macd_sig:
            signal = "SELL"
            reason = "RSI Overbought + MACD Bearish Crossover"
        else:
            signal = "HOLD"
            reason = "Sinyal lemah, tidak cocok untuk scalping"

        return {
            "signal": signal,
            "price": round(price, 2),
            "tp_pips": tp_pips if signal in ['BUY', 'SELL'] else "-",
            "sl_pips": sl_pips if signal in ['BUY', 'SELL'] else "-",
            "rsi": round(rsi, 2),
            "macd": round(macd_val, 2),
            "reason": reason
        }

    except Exception as e:
        return {"error": f"Gagal menganalisis data: {e}"}
