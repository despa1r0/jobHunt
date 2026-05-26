from app.models import VacancyCreate
from app.scrapers.djinni import scrape_djinni_jobs


SCRAPERS = {
    "djinni": scrape_djinni_jobs,
}


def scrape_jobs(source: str = "djinni") -> list[VacancyCreate]:
    scraper = SCRAPERS.get(source)
    if scraper is None:
        supported_sources = ", ".join(sorted(SCRAPERS))
        raise ValueError(f"Unsupported source: {source}. Supported: {supported_sources}")
    return scraper()
