import os
from functools import lru_cache


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "nanohero")
    ENV: str = os.getenv("ENV", "dev")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Security / JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev_secret_change_me")
    JWT_ALG: str = os.getenv("JWT_ALG", "HS256")

    # CORS
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "https://overlay.nanohero.io,https://*.nanohero.io,http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173",
    )

    # Database
    _DEFAULT_DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/nanohero"
    DATABASE_URL: str = os.getenv("DATABASE_URL", _DEFAULT_DB_URL)

    # Twitch API
    TWITCH_CLIENT_ID: str = os.getenv("TWITCH_CLIENT_ID", "")
    TWITCH_CLIENT_SECRET: str = os.getenv("TWITCH_CLIENT_SECRET", "")
    TWITCH_APP_ACCESS_TOKEN: str | None = os.getenv("TWITCH_APP_ACCESS_TOKEN")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # K_SERVICE est une variable d'environnement définie par Cloud Run.
    # Si elle existe et que la DATABASE_URL est toujours la valeur par défaut,
    # cela signifie que l'injection de secret a échoué.
    if os.getenv("K_SERVICE") and settings.DATABASE_URL == settings._DEFAULT_DB_URL:
        raise ValueError(
            "FATAL: DATABASE_URL is not set in the Cloud Run environment. "
            "This indicates a problem with secret injection. "
            "Please check that all required secrets exist and that the service account has the 'Secret Manager Secret Accessor' role for EACH of them."
        )
    return settings

