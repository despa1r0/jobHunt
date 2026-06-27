from __future__ import annotations

from typing import Any

from app.normalization.schemas import NormalizedJob, Salary


DISCORD_GREEN = 0x2ECC71
MAX_FIELD_VALUE = 1024
MAX_DESCRIPTION = 4096
MAX_TITLE = 256
SOURCE_THUMBNAILS = {
    "djinni": "https://djinni.co/favicon.ico",
    "praca_pl": "https://www.praca.pl/favicon.ico",
}


def build_job_embed_payload(job_data: NormalizedJob | dict[str, Any]) -> dict[str, Any]:
    job = (
        job_data
        if isinstance(job_data, NormalizedJob)
        else NormalizedJob.model_validate(job_data)
    )
    embed = {
        "title": _truncate(job.title, MAX_TITLE),
        "url": str(job.source_url),
        "description": _truncate(job.summary or "No summary provided.", MAX_DESCRIPTION),
        "color": DISCORD_GREEN,
        "fields": _build_fields(job),
        "author": {
            "name": f"{job.source} normalized job",
        },
        "footer": {
            "text": f"{job.source} job alert",
        },
    }
    thumbnail_url = SOURCE_THUMBNAILS.get(job.source)
    if thumbnail_url:
        embed["thumbnail"] = {"url": thumbnail_url}
    return {"embeds": [embed]}


def _build_fields(job: NormalizedJob) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []

    _add_field(fields, "Company", job.company)
    _add_field(fields, "Location", job.location)
    _add_field(fields, "Work mode", job.remote_type)
    _add_field(fields, "Seniority", job.seniority)
    _add_field(fields, "Salary", _format_salary(job.salary))
    _add_field(fields, "Requirements", _format_list(job.requirements, bullet=True))
    _add_field(fields, "Responsibilities", _format_list(job.responsibilities, bullet=True))
    _add_field(fields, "Required skills", _format_list(job.required_skills, bullet=True))
    _add_field(fields, "Optional skills", _format_list(job.optional_skills, bullet=True))
    _add_field(fields, "Languages", _format_languages(job))
    _add_field(fields, "Benefits", _format_list(job.benefits, bullet=True))

    return fields


def _add_field(
    fields: list[dict[str, Any]],
    name: str,
    value: str | None,
    inline: bool = False,
) -> None:
    if not value:
        return
    fields.append(
        {
            "name": name,
            "value": _truncate(value, MAX_FIELD_VALUE),
            "inline": inline,
        }
    )


def _format_salary(salary: Salary | None) -> str | None:
    if salary is None:
        return None

    parts: list[str] = []
    if salary.min is not None and salary.max is not None:
        if salary.min == salary.max:
            parts.append(str(salary.min))
        else:
            parts.append(f"{salary.min}-{salary.max}")
    elif salary.min is not None:
        parts.append(f"from {salary.min}")
    elif salary.max is not None:
        parts.append(f"up to {salary.max}")

    if salary.currency:
        parts.append(salary.currency)
    if salary.period:
        parts.append(f"/ {salary.period}")

    return " ".join(parts) or None


def _format_list(values: list[str], bullet: bool = False) -> str | None:
    cleaned = [value.strip() for value in values if value.strip()]
    if not cleaned:
        return None
    if bullet:
        return "\n".join(f"- {value}" for value in cleaned)
    return ", ".join(cleaned)


def _format_languages(job: NormalizedJob) -> str | None:
    if not job.languages:
        return None
    values = [
        f"{language.name} {language.level}".strip()
        for language in job.languages
        if language.name.strip()
    ]
    if not values:
        return None
    return "\n".join(f"- {value}" for value in values)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."
