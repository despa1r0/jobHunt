from fastapi import FastAPI

from app.config import get_settings
from app.db import create_tables


settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)


@app.on_event("startup")
def on_startup() -> None:
    create_tables()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
