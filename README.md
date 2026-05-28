# jobHunt

Small job scraper project for collecting vacancies, saving them to Postgres, and sending selected results to Telegram.

## Current flow

- `manual/run_scraper.py` opens Djinni in Chromium with Playwright, parses visible vacancies, and saves them to Postgres.
- `manual/run_bot_test.py` starts the temporary Telegram bot polling loop.
- Browser is visible by default because `SCRAPER_HEADLESS=false`.

## Local setup

Create `.env` from `.env.example` and fill real credentials:

```env
POSTGRES_PASSWORD=strongpass
POSTGRES_DB=postgres
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Install dependencies:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
```

Run headed Djinni scraper:

```powershell
.venv\Scripts\python.exe manual\run_scraper.py
```

Run test Telegram bot:

```powershell
.venv\Scripts\python.exe manual\run_bot_test.py
```

Useful bot commands:

```text
/start
/count
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
/scrape
```

Vacancy messages include inline buttons:

```text
Prev
Next
Not interested
```

`Not interested` removes the vacancy from the active list for the current chat.
Use `/reset_seen` if old vacancies disappeared from the active list and should be shown again.
