# Project Status

## Current Architecture

```text
Scrapers (Playwright)
    -> normalization / gpt4free
    -> Pydantic validation
    -> PostgreSQL
    -> service layer
    -> FastAPI / Telegram / Discord
```

## Implemented

- Two scraper sources: `djinni`, `praca_pl`.
- `all` source mode for scraping and viewing jobs from every supported source.
- Normalized job JSON stored in `jobs.normalized_data`.
- Pydantic schema validation for normalized jobs.
- PostgreSQL tables for users, filters, jobs, user job state, and bot state.
- Telegram bot with filters, scrape commands, active list navigation, and hidden jobs.
- Discord bot with slash commands, command hints, embeds from normalized data, and action buttons.
- FastAPI endpoints for jobs, filters, scraping, user active jobs, save, hide, and reset.
- Shared `app/services` layer used by API and Discord to avoid duplicated logic.

## Important Runtime Settings

```text
NORMALIZATION_USE_GPT4FREE=true
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
DISCORD_GUILD_ID=...
SCRAPER_HEADLESS=true
```

`DISCORD_GUILD_ID` is recommended during development because Discord syncs guild slash commands much faster than global commands.

## Next Work

- Move Telegram bot onto the same service layer as Discord and API.
- Add API authentication before exposing it publicly.
- Add background scrape jobs instead of blocking `/scrape` calls for long runs.
- Add Alembic migrations for schema changes.
- Add a web dashboard that consumes the FastAPI endpoints.
- Add Discord scheduled notifications for newly found jobs.
