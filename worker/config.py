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
    is_prod = "K_SERVICE" in os.environ
    
    if is_prod:
        # En production, on vérifie que les secrets essentiels sont bien présents.
        # S'ils sont absents, cela signifie généralement un problème de configuration sur Cloud Run.
        
        # 1. Vérification de la base de données
        if settings.DATABASE_URL == settings._DEFAULT_DB_URL:
            raise ValueError(
                "FATAL: DATABASE_URL is not set correctly in the Cloud Run environment. "
                "This often indicates a problem with secret injection. "
                "Please check that the 'DATABASE_URL' secret is correctly mounted and that the service account has the 'Secret Manager Secret Accessor' role."
            )
        
        # 2. Vérification des identifiants Twitch
        missing_secrets = []
        if not settings.TWITCH_CLIENT_ID:
            missing_secrets.append("TWITCH_CLIENT_ID")
        if not settings.TWITCH_CLIENT_SECRET:
            missing_secrets.append("TWITCH_CLIENT_SECRET")
        
        if missing_secrets:
            raise ValueError(f"FATAL: The following required secrets are not set in the Cloud Run environment for the worker: {', '.join(missing_secrets)}. Please check your service configuration.")
            
    return settings
