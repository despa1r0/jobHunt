from dataclasses import dataclass
from datetime import datetime
from html import escape
import unicodedata

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.normalization.cleaner import content_hash
from app.normalization.llm import normalized_to_json, normalize_job_payload
from app.normalization.schemas import NormalizedJob
from app.scrapers.sources import ALL_SOURCES, SUPPORTED_SOURCES


@dataclass(frozen=True)
class VacancySection:
    title: str
    lines: list[str]

    def as_blockquote_html(self, body: str) -> str:
        if self.title == "About":
            return f"<blockquote expandable>{escape(body)}</blockquote>"

        return (
            f"<b>{escape(self.title)}</b>\n"
            f"<blockquote expandable>{escape(body)}</blockquote>"
        )

    def as_blockquote_chunks(self, max_body_chars: int) -> list[str]:
        body = "\n".join(self.lines).strip()
        if not body:
            return []

        return [
            self.as_blockquote_html(chunk)
            for chunk in _split_text_chunks(body, max_body_chars)
        ]


class JobCreate(BaseModel):
    source: str = Field(min_length=1, max_length=32)
    external_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    salary: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    url: str = Field(min_length=1)
    description_raw: str | None = None
    description_html: str | None = None
    normalized_data: NormalizedJob | dict | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_description(cls, data: object) -> object:
        if (
            isinstance(data, dict)
            and "description" in data
            and "description_raw" not in data
        ):
            data = data.copy()
            data["description_raw"] = data.pop("description")
        return data

    @property
    def description(self) -> str | None:
        return self.description_raw


VacancyCreate = JobCreate


class ScrapeFilters(BaseModel):
    source: str = "all"
    search_keywords: str = "Python"
    experience_levels: str = "no_exp,1y"
    english_levels: str = "pre,intermediate,upper"
    location: str | None = None
    include_keywords: str | None = None
    exclude_keywords: str | None = None


