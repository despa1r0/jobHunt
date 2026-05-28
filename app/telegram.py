from typing import Any

import requests

from app.config import get_settings


def send_telegram_message(
    text: str,
    chat_id: str | None = None,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
    disable_web_page_preview: bool = False,
) -> dict:
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is empty")

    target_chat_id = chat_id or settings.telegram_chat_id

    if not target_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is empty")

    payload: dict[str, Any] = {
        "chat_id": target_chat_id,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_web_page_preview:
        payload["disable_web_page_preview"] = True

    response = requests.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def try_send_telegram_message(
    text: str,
    chat_id: str | None = None,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
    disable_web_page_preview: bool = False,
) -> dict | None:
    try:
        return send_telegram_message(
            text,
            chat_id=chat_id,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
    except requests.RequestException as exc:
        print(f"Telegram sendMessage failed: {exc}")
        return None


def edit_telegram_message(
    chat_id: str,
    message_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
    disable_web_page_preview: bool = False,
) -> dict:
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is empty")

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_web_page_preview:
        payload["disable_web_page_preview"] = True

    response = requests.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/editMessageText",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def try_edit_telegram_message(
    chat_id: str,
    message_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
    disable_web_page_preview: bool = False,
) -> dict | None:
    try:
        return edit_telegram_message(
            chat_id,
            message_id,
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
    except requests.RequestException as exc:
        print(f"Telegram editMessageText failed: {exc}")
        return None


def answer_callback_query(callback_query_id: str, text: str | None = None) -> dict:
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is empty")

    payload: dict[str, Any] = {
        "callback_query_id": callback_query_id,
    }
    if text:
        payload["text"] = text

    response = requests.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def try_answer_callback_query(
    callback_query_id: str,
    text: str | None = None,
) -> dict | None:
    try:
        return answer_callback_query(callback_query_id, text=text)
    except requests.RequestException as exc:
        print(f"Telegram answerCallbackQuery failed: {exc}")
        return None


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
