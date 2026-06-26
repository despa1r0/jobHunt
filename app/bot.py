from html import escape

from app.db import SessionLocal, create_tables
from app.flow import scrape_and_save
from app.models import (
    clear_sent_vacancies,
    count_vacancies,
    count_vacancies_by_source,
    format_vacancy_filter,
    get_active_vacancies,
    get_latest_vacancies,
    get_or_create_bot_state,
    get_or_create_user,
    get_or_create_vacancy_filter,
    get_vacancy_by_id,
    mark_vacancy_sent,
    supported_filter_sources,
    update_bot_offset,
    update_vacancy_filter,
)
from app.scrapers.sources import ALL_SOURCES
from app.telegram import (
    get_telegram_updates,
    send_telegram_message,
    try_answer_callback_query,
    try_edit_telegram_message,
)


WELCOME_TEXT = (
    "Vacancy bot is running.\n"
    "Commands:\n"
    "/help - show commands\n"
    "/count - show saved vacancies count\n"
    "/stats - show saved and active vacancy stats\n"
    "/latest [source] - show latest saved vacancies\n"
    "/active - show active vacancies count\n"
    "/next - show active vacancy with navigation buttons\n"
    "/new - show new vacancies matching your filters\n"
    "/reset_seen - return hidden/seen vacancies to active list\n"
    "/filters - show current filters\n"
    "/set_keywords Python\n"
    "/set_experience no_exp,1y\n"
    "/set_english pre,intermediate,upper\n"
    "/set_location remote poznan\n"
    "/include python fastapi\n"
    "/exclude senior lead\n"
    "/clear_location\n"
    "/clear_include\n"
    "/clear_exclude\n"
    "/set_source all|djinni|praca_pl\n"
    "/scrape - scrape current source with current filters\n"
    "/scrape all - scrape every supported source with current filters"
)


def run_bot_polling() -> None:
    create_tables()
    next_update_id: int | None = None

    print("Bot polling started. Press Ctrl+C to stop.")

    while True:
        updates = get_telegram_updates(offset=next_update_id, timeout=20)

        for update in updates:
            next_update_id = update["update_id"] + 1
            callback_query = update.get("callback_query")
            if callback_query:
                handle_callback_query(callback_query)
                continue

            message = update.get("message")
            if not message:
                continue

            chat_id = str(message["chat"]["id"])
            text = (message.get("text") or "").strip()
            response = handle_bot_command(chat_id=chat_id, text=text)

            if response:
                if isinstance(response, BotMessage):
                    send_telegram_message(
                        response.text,
                        chat_id=chat_id,
                        reply_markup=response.reply_markup,
                        parse_mode=response.parse_mode,
                        disable_web_page_preview=response.disable_web_page_preview,
                    )
                else:
                    send_telegram_message(response, chat_id=chat_id)


class BotMessage:
    def __init__(
        self,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = False,
    ) -> None:
        self.text = text
        self.reply_markup = reply_markup
        self.parse_mode = parse_mode
        self.disable_web_page_preview = disable_web_page_preview


def handle_bot_command(chat_id: str, text: str) -> str | BotMessage | None:
    if text == "/start":
        with SessionLocal() as db:
            get_or_create_user(db, chat_id)
            get_or_create_bot_state(db, chat_id)
            get_or_create_vacancy_filter(db, chat_id)
        return WELCOME_TEXT

    if text == "/help":
        return WELCOME_TEXT

    if text == "/count":
        with SessionLocal() as db:
            total = count_vacancies(db)
        return f"Saved vacancies: {total}"

    if text == "/stats":
        return _handle_stats(chat_id)

    if text == "/latest" or text.startswith("/latest "):
        return _handle_latest(text)

    if text == "/active":
        return _handle_active_count(chat_id)

    if text == "/next":
        return _handle_next(chat_id)

    if text == "/new":
        return _handle_new(chat_id)

    if text == "/filters":
        with SessionLocal() as db:
            vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
            return format_vacancy_filter(vacancy_filter)

    if text == "/scrape" or text.startswith("/scrape "):
        return _handle_scrape(chat_id, text)

    if text == "/reset_seen":
        return _handle_reset_seen(chat_id)

    if text.startswith("/set_keywords"):
        return _handle_filter_update(chat_id, text, "search_keywords")

    if text.startswith("/set_experience"):
        return _handle_filter_update(chat_id, text, "experience_levels")

    if text.startswith("/set_english"):
        return _handle_filter_update(chat_id, text, "english_levels")

    if text.startswith("/set_location"):
        return _handle_filter_update(chat_id, text, "location")

    if text.startswith("/include"):
        return _handle_filter_update(chat_id, text, "include_keywords")

    if text.startswith("/exclude"):
        return _handle_filter_update(chat_id, text, "exclude_keywords")

    if text == "/clear_location":
        return _handle_clear_filter(chat_id, "location")

    if text == "/clear_include":
        return _handle_clear_filter(chat_id, "include_keywords")

    if text == "/clear_exclude":
        return _handle_clear_filter(chat_id, "exclude_keywords")

    if text.startswith("/set_source"):
        return _handle_source_update(chat_id, text)

    return "Unknown command. Use /start to see available commands."


