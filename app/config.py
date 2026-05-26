from functools import lru_cache
import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "jobHunt")
        self.app_env = os.getenv("APP_ENV", "dev")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"

        self.postgres_user = os.getenv("POSTGRES_USER", "postgres")
        self.postgres_password = os.getenv("POSTGRES_PASSWORD", "postgres")
        self.postgres_host = os.getenv("POSTGRES_HOST", "localhost")
        self.postgres_port = os.getenv("POSTGRES_PORT", "5432")
        self.postgres_db = os.getenv("POSTGRES_DB", "jobhunt")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.scraper_headless = os.getenv("SCRAPER_HEADLESS", "false").lower() == "true"
        self.djinni_url = os.getenv(
            "DJINNI_URL",
            "https://djinni.co/jobs/?primary_keyword=Python&exp_level=no_exp",
        )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
