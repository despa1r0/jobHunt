from __future__ import annotations

from dataclasses import dataclass

from app.db import SessionLocal
from app.flow import scrape_and_save
from app.models import JobCreate, ScrapeFilters, get_or_create_vacancy_filter
from app.services.filters import validate_source


@dataclass(frozen=True)
class ScrapeResult:
    source: str
    saved_count: int
    jobs: list[JobCreate]


def scrape_for_user(
    user_key: str | None = None,
    source: str | None = None,
    filters: ScrapeFilters | None = None,
) -> ScrapeResult:
    scrape_filters = filters or _filters_for_user(user_key)
    selected_source = source or scrape_filters.source
    validate_source(selected_source)
    scrape_filters = scrape_filters.model_copy(update={"source": selected_source})

    jobs = scrape_and_save(source=scrape_filters.source, filters=scrape_filters)
    return ScrapeResult(
        source=scrape_filters.source,
        saved_count=len(jobs),
        jobs=jobs,
    )


def _filters_for_user(user_key: str | None) -> ScrapeFilters:
    if not user_key:
        return ScrapeFilters()

    with SessionLocal() as db:
        vacancy_filter = get_or_create_vacancy_filter(db, user_key)
        return vacancy_filter.to_scrape_filters()
