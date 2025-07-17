import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
