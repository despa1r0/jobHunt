import hashlib
import logging
import time
from urllib.parse import urlencode, urljoin

from playwright.sync_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from app.config import get_settings
from app.models import ScrapeFilters, VacancyCreate


logger = logging.getLogger(__name__)


def scrape_djinni_jobs(
    filters: ScrapeFilters | None = None,
    limit: int | None = None,
    pause_before_close: bool = False,
) -> list[VacancyCreate]:
    settings = get_settings()
    _ensure_logging_configured()
    search_url = _build_djinni_search_url(filters) if filters else settings.djinni_url
    logger.info(
        "Djinni scrape started: url=%s headless=%s",
        search_url,
        settings.scraper_headless,
    )

    with sync_playwright() as playwright:
        browser = None

        try:
            browser = playwright.chromium.launch(
                headless=settings.scraper_headless,
                slow_mo=0 if settings.scraper_headless else 250,
            )
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.set_default_timeout(settings.scraper_selector_timeout_ms)
            page.set_default_navigation_timeout(settings.scraper_navigation_timeout_ms)

            _goto_with_retries(
                page,
                search_url,
                timeout_ms=settings.scraper_navigation_timeout_ms,
                retries=settings.scraper_retry_count,
            )

            try:
                page.wait_for_selector(
                    "[id^='job-item-']",
                    timeout=settings.scraper_selector_timeout_ms,
                )
            except PlaywrightTimeoutError:
                logger.info("No Djinni vacancy cards found for url=%s", search_url)
                return []

            urls = _collect_djinni_job_urls(page, limit)
            logger.info("Djinni job links found: count=%s url=%s", len(urls), search_url)

            vacancies: list[VacancyCreate] = []
            for index, url in enumerate(urls, start=1):
                logger.info(
                    "Djinni vacancy open: index=%s total=%s url=%s",
                    index,
                    len(urls),
                    url,
                )

                try:
                    _goto_with_retries(
                        page,
                        url,
                        timeout_ms=settings.scraper_navigation_timeout_ms,
                        retries=settings.scraper_retry_count,
                    )
                    page.wait_for_selector(
                        "h1",
                        timeout=settings.scraper_selector_timeout_ms,
                    )
                    vacancies.append(_parse_djinni_detail_page(page, url))
                except (PlaywrightError, ValueError) as exc:
                    logger.exception(
                        "Failed to parse Djinni vacancy: url=%s error=%s",
                        url,
                        exc,
                    )

            logger.info("Djinni scrape finished: parsed=%s url=%s", len(vacancies), search_url)
            return vacancies
        finally:
            try:
                if pause_before_close and not settings.scraper_headless:
                    input("Press Enter to close browser...")
            finally:
                if browser is not None:
                    browser.close()
                    logger.info("Djinni browser closed")


def _ensure_logging_configured() -> None:
    if logging.getLogger().handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _goto_with_retries(
    page: Page,
    url: str,
    timeout_ms: int,
    retries: int,
) -> None:
    attempts = max(1, retries + 1)

    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return
        except PlaywrightError as exc:
            if attempt >= attempts:
                logger.exception(
                    "Page navigation failed after retries: url=%s attempts=%s",
                    url,
                    attempts,
                )
                raise

            delay_seconds = min(2 * attempt, 10)
            logger.warning(
                "Page navigation failed, retrying: url=%s attempt=%s/%s delay=%ss error=%s",
                url,
                attempt,
                attempts,
                delay_seconds,
                exc,
            )
            time.sleep(delay_seconds)


def _collect_djinni_job_urls(page: Page, limit: int | None) -> list[str]:
    urls: list[str] = []

    cards = page.locator("[id^='job-item-']").all()
    for card in cards:
        link = card.locator("a.job_item__header-link[href*='/jobs/']").first

        if link.count() == 0:
            continue

        href = link.get_attribute("href")
        if href:
            urls.append(urljoin("https://djinni.co", href))

        if limit is not None and len(urls) >= limit:
            return _unique_urls(urls)

    if not urls:
        all_urls = page.locator("a").evaluate_all(
            """(els) => els
                .map((a) => a.href)
                .filter((href) => /\\/jobs\\/\\d+-/.test(href))"""
        )
        urls.extend(all_urls)

    unique_urls = _unique_urls(urls)
    if limit is None:
        return unique_urls
    return unique_urls[:limit]


def _build_djinni_search_url(filters: ScrapeFilters) -> str:
    params: list[tuple[str, str]] = [
        ("search_type", "basic-search"),
        ("primary_keyword", filters.search_keywords),
    ]

    for exp_level in _split_filter_value(filters.experience_levels):
        params.append(("exp_level", exp_level))

    for english_level in _split_filter_value(filters.english_levels):
        params.append(("english_level", english_level))

    return f"https://djinni.co/jobs/?{urlencode(params)}"


def _split_filter_value(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        item.strip()
        for item in value.replace(",", " ").split()
        if item.strip()
    ]


def _parse_djinni_detail_page(page: Page, url: str) -> VacancyCreate:
    description = _extract_detail_text(page)
    page_lines = _extract_page_lines(page)
    title = _safe_inner_text(page, "h1") or _extract_title_from_lines(page_lines)

    return VacancyCreate(
        source="djinni",
        external_id=_build_external_id(url),
        title=title[:255],
        company_name=_extract_company_name_from_detail(page_lines, title),
        salary=_extract_salary(page_lines),
        location=_extract_location(page_lines),
        url=url,
        description=description,
    )


def _extract_detail_text(page: Page) -> str:
    detail_selectors = [
        ".job-post__description",
        "[data-original-text]",
        "[id^='job-description-'] .js-truncated-text",
    ]

    for selector in detail_selectors:
        locator = page.locator(selector).first
        if locator.count() == 0:
            continue
        text = locator.inner_text(timeout=5000).strip()
        if text:
            return _clean_description_text(text)

    return _clean_description_text(page.locator("body").inner_text(timeout=10000))


def _extract_page_lines(page: Page) -> list[str]:
    page_text = page.locator(".job-post-page").first
    if page_text.count() == 0:
        page_text = page.locator("body").first
    text = page_text.inner_text(timeout=10000)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _clean_description_text(text: str) -> str:
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

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _normalize_text(raw_line)
        if not line or line in ignored_lines:
            continue
        if line.startswith("Response activity:"):
            continue
        if line.startswith("Last responded"):
            continue
        if line.startswith("Published ") or line.startswith("Updated "):
            continue
        if line.endswith(" views") or line.endswith(" applications"):
            continue
        lines.append(line)

    return "\n".join(lines)


def _normalize_text(text: str) -> str:
    replacements = {
        "\xa0": " ",
        "\u202f": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return " ".join(text.split())


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


def _extract_location(lines: list[str]) -> str | None:
    exact_locations = {
        "Remote",
        "Full Remote",
        "Worldwide",
        "Ukraine",
        "Poland",
        "Countries of Europe or Ukraine",
    }
    city_locations = ["Kyiv", "Warsaw", "Lviv"]

    for line in lines:
        normalized_line = _normalize_text(line)
        if normalized_line in exact_locations:
            return normalized_line[:255]
        if normalized_line in city_locations:
            return normalized_line[:255]
        if normalized_line.startswith("Countries of "):
            return normalized_line[:255]
        if len(normalized_line) <= 40 and normalized_line.endswith(" Remote"):
            return normalized_line[:255]

    return None


def _extract_salary(lines: list[str]) -> str | None:
    for line in lines:
        normalized_line = _normalize_text(line)
        if "$" in normalized_line or "EUR" in normalized_line.upper():
            return normalized_line[:255]

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
