import os
from openwa import AsyncOpenWAClient

OPENWA_URL = os.getenv("OPENWA_URL", "http://localhost:2785")
OPENWA_API_KEY = os.getenv("OPENWA_TOKEN")  # ← Usa OPENWA_TOKEN (la variable que tienes)
SESSION_ID = os.getenv("SESSION_ID", "whatsapp-session")

if not OPENWA_API_KEY:
    raise ValueError("OPENWA_TOKEN environment variable is required")

client = AsyncOpenWAClient(base_url=OPENWA_URL, api_key=OPENWA_API_KEY)

async def send_text_message(chat_id: str, text: str):
    """Envía mensaje de texto."""
    await client.messages.send_text(SESSION_ID, {"chatId": chat_id, "text": text})

async def send_catalog(chat_id: str):
    """Envía el catálogo de WhatsApp Business."""
    await client.catalog.send_catalog(SESSION_ID, {"chatId": chat_id})

async def send_product(chat_id: str, product_id: str):
    """Envía un producto específico."""
    await client.catalog.send_product(SESSION_ID, {"chatId": chat_id, "productId": product_id})

async def send_interactive_buttons(chat_id: str, text: str, buttons: list):
    """Envía botones interactivos (opcional)."""
    pass
