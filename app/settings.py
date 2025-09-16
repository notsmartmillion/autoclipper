# app/settings.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # pydantic-settings v2 config
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,   # env var names can be upper/lower
        extra="ignore",         # ignore unknown env keys instead of crashing
    )

    # ---- General
    app_env: str = "development"
    log_level: str = "INFO"

    # ---- Core services
    postgres_url: str | None = Field(default=None, alias="POSTGRES_URL")
    redis_url: str = Field(alias="REDIS_URL")

    # ---- Celery (optional; will fall back to redis_url if not provided)
    celery_broker_url: str | None = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(default=None, alias="CELERY_RESULT_BACKEND")

    # ---- YouTube / Google
    yt_api_key: str | None = Field(default=None, alias="YT_API_KEY")
    yt_client_id: str | None = Field(default=None, alias="YT_CLIENT_ID")
    yt_client_secret: str | None = Field(default=None, alias="YT_CLIENT_SECRET")
    yt_refresh_token: str | None = Field(default=None, alias="YT_REFRESH_TOKEN")

    # ---- OpenAI
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # ---- S3 (optional)
    s3_endpoint: str | None = Field(default=None, alias="S3_ENDPOINT")
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    s3_key: str | None = Field(default=None, alias="S3_KEY")
    s3_secret: str | None = Field(default=None, alias="S3_SECRET")

    # ---- Feature flags
    auto_pipeline_enabled: bool = Field(default=True, alias="AUTO_PIPELINE_ENABLED")
    publish_enabled: bool = Field(default=False, alias="PUBLISH_ENABLED")

    # ---- Back-compat UPPERCASE read-only properties
    @property
    def YT_API_KEY(self) -> str | None: return self.yt_api_key
    @property
    def YT_CLIENT_ID(self) -> str | None: return self.yt_client_id
    @property
    def YT_CLIENT_SECRET(self) -> str | None: return self.yt_client_secret
    @property
    def YT_REFRESH_TOKEN(self) -> str | None: return self.yt_refresh_token
    @property
    def OPENAI_API_KEY(self) -> str | None: return self.openai_api_key
    @property
    def POSTGRES_URL(self) -> str | None: return self.postgres_url
    @property
    def REDIS_URL(self) -> str: return self.redis_url
    @property
    def PUBLISH_ENABLED(self) -> bool: return self.publish_enabled
    @property
    def AUTO_PIPELINE_ENABLED(self) -> bool: return self.auto_pipeline_enabled

    # ---- Helpers for Celery wiring (prefer explicit env, fall back to REDIS_URL)
    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


# module-level singleton
S = Settings()
