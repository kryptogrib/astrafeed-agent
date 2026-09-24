"""Small, single-service configuration for the Token Brief engine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


def load_dotenv(path: Path) -> None:
    """Fill os.environ from a KEY=VALUE file; real environment variables win.

    Deliberately minimal (no interpolation, no export keyword) so `make login`,
    which writes TELEGRAM_SESSION into .env, works without extra dependencies.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class TelegramCfg(BaseModel):
    api_id: int = 0
    api_hash: str = ""
    session: str = ""


class OpenRouterCfg(BaseModel):
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    cheap_model: str = "deepseek/deepseek-v4-flash"
    strong_model: str = "deepseek/deepseek-v4-pro"
    score_parse_retries: int = 1
    score_max_items_per_batch: int = 40
    score_coverage_retries: int = 2
    score_token_limit_param: Literal["max_tokens", "max_completion_tokens"] | None = None
    score_max_tokens: int | None = None
    embedding_model: str = "openai/text-embedding-3-small"


class PrefilterCfg(BaseModel):
    min_length: int = 0
    blacklist_keywords: list[str] = Field(default_factory=list)
    drop_regexes: list[str] = Field(default_factory=list)


class AuditSettings(BaseModel):
    enabled: bool = True
    queue_events: int = Field(default=256, gt=0)
    queue_bytes: int = Field(default=16 * 1024 * 1024, gt=0)
    event_bytes: int = Field(default=4 * 1024 * 1024, gt=0)
    start_wait_seconds: float = Field(default=0.025, gt=0)
    cleanup_limit: int = Field(default=100, gt=0)
    cleanup_seconds: float = Field(default=60, gt=0)


class AgendaSettings(BaseModel):
    extract_concurrency: int = Field(default=12, ge=1, le=32)
    assign_concurrency: int = Field(default=16, ge=1, le=32)
    backfill_batch_size: int = Field(default=128, ge=1, le=256)
    cycle_post_limit: int = Field(default=128, ge=1, le=256)
    assignment_mode: Literal["auto", "strict", "relaxed"] = "auto"
    merge_cosine_threshold: float = Field(default=0.92, ge=0, le=1)


class Settings(BaseModel):
    database_url: str = "sqlite+aiosqlite:///astrafeed.db"
    language: str = "en"
    poll_seconds: int = Field(default=300, gt=0)
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, gt=0, le=65535)
    backfill_hours: int = Field(default=24, gt=0)
    ingestion_max_channels_first_run: int = Field(default=5, gt=0)
    ingestion_max_posts_per_channel: int = Field(default=200, gt=0)
    ingestion_max_posts_per_run: int = Field(default=1000, gt=0)
    llm_daily_budget_usd: float = Field(default=5.0, ge=0, allow_inf_nan=False)
    llm_reservation_usd: float = Field(default=0.5, gt=0)
    llm_max_tokens: int = Field(default=8192, gt=0)
    report_window_hours: int = Field(default=24, gt=0)
    report_min_importance: int = Field(default=1, ge=1, le=5)
    editorial_mode: Literal["off", "format", "insights"] = "format"
    dedup_window_days: int = Field(default=7, gt=0)
    telegram: TelegramCfg = Field(default_factory=TelegramCfg)
    openrouter: OpenRouterCfg = Field(default_factory=OpenRouterCfg)
    prefilter: PrefilterCfg = Field(default_factory=PrefilterCfg)
    channels: list[str] = Field(default_factory=list)
    # Public channels without comments: posts only, used as the "news" side of Pulse.
    news_channels: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=lambda: ["crypto markets"])
    audit: AuditSettings = Field(default_factory=AuditSettings)
    agenda: AgendaSettings = Field(default_factory=AgendaSettings)

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> Settings:
        config_path = Path(path)
        load_dotenv(config_path.parent / ".env")
        values = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
        values = values or {}
        # Environment variables take precedence over the YAML file.
        env_map = {
            "ASTRAFEED_DATABASE_URL": ("database_url",),
            "ASTRAFEED_LANGUAGE": ("language",),
            "ASTRAFEED_POLL_SECONDS": ("poll_seconds",),
            "ASTRAFEED_API_HOST": ("api_host",),
            "ASTRAFEED_API_PORT": ("api_port",),
            "TELEGRAM_API_ID": ("telegram", "api_id"),
            "TELEGRAM_API_HASH": ("telegram", "api_hash"),
            "TELEGRAM_SESSION": ("telegram", "session"),
            "OPENROUTER_API_KEY": ("openrouter", "api_key"),
            "OPENROUTER_BASE_URL": ("openrouter", "base_url"),
            "ASTRAFEED_LLM_DAILY_BUDGET_USD": ("llm_daily_budget_usd",),
        }
        for name, keys in env_map.items():
            if name not in os.environ:
                continue
            target = values
            for key in keys[:-1]:
                target = target.setdefault(key, {})
            target[keys[-1]] = os.environ[name]
        return cls.model_validate(values)
