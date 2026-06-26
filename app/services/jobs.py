from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    SentVacancy,
    Vacancy,
    clear_sent_vacancies,
    count_vacancies,
    count_vacancies_by_source,
    get_active_vacancies,
    get_latest_vacancies,
    get_or_create_bot_state,
    get_or_create_user,
    get_or_create_vacancy_filter,
    get_vacancy_by_id,
    update_bot_offset,
)
from app.scrapers.sources import ALL_SOURCES


@dataclass(frozen=True)
class ActiveJobResult:
    vacancy: Vacancy | None
    position: int
    total: int


def get_job_stats() -> dict[str, Any]:
    with SessionLocal() as db:
        return {
            "saved_vacancies": count_vacancies(db),
            "by_source": count_vacancies_by_source(db),
        }


def list_jobs(source: str | None = None, limit: int = 10) -> list[Vacancy]:
    selected_source = None if source in {None, "", ALL_SOURCES} else source
    with SessionLocal() as db:
        return get_latest_vacancies(db, limit=limit, source=selected_source)


def get_job(job_id: int) -> Vacancy | None:
    with SessionLocal() as db:
        return get_vacancy_by_id(db, job_id)


def get_active_job(
    user_key: str,
    offset_delta: int = 0,
    reset_offset: bool = False,
) -> ActiveJobResult:
    ensure_user_state(user_key)
    with SessionLocal() as db:
        state = get_or_create_bot_state(db, user_key)
        vacancy_filter = get_or_create_vacancy_filter(db, user_key)
        active_vacancies = get_active_vacancies(db, user_key, vacancy_filter)
        total = len(active_vacancies)

        if total == 0:
            update_bot_offset(db, user_key, 0)
            return ActiveJobResult(vacancy=None, position=0, total=0)

        current_offset = 0 if reset_offset else state.current_offset + offset_delta
        if current_offset < 0:
            current_offset = total - 1
        if current_offset >= total:
            current_offset = 0

        vacancy = active_vacancies[current_offset]
        update_bot_offset(db, user_key, current_offset)
        return ActiveJobResult(
            vacancy=vacancy,
            position=current_offset + 1,
            total=total,
        )


def get_active_job_count(user_key: str) -> int:
    ensure_user_state(user_key)
    with SessionLocal() as db:
        vacancy_filter = get_or_create_vacancy_filter(db, user_key)
        return len(get_active_vacancies(db, user_key, vacancy_filter))


def set_user_job_state(
    *,
    user_key: str,
    job_id: int,
    is_saved: int | None = None,
    is_viewed: int | None = None,
    is_hidden: int | None = None,
) -> None:
    ensure_user_state(user_key)
    with SessionLocal() as db:
        user = get_or_create_user(db, user_key)
        vacancy_filter = get_or_create_vacancy_filter(db, user_key)
        row = db.execute(
            select(SentVacancy).where(
                SentVacancy.chat_id == user_key,
                SentVacancy.vacancy_id == job_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = SentVacancy(
                user_id=user.id,
                chat_id=user_key,
                vacancy_id=job_id,
                filter_id=vacancy_filter.id,
            )
            db.add(row)

        if is_saved is not None:
            row.is_saved = is_saved
        if is_viewed is not None:
            row.is_viewed = is_viewed
        if is_hidden is not None:
            row.is_hidden = is_hidden

        db.commit()


def reset_user_jobs(user_key: str) -> int:
    ensure_user_state(user_key)
    with SessionLocal() as db:
        removed = clear_sent_vacancies(db, user_key)
        update_bot_offset(db, user_key, 0)
        return removed


def ensure_user_state(user_key: str) -> None:
    with SessionLocal() as db:
        get_or_create_user(db, user_key)
        get_or_create_bot_state(db, user_key)
        get_or_create_vacancy_filter(db, user_key)


def serialize_job(
    vacancy: Vacancy,
    include_description: bool = False,
) -> dict[str, Any]:
    payload = {
        "id": vacancy.id,
        "source": vacancy.source,
        "external_id": vacancy.external_id,
        "title": vacancy.title,
        "company_name": vacancy.company_name,
        "salary": vacancy.salary,
        "location": vacancy.location,
        "url": vacancy.url,
        "status": vacancy.status,
        "content_hash": vacancy.content_hash,
        "first_seen_at": _datetime_to_iso(vacancy.first_seen_at),
        "last_seen_at": _datetime_to_iso(vacancy.last_seen_at),
        "normalized_data": vacancy.normalized_data,
    }
    if include_description:
        payload["description_raw"] = vacancy.description_raw
        payload["description_html"] = vacancy.description_html
    return payload


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
