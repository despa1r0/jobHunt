import logging

from app.db import SessionLocal, create_tables
from app.models import ScrapeFilters, VacancyCreate, save_vacancies
from app.scrapers import scrape_jobs


logger = logging.getLogger(__name__)


def scrape_and_save(
    source: str = "djinni",
    filters: ScrapeFilters | None = None,
    pause_before_close: bool = False,
) -> list[VacancyCreate]:
    _ensure_logging_configured()
    logger.info("Scrape flow started: source=%s", source)
    vacancies = scrape_jobs(
        source=source,
        filters=filters,
        pause_before_close=pause_before_close,
    )

    if not vacancies:
        logger.info("Scrape flow finished: source=%s saved=0", source)
        return []

    create_tables()

    with SessionLocal() as db:
        save_vacancies(db, vacancies)

    logger.info("Scrape flow finished: source=%s saved=%s", source, len(vacancies))
    return vacancies


def scrape_and_save_djinni(pause_before_close: bool = False) -> list[VacancyCreate]:
    return scrape_and_save(source="djinni", pause_before_close=pause_before_close)


def _ensure_logging_configured() -> None:
    if logging.getLogger().handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
