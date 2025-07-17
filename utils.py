from datetime import datetime
import pytz

WIB = pytz.timezone('Asia/Jakarta')

def is_market_open():
    now = datetime.now(WIB)
    hari = now.weekday()  # 0 = Senin, 4 = Jumat, 5 & 6 = Sabtu/Minggu
    jam = now.hour

    if hari == 4 and jam >= 22:
        return False  # Tutup Jumat pkl 22
    elif 5 <= hari <= 6:
        return False  # Tutup Sabtu-Minggu
    return True

def get_current_time_str():
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
