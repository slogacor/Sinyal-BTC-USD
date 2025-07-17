import telegram
from telegram.ext import Updater, CommandHandler
from strategies import get_scalping_signal, get_xauusd_price  # ✅ Pastikan fungsi ini ada di strategies.py
from utils import is_market_open, get_current_time_str
import openai
import schedule
import time
import random
import logging

# --- Konfigurasi Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Load Config ---
from config import BOT_TOKEN, OPENAI_API_KEY, GROUP_CHAT_ID

bot = telegram.Bot(token=BOT_TOKEN)
openai.api_key = OPENAI_API_KEY

# --- Perintah Bot ---

def start(update, context):
    logger.info("/start command received")
    update.message.reply_text("Halo! Saya adalah mentor trading XAU/USD Anda.")

def harga(update, context):
    logger.info("/harga command received")

    if not is_market_open():
        update.message.reply_text("Market sedang tutup.")
        return

    try:
        price = get_xauusd_price()
        if price is None:
            update.message.reply_text("Gagal mengambil harga saat ini.")
            return
        update.message.reply_text(f"Harga XAU/USD saat ini: ${price}")
    except Exception as e:
        logger.error(f"Error di /harga: {e}")
        update.message.reply_text("Gagal mengambil harga. Coba lagi nanti.")

def signal(update, context):
    logger.info("/signal command received")

    if not is_market_open():
        update.message.reply_text("Market sedang tutup.")
        return

    try:
        sig = get_scalping_signal()
        msg = f"""
🔍 SINYAL TERBARU - XAU/USD
🕒 Waktu: {get_current_time_str()}
💰 Harga: ${sig['price']}
📊 RSI(14): {sig['rsi']} 
📉 MACD: {sig['macd']}

🎯 Rekomendasi: {sig['signal']}
⚖️ Alasan: {sig['reason']}
📈 Target Profit: {sig['tp_pips']} pips
🛑 Stop Loss: {sig['sl_pips']} pips
⚖️ Risk/Reward: 1 : 3
"""
        update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Error di /signal: {e}")
        update.message.reply_text("Gagal mendapatkan sinyal saat ini.")

def tanya(update, context):
    logger.info("/tanya command received")

    if not is_market_open():
        update.message.reply_text("Market sedang tutup.")
        return

    try:
        if len(context.args) == 0:
            update.message.reply_text("Silakan tuliskan pertanyaan Anda setelah perintah /tanya.")
            return

        question = ' '.join(context.args)
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=f"Kamu adalah mentor trading profesional. Jelaskan: {question}",
            max_tokens=200
        )
        update.message.reply_text(response.choices[0].text.strip())
    except Exception as e:
        logger.error(f"Error di /tanya: {e}")
        update.message.reply_text("Maaf, saya tidak bisa menjawab saat ini.")

def tip(update, context):
    logger.info("/tip command received")

    tips = [
        "Selalu gunakan stop loss meski scalping cepat.",
        "Cari pola candlestick reversal untuk entry lebih akurat.",
        "Jangan scalping saat rilis berita besar.",
        "Fokus pada timeframe M1 atau M5 saja."
    ]
    update.message.reply_text("💡 TIP HARI INI:\n" + random.choice(tips))

# --- Auto Signal ---
def auto_signal_job():
    logger.info("Menjalankan job otomatis...")
    if not is_market_open():
        return

    try:
        sig = get_scalping_signal()
        msg = f"[AUTO] {sig['signal']} XAU/USD | TP: {sig['tp_pips']} pips | SL: {sig['sl_pips']} pips"
        if GROUP_CHAT_ID:
            bot.send_message(chat_id=GROUP_CHAT_ID, text=msg)
    except Exception as e:
        logger.error(f"Error dalam job otomatis: {e}")

# --- Scheduler ---
def job_scheduler():
    schedule.every().hour.at(":00").do(auto_signal_job)

    while True:
        schedule.run_pending()
        time.sleep(1)

# --- Main ---
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Register handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("harga", harga))
    dp.add_handler(CommandHandler("signal", signal))
    dp.add_handler(CommandHandler("tanya", tanya))
    dp.add_handler(CommandHandler("tip", tip))

    print("🤖 Bot siap! Menunggu perintah...")
    updater.start_polling(drop_pending_updates=True)  # ✅ Membersihkan pesan lama saat restart

    # Jalankan scheduler di thread terpisah
    from threading import Thread
    scheduler_thread = Thread(target=job_scheduler, daemon=True)
    scheduler_thread.start()

    updater.idle()  # Biar tetap hidup sampai dihentikan

if __name__ == "__main__":
    main()
