from app.models import JobCreate, ScrapeFilters
from app.scrapers.djinni import scrape_djinni_jobs
from app.scrapers.praca_pl import scrape_praca_pl_jobs


SCRAPERS = {
    "djinni": scrape_djinni_jobs,
    "praca_pl": scrape_praca_pl_jobs,
}


def scrape_jobs(
    source: str = "djinni",
    filters: ScrapeFilters | None = None,
    pause_before_close: bool = False,
) -> list[JobCreate]:
    scraper = SCRAPERS.get(source)
    if scraper is None:
        supported_sources = ", ".join(sorted(SCRAPERS))
        raise ValueError(f"Unsupported source: {source}. Supported: {supported_sources}")
    return scraper(filters=filters, pause_before_close=pause_before_close)
