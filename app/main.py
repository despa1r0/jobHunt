from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.config import get_settings
from app.db import create_tables
from app.models import ScrapeFilters, format_vacancy_filter
from app.services.filters import (
    get_user_filter,
    supported_sources,
    update_user_filter_text,
)
from app.services.jobs import (
    get_active_job,
    get_active_job_count,
    get_job,
    get_job_stats,
    list_jobs,
    reset_user_jobs,
    serialize_job,
    set_user_job_state,
)
from app.services.scraping import scrape_for_user


settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)


class ScrapeRequest(BaseModel):
    source: str | None = None
    user_key: str | None = None
    filters: ScrapeFilters | None = None


class FilterUpdateRequest(BaseModel):
    source: str | None = None
    search_keywords: str | None = None
    experience_levels: str | None = None
    english_levels: str | None = None
    location: str | None = None
    include_keywords: str | None = None
    exclude_keywords: str | None = None


class JobStateRequest(BaseModel):
    user_key: str


@app.on_event("startup")
def on_startup() -> None:
    create_tables()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
def vacancy_stats() -> dict[str, Any]:
    return get_job_stats()


@app.get("/sources")
def sources() -> dict[str, list[str]]:
    return {"sources": supported_sources()}


@app.post("/scrape")
def scrape_jobs(request: ScrapeRequest) -> dict[str, Any]:
    try:
        result = scrape_for_user(
            user_key=request.user_key,
            source=request.source,
            filters=request.filters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "source": result.source,
        "saved_count": result.saved_count,
    }


@app.get("/jobs")
def jobs(
    source: str | None = None,
    limit: int = Query(default=10, ge=1, le=25),
) -> list[dict[str, Any]]:
    return [_serialize_job(job) for job in list_jobs(source=source, limit=limit)]


@app.get("/jobs/{job_id}")
def job_detail(job_id: int) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize_job(job, include_description=True)


@app.get("/users/{user_key}/filters")
def user_filters(user_key: str) -> dict[str, Any]:
    vacancy_filter = get_user_filter(user_key)
    return {
        "filter": {
            "source": vacancy_filter.source,
            "search_keywords": vacancy_filter.search_keywords,
            "experience_levels": vacancy_filter.experience_levels,
            "english_levels": vacancy_filter.english_levels,
            "location": vacancy_filter.location,
            "include_keywords": vacancy_filter.include_keywords,
            "exclude_keywords": vacancy_filter.exclude_keywords,
        },
        "text": format_vacancy_filter(vacancy_filter),
    }


@app.put("/users/{user_key}/filters")
def update_user_filters(
    user_key: str,
    request: FilterUpdateRequest,
) -> dict[str, str]:
    values = request.model_dump(exclude_unset=True)
    try:
        filters_text = update_user_filter_text(user_key, **values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"text": filters_text}


@app.get("/users/{user_key}/jobs/active")
def active_job(
    user_key: str,
    offset_delta: int = 0,
    reset_offset: bool = False,
) -> dict[str, Any]:
    result = get_active_job(
        user_key=user_key,
        offset_delta=offset_delta,
        reset_offset=reset_offset,
    )
    if result.vacancy is None:
        return {"job": None, "position": 0, "total": 0}

    return {
        "job": _serialize_job(result.vacancy),
        "position": result.position,
        "total": result.total,
    }


@app.get("/users/{user_key}/jobs/active/count")
def active_job_count(user_key: str) -> dict[str, int]:
    return {"active_jobs": get_active_job_count(user_key)}


@app.post("/jobs/{job_id}/save")
def save_job(job_id: int, request: JobStateRequest) -> dict[str, str]:
    _ensure_job_exists(job_id)
    set_user_job_state(
        user_key=request.user_key,
        job_id=job_id,
        is_saved=1,
        is_viewed=1,
    )
    return {"status": "saved"}


@app.post("/jobs/{job_id}/hide")
def hide_job(job_id: int, request: JobStateRequest) -> dict[str, str]:
    _ensure_job_exists(job_id)
    set_user_job_state(
        user_key=request.user_key,
        job_id=job_id,
        is_hidden=1,
        is_viewed=1,
    )
    return {"status": "hidden"}


@app.post("/users/{user_key}/jobs/reset-seen")
def reset_seen(user_key: str) -> dict[str, int]:
    return {"removed": reset_user_jobs(user_key)}


@app.get("/vacancies")
def list_vacancies(
    source: str | None = None,
    limit: int = Query(default=10, ge=1, le=25),
) -> list[dict[str, Any]]:
    return jobs(source=source, limit=limit)


@app.get("/vacancies/{vacancy_id}")
def vacancy_detail(vacancy_id: int) -> dict[str, Any]:
    return job_detail(vacancy_id)


def _ensure_job_exists(job_id: int) -> None:
    if get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")


def _serialize_job(job, include_description: bool = False) -> dict[str, Any]:
    return serialize_job(job, include_description=include_description)
