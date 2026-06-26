# jobHunt

Small job scraper project for collecting vacancies, normalizing them into JSON, saving them to Postgres, and sending selected results to Telegram or Discord.

## Current flow

- `manual/run_scraper.py` opens a selected source in Chromium with Playwright, parses visible vacancies, and saves them to Postgres.
- `manual/run_bot_test.py` starts the Telegram bot polling loop.
- `manual/run_discord_bot.py` starts the Discord slash-command bot.
- `app/main.py` exposes the FastAPI API for jobs, filters, user state, and scraping.
- Browser is visible locally when `SCRAPER_HEADLESS=false`.
- Docker/production-style runs can use `APP_ENV=docker` or `SCRAPER_HEADLESS=true`.
- Supported sources:
  - `djinni`
  - `praca_pl`

## Local setup

Create `.env` from `.env.example` and fill real credentials:

```env
POSTGRES_PASSWORD=strongpass
POSTGRES_DB=postgres
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=target_channel_id
DISCORD_GUILD_ID=dev_server_id
SCRAPER_HEADLESS=false
SCRAPER_NAVIGATION_TIMEOUT_MS=60000
SCRAPER_SELECTOR_TIMEOUT_MS=10000
SCRAPER_RETRY_COUNT=2
NORMALIZATION_USE_GPT4FREE=false
DJINNI_URL=https://djinni.co/jobs/?primary_keyword=Python&exp_level=no_exp
PRACA_PL_URL=https://www.praca.pl/s-python.html
```

Install dependencies:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
```

Run headed scraper:

```powershell
.venv\Scripts\python.exe manual\run_scraper.py
.venv\Scripts\python.exe manual\run_scraper.py praca_pl
```

Run test Telegram bot:

```powershell
.venv\Scripts\python.exe manual\run_bot_test.py
```

Run Discord bot:

```powershell
.venv\Scripts\python.exe manual\run_discord_bot.py
```

Run API locally:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Build the headless bot worker image:

```powershell
docker build -t jobhunt-bot .
```

Run the image with your environment file:

```powershell
docker run --env-file .env jobhunt-bot
```

## VPS deployment with Docker Compose

Copy the project to the server, create `.env` from `.env.example`, and set real values for:

```env
POSTGRES_PASSWORD=strongpass
POSTGRES_DB=jobhunt
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SCRAPER_HEADLESS=true
```

Start Postgres and the Telegram bot worker:

```bash
docker compose up -d --build postgres bot-worker
```

Optional API service:

```bash
docker compose --profile api up -d --build
```

Discord bot service:

```bash
docker compose --profile discord up -d --build postgres discord-worker
```

Check logs:

```bash
docker compose logs -f bot-worker
```

Rebuild the VPS after pulling new code:

```bash
git pull origin main
docker compose down
docker compose up -d --build postgres bot-worker
```

After schema-breaking changes, reset tables once:

```bash
docker compose exec bot-worker python manual/reset_db.py --yes
```

This drops and recreates ORM tables: `users`, `search_filters`, `jobs`, `user_jobs`, and `bot_states`.
It also removes legacy tables: `vacancies`, `vacancy_filters`, and `sent_vacancies`.

## Filters

Production filters are stored in Postgres and edited through Telegram commands:

```text
/set_source all
/set_keywords Python FastAPI
/set_experience no_exp,1y
/set_english pre,intermediate,upper
/set_location remote poznan
/include python fastapi sql backend
/exclude senior lead architect manager devops
/scrape all
```

For Praca.pl:

```text
/set_source praca_pl
/set_keywords python junior
/set_location warszawa
/include python sql backend
/exclude senior lead manager
```

Static examples live in `manual/filter_examples.py`. Use that file as a template for hardcoded local/manual filters, not as the production source of truth.

Multiple locations are treated as OR in post-filtering:

```text
/set_location remote poznan
```

This matches vacancies that mention `remote` or `poznan`. Polish diacritics are normalized, so `poznan` also matches `Poznań`.

`/scrape all` runs every supported source. `/set_source all` shows active vacancies from every supported source.

There is no hardcoded scraper limit. Scrapers parse all vacancy links visible on the loaded search page. API list endpoints are capped to 25 items, and `/latest` shows 5 items.

Useful bot commands:

```text
/start
/help
/count
/stats
/latest
/latest djinni
/active
/next
/new
/reset_seen
/filters
/set_keywords Python FastAPI
/set_experience no_exp,1y
/set_english pre,intermediate,upper
/set_location remote
/include python fastapi
/exclude senior lead
/clear_location
/clear_include
/clear_exclude
/set_source all
/set_source praca_pl
/scrape
/scrape all
```

Vacancy messages include inline buttons:

```text
Prev
Next
Details prev
Details next
Not interested
```

`Not interested` removes the vacancy from the active list for the current chat.
`Details prev` and `Details next` appear only when vacancy details are longer than one Telegram message.
Use `/reset_seen` if old vacancies disappeared from the active list and should be shown again.

Optional API endpoints:

```text
GET /health
GET /stats
GET /vacancies?limit=10
GET /vacancies?source=djinni&limit=5
GET /vacancies/{vacancy_id}
```

## Discord Bot

The Discord bot uses slash commands and sends vacancies as embeds built from `jobs.normalized_data`.
Start typing `/` in Discord to see command hints and parameter fields. Set `DISCORD_GUILD_ID`
for fast command sync on one server. Without it, Discord global slash commands can take time to appear.

Required Discord `.env` values:

```env
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
DISCORD_GUILD_ID=...
NORMALIZATION_USE_GPT4FREE=true
```

The bot needs these channel permissions:

```text
View Channel
Send Messages
Embed Links
Read Message History
Use Slash Commands
```

Run locally:

```powershell
.venv\Scripts\python.exe manual\run_discord_bot.py
```

Run with Docker Compose:

```bash
docker compose --profile discord up -d --build postgres discord-worker
```

Useful Discord commands:

```text
/menu
/count
/stats
/latest
/latest source:all
/filters
/set_source source:all
/set_keywords value:Python FastAPI
/set_experience value:no_exp,1y
/set_english value:pre,intermediate,upper
/set_location value:remote poznan
/include value:python sql backend
/exclude value:senior lead manager
/clear_location
/clear_include
/clear_exclude
/scrape
/scrape source:all
/new
/next
/prev
/reset_seen
```

Vacancy embeds include buttons: `Open`, `Prev`, `Next`, `Save`, and `Hide`.

## API

The API is the integration point for future UI clients. Discord and FastAPI share the same service layer, so the bot and API use the same filter, state, and scrape logic.

Useful endpoints:

```text
GET  /health
GET  /stats
GET  /sources
GET  /jobs?source=all&limit=10
GET  /jobs/{job_id}
POST /scrape
GET  /users/{user_key}/filters
PUT  /users/{user_key}/filters
GET  /users/{user_key}/jobs/active
GET  /users/{user_key}/jobs/active/count
POST /jobs/{job_id}/save
POST /jobs/{job_id}/hide
POST /users/{user_key}/jobs/reset-seen
```

Example scrape request:

```json
{
  "user_key": "discord:123456789",
  "source": "all"
}
```

Example filter update:

```json
{
  "source": "all",
  "search_keywords": "Python FastAPI",
  "location": "remote poznan",
  "include_keywords": "python sql backend",
  "exclude_keywords": "senior lead manager"
}
```

Old `/vacancies` endpoints are still available as aliases for `/jobs`.