def _handle_next(chat_id: str) -> str | BotMessage:
    message = _build_active_vacancy_message(chat_id=chat_id, offset_delta=0)
    if message:
        return message
    return "No active vacancies for current filters. Run /scrape or adjust /filters."


def _build_active_vacancy_message(
    chat_id: str,
    offset_delta: int = 0,
) -> BotMessage | None:
    with SessionLocal() as db:
        state = get_or_create_bot_state(db, chat_id)
        vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
        active_vacancies = get_active_vacancies(db, chat_id, vacancy_filter)
        total = len(active_vacancies)

        if total == 0:
            update_bot_offset(db, chat_id, 0)
            return None

        current_offset = state.current_offset + offset_delta
        if current_offset < 0:
            current_offset = total - 1
        if current_offset >= total:
            current_offset = 0

        vacancy = active_vacancies[current_offset]
        update_bot_offset(db, chat_id, current_offset)
        pages = vacancy.telegram_html_pages()
        text = _format_vacancy_text(
            pages[0],
            vacancy_position=current_offset + 1,
            vacancy_total=total,
            details_page=0,
            details_total=len(pages),
        )

    return BotMessage(
        text=text,
        reply_markup=_vacancy_keyboard(
            vacancy.id,
            details_page=0,
            details_total=len(pages),
        ),
        parse_mode="HTML",
        disable_web_page_preview=False,
    )


def _handle_new(chat_id: str) -> str | BotMessage | None:
    with SessionLocal() as db:
        update_bot_offset(db, chat_id, 0)

    message = _build_active_vacancy_message(chat_id=chat_id, offset_delta=0)
    if message:
        return message
    return "No new vacancies for current filters."


def _handle_scrape(chat_id: str, text: str = "/scrape") -> str:
    with SessionLocal() as db:
        vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
        filters = vacancy_filter.to_scrape_filters()

    _, _, raw_source = text.partition(" ")
    requested_source = raw_source.strip()
    if requested_source:
        if requested_source not in supported_filter_sources():
            return _unsupported_source_message()
        filters = filters.model_copy(update={"source": requested_source})

    vacancies = scrape_and_save(source=filters.source, filters=filters)
    return f"Scraped and saved vacancies: {len(vacancies)}"


def _handle_stats(chat_id: str) -> str:
    with SessionLocal() as db:
        vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
        active_total = len(get_active_vacancies(db, chat_id, vacancy_filter))
        saved_total = count_vacancies(db)
        by_source = count_vacancies_by_source(db)

    source_lines = [
        f"- {source}: {total}"
        for source, total in sorted(by_source.items())
    ]
    if not source_lines:
        source_lines = ["- no saved vacancies yet"]

    return "\n".join(
        [
            f"Saved vacancies: {saved_total}",
            f"Active vacancies for current filters: {active_total}",
            "By source:",
            *source_lines,
        ]
    )


