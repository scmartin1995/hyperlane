"""Runtime configuration. Everything comes from environment variables / .env.

Secrets (API keys, Slack tokens, IMAP passwords) never go into the database;
they live only in the local .env file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # server
    host: str = Field("127.0.0.1", alias="HYPERLANE_HOST")
    port: int = Field(8787, alias="HYPERLANE_PORT")
    secret: str = Field("dev-secret-change-me", alias="HYPERLANE_SECRET")
    db_path: str = Field("./data/hyperlane.db", alias="HYPERLANE_DB_PATH")
    frontend_dist: str = Field(str(ROOT / "frontend" / "dist"), alias="HYPERLANE_FRONTEND_DIST")

    # llm
    llm_provider: str = Field("claude-code", alias="HYPERLANE_LLM_PROVIDER")  # anthropic | bedrock | claude-code
    llm_model: str = Field("claude-opus-5-5", alias="HYPERLANE_LLM_MODEL")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    aws_region: str | None = Field(None, alias="AWS_REGION")
    bedrock_model: str = Field("anthropic.claude-opus-5-5", alias="HYPERLANE_BEDROCK_MODEL")

    # slack
    slack_bot_token: str | None = Field(None, alias="SLACK_BOT_TOKEN")
    slack_app_token: str | None = Field(None, alias="SLACK_APP_TOKEN")
    slack_default_channel: str | None = Field(None, alias="SLACK_DEFAULT_CHANNEL")

    # teams
    teams_webhook_url: str | None = Field(None, alias="TEAMS_WEBHOOK_URL")

    # email intake
    intake_imap_host: str | None = Field(None, alias="INTAKE_IMAP_HOST")
    intake_imap_user: str | None = Field(None, alias="INTAKE_IMAP_USER")
    intake_imap_password: str | None = Field(None, alias="INTAKE_IMAP_PASSWORD")
    intake_imap_folder: str = Field("INBOX", alias="INTAKE_IMAP_FOLDER")
    intake_smtp_host: str | None = Field(None, alias="INTAKE_SMTP_HOST")
    intake_smtp_port: int = Field(587, alias="INTAKE_SMTP_PORT")
    intake_smtp_user: str | None = Field(None, alias="INTAKE_SMTP_USER")
    intake_smtp_password: str | None = Field(None, alias="INTAKE_SMTP_PASSWORD")
    intake_from_address: str | None = Field(None, alias="INTAKE_FROM_ADDRESS")
    intake_poll_seconds: int = Field(60, alias="INTAKE_POLL_SECONDS")

    @property
    def db_file(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else (ROOT / p)

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_bot_token and self.slack_app_token)

    @property
    def teams_enabled(self) -> bool:
        return bool(self.teams_webhook_url)

    @property
    def email_intake_enabled(self) -> bool:
        return bool(self.intake_imap_host and self.intake_imap_user and self.intake_imap_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
