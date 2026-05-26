from pathlib import Path

from app.db import SessionLocal, create_tables
from app.models import VacancyCreate, get_latest_vacancy, save_vacancies, save_vacancy
from app.parser import parse_vacancy_text
from app.scraper import scrape_djinni_jobs
from app.telegram import send_telegram_message


def save_example_vacancy(path: Path) -> str:
    raw_text = path.read_text(encoding="utf-8").strip()

    if not raw_text:
        raise ValueError(f"{path} is empty")

    create_tables()
    parsed_vacancy = parse_vacancy_text(raw_text)

    with SessionLocal() as db:
        saved_vacancy = save_vacancy(db, parsed_vacancy)
        latest_vacancy = get_latest_vacancy(db)

    lines = [
        f"Saved vacancy id: {saved_vacancy.id}",
        "",
        "Telegram preview:",
        saved_vacancy.as_telegram_message(),
    ]

    if latest_vacancy:
        lines.extend(["", f"Latest vacancy from DB: {latest_vacancy.title}"])

    return "\n".join(lines)


def send_example_vacancy(path: Path) -> dict:
    raw_text = path.read_text(encoding="utf-8").strip()

    if not raw_text:
        raise ValueError(f"{path} is empty")

    create_tables()
    parsed_vacancy = parse_vacancy_text(raw_text)

    with SessionLocal() as db:
        saved_vacancy = save_vacancy(db, parsed_vacancy)

    return send_telegram_message(saved_vacancy.as_telegram_message())


def scrape_and_save_djinni(limit: int = 10) -> list[VacancyCreate]:
    vacancies = scrape_djinni_jobs(limit=limit)

    if not vacancies:
        return []

    create_tables()

    with SessionLocal() as db:
        save_vacancies(db, vacancies)

    return vacancies