def _handle_latest(text: str) -> str | BotMessage:
    _, _, raw_source = text.partition(" ")
    source = raw_source.strip() or None
    if source == ALL_SOURCES:
        source = None
    if source and source not in supported_filter_sources():
        return _unsupported_source_message(prefix="Unsupported source for /latest.")

    with SessionLocal() as db:
        vacancies = get_latest_vacancies(db, limit=5, source=source)

    if not vacancies:
        return "No saved vacancies yet."

    lines = ["<b>Latest saved vacancies:</b>"]
    for index, vacancy in enumerate(vacancies, start=1):
        company = f" at {vacancy.company_name}" if vacancy.company_name else ""
        location = f" ({vacancy.location})" if vacancy.location else ""
        lines.append(
            "\n".join(
                [
                    f"{index}. <b>{escape(vacancy.title)}</b>{escape(company)}",
                    f"   {escape(vacancy.source)}{escape(location)}",
                    f"   {escape(vacancy.url)}",
                ]
            )
        )

    return BotMessage(
        "\n\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def _handle_active_count(chat_id: str) -> str:
    with SessionLocal() as db:
        vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
        active_total = len(get_active_vacancies(db, chat_id, vacancy_filter))
        saved_total = count_vacancies(db)

    return (
        f"Active vacancies: {active_total}\n"
        f"Saved vacancies: {saved_total}\n"
        "Active excludes vacancies marked as not interesting or previously hidden."
    )


def _handle_reset_seen(chat_id: str) -> str:
    with SessionLocal() as db:
        removed = clear_sent_vacancies(db, chat_id)
        update_bot_offset(db, chat_id, 0)

    return f"Returned hidden/seen vacancies to active list: {removed}"


def _handle_filter_update(chat_id: str, text: str, field_name: str) -> str:
    _, _, raw_value = text.partition(" ")
    value = raw_value.strip() or None

    if value is None:
        return "Value is empty. Example: /set_keywords Python"

    with SessionLocal() as db:
        vacancy_filter = update_vacancy_filter(db, chat_id, **{field_name: value})
        return "Filters updated:\n" + format_vacancy_filter(vacancy_filter)


def _handle_clear_filter(chat_id: str, field_name: str) -> str:
    with SessionLocal() as db:
        vacancy_filter = update_vacancy_filter(db, chat_id, **{field_name: None})
        update_bot_offset(db, chat_id, 0)
        return "Filters updated:\n" + format_vacancy_filter(vacancy_filter)


def _handle_source_update(chat_id: str, text: str) -> str:
    _, _, raw_value = text.partition(" ")
    source = raw_value.strip()

    if source not in supported_filter_sources():
        return _unsupported_source_message()

    with SessionLocal() as db:
        vacancy_filter = update_vacancy_filter(db, chat_id, source=source)
        return "Filters updated:\n" + format_vacancy_filter(vacancy_filter)


def _unsupported_source_message(prefix: str = "Unsupported source.") -> str:
    sources = ", ".join(sorted(supported_filter_sources()))
    return f"{prefix} Use one of: {sources}"


def handle_callback_query(callback_query: dict) -> None:
    callback_query_id = callback_query["id"]
    data = callback_query.get("data") or ""
    message = callback_query.get("message") or {}
    chat_id = str(message.get("chat", {}).get("id", ""))
    message_id = message.get("message_id")

    if not chat_id or message_id is None:
        try_answer_callback_query(callback_query_id)
        return

    if data == "vacancy:next":
        bot_message = _build_active_vacancy_message(chat_id=chat_id, offset_delta=1)
        if bot_message:
            try_edit_telegram_message(
                chat_id,
                message_id,
                bot_message.text,
                reply_markup=bot_message.reply_markup,
                parse_mode=bot_message.parse_mode,
                disable_web_page_preview=bot_message.disable_web_page_preview,
            )
        try_answer_callback_query(callback_query_id)
        return

    if data == "vacancy:prev":
        bot_message = _build_active_vacancy_message(chat_id=chat_id, offset_delta=-1)
        if bot_message:
            try_edit_telegram_message(
                chat_id,
                message_id,
                bot_message.text,
                reply_markup=bot_message.reply_markup,
                parse_mode=bot_message.parse_mode,
                disable_web_page_preview=bot_message.disable_web_page_preview,
            )
        try_answer_callback_query(callback_query_id)
        return

    if data.startswith("vacancy:skip:"):
        vacancy_id = int(data.rsplit(":", 1)[1])
        with SessionLocal() as db:
            mark_vacancy_sent(db, chat_id, vacancy_id)

        bot_message = _build_active_vacancy_message(chat_id=chat_id, offset_delta=0)
        if bot_message:
            try_edit_telegram_message(
                chat_id,
                message_id,
                bot_message.text,
                reply_markup=bot_message.reply_markup,
                parse_mode=bot_message.parse_mode,
                disable_web_page_preview=bot_message.disable_web_page_preview,
            )
        else:
            try_edit_telegram_message(chat_id, message_id, "No active vacancies left.")
        try_answer_callback_query(callback_query_id, text="Marked as not interesting")
        return

    if data.startswith("vacancy:details:"):
        parsed = _parse_vacancy_details_callback(data)
        if parsed is None:
            try_answer_callback_query(callback_query_id)
            return

        vacancy_id, details_page = parsed
        bot_message = _build_vacancy_details_message(
            chat_id=chat_id,
            vacancy_id=vacancy_id,
            details_page=details_page,
        )
        if bot_message:
            try_edit_telegram_message(
                chat_id,
                message_id,
                bot_message.text,
                reply_markup=bot_message.reply_markup,
                parse_mode=bot_message.parse_mode,
                disable_web_page_preview=bot_message.disable_web_page_preview,
            )
        try_answer_callback_query(callback_query_id)
        return

    try_answer_callback_query(callback_query_id)


def _build_vacancy_details_message(
    chat_id: str,
    vacancy_id: int,
    details_page: int,
) -> BotMessage | None:
    with SessionLocal() as db:
        vacancy = get_vacancy_by_id(db, vacancy_id)
        if vacancy is None:
            return None

        pages = vacancy.telegram_html_pages()
        if not pages:
            return None

        details_page = _clamp(details_page, minimum=0, maximum=len(pages) - 1)
        vacancy_position, vacancy_total = _get_vacancy_position(db, chat_id, vacancy_id)
        text = _format_vacancy_text(
            pages[details_page],
            vacancy_position=vacancy_position,
            vacancy_total=vacancy_total,
            details_page=details_page,
            details_total=len(pages),
        )

    return BotMessage(
        text=text,
        reply_markup=_vacancy_keyboard(
            vacancy_id,
            details_page=details_page,
            details_total=len(pages),
        ),
        parse_mode="HTML",
        disable_web_page_preview=False,
    )


def _parse_vacancy_details_callback(data: str) -> tuple[int, int] | None:
    parts = data.split(":")
    if len(parts) != 4:
        return None

    _, _, vacancy_id, details_page = parts
    try:
        return int(vacancy_id), int(details_page)
    except ValueError:
        return None


def _get_vacancy_position(
    db,
    chat_id: str,
    vacancy_id: int,
) -> tuple[int | None, int | None]:
    vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
    active_vacancies = get_active_vacancies(db, chat_id, vacancy_filter)
    vacancy_total = len(active_vacancies)

    for index, vacancy in enumerate(active_vacancies):
        if vacancy.id == vacancy_id:
            return index + 1, vacancy_total

    return None, vacancy_total


def _format_vacancy_text(
    page_text: str,
    vacancy_position: int | None,
    vacancy_total: int | None,
    details_page: int,
    details_total: int,
) -> str:
    counters: list[str] = []
    if vacancy_position is not None and vacancy_total is not None:
        counters.append(f"{vacancy_position}/{vacancy_total}")
    if details_total > 1:
        counters.append(f"details {details_page + 1}/{details_total}")
    if not counters:
        return page_text

    return f"{page_text}\n\n[{' | '.join(counters)}]"


def _vacancy_keyboard(
    vacancy_id: int,
    details_page: int = 0,
    details_total: int = 1,
) -> dict:
    inline_keyboard = [
        [
            {"text": "Prev", "callback_data": "vacancy:prev"},
            {"text": "Next", "callback_data": "vacancy:next"},
        ],
    ]

    if details_total > 1:
        detail_buttons = []
        if details_page > 0:
            detail_buttons.append(
                {
                    "text": "Details prev",
                    "callback_data": f"vacancy:details:{vacancy_id}:{details_page - 1}",
                }
            )
        if details_page < details_total - 1:
            detail_buttons.append(
                {
                    "text": "Details next",
                    "callback_data": f"vacancy:details:{vacancy_id}:{details_page + 1}",
                }
            )
        inline_keyboard.append(detail_buttons)

    inline_keyboard.append(
        [
            {
                "text": "Not interested",
                "callback_data": f"vacancy:skip:{vacancy_id}",
            }
        ]
    )

    return {
        "inline_keyboard": inline_keyboard,
    }


def _clamp(value: int, minimum: int, maximum: int) -> int:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
