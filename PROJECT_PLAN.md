# Project Plan

## Current Status

- Python project structure is created.
- `.env` configuration is connected.
- PostgreSQL connection works through SQLAlchemy.
- `vacancies` table is created through ORM.
- Djinni scraper works through Playwright.
- Browser can run in visible mode for debugging.
- Scraper opens Djinni search page and then opens vacancy detail pages.
- Scraper saves vacancies to PostgreSQL.
- Existing vacancies are updated by `external_id`.
- Telegram Bot API integration works.
- Test Telegram bot can read saved vacancies from the database.
- Telegram bot supports basic commands:
  - `/start`
  - `/count`
  - `/next`
- Vacancy text is cleaned before Telegram output.
- Telegram output is formatted as a readable vacancy card.
- Manual test runners are moved to `manual/`.
- Git repository is initialized.

## Current Important Files

- `app/config.py` - reads `.env` settings.
- `app/db.py` - SQLAlchemy engine, session, and table creation.
- `app/models.py` - vacancy schema, ORM model, database helpers, Telegram formatting.
- `app/scrapers/djinni.py` - current Djinni scraper.
- `app/scrapers/registry.py` - scraper registry by source name.
- `app/telegram.py` - Telegram API wrapper.
- `app/main.py` - FastAPI entry point, currently minimal.
- `manual/run_scraper.py` - manual Djinni scraper run.
- `manual/run_bot_test.py` - temporary Telegram bot polling run.

## Technical Decisions

- No vacancy save limit.
- The scraper should save every vacancy found by the configured search filters.
- Current focus is one high-quality source: Djinni.
- New job boards should be added only after the Djinni flow is stable.
- Filters are the main next feature.
- Filters should be configurable through the bot in the future.
- The code should be structured so a new source can be connected without rewriting bot logic.

## Cleanup Done

- Removed `app/parser.py`.
- Removed `example.txt`.
- Removed `manual/run_flow.py`.
- Removed old example flow code from `app/flow.py`.
- Moved Djinni scraper from `app/scraper.py` to `app/scrapers/djinni.py`.
- Added scraper registry in `app/scrapers/registry.py`.

## Next Implementation Steps

1. Add filter model.

   Required filter fields:
   - source
   - search keywords
   - experience level
   - English level
   - location or remote mode
   - include keywords
   - exclude keywords

2. Make Djinni scraper build search URL from filters.

   Current behavior:
   - hardcoded full `DJINNI_URL` in `.env`

   Target behavior:
   - bot/database stores filters
   - scraper builds Djinni URL from those filters
   - scraper saves all matching vacancies

3. Move bot logic from `manual/run_bot_test.py` into `app/bot.py`.

   `manual/run_bot_test.py` should only start the bot.

4. Add bot commands for filters.

   Minimum commands:
   - `/start`
   - `/count`
   - `/next`
   - `/filters`
   - `/set_keywords`
   - `/set_experience`
   - `/set_english`
   - `/set_location`
   - `/scrape`

5. Add bot state persistence.

   Required table:
   - `bot_states`

   Required fields:
   - `chat_id`
   - `current_offset`
   - `selected_source`
   - `created_at`
   - `updated_at`

6. Track sent vacancies.

   Required table:
   - `sent_vacancies`

   Required fields:
   - `chat_id`
   - `vacancy_id`
   - `sent_at`

   Purpose:
   - avoid sending the same vacancy multiple times
   - allow `/new` command later

7. Add `/new` command.

   Behavior:
   - find saved vacancies matching current filters
   - exclude vacancies already sent to this chat
   - send all new vacancies
   - mark sent vacancies in database

8. Add automatic worker loop.

    Behavior:
    - periodically run scraper with saved filters
    - save new and updated vacancies
    - send new matching vacancies through Telegram

9. Add Alembic migrations.

    Needed before adding more tables:
    - `vacancies`
    - `bot_states`
    - `sent_vacancies`
    - filter table

10. Expand FastAPI after bot flow is stable.

    Minimum endpoints:
    - `GET /health`
    - `GET /vacancies`
    - `GET /vacancies/{id}`
    - `POST /scrape`
    - `GET /filters`

11. Add Docker setup.

    Required services:
    - app
    - postgres
    - bot worker

12. Deploy to VPS.

    Required:
    - `.env` on server
    - Docker Compose
    - restart policy
    - logs
    - database backup plan

## Later Work

- Add OLX scraper.
- Add more job boards.
- Add source selection in bot.
- Add advanced filtering commands.
- Add scheduled scraping configuration through bot.
- Add admin-only bot commands.

## Immediate Priority

Build a clean Djinni-only MVP:

- implement filters
- move bot logic into `app/bot.py`
- add persistent bot state
- add sent vacancy tracking
- add `/new`
- add automatic scraping loop
