def get_scalping_signal():
    try:
        # Ambil data historis XAU/USD
        url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=5min&outputsize=100&apikey={TWELVE_DATA_API_KEY}"
        response = requests.get(url).json()

        if 'values' not in response:
            return {"error": "Gagal mengambil data historis untuk analisis."}

        # Ubah ke DataFrame
        df = pd.DataFrame(response['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime')
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)

        # Hitung indikator
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=9).rsi()
        macd = ta.trend.MACD(close=df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()

        # Hitung SNR dan deteksi pola
        pivot, r1, s1 = calculate_pivot_points(df)
        pattern = detect_candlestick_pattern(df)

        # Ambil nilai terakhir
        last = df.iloc[-1]
        price = last['close']
        rsi = last['rsi']
        macd_val = last['macd']
        macd_sig = last['macd_signal']

        sl_pips = 10
        tp_pips = 30
        signal = "JANGAN ENTRY DULU !!"
        reason = "Sinyal tidak cukup kuat atau tidak ada konfirmasi."

        # Logika longgar: BUY
        if rsi < 45 and (macd_val - macd_sig) > 0.05:
            signal = "BUY"
            reason = "RSI mendekati oversold + MACD bullish crossover"

            if pattern in ["Hammer", "Bullish Engulfing"]:
                reason += f" + Pola candlestick {pattern}"

            if abs(price - s1) / s1 < 0.003:
                reason += " + Harga dekat support"

        # Logika longgar: SELL
        elif rsi > 55 and (macd_sig - macd_val) > 0.05:
            signal = "SELL"
            reason = "RSI mendekati overbought + MACD bearish crossover"

            if pattern in ["Bearish Engulfing"]:
                reason += f" + Pola candlestick {pattern}"

            if abs(price - r1) / r1 < 0.003:
                reason += " + Harga dekat resistance"

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
