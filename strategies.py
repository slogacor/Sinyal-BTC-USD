import requests
from config import TWELVE_DATA_API_KEY

def get_xauusd_price():
    url = f"https://api.twelvedata.com/quote?symbol=XAU/USD&apikey={TWELVE_DATA_API_KEY}"
    res = requests.get(url).json()
    return float(res['values']['price'])

def get_scalping_signal():
    rsi = 28  # dummy data
    macd = 5.3  # dummy data
    price = get_xauusd_price()

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
