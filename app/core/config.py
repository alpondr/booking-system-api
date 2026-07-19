from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # pydantic-settings reads these from the .env file (or real env vars).
    # Field names are matched to env var names case-insensitively,
    # e.g. database_url <-> DATABASE_URL
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Single settings instance, imported wherever config is needed
settings = Settings()
