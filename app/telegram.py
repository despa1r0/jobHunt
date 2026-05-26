import requests

from app.config import get_settings


def send_telegram_message(text: str) -> dict:
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is empty")

    if not settings.telegram_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is empty")

    response = requests.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={
            "chat_id": settings.telegram_chat_id,
            "text": text,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
