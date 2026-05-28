from datetime import datetime
from html import escape

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, delete, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base


class VacancyCreate(BaseModel):
    source: str = Field(min_length=1, max_length=32)
    external_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    salary: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    url: str = Field(min_length=1)
    description: str | None = None


class ScrapeFilters(BaseModel):
    source: str = "djinni"
    search_keywords: str = "Python"
    experience_levels: str = "no_exp,1y"
    english_levels: str = "pre,intermediate,upper"
    location: str | None = None
    include_keywords: str | None = None
    exclude_keywords: str | None = None


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def as_telegram_message(self) -> str:
        parts = [self.title]

        if self.company_name:
            parts.append(f"Company: {self.company_name}")
        if self.salary:
            parts.append(f"Salary: {self.salary}")
        if self.location:
            parts.append(f"Location: {self.location}")

        description = _format_description(
            self.description,
            title=self.title,
            company_name=self.company_name,
            salary=self.salary,
            location=self.location,
        )
        if description:
            parts.append("")
            parts.append("About:")
            parts.append(description)

        parts.append("")
        parts.append(f"Link: {self.url}")

        return "\n".join(parts)

    def as_telegram_html(self) -> str:
        parts = [f"<b>{escape(self.title)}</b>"]

        if self.company_name:
            parts.append(f"<b>Company:</b> {escape(self.company_name)}")
        if self.salary:
            parts.append(f"<b>Salary:</b> {escape(self.salary)}")
        if self.location:
            parts.append(f"<b>Location:</b> {escape(self.location)}")

        details = _format_description_html(
            self.description,
            title=self.title,
            company_name=self.company_name,
            salary=self.salary,
            location=self.location,
        )
        if details:
            parts.append("")
            parts.append("<b>Details:</b>")
            parts.append(f"<blockquote expandable>{details}</blockquote>")

        parts.append("")
        parts.append(f"Link: {escape(self.url)}")

        return "\n".join(parts)


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
    __tablename__ = "vacancy_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="djinni")
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
    __tablename__ = "sent_vacancies"
    __table_args__ = (
        UniqueConstraint("chat_id", "vacancy_id", name="uq_sent_vacancy_chat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(64), index=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id"), index=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def save_vacancy(db: Session, payload: VacancyCreate) -> Vacancy:
    existing = db.execute(
        select(Vacancy).where(Vacancy.external_id == payload.external_id)
    ).scalar_one_or_none()

    if existing is None:
        existing = Vacancy(**payload.model_dump())
        db.add(existing)
    else:
        for field_name, value in payload.model_dump().items():
            setattr(existing, field_name, value)

    db.commit()
    db.refresh(existing)
    return existing


def save_vacancies(db: Session, payloads: list[VacancyCreate]) -> list[Vacancy]:
    return [save_vacancy(db, payload) for payload in payloads]


def get_latest_vacancy(db: Session) -> Vacancy | None:
    statement = select(Vacancy).order_by(Vacancy.id.desc()).limit(1)
    return db.execute(statement).scalars().first()


def count_vacancies(db: Session) -> int:
    return db.execute(select(func.count(Vacancy.id))).scalar_one()


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
            .where(Vacancy.source == vacancy_filter.source)
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
    sent_ids = select(SentVacancy.vacancy_id).where(SentVacancy.chat_id == chat_id)
    vacancies = list(
        db.execute(
            select(Vacancy)
            .where(Vacancy.source == vacancy_filter.source)
            .where(Vacancy.id.not_in(sent_ids))
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

    db.add(SentVacancy(chat_id=chat_id, vacancy_id=vacancy_id))
    db.commit()


def clear_sent_vacancies(db: Session, chat_id: str) -> int:
    result = db.execute(delete(SentVacancy).where(SentVacancy.chat_id == chat_id))
    db.commit()
    return result.rowcount or 0


def vacancy_matches_filter(vacancy: Vacancy, vacancy_filter: VacancyFilter) -> bool:
    haystack = " ".join(
        value or ""
        for value in [
            vacancy.title,
            vacancy.company_name,
            vacancy.salary,
            vacancy.location,
            vacancy.description,
        ]
    ).lower()

    include_keywords = _split_filter_values(vacancy_filter.include_keywords)
    exclude_keywords = _split_filter_values(vacancy_filter.exclude_keywords)

    if include_keywords and not any(keyword in haystack for keyword in include_keywords):
        return False
    if exclude_keywords and any(keyword in haystack for keyword in exclude_keywords):
        return False
    if vacancy_filter.location and vacancy_filter.location.lower() not in haystack:
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
        item.strip().lower()
        for item in value.replace(",", " ").split()
        if item.strip()
    ]


def _format_description(
    description: str | None,
    max_lines: int = 12,
    max_chars: int = 1800,
    title: str | None = None,
    company_name: str | None = None,
    salary: str | None = None,
    location: str | None = None,
) -> str:
    if not description:
        return ""

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

    if not cleaned_lines:
        return ""

    short_lines = cleaned_lines[:max_lines]
    result = "\n".join(f"- {line}" for line in short_lines)

    if len(result) > max_chars:
        return result[: max_chars - 3].rstrip() + "..."

    return result


def _format_description_html(
    description: str | None,
    max_chars: int = 3000,
    title: str | None = None,
    company_name: str | None = None,
    salary: str | None = None,
    location: str | None = None,
) -> str:
    cleaned_lines = _clean_description_lines(
        description,
        title=title,
        company_name=company_name,
        salary=salary,
        location=location,
    )
    if not cleaned_lines:
        return ""

    html = _format_lines_as_sections(cleaned_lines)
    if len(html) > max_chars:
        html = html[: max_chars - 3].rstrip() + "..."

    return html


def _format_lines_as_sections(lines: list[str]) -> str:
    formatted_lines: list[str] = []

    for line in lines:
        normalized_line = line.rstrip(":").strip()
        escaped_line = escape(line)

        if _looks_like_section_heading(normalized_line):
            if formatted_lines:
                formatted_lines.append("")
            formatted_lines.append(f"<b>{escaped_line}</b>")
            continue

        formatted_lines.append(escaped_line)

    return "\n".join(formatted_lines)


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
