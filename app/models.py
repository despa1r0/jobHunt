from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, Text, func, select
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
        "Python",
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
