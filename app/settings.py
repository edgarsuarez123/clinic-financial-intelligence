from dataclasses import dataclass,field
import os

@dataclass(frozen=True)
class Settings:
    database_url: str
    app_environment: str = "production"
    session_minutes: int = 30
    login_limit: int = 5
    login_window_seconds: int = 900
    log_level: str = "INFO"
    ingestion_config_path: str | None = None
    simulation_config_path: str | None = None
    analytics_config_path: str | None = None
    query_config_path: str | None = None
    query_database_url: str | None = field(default=None,repr=False)
    llm_api_key: str | None = field(default=None,repr=False)

    def __post_init__(self):
        if self.app_environment not in {"dev","test","staging","production"}: raise ValueError("Invalid APP_ENV")
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must use PostgreSQL")
        if not 1 <= self.session_minutes <= 1440:
            raise ValueError("SESSION_MINUTES must be between 1 and 1440")
        if self.login_limit < 1 or self.login_window_seconds < 1:
            raise ValueError("Login limits must be positive")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Invalid LOG_LEVEL")

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.environ["DATABASE_URL"],
            app_environment=os.getenv("APP_ENV","production"),
            session_minutes=int(os.getenv("SESSION_MINUTES", "30")),
            login_limit=int(os.getenv("LOGIN_LIMIT", "5")),
            login_window_seconds=int(os.getenv("LOGIN_WINDOW_SECONDS", "900")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            ingestion_config_path=os.getenv("INGESTION_CONFIG_PATH"),
            simulation_config_path=os.getenv("SIMULATION_CONFIG_PATH"),
            analytics_config_path=os.getenv("ANALYTICS_CONFIG_PATH"),
            query_config_path=os.getenv("QUERY_CONFIG_PATH"),
            query_database_url=os.getenv("QUERY_DATABASE_URL"),
            llm_api_key=os.getenv("LLM_API_KEY"),
        )
