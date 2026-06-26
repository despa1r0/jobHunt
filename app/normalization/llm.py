from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from app.config import get_settings
from app.normalization.cleaner import clean_text, compact_llm_input
from app.normalization.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.normalization.schemas import Language, NormalizedJob, Salary

if TYPE_CHECKING:
    from app.models import JobCreate


logger = logging.getLogger(__name__)

KNOWN_SKILLS = [
    "Python",
    "Django",
    "FastAPI",
    "Flask",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "Linux",
    "Git",
    "REST",
    "GraphQL",
    "API",
    "JavaScript",
    "TypeScript",
    "React",
    "Vue",
    "Angular",
    "HTML",
    "CSS",
    "Selenium",
    "Playwright",
    "Pytest",
    "Pandas",
    "NumPy",
    "TensorFlow",
    "PyTorch",
    "Machine Learning",
    "AI",
    "CI/CD",
    "Jenkins",
    "GitHub Actions",
    "RabbitMQ",
    "Kafka",
    "Celery",
]

OPTIONAL_SECTION_MARKERS = (
    "nice to have",
    "will be a plus",
    "would be a plus",
    "mile widziane",
    "буде плюсом",
    "будет плюсом",
)

REQUIREMENT_SECTION_MARKERS = (
    "requirements",
    "required skills",
    "what we expect",
    "about you",
    "nasze wymagania",
    "wymagania",
    "вимоги",
    "требования",
)

RESPONSIBILITY_SECTION_MARKERS = (
    "responsibilities",
    "what you will do",
    "what you'll do",
    "your tasks",
    "zakres obowiązków",
    "obowiązki",
    "відповідальність",
    "обязанности",
)

BENEFIT_SECTION_MARKERS = (
    "benefits",
    "what we offer",
    "we offer",
    "oferujemy",
    "co oferujemy",
    "що ми пропонуємо",
    "что мы предлагаем",
)


def normalize_job_payload(payload: "JobCreate") -> NormalizedJob:
    settings = get_settings()
    if getattr(settings, "normalization_use_gpt4free", False):
        try:
            normalized = _normalize_with_gpt4free(payload)
            normalized = _enrich_normalized_job(payload, normalized)
            _log_normalization_result(payload, normalized, method="gpt4free")
            return normalized
        except Exception as exc:  # noqa: BLE001
            logger.warning("gpt4free normalization failed, using fallback: %s", exc)

    normalized = normalize_without_llm(payload)
    normalized = _enrich_normalized_job(payload, normalized)
    _log_normalization_result(payload, normalized, method="fallback")
    return normalized


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


def _enrich_normalized_job(
    payload: "JobCreate",
    normalized: NormalizedJob,
) -> NormalizedJob:
    text = clean_text(payload.description_raw)
    section_items = _extract_section_items(text)
    required_skills = normalized.required_skills or _extract_skills(text)
    optional_skills = normalized.optional_skills or _extract_skills(
        "\n".join(section_items["optional_skills"])
    )

    updates: dict[str, Any] = {}
    if not normalized.required_skills and required_skills:
        updates["required_skills"] = required_skills
    if not normalized.optional_skills and optional_skills:
        updates["optional_skills"] = [
            skill for skill in optional_skills if skill not in required_skills
        ]
    if not normalized.requirements and section_items["requirements"]:
        updates["requirements"] = section_items["requirements"]
    if not normalized.responsibilities and section_items["responsibilities"]:
        updates["responsibilities"] = section_items["responsibilities"]
    if not normalized.benefits and section_items["benefits"]:
        updates["benefits"] = section_items["benefits"]
    if not normalized.languages:
        languages = _extract_languages(text)
        if languages:
            updates["languages"] = languages

    if not updates:
        return normalized
    return normalized.model_copy(update=updates)


def _extract_skills(text: str | None) -> list[str]:
    if not text:
        return []

    found: list[str] = []
    lower_text = text.lower()
    for skill in KNOWN_SKILLS:
        pattern = r"(?<![\w+#.-])" + re.escape(skill.lower()) + r"(?![\w+#.-])"
        if re.search(pattern, lower_text) and skill not in found:
            found.append(skill)
    return found[:12]


def _extract_section_items(text: str | None) -> dict[str, list[str]]:
    sections = {
        "requirements": [],
        "responsibilities": [],
        "benefits": [],
        "optional_skills": [],
    }
    if not text:
        return sections

    current_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip(" \t-*•")
        if not line:
            continue

        detected_key = _detect_section_key(line)
        if detected_key is not None:
            current_key = detected_key
            remainder = _strip_heading_prefix(line)
            if remainder:
                _append_section_item(sections[current_key], remainder)
            continue

        if current_key is not None:
            _append_section_item(sections[current_key], line)

    return sections


def _detect_section_key(line: str) -> str | None:
    normalized = line.lower().strip(" :")
    checks = [
        ("optional_skills", OPTIONAL_SECTION_MARKERS),
        ("requirements", REQUIREMENT_SECTION_MARKERS),
        ("responsibilities", RESPONSIBILITY_SECTION_MARKERS),
        ("benefits", BENEFIT_SECTION_MARKERS),
    ]
    for key, markers in checks:
        if any(normalized.startswith(marker) for marker in markers):
            return key
    return None


def _strip_heading_prefix(line: str) -> str:
    if ":" not in line:
        return ""
    return line.split(":", 1)[1].strip(" -*•")


def _append_section_item(items: list[str], value: str) -> None:
    value = " ".join(value.split())
    if not value or len(value) < 2:
        return
    if len(value) > 220:
        value = value[:217].rsplit(" ", 1)[0] + "..."
    if value not in items and len(items) < 8:
        items.append(value)


def _extract_languages(text: str | None) -> list[Language]:
    if not text:
        return []

    languages: list[Language] = []
    patterns = [
        (r"\bEnglish\b[^\n,;.]{0,30}\b(A1|A2|B1|B2|C1|C2)\b", "English"),
        (r"\bPolish\b[^\n,;.]{0,30}\b(A1|A2|B1|B2|C1|C2)\b", "Polish"),
        (r"\bUkrainian\b[^\n,;.]{0,30}\b(A1|A2|B1|B2|C1|C2)\b", "Ukrainian"),
    ]
    for pattern, name in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            languages.append(Language(name=name, level=match.group(1).upper()))

    if not languages and re.search(r"\benglish\b", text, flags=re.IGNORECASE):
        languages.append(Language(name="English", level=None))
    return languages


def _log_normalization_result(
    payload: "JobCreate",
    normalized: NormalizedJob,
    method: str,
) -> None:
    logger.info(
        "Job normalized: method=%s source=%s title=%r skills=%s requirements=%s "
        "responsibilities=%s benefits=%s languages=%s",
        method,
        payload.source,
        payload.title,
        len(normalized.required_skills) + len(normalized.optional_skills),
        len(normalized.requirements),
        len(normalized.responsibilities),
        len(normalized.benefits),
        len(normalized.languages),
    )


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
