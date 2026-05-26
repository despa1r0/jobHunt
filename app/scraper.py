import hashlib
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright

from app.config import get_settings
from app.models import VacancyCreate


def scrape_djinni_jobs(limit: int = 10) -> list[VacancyCreate]:
    settings = get_settings()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=settings.scraper_headless,
            slow_mo=250,
        )
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        try:
            page.goto(settings.djinni_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            return _parse_djinni_page(page, limit)
        finally:
            input("Press Enter to close browser...")
            browser.close()


def _parse_djinni_page(page: Page, limit: int) -> list[VacancyCreate]:
    cards = page.locator("li[id^='job-item-'], .job-list-item, article").all()
    vacancies: list[VacancyCreate] = []

    for card in cards[:limit]:
        title_link = card.locator("a[href*='/jobs/']").first

        if title_link.count() == 0:
            continue

        title = title_link.inner_text(timeout=5000).strip()
        relative_url = title_link.get_attribute("href") or ""
        url = urljoin("https://djinni.co", relative_url)
        text = card.inner_text(timeout=5000).strip()

        if not title or not url:
            continue

        vacancies.append(
            VacancyCreate(
                source="djinni",
                external_id=_build_external_id(url),
                title=title[:255],
                company_name=_extract_company_name(text),
                salary=_extract_salary(text),
                location=_extract_location(text),
                url=url,
                description=text,
            )
        )

    return vacancies


def _build_external_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:40]


def _extract_company_name(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if len(lines) >= 2:
        return lines[1][:255]

    return None


def _extract_salary(text: str) -> str | None:
    for line in text.splitlines():
        stripped_line = line.strip()
        if "$" in stripped_line or "€" in stripped_line:
            return stripped_line[:255]
    return None


def _extract_location(text: str) -> str | None:
    known_locations = ["Remote", "Kyiv", "Warsaw", "Lviv", "Ukraine", "Poland"]

    for line in text.splitlines():
        stripped_line = line.strip()
        if any(location.lower() in stripped_line.lower() for location in known_locations):
            return stripped_line[:255]

    return None
