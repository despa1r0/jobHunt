# jobHunt

Small job scraper project for collecting vacancies, saving them to Postgres, and sending selected results to Telegram.

## Current flow

- `run_flow.py` reads `example.txt`, saves one vacancy to Postgres, and can send it to Telegram.
- `run_scraper.py` opens Djinni in Chromium with Playwright, parses visible vacancies, and saves them to Postgres.
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

Run example flow:

```powershell
.venv\Scripts\python.exe run_flow.py
```

Run headed Djinni scraper:

```powershell
.venv\Scripts\python.exe run_scraper.py
```