class Vacancy(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    @property
    def created_at(self) -> datetime:
        return self.first_seen_at

    @property
    def updated_at(self) -> datetime:
        return self.last_seen_at

    @property
    def company(self) -> str | None:
        return self._normalized_value("company") or self.company_name

    @property
    def salary(self) -> str | None:
        salary = self._normalized_value("salary")
        if not isinstance(salary, dict):
            return None

        values = []
        if salary.get("min") is not None and salary.get("max") is not None:
            if salary["min"] == salary["max"]:
                values.append(str(salary["min"]))
            else:
                values.append(f"{salary['min']}-{salary['max']}")
        elif salary.get("min") is not None:
            values.append(f"from {salary['min']}")
        elif salary.get("max") is not None:
            values.append(f"up to {salary['max']}")

        if salary.get("currency"):
            values.append(str(salary["currency"]))
        if salary.get("period"):
            values.append(f"/ {salary['period']}")
        return " ".join(values) or None

    @property
    def location(self) -> str | None:
        value = self._normalized_value("location")
        return str(value) if value else None

    @property
    def description(self) -> str | None:
        return self.description_raw

    def _normalized_value(self, key: str):
        if not isinstance(self.normalized_data, dict):
            return None
        return self.normalized_data.get(key)

    def as_telegram_html(self, details_page: int = 0) -> str:
        pages = self.telegram_html_pages()
        if not pages:
            return ""
        if details_page < 0:
            details_page = 0
        if details_page >= len(pages):
            details_page = len(pages) - 1

        return pages[details_page]

    def telegram_html_pages(self, max_chars: int = 3900) -> list[str]:
        parts = self._telegram_header_parts()

        parts.append("")
        parts.append(f"Link: {escape(self.url)}")

        sections = self.telegram_sections()
        if not sections:
            return ["\n".join(parts)]

        return _format_vacancy_pages(parts, sections, max_chars=max_chars)

    def telegram_sections(self) -> list[VacancySection]:
        return _split_description_sections(
            self.description,
            title=self.title,
            company_name=self.company_name,
            salary=self.salary,
            location=self.location,
        )

    def _telegram_header_parts(self) -> list[str]:
        parts = [f"<b>{escape(self.title)}</b>"]

        parts.append(f"<b>Source:</b> {escape(self.source)}")
        if self.company_name:
            parts.append(f"<b>Company:</b> {escape(self.company_name)}")
        if self.salary:
            parts.append(f"<b>Salary:</b> {escape(self.salary)}")
        if self.location:
            parts.append(f"<b>Location:</b> {escape(self.location)}")
        return parts


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telegram_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BotState(Base):
    __tablename__ = "bot_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    selected_source: Mapped[str] = mapped_column(String(32), default="djinni")
    current_offset: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class VacancyFilter(Base):
    __tablename__ = "search_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default=ALL_SOURCES)
    search_keywords: Mapped[str] = mapped_column(String(255), default="Python")
    experience_levels: Mapped[str] = mapped_column(String(255), default="no_exp,1y")
    english_levels: Mapped[str] = mapped_column(
        String(255), default="pre,intermediate,upper"
    )
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    include_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclude_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_scrape_filters(self) -> ScrapeFilters:
        return ScrapeFilters(
            source=self.source,
            search_keywords=self.search_keywords,
            experience_levels=self.experience_levels,
            english_levels=self.english_levels,
            location=self.location,
            include_keywords=self.include_keywords,
            exclude_keywords=self.exclude_keywords,
        )


class SentVacancy(Base):
    __tablename__ = "user_jobs"
    __table_args__ = (
        UniqueConstraint("chat_id", "vacancy_id", name="uq_user_jobs_chat_vacancy"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    chat_id: Mapped[str] = mapped_column(String(64), index=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    filter_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_filters.id"),
        nullable=True,
    )
    is_viewed: Mapped[int] = mapped_column(Integer, default=0)
    is_saved: Mapped[int] = mapped_column(Integer, default=0)
    is_hidden: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def save_vacancy(db: Session, payload: VacancyCreate) -> Vacancy:
    existing = db.execute(
        select(Vacancy).where(
            Vacancy.source == payload.source,
            Vacancy.external_id == payload.external_id,
        )
    ).scalar_one_or_none()
    normalized_data = normalized_to_json(payload.normalized_data)
    if not normalized_data and _existing_raw_payload_matches(existing, payload):
        normalized_data = existing.normalized_data
    if not normalized_data:
        normalized_data = normalize_job_payload(payload).model_dump(mode="json")

    payload_hash = content_hash(
        payload.title,
        payload.company_name,
        payload.url,
        payload.description_raw,
        str(normalized_data),
    )
    values = {
        "source": payload.source,
        "external_id": payload.external_id,
        "url": payload.url,
        "title": payload.title,
        "company_name": payload.company_name,
        "description_raw": payload.description_raw,
        "description_html": payload.description_html,
        "normalized_data": normalized_data,
        "content_hash": payload_hash,
        "status": "active",
    }

    if existing is None:
        existing = Vacancy(**values)
        db.add(existing)
    else:
        for field_name, value in values.items():
            setattr(existing, field_name, value)
        existing.last_seen_at = func.now()

    db.commit()
    db.refresh(existing)
    return existing


def _existing_raw_payload_matches(
    existing: Vacancy | None,
    payload: VacancyCreate,
) -> bool:
    if existing is None or not existing.normalized_data:
        return False
    return (
        existing.title == payload.title
        and existing.company_name == payload.company_name
        and existing.url == payload.url
        and existing.description_raw == payload.description_raw
        and existing.description_html == payload.description_html
    )


def save_vacancies(db: Session, payloads: list[VacancyCreate]) -> list[Vacancy]:
    return [save_vacancy(db, payload) for payload in payloads]


def get_latest_vacancy(db: Session) -> Vacancy | None:
    statement = select(Vacancy).order_by(Vacancy.id.desc()).limit(1)
    return db.execute(statement).scalars().first()


def get_latest_vacancies(
    db: Session,
    limit: int = 5,
    source: str | None = None,
) -> list[Vacancy]:
    limit = max(1, min(limit, 25))
    statement = select(Vacancy).order_by(Vacancy.id.desc()).limit(limit)
    if source and source != ALL_SOURCES:
        statement = statement.where(Vacancy.source == source)
    return list(db.execute(statement).scalars())


def get_vacancy_by_id(db: Session, vacancy_id: int) -> Vacancy | None:
    statement = select(Vacancy).where(Vacancy.id == vacancy_id)
    return db.execute(statement).scalar_one_or_none()


def count_vacancies(db: Session) -> int:
    return db.execute(select(func.count(Vacancy.id))).scalar_one()


def count_vacancies_by_source(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Vacancy.source, func.count(Vacancy.id)).group_by(Vacancy.source)
    ).all()
    return {source: total for source, total in rows}


def get_vacancy_page(db: Session, offset: int, limit: int = 1) -> list[Vacancy]:
    statement = select(Vacancy).order_by(Vacancy.id.desc()).offset(offset).limit(limit)
    return list(db.execute(statement).scalars())


def get_filtered_vacancies(
    db: Session,
    vacancy_filter: VacancyFilter,
) -> list[Vacancy]:
    vacancies = list(
        db.execute(
            select(Vacancy)
            .order_by(Vacancy.id.desc())
        ).scalars()
    )
    return [
        vacancy
        for vacancy in vacancies
        if vacancy_matches_filter(vacancy, vacancy_filter)
    ]


def get_or_create_bot_state(db: Session, chat_id: str) -> BotState:
    state = db.execute(
        select(BotState).where(BotState.chat_id == chat_id)
    ).scalar_one_or_none()
    if state is not None:
        return state

    state = BotState(chat_id=chat_id)
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def get_or_create_user(db: Session, telegram_id: str) -> User:
    user = db.execute(
        select(User).where(User.telegram_id == telegram_id)
    ).scalar_one_or_none()
    if user is not None:
        return user

    user = User(telegram_id=telegram_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_vacancy_filter(db: Session, chat_id: str) -> VacancyFilter:
    vacancy_filter = db.execute(
        select(VacancyFilter).where(VacancyFilter.chat_id == chat_id)
    ).scalar_one_or_none()
    if vacancy_filter is not None:
        return vacancy_filter

    vacancy_filter = VacancyFilter(chat_id=chat_id)
    db.add(vacancy_filter)
    db.commit()
    db.refresh(vacancy_filter)
    return vacancy_filter


def update_vacancy_filter(db: Session, chat_id: str, **values: str | None) -> VacancyFilter:
    vacancy_filter = get_or_create_vacancy_filter(db, chat_id)

    for field_name, value in values.items():
        if hasattr(vacancy_filter, field_name):
            setattr(vacancy_filter, field_name, value)

    db.commit()
    db.refresh(vacancy_filter)
    return vacancy_filter


def update_bot_offset(db: Session, chat_id: str, current_offset: int) -> BotState:
    state = get_or_create_bot_state(db, chat_id)
    state.current_offset = current_offset
    db.commit()
    db.refresh(state)
    return state


def get_unsent_vacancies(
    db: Session,
    chat_id: str,
    vacancy_filter: VacancyFilter,
) -> list[Vacancy]:
    hidden_ids = select(SentVacancy.vacancy_id).where(
        SentVacancy.chat_id == chat_id,
        SentVacancy.is_hidden == 1,
    )
    vacancies = list(
        db.execute(
            select(Vacancy)
            .where(Vacancy.id.not_in(hidden_ids))
            .order_by(Vacancy.id.desc())
        ).scalars()
    )
    return [
        vacancy
        for vacancy in vacancies
        if vacancy_matches_filter(vacancy, vacancy_filter)
    ]


def get_active_vacancies(
    db: Session,
    chat_id: str,
    vacancy_filter: VacancyFilter,
) -> list[Vacancy]:
    return get_unsent_vacancies(db, chat_id, vacancy_filter)


def mark_vacancy_sent(db: Session, chat_id: str, vacancy_id: int) -> None:
    existing = db.execute(
        select(SentVacancy).where(
            SentVacancy.chat_id == chat_id,
            SentVacancy.vacancy_id == vacancy_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    user = get_or_create_user(db, chat_id)
    vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
    db.add(
        SentVacancy(
            user_id=user.id,
            chat_id=chat_id,
            vacancy_id=vacancy_id,
            filter_id=vacancy_filter.id,
            is_viewed=1,
            is_hidden=1,
        )
    )
    db.commit()


def clear_sent_vacancies(db: Session, chat_id: str) -> int:
    result = db.execute(delete(SentVacancy).where(SentVacancy.chat_id == chat_id))
    db.commit()
    return result.rowcount or 0


def vacancy_matches_filter(vacancy: Vacancy, vacancy_filter: VacancyFilter) -> bool:
    haystack = _normalize_filter_text(
        " ".join(
            value or ""
            for value in [
                vacancy.title,
                vacancy.company_name,
                vacancy.salary,
                vacancy.location,
                vacancy.description,
            ]
        )
    )

    include_keywords = _split_filter_values(vacancy_filter.include_keywords)
    exclude_keywords = _split_filter_values(vacancy_filter.exclude_keywords)

    if include_keywords and not any(keyword in haystack for keyword in include_keywords):
        return False
    if exclude_keywords and any(keyword in haystack for keyword in exclude_keywords):
        return False
    if vacancy_filter.source != ALL_SOURCES and vacancy.source != vacancy_filter.source:
        return False

    location_values = _split_filter_values(vacancy_filter.location)
    if location_values and not any(location in haystack for location in location_values):
        return False

    return True


def format_vacancy_filter(vacancy_filter: VacancyFilter) -> str:
    return "\n".join(
        [
            f"Source: {vacancy_filter.source}",
            f"Keywords: {vacancy_filter.search_keywords}",
            f"Experience: {vacancy_filter.experience_levels}",
            f"English: {vacancy_filter.english_levels}",
            f"Location: {vacancy_filter.location or '-'}",
            f"Include: {vacancy_filter.include_keywords or '-'}",
            f"Exclude: {vacancy_filter.exclude_keywords or '-'}",
        ]
    )


def _split_filter_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        _normalize_filter_text(item.strip())
        for item in value.replace(",", " ").split()
        if item.strip()
    ]


def supported_filter_sources() -> set[str]:
    return {*SUPPORTED_SOURCES, ALL_SOURCES}


def _normalize_filter_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _split_description_sections(
    description: str | None,
    title: str | None = None,
    company_name: str | None = None,
    salary: str | None = None,
    location: str | None = None,
) -> list[VacancySection]:
    cleaned_lines = _clean_description_lines(
        description,
        title=title,
        company_name=company_name,
        salary=salary,
        location=location,
    )
    if not cleaned_lines:
        return []

    sections: list[VacancySection] = []
    current_title = "About"
    current_lines: list[str] = []

    for line in cleaned_lines:
        normalized_line = line.rstrip(":").strip()
        if _looks_like_section_heading(normalized_line):
            if current_lines:
                sections.append(VacancySection(current_title, current_lines))
            current_title = normalized_line
            current_lines = []
            continue

        current_lines.append(line)

    if current_lines:
        sections.append(VacancySection(current_title, current_lines))

    return sections


def _format_vacancy_pages(
    header_parts: list[str],
    sections: list[VacancySection],
    max_chars: int,
) -> list[str]:
    base_parts = [*header_parts, "", "<b>Details:</b>"]
    base_text = "\n".join(base_parts)
    max_block_body_chars = max(800, max_chars - len(base_text) - 250)
    blocks = [
        block
        for section in sections
        for block in section.as_blockquote_chunks(max_block_body_chars)
    ]
    if not blocks:
        return ["\n".join(header_parts)]

    pages: list[str] = []
    current_parts = base_parts.copy()

    for block in blocks:
        candidate = "\n".join([*current_parts, "", block])
        if len(candidate) > max_chars and len(current_parts) > len(base_parts):
            pages.append("\n".join(current_parts))
            current_parts = [*base_parts, "", block]
            continue

        current_parts.append("")
        current_parts.append(block)

    if len(current_parts) > len(base_parts):
        pages.append("\n".join(current_parts))

    return pages


def _split_text_chunks(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if len(line) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_line(line, max_chars))
            continue

        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        chunks.append(current)
        current = line

    if current:
        chunks.append(current)

    return chunks


def _split_long_line(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    remaining = text.strip()

    while len(remaining) > max_chars:
        split_at = remaining.rfind(" ", 0, max_chars)
        if split_at <= 0:
            split_at = max_chars

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def _looks_like_section_heading(line: str) -> bool:
    normalized = line.lower()
    known_headings = {
        "requirements",
        "required skills",
        "what we are looking for",
        "what are we looking for",
        "what you'll be doing",
        "what you will do",
        "responsibilities",
        "nice to have",
        "nice-to-have",
        "what we offer",
        "we offer",
        "about the role",
        "about you",
        "zakres obowiązków",
        "obowiązki",
        "zadania",
        "twoje zadania",
        "twój zakres obowiązków",
        "opis stanowiska",
        "wymagania",
        "oczekiwania",
        "mile widziane",
        "oferujemy",
        "co oferujemy",
        "benefity",
        "nasze wymagania",
        "what we expect",
        "вимоги",
        "обов'язки",
        "обовʼязки",
        "відповідальність",
        "що потрібно робити",
        "що ми очікуємо",
        "що ми пропонуємо",
        "буде плюсом",
        "буде перевагою",
        "про компанію",
        "требования",
        "обязанности",
        "ответственность",
        "что нужно делать",
        "что мы ожидаем",
        "что мы предлагаем",
        "будет плюсом",
        "будет преимуществом",
        "о компании",
    }

    if normalized in known_headings:
        return True
    if normalized.startswith("requirements"):
        return True
    if normalized.startswith("nice to have"):
        return True
    if normalized.startswith("what we offer"):
        return True
    if normalized.startswith("what you'll"):
        return True
    if normalized.startswith("what will"):
        return True
    if normalized.startswith("what you will"):
        return True
    if normalized.startswith("responsibilities"):
        return True
    if normalized.startswith("zakres obowiązków"):
        return True
    if normalized.startswith("twój zakres obowiązków"):
        return True
    if normalized.startswith("opis stanowiska"):
        return True
    if normalized.startswith("wymagania"):
        return True
    if normalized.startswith("oferujemy"):
        return True
    if normalized.startswith("mile widziane"):
        return True
    if normalized.startswith("benefity"):
        return True
    if normalized.startswith("вимоги"):
        return True
    if normalized.startswith("обов"):
        return True
    if normalized.startswith("що ми"):
        return True
    if normalized.startswith("що потрібно"):
        return True
    if normalized.startswith("буде плюсом"):
        return True
    if normalized.startswith("буде перевагою"):
        return True
    if normalized.startswith("про компан"):
        return True
    if normalized.startswith("требования"):
        return True
    if normalized.startswith("обязанности"):
        return True
    if normalized.startswith("ответствен"):
        return True
    if normalized.startswith("что мы"):
        return True
    if normalized.startswith("что нужно"):
        return True
    if normalized.startswith("будет плюсом"):
        return True
    if normalized.startswith("будет преимуществом"):
        return True
    if normalized.startswith("о компании"):
        return True

    return False


def _clean_description_lines(
    description: str | None,
    title: str | None = None,
    company_name: str | None = None,
    salary: str | None = None,
    location: str | None = None,
) -> list[str]:
    if not description:
        return []

    ignored_lines = {
        "Djinni",
        "Candidates",
        "Jobs",
        "Salaries",
        "Log In",
        "Sign Up",
        "All jobs",
        "Development",
        "Apply for the job",
    }

    cleaned_lines: list[str] = []
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line or line in ignored_lines:
            continue
        if title and line == title:
            continue
        if company_name and line == company_name:
            continue
        if salary and line == salary:
            continue
        if location and line == location:
            continue
        if line.startswith("Unknown command."):
            continue
        if line.startswith("Response activity:"):
            continue
        if line.startswith("Last responded"):
            continue
        if line.startswith("Published ") or line.startswith("Updated "):
            continue
        if line.endswith(" views") or line.endswith(" applications"):
            continue
        cleaned_lines.append(line)

    return cleaned_lines
