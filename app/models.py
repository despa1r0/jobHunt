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
        parts = [
            f"Title: {self.title}",
            f"Source: {self.source}",
            f"Company: {self.company_name or '-'}",
            f"Salary: {self.salary or '-'}",
            f"Location: {self.location or '-'}",
            f"URL: {self.url}",
        ]

        if self.description:
            parts.append("")
            parts.append(self.description)

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
    return db.execute(select(Vacancy).order_by(Vacancy.id.desc())).scalar_one_or_none()
