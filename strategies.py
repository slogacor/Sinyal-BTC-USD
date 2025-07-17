import requests
from config import TWELVE_DATA_API_KEY

def get_xauusd_price():
    url = f"https://api.twelvedata.com/quote?symbol=XAU/USD&apikey={TWELVE_DATA_API_KEY}"
    
    try:
        res = requests.get(url).json()

        # Cek apakah ada error dalam respons
        if 'error' in res:
            print(f"API Error: {res['error']}")
            return None

        # Pastikan 'close' tersedia di dalam respons
        if 'close' not in res:
            print("Harga tidak tersedia dalam respons API")
            print("Respons API:", res)
            return None

        # Kembalikan harga sebagai float
        return float(res['close'])

    except Exception as e:
        print(f"Terjadi kesalahan saat mengambil harga: {e}")
        return None


def get_scalping_signal():
    rsi = 28  # Dummy data
    macd = 5.3  # Dummy data
    price = get_xauusd_price()

    if price is None:
        return {"error": "Gagal mendapatkan harga emas"}

    if rsi < 30 and macd > 0:
        signal = "BUY"
        sl_pips = -10
        tp_pips = sl_pips * -3  # Risk/Reward 1:3
        reason = "Oversold + Bullish Momentum"
    elif rsi > 70 and macd < 0:
        signal = "SELL"
        sl_pips = -10
        tp_pips = sl_pips * -3
        reason = "Overbought + Bearish Momentum"
    else:
        signal = "HOLD"
        tp_pips = "-"
        sl_pips = "-"
        reason = "Tidak ada peluang jelas"

    return {
        "signal": signal,
        "price": price,
        "tp_pips": tp_pips,
        "sl_pips": sl_pips,
        "rsi": rsi,
        "macd": macd,
        "reason": reason
    }
