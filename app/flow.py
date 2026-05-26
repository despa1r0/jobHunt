from app.db import SessionLocal, create_tables
from app.models import VacancyCreate, save_vacancies
from app.scrapers import scrape_jobs


def scrape_and_save(source: str = "djinni") -> list[VacancyCreate]:
    vacancies = scrape_jobs(source=source)

    if not vacancies:
        return []

    create_tables()

    with SessionLocal() as db:
        save_vacancies(db, vacancies)

    return vacancies


def scrape_and_save_djinni() -> list[VacancyCreate]:
    return scrape_and_save(source="djinni")
