from app.models import JobCreate, ScrapeFilters
from app.scrapers.djinni import scrape_djinni_jobs
from app.scrapers.praca_pl import scrape_praca_pl_jobs
from app.scrapers.sources import ALL_SOURCES, SUPPORTED_SOURCES


SCRAPERS = {
    "djinni": scrape_djinni_jobs,
    "praca_pl": scrape_praca_pl_jobs,
}

def scrape_jobs(
    source: str = "djinni",
    filters: ScrapeFilters | None = None,
    pause_before_close: bool = False,
) -> list[JobCreate]:
    if source == ALL_SOURCES:
        vacancies: list[JobCreate] = []
        for source_name in SUPPORTED_SOURCES:
            source_filters = (
                filters.model_copy(update={"source": source_name})
                if filters is not None
                else None
            )
            vacancies.extend(
                scrape_jobs(
                    source=source_name,
                    filters=source_filters,
                    pause_before_close=pause_before_close,
                )
            )
        return vacancies

    scraper = SCRAPERS.get(source)
    if scraper is None:
        supported_sources = ", ".join([*SUPPORTED_SOURCES, ALL_SOURCES])
        raise ValueError(f"Unsupported source: {source}. Supported: {supported_sources}")
    return scraper(filters=filters, pause_before_close=pause_before_close)
