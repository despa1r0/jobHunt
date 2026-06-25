from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from app.config import get_settings
from app.db import SessionLocal, create_tables
from app.models import (
    Vacancy,
    count_vacancies,
    count_vacancies_by_source,
    get_latest_vacancies,
    get_vacancy_by_id,
)


settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)


@app.on_event("startup")
def on_startup() -> None:
    create_tables()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
def vacancy_stats() -> dict[str, Any]:
    with SessionLocal() as db:
        return {
            "saved_vacancies": count_vacancies(db),
            "by_source": count_vacancies_by_source(db),
        }


@app.get("/vacancies")
def list_vacancies(
    source: str | None = None,
    limit: int = Query(default=10, ge=1, le=25),
) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        vacancies = get_latest_vacancies(db, limit=limit, source=source)
        return [_serialize_vacancy(vacancy) for vacancy in vacancies]


@app.get("/vacancies/{vacancy_id}")
def vacancy_detail(vacancy_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        vacancy = get_vacancy_by_id(db, vacancy_id)
        if vacancy is None:
            raise HTTPException(status_code=404, detail="Vacancy not found")
        return _serialize_vacancy(vacancy, include_description=True)


def _serialize_vacancy(
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
