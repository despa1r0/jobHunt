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

            urls = _collect_djinni_job_urls(page, limit)
            print(f"Found Djinni job links: {len(urls)}")

            vacancies: list[VacancyCreate] = []
            for index, url in enumerate(urls, start=1):
                print(f"[{index}/{len(urls)}] Opening {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)
                vacancies.append(_parse_djinni_detail_page(page, url))

            return vacancies
        finally:
            input("Press Enter to close browser...")
            browser.close()


def _collect_djinni_job_urls(page: Page, limit: int) -> list[str]:
    urls: list[str] = []

    cards = page.locator("[id^='job-item-']").all()
    for card in cards:
        link = card.locator("a.job_item__header-link[href*='/jobs/']").first

        if link.count() == 0:
            continue

        href = link.get_attribute("href")
        if href:
            urls.append(urljoin("https://djinni.co", href))

        if len(urls) >= limit:
            return _unique_urls(urls)

    if not urls:
        all_urls = page.locator("a").evaluate_all(
            """(els) => els
                .map((a) => a.href)
                .filter((href) => /\\/jobs\\/\\d+-/.test(href))"""
        )
        urls.extend(all_urls[:limit])

    return _unique_urls(urls)[:limit]


def _parse_djinni_detail_page(page: Page, url: str) -> VacancyCreate:
    body_text = page.locator("body").inner_text(timeout=10000).strip()
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    title = _safe_inner_text(page, "h1") or _extract_title_from_lines(lines)

    return VacancyCreate(
        source="djinni",
        external_id=_build_external_id(url),
        title=title[:255],
        company_name=_extract_company_name_from_detail(lines, title),
        salary=_extract_salary(body_text),
        location=_extract_location(body_text),
        url=url,
        description=body_text,
    )


def _safe_inner_text(page: Page, selector: str) -> str | None:
    locator = page.locator(selector).first
    if locator.count() == 0:
        return None
    text = locator.inner_text(timeout=5000).strip()
    return text or None


def _extract_title_from_lines(lines: list[str]) -> str:
    ignored = {"Djinni", "Candidates", "Jobs", "Salaries", "Log In", "Sign Up"}
    for line in lines:
        if line not in ignored:
            return line
    raise ValueError("Could not extract Djinni vacancy title")


def _extract_company_name_from_detail(lines: list[str], title: str) -> str | None:
    for index, line in enumerate(lines):
        if line == title and index + 1 < len(lines):
            return lines[index + 1][:255]
    return None


def _extract_salary(text: str) -> str | None:
    for line in text.splitlines():
        stripped_line = line.strip()
        if "$" in stripped_line or "EUR" in stripped_line.upper():
            return stripped_line[:255]
    return None


def _extract_location(text: str) -> str | None:
    known_locations = ["Remote", "Kyiv", "Warsaw", "Lviv", "Ukraine", "Poland", "Europe"]

    for line in text.splitlines():
        stripped_line = line.strip()
        if any(location.lower() in stripped_line.lower() for location in known_locations):
            return stripped_line[:255]

    return None


def _build_external_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:40]


def _unique_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for url in urls:
        normalized_url = url.split("#", 1)[0]
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        result.append(normalized_url)

    return result
