import hashlib
import logging
import re
import time
from urllib.parse import urljoin

from playwright.sync_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from app.config import get_settings
from app.models import ScrapeFilters, VacancyCreate


logger = logging.getLogger(__name__)

PRACA_PL_BASE_URL = "https://www.praca.pl"


def scrape_praca_pl_jobs(
    filters: ScrapeFilters | None = None,
    limit: int | None = None,
    pause_before_close: bool = False,
) -> list[VacancyCreate]:
    settings = get_settings()
    _ensure_logging_configured()
    search_url = _build_praca_pl_search_url(filters) if filters else settings.praca_pl_url
    logger.info(
        "Praca.pl scrape started: url=%s headless=%s",
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
                    "a.listing__title[href*='.html'], a[href*='praca.pl/'][href*='.html']",
                    timeout=settings.scraper_selector_timeout_ms,
                )
            except PlaywrightTimeoutError:
                logger.info("No Praca.pl vacancy cards found for url=%s", search_url)
                return []

            urls = _collect_praca_pl_job_urls(page, limit)
            logger.info("Praca.pl job links found: count=%s url=%s", len(urls), search_url)

            vacancies: list[VacancyCreate] = []
            for index, url in enumerate(urls, start=1):
                logger.info(
                    "Praca.pl vacancy open: index=%s total=%s url=%s",
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
                        ".app-offer__title, h1",
                        timeout=settings.scraper_selector_timeout_ms,
                    )
                    vacancies.append(_parse_praca_pl_detail_page(page, url))
                except (PlaywrightError, ValueError) as exc:
                    logger.exception(
                        "Failed to parse Praca.pl vacancy: url=%s error=%s",
                        url,
                        exc,
                    )

            logger.info("Praca.pl scrape finished: parsed=%s url=%s", len(vacancies), search_url)
            return vacancies
        finally:
            try:
                if pause_before_close and not settings.scraper_headless:
                    input("Press Enter to close browser...")
            finally:
                if browser is not None:
                    browser.close()
                    logger.info("Praca.pl browser closed")


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


def _collect_praca_pl_job_urls(page: Page, limit: int | None) -> list[str]:
    urls: list[str] = []

    links = page.locator("a.listing__title[href]").all()
    for link in links:
        href = link.get_attribute("href")
        if href and _looks_like_praca_pl_vacancy_url(href):
            urls.append(urljoin(PRACA_PL_BASE_URL, href))

        if limit is not None and len(urls) >= limit:
            return _unique_urls(urls)

    if not urls:
        all_urls = page.locator("a[href]").evaluate_all(
            """(els) => els
                .map((a) => a.href)
                .filter((href) => /_[0-9]{6,}\\.html([#?].*)?$/.test(href))"""
        )
        urls.extend(url for url in all_urls if _looks_like_praca_pl_vacancy_url(url))

    unique_urls = _unique_urls(urls)
    if limit is None:
        return unique_urls
    return unique_urls[:limit]


def _looks_like_praca_pl_vacancy_url(url: str) -> bool:
    return bool(re.search(r"_[0-9]{6,}\.html(?:[#?].*)?$", url)) and "oferty-pracy_" not in url


def _build_praca_pl_search_url(filters: ScrapeFilters) -> str:
    keywords_slug = _slugify_search_part(filters.search_keywords or "python", default="python")
    location_slug = _slugify_search_part(filters.location or "", default="")

    if location_slug:
        return f"{PRACA_PL_BASE_URL}/s-{keywords_slug},{location_slug}.html"
    return f"{PRACA_PL_BASE_URL}/s-{keywords_slug}.html"


