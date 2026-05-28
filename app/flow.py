from app.db import SessionLocal, create_tables
from app.models import ScrapeFilters, VacancyCreate, save_vacancies
from app.scrapers import scrape_jobs


def scrape_and_save(
    source: str = "djinni",
    filters: ScrapeFilters | None = None,
    pause_before_close: bool = False,
) -> list[VacancyCreate]:
    vacancies = scrape_jobs(
        source=source,
        filters=filters,
        pause_before_close=pause_before_close,
    )

    if not vacancies:
        return []

    create_tables()

    with SessionLocal() as db:
        save_vacancies(db, vacancies)

    return vacancies


def scrape_and_save_djinni(pause_before_close: bool = False) -> list[VacancyCreate]:
    return scrape_and_save(source="djinni", pause_before_close=pause_before_close)
