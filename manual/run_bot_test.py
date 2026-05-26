from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import SessionLocal, create_tables
from app.models import count_vacancies, get_vacancy_page
from app.telegram import get_telegram_updates, send_telegram_message


WELCOME_TEXT = (
    "Vacancy bot is running.\n"
    "Commands:\n"
    "/start - show this message\n"
    "/count - show how many vacancies are saved\n"
    "/next - send the next vacancy from the database"
)


def main() -> None:
    create_tables()
    next_update_id: int | None = None
    current_index = 0

    print("Bot polling started. Press Ctrl+C to stop.")

    while True:
        updates = get_telegram_updates(offset=next_update_id, timeout=20)

        for update in updates:
            next_update_id = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue

            chat_id = str(message["chat"]["id"])
            text = (message.get("text") or "").strip()

            if text == "/start":
                current_index = 0
                send_telegram_message(WELCOME_TEXT, chat_id=chat_id)
                continue

            if text == "/count":
                with SessionLocal() as db:
                    total = count_vacancies(db)
                send_telegram_message(f"Saved vacancies: {total}", chat_id=chat_id)
                continue

            if text == "/next":
                with SessionLocal() as db:
                    vacancies = get_vacancy_page(db, offset=current_index, limit=1)
                    total = count_vacancies(db)

                if not vacancies:
                    current_index = 0
                    send_telegram_message(
                        "No more vacancies in the current list. Send /next to start from the newest one again.",
                        chat_id=chat_id,
                    )
                    continue

                vacancy = vacancies[0]
                current_index += 1
                send_telegram_message(
                    f"{vacancy.as_telegram_message()}\n\n[{current_index}/{total}]",
                    chat_id=chat_id,
                )
                continue

            send_telegram_message(
                "Unknown command. Use /start, /count, or /next.",
                chat_id=chat_id,
            )


if __name__ == "__main__":
    main()
