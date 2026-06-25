from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from app.config import get_settings
from app.normalization.cleaner import compact_llm_input
from app.normalization.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.normalization.schemas import NormalizedJob, Salary

if TYPE_CHECKING:
    from app.models import JobCreate


logger = logging.getLogger(__name__)


def normalize_job_payload(payload: "JobCreate") -> NormalizedJob:
    settings = get_settings()
    if getattr(settings, "normalization_use_gpt4free", False):
        try:
            return _normalize_with_gpt4free(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gpt4free normalization failed, using fallback: %s", exc)

    return normalize_without_llm(payload)


def normalize_without_llm(payload: "JobCreate") -> NormalizedJob:
    return NormalizedJob(
        title=payload.title,
        company=payload.company_name,
        source=payload.source,
        source_url=payload.url,
        location=payload.location,
        remote_type=_guess_remote_type(payload.location, payload.description_raw),
        seniority=_guess_seniority(payload.title, payload.description_raw),
        salary=_parse_salary(payload.salary),
        required_skills=[],
        optional_skills=[],
        languages=[],
        responsibilities=[],
        requirements=[],
        benefits=[],
        summary=_build_summary(payload.description_raw),
    )


def _normalize_with_gpt4free(payload: "JobCreate") -> NormalizedJob:
    try:
        import g4f  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("Install g4f to enable NORMALIZATION_USE_GPT4FREE=true") from exc

    input_text = compact_llm_input(
        title=payload.title,
        company_name=payload.company_name,
        source=payload.source,
        source_url=payload.url,
        location=payload.location,
        salary=payload.salary,
        description_raw=payload.description_raw,
    )
    response = g4f.ChatCompletion.create(
        model=getattr(g4f.models, "gpt_4", "gpt-4"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(input_text=input_text),
            },
        ],
    )
    raw_json = _extract_json_object(str(response))
    return NormalizedJob.model_validate_json(raw_json)


def normalized_to_json(value: NormalizedJob | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if value == {}:
        return {}
    if isinstance(value, NormalizedJob):
        return value.model_dump(mode="json")
    return NormalizedJob.model_validate(value).model_dump(mode="json")


def _extract_json_object(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        raise ValueError("LLM response does not contain a JSON object")

    candidate = match.group(0)
    json.loads(candidate)
    return candidate


def _guess_remote_type(
    location: str | None,
    description_raw: str | None,
) -> str | None:
    text = f"{location or ''}\n{description_raw or ''}".lower()
    if "hybrid" in text or "hybryd" in text:
        return "hybrid"
    if "remote" in text or "zdaln" in text:
        return "remote"
    if "office" in text or "on-site" in text or "stacjonarn" in text:
        return "office"
    return None


def _guess_seniority(title: str | None, description_raw: str | None) -> str | None:
    text = f"{title or ''}\n{description_raw or ''}".lower()
    checks = [
        ("intern", ("intern", "trainee", "praktykant")),
        ("junior", ("junior", "jr.", "entry level")),
        ("senior", ("senior", "sr.")),
        ("lead", ("lead", "principal")),
        ("manager", ("manager", "head of")),
        ("mid", ("middle", "mid ", "regular")),
    ]
    for value, markers in checks:
        if any(marker in text for marker in markers):
            return value
    return None


def _parse_salary(value: str | None) -> Salary | None:
    if not value:
        return None

    normalized = value.replace("\xa0", " ")
    numbers = [
        int(match.replace(" ", ""))
        for match in re.findall(r"\d[\d ]*", normalized)
        if match.strip()
    ]
    currency = _detect_currency(normalized)
    period = _detect_period(normalized)

    if not numbers and currency is None:
        return None

    return Salary(
        min=min(numbers) if numbers else None,
        max=max(numbers) if numbers else None,
        currency=currency,
        period=period,
    )


def _detect_currency(value: str) -> str | None:
    lower = value.lower()
    if "pln" in lower or "zl" in lower or "zlot" in lower:
        return "PLN"
    if "eur" in lower or "euro" in lower:
        return "EUR"
    if "$" in lower or "usd" in lower:
        return "USD"
    return None


def _detect_period(value: str) -> str | None:
    lower = value.lower()
    if any(marker in lower for marker in ["hour", "/h", "godz"]):
        return "hour"
    if any(marker in lower for marker in ["year", "rok"]):
        return "year"
    if any(marker in lower for marker in ["day", "dzien"]):
        return "day"
    if any(marker in lower for marker in ["month", "mies", "msc"]):
        return "month"
    return None


def _build_summary(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(value.split())
    if len(text) <= 280:
        return text
    return text[:277].rsplit(" ", 1)[0] + "..."
