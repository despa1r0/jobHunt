FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV APP_ENV=docker
ENV SCRAPER_HEADLESS=true
ENV SCRAPER_NAVIGATION_TIMEOUT_MS=60000
ENV SCRAPER_SELECTOR_TIMEOUT_MS=10000
ENV SCRAPER_RETRY_COUNT=2

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY manual ./manual

CMD ["python", "manual/run_bot_test.py"]
