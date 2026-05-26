import requests

from app.config import get_settings


def send_telegram_message(text: str, chat_id: str | None = None) -> dict:
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is empty")

    target_chat_id = chat_id or settings.telegram_chat_id

    if not target_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is empty")

    response = requests.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={
            "chat_id": target_chat_id,
            "text": text,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_telegram_updates(offset: int | None = None, timeout: int = 30) -> list[dict]:
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is empty")

    response = requests.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
        params={
            "offset": offset,
            "timeout": timeout,
        },
        timeout=timeout + 10,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("result", [])
