import hashlib
import re
from urllib.parse import urlparse

from app.models import VacancyCreate


FIELD_MAP = {
    "source": "source",
    "external_id": "external_id",
    "title": "title",
    "company_name": "company_name",
    "salary": "salary",
    "location": "location",
    "url": "url",
    "description": "description",
}

URL_PATTERN = re.compile(r"https?://\S+")


def parse_vacancy_text(raw_text: str) -> VacancyCreate:
    data: dict[str, str] = {}

    for line in raw_text.splitlines():
        stripped_line = line.strip()
        if not stripped_line or ":" not in stripped_line:
            continue

        key, value = stripped_line.split(":", 1)
        mapped_key = FIELD_MAP.get(key.strip().lower())

        if mapped_key:
            data[mapped_key] = value.strip()

    if data:
        return VacancyCreate(**data)

    url = _extract_url(raw_text)
    title = _extract_title(raw_text)

    if not title:
        raise ValueError("Could not extract vacancy title from text")

    return VacancyCreate(
        source=_extract_source(url),
        external_id=_build_external_id(url, title, raw_text),
        title=title[:255],
        company_name=_extract_company_name(raw_text),
        salary=None,
        location=None,
        url=url or "about:blank",
        description=raw_text.strip(),
    )


def _extract_url(raw_text: str) -> str | None:
    match = URL_PATTERN.search(raw_text)
    if match:
        return match.group(0).rstrip(".,)")
    return None


def _extract_title(raw_text: str) -> str | None:
    for line in raw_text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if stripped_line.endswith(":"):
            continue
        if URL_PATTERN.search(stripped_line):
            continue
        return stripped_line
    return None


def _extract_company_name(raw_text: str) -> str | None:
    company_match = re.search(r"About company\s+(.+)", raw_text, re.IGNORECASE)
    if company_match:
        return company_match.group(1).strip()

    site_match = re.search(r"https?://(?:www\.)?([^/\s]+)", raw_text)
    if site_match:
        domain = site_match.group(1).lower()
        if domain.startswith("group107"):
            return "GROUP 107"

    return None


def _extract_source(url: str | None) -> str:
    if not url:
        return "unknown"

    domain = urlparse(url).netloc.lower()
    if "djinni" in domain:
        return "djinni"
    if "olx" in domain:
        return "olx"
    return domain.replace("www.", "")[:32] or "unknown"


def _build_external_id(url: str | None, title: str, raw_text: str) -> str:
    if url:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()[:40]
    return hashlib.sha1(f"{title}\n{raw_text}".encode("utf-8")).hexdigest()[:40]
