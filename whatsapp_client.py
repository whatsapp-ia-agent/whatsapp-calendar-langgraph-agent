import os
from openwa import AsyncOpenWAClient

OPENWA_URL = os.getenv("OPENWA_URL", "http://localhost:2785")
OPENWA_API_KEY = os.getenv("OPENWA_API_KEY")
SESSION_ID = os.getenv("SESSION_ID")

client = AsyncOpenWAClient(base_url=OPENWA_URL, api_key=OPENWA_API_KEY)

async def send_text_message(chat_id: str, text: str):
    await client.messages.send_text(SESSION_ID, {"chatId": chat_id, "text": text})

async def send_catalog(chat_id: str):
    await client.catalog.send_catalog(SESSION_ID, {"chatId": chat_id})

async def send_product(chat_id: str, product_id: str):
    await client.catalog.send_product(SESSION_ID, {"chatId": chat_id, "productId": product_id})

async def send_interactive_buttons(chat_id: str, text: str, buttons: list):
    pass
