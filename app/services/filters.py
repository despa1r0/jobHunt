from __future__ import annotations

from app.db import SessionLocal
from app.models import (
    VacancyFilter,
    format_vacancy_filter,
    get_or_create_vacancy_filter,
    supported_filter_sources,
    update_bot_offset,
    update_vacancy_filter,
)


def get_user_filter(user_key: str) -> VacancyFilter:
    with SessionLocal() as db:
        return get_or_create_vacancy_filter(db, user_key)


def get_user_filter_text(user_key: str) -> str:
    with SessionLocal() as db:
        vacancy_filter = get_or_create_vacancy_filter(db, user_key)
        return format_vacancy_filter(vacancy_filter)


def update_user_filter(user_key: str, **values: str | None) -> VacancyFilter:
    source = values.get("source")
    if source is not None:
        validate_source(source)

    with SessionLocal() as db:
        vacancy_filter = update_vacancy_filter(db, user_key, **values)
        update_bot_offset(db, user_key, 0)
        return vacancy_filter


def update_user_filter_text(user_key: str, **values: str | None) -> str:
    vacancy_filter = update_user_filter(user_key, **values)
    return format_vacancy_filter(vacancy_filter)


def supported_sources() -> list[str]:
    return sorted(supported_filter_sources())


def validate_source(source: str) -> None:
    if source not in supported_filter_sources():
        sources = ", ".join(supported_sources())
        raise ValueError(f"Unsupported source. Use one of: {sources}")