def _slugify_search_part(value: str, default: str) -> str:
    slug = re.sub(r"[^0-9A-Za-zĄąĆćĘęŁłŃńÓóŚśŹźŻż]+", "-", value.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or default


def _parse_praca_pl_detail_page(page: Page, url: str) -> VacancyCreate:
    description = _extract_detail_text(page)
    page_lines = _extract_page_lines(page)
    title = _safe_inner_text(page, ".app-offer__title") or _safe_inner_text(page, "h1")
    if not title:
        title = _extract_title_from_lines(page_lines)

    return VacancyCreate(
        source="praca_pl",
        external_id=_extract_external_id(url),
        title=title[:255],
        company_name=_extract_company_name(page),
        salary=_extract_salary(page, page_lines),
        location=_extract_location(page),
        url=url,
        description=description,
    )


def _extract_detail_text(page: Page) -> str:
    detail_selectors = [
        ".app-offer__content .f1template_content",
        ".app-offer__content .szcont",
        ".app-offer__szcont-block",
        "article.app-offer__content",
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
    page_text = page.locator(".app-offer").first
    if page_text.count() == 0:
        page_text = page.locator("body").first
    text = page_text.inner_text(timeout=10000)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _clean_description_text(text: str) -> str:
    ignored_lines = {
        "Praca.pl",
        "Aplikuj",
        "Aplikuj szybko",
        "Drukuj",
        "Obserwuj",
        "Włącz job alert",
        "Pokaż nr tel.",
        "Zobacz na mapie",
    }

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _normalize_text(raw_line)
        if not line or line in ignored_lines:
            continue
        if line.startswith("Wyrażam zgodę na przetwarzanie"):
            continue
        if line.startswith("Jeżeli CV zawiera zdjęcie"):
            continue
        if line.startswith("Administratorem danych osobowych"):
            continue
        if line.startswith("Prosimy o dopisanie"):
            continue
        if line.startswith("Klikając przycisk"):
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
        "\u201e": '"',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return " ".join(text.split())


def _safe_inner_text(page: Page, selector: str) -> str | None:
    locator = page.locator(selector).first
    if locator.count() == 0:
        return None
    text = locator.inner_text(timeout=5000).strip()
    return _normalize_text(text) or None


def _extract_title_from_lines(lines: list[str]) -> str:
    ignored = {"Praca.pl", "Oferty pracy", "Aplikuj", "Aplikuj szybko"}
    for line in lines:
        if line not in ignored:
            return line
    raise ValueError("Could not extract Praca.pl vacancy title")


def _extract_company_name(page: Page) -> str | None:
    selectors = [
        ".app-offer__employer-data span",
        ".app-offer__main-item--employer",
        ".app-offer__logo-img",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() == 0:
            continue

        if selector == ".app-offer__logo-img":
            text = locator.get_attribute("alt") or ""
        else:
            text = locator.inner_text(timeout=5000)

        text = _normalize_text(text).removeprefix("Praca ").strip()
        if text:
            return text[:255]

    return None


def _extract_location(page: Page) -> str | None:
    selectors = [
        ".app-offer__main-item--location",
        ".app-offer__header-item--remote-work",
        ".app-offer__header-item--home",
    ]
    parts: list[str] = []

    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() == 0:
            continue
        text = _normalize_text(locator.inner_text(timeout=5000)).replace("Mapa", "").strip()
        if text and text not in parts:
            parts.append(text)

    if not parts:
        return None
    return " | ".join(parts)[:255]


def _extract_salary(page: Page, lines: list[str]) -> str | None:
    selectors = [
        ".app-offer__salary",
        ".app-offer__header-item--salary",
    ]
    for selector in selectors:
        text = _safe_inner_text(page, selector)
        if text:
            return text[:255]

    for line in lines:
        normalized_line = _normalize_text(line)
        lower_line = normalized_line.lower()
        has_money = "zł" in lower_line or "pln" in lower_line
        has_salary_context = any(
            marker in lower_line
            for marker in ["brutto", "netto", "mies", "godz", "wynagrodzenie"]
        )
        if has_money and has_salary_context:
            return normalized_line[:255]

    return None


def _extract_external_id(url: str) -> str:
    match = re.search(r"_([0-9]{6,})\.html(?:[#?].*)?$", url)
    if match:
        return f"praca_pl:{match.group(1)}"
    return f"praca_pl:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:40]}"


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
