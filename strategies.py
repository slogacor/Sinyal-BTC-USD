import requests

def get_xauusd_price():
    url = f"https://api.twelvedata.com/quote?symbol=XAU/USD&apikey={TWELVE_DATA_API_KEY}"
    res = requests.get(url).json()
    return float(res['values']['price'])

def get_scalping_signal():
    rsi = 28  # dummy data, nanti bisa ambil dari API atau indikator
    macd = 5.3  # dummy data

    price = get_xauusd_price()
    signal = ""
    reason = ""

    if rsi < 30 and macd > 0:
        signal = "BUY"
        tp = price + 5
        sl = price - 5
        reason = "Oversold + Bullish Momentum"
    elif rsi > 70 and macd < 0:
        signal = "SELL"
        tp = price - 5
        sl = price + 5
        reason = "Overbought + Bearish Momentum"
    else:
        signal = "HOLD"
        tp = "-"
        sl = "-"
        reason = "Tidak ada peluang jelas"

    return {
        "signal": signal,
        "price": price,
        "tp": tp,
        "sl": sl,
        "rsi": rsi,
        "macd": macd,
        "reason": reason
    }
