import telegram
from telegram.ext import Updater, CommandHandler
from strategies import get_scalping_signal, get_xauusd_price
from utils import is_market_open, get_current_time_str
import openai
import schedule
import time
import random
import logging
import threading
from datetime import datetime
import copy

# --- Konfigurasi Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Load Config ---
from config import BOT_TOKEN, OPENAI_API_KEY, GROUP_CHAT_ID

bot = telegram.Bot(token=BOT_TOKEN)
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Variabel global
last_signal_result = None
last_sent_signal = None

# --- Bot Commands ---
def start(update, context):
    update.message.reply_text("Halo! Saya adalah mentor trading XAU/USD Anda.")

def harga(update, context):
    if not is_market_open():
        update.message.reply_text("Market sedang tutup.")
        return

    price = get_xauusd_price()
    if price:
        update.message.reply_text(f"Harga XAU/USD saat ini: ${price}")
    else:
        update.message.reply_text("Gagal mengambil harga.")

def signal(update, context):
    if not is_market_open():
        update.message.reply_text("Market sedang tutup.")
        return

    sig = get_scalping_signal()
    if 'error' in sig:
        update.message.reply_text(f"Error: {sig['error']}")
        return

    msg = f"""
🔍 SINYAL TERBARU - XAU/USD
🕒 Waktu: {get_current_time_str()}
💰 Harga: ${sig['price']}
📊 RSI(14): {sig['rsi']}
📉 MACD: {sig['macd']}

🎯 Rekomendasi: {sig['signal']}
⚖️ Alasan: {sig['reason']}
📈 TP: {sig['tp_pips']} pips
🛑 SL: {sig['sl_pips']} pips
⚖️ Risk/Reward: 1 : 3
"""
    update.message.reply_text(msg)

def tanya(update, context):
    if not is_market_open():
        update.message.reply_text("Market sedang tutup.")
        return

    if not context.args:
        update.message.reply_text("Silakan tulis pertanyaan setelah /tanya.")
        return

    question = ' '.join(context.args)
    response = client.completions.create(
        model="text-davinci-003",
        prompt=f"Kamu adalah mentor trading profesional. Jelaskan: {question}",
        max_tokens=200
    )
    update.message.reply_text(response.choices[0].text.strip())

def tip(update, context):
    tips = [
        "Selalu gunakan stop loss meski scalping cepat.",
        "Cari pola candlestick reversal untuk entry lebih akurat.",
        "Jangan scalping saat rilis berita besar.",
        "Fokus pada timeframe M1 atau M5 saja."
    ]
    update.message.reply_text("💡 TIP HARI INI:\n" + random.choice(tips))

# --- Auto Signal ---
def auto_signal_check():
    global last_signal_result
    if not is_market_open():
        logger.info("[auto_signal_check] Market tutup.")
        return

    try:
        sig = get_scalping_signal()
        if 'error' in sig:
            logger.error(f"Error sinyal otomatis: {sig['error']}")
            return
        last_signal_result = copy.deepcopy(sig)
        logger.info(f"[auto_signal_check] Sinyal diperbarui - {sig['signal']} @ {get_current_time_str()}")
    except Exception as e:
        logger.error(f"Exception auto_signal_check: {e}")

def auto_signal_send():
    global last_signal_result, last_sent_signal

    if not is_market_open():
        logger.info("[auto_signal_send] Market tutup.")
        return

    now = datetime.now()
    logger.info(f"[auto_signal_send] Eksekusi di menit: {now.minute}")

    if now.minute != 52:
        logger.info("[auto_signal_send] Bukan menit 52, skip.")
        return

    if last_signal_result is None:
        logger.warning("[auto_signal_send] Tidak ada sinyal untuk dikirim.")
        return

    if last_sent_signal == last_signal_result:
        logger.info("[auto_signal_send] Sinyal sama, tidak dikirim ulang.")
        return

    try:
        sig = last_signal_result
        msg = f"""
📡 AUTO SIGNAL (Jam {now.hour:02d}:52) - XAU/USD
🕒 Waktu: {get_current_time_str()}
💰 Harga: ${sig['price']}
📊 RSI(14): {sig['rsi']}
📉 MACD: {sig['macd']}

🎯 Rekomendasi: {sig['signal']}
📈 TP: {sig['tp_pips']} pips
🛑 SL: {sig['sl_pips']} pips
⚖️ Alasan: {sig['reason']}
"""

        bot.send_message(chat_id=GROUP_CHAT_ID, text=msg)
        last_sent_signal = copy.deepcopy(sig)
        logger.info("[auto_signal_send] ✅ Sinyal dikirim.")
    except Exception as e:
        logger.error(f"Error kirim sinyal otomatis: {e}")

# --- Scheduler ---
def job_scheduler():
    schedule.every(5).minutes.do(auto_signal_check)
    schedule.every().minute.do(auto_signal_send)

    logger.info("Scheduler aktif.")
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- Main ---
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("harga", harga))
    dp.add_handler(CommandHandler("signal", signal))
    dp.add_handler(CommandHandler("tanya", tanya))
    dp.add_handler(CommandHandler("tip", tip))

    print("🤖 Bot aktif. Menunggu perintah...")
    updater.start_polling(drop_pending_updates=True)

    scheduler_thread = threading.Thread(target=job_scheduler, daemon=True)
    scheduler_thread.start()

    updater.idle()

if __name__ == "__main__":
    main()
