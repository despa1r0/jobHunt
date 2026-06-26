from functools import lru_cache
import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "jobHunt")
        self.app_env = os.getenv("APP_ENV", "dev")
        self.debug = _env_bool("DEBUG", default=False)

        self.postgres_user = os.getenv("POSTGRES_USER", "postgres")
        self.postgres_password = os.getenv("POSTGRES_PASSWORD", "postgres")
        self.postgres_host = os.getenv("POSTGRES_HOST", "localhost")
        self.postgres_port = os.getenv("POSTGRES_PORT", "5432")
        self.postgres_db = os.getenv("POSTGRES_DB", "jobhunt")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.discord_bot_token = os.getenv("DISCORD_BOT_TOKEN", "")
        self.discord_channel_id = os.getenv("DISCORD_CHANNEL_ID", "")
        self.discord_guild_id = os.getenv("DISCORD_GUILD_ID", "")
        self.discord_command_prefix = os.getenv("DISCORD_COMMAND_PREFIX", "!")
        self.scraper_headless = _env_bool(
            "SCRAPER_HEADLESS",
            default=self.app_env.lower() in {"docker", "prod", "production"},
        )
        self.scraper_navigation_timeout_ms = _env_int(
            "SCRAPER_NAVIGATION_TIMEOUT_MS",
            default=60000,
        )
        self.scraper_selector_timeout_ms = _env_int(
            "SCRAPER_SELECTOR_TIMEOUT_MS",
            default=10000,
        )
        self.scraper_retry_count = _env_int("SCRAPER_RETRY_COUNT", default=2)
        self.normalization_provider = os.getenv(
            "NORMALIZATION_PROVIDER",
            "",
        ).strip().lower()
        self.normalization_use_gpt4free = _env_bool(
            "NORMALIZATION_USE_GPT4FREE",
            default=False,
        )
        self.openmodel_api_key = os.getenv("OPENMODEL_API_KEY", "")
        self.openmodel_model = os.getenv("OPENMODEL_MODEL", "deepseek-v4-flash")
        self.openmodel_base_url = os.getenv(
            "OPENMODEL_BASE_URL",
            "https://api.openmodel.ai",
        ).rstrip("/")
        self.openmodel_timeout_seconds = _env_int(
            "OPENMODEL_TIMEOUT_SECONDS",
            default=90,
        )
        self.djinni_url = os.getenv(
            "DJINNI_URL",
            "https://djinni.co/jobs/?primary_keyword=Python&exp_level=no_exp",
        )
        self.praca_pl_url = os.getenv(
            "PRACA_PL_URL",
            "https://www.praca.pl/s-python.html",
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


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
