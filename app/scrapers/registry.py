from app.models import ScrapeFilters, VacancyCreate
from app.scrapers.djinni import scrape_djinni_jobs


SCRAPERS = {
    "djinni": scrape_djinni_jobs,
}


def scrape_jobs(
    source: str = "djinni",
    filters: ScrapeFilters | None = None,
    pause_before_close: bool = False,
) -> list[VacancyCreate]:
    scraper = SCRAPERS.get(source)
    if scraper is None:
        supported_sources = ", ".join(sorted(SCRAPERS))
        raise ValueError(f"Unsupported source: {source}. Supported: {supported_sources}")
    return scraper(filters=filters, pause_before_close=pause_before_close)
