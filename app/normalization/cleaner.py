from __future__ import annotations

import hashlib
import re


def clean_text(value: str | None) -> str:
    if not value:
        return ""

    replacements = {
        "\xa0": " ",
        "\u202f": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
    }
    for old, new in replacements.items():
        value = value.replace(old, new)

    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def compact_llm_input(
    *,
    title: str,
    company_name: str | None,
    source: str,
    source_url: str,
    location: str | None,
    salary: str | None,
    description_raw: str | None,
    max_chars: int = 12000,
) -> str:
    parts = [
        f"Title: {clean_text(title)}",
        f"Company: {clean_text(company_name) or 'null'}",
        f"Source: {clean_text(source)}",
        f"Source URL: {clean_text(source_url)}",
        f"Location: {clean_text(location) or 'null'}",
        f"Salary: {clean_text(salary) or 'null'}",
        "",
        "Description:",
        clean_text(description_raw),
    ]
    text = "\n".join(parts).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit("\n", 1)[0].strip()


def content_hash(*values: str | None) -> str:
    normalized = "\n".join(clean_text(value) for value in values if value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def split_words(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.lower() for item in re.split(r"[\s,;]+", value) if item.strip()]
