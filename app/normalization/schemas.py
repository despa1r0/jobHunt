from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Salary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: int | None = None
    max: int | None = None
    currency: str | None = Field(default=None, max_length=16)
    period: Literal["hour", "day", "month", "year"] | None = None


class Language(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    level: str | None = Field(default=None, max_length=32)


class NormalizedJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    source: str = Field(min_length=1, max_length=32)
    source_url: HttpUrl
    location: str | None = Field(default=None, max_length=255)
    remote_type: Literal["remote", "hybrid", "office"] | None = None
    seniority: Literal[
        "intern",
        "junior",
        "mid",
        "senior",
        "lead",
        "manager",
    ] | None = None
    salary: Salary | None = None
    required_skills: list[str] = Field(default_factory=list)
    optional_skills: list[str] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    summary: str | None = None
