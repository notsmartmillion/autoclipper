from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"

    postgres_url: str
    redis_url: str

    yt_api_key: str | None = None
    yt_client_id: str | None = None
    yt_client_secret: str | None = None
    yt_refresh_token: str | None = None

    openai_api_key: str | None = None

    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_key: str | None = None
    s3_secret: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = False
