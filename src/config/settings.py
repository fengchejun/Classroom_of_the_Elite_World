from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "ELITE_", "env_file": ".env", "extra": "ignore"}

    # Database
    database_url: str = "sqlite+aiosqlite:///elite_simulator.db"
    database_url_sync: str = "sqlite:///elite_simulator.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM - DeepSeek
    deepseek_api_key: str = "sk-a027465f568346db99147bb047d7a643"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.8

    # Forecaster (use cheaper model)
    forecaster_model: str = "deepseek-chat"
    forecaster_schedule_day: int = 7  # Sunday
    forecaster_schedule_slot: str = "evening"

    # Spotlight
    spotlight_max_npcs: int = 3
    spotlight_base_count: int = 2

    # Dialogue
    dialogue_summary_threshold: int = 10
    max_history_dialogues: int = 10

    # App
    debug: bool = False
    log_level: str = "INFO"

    @property
    def async_database_url(self) -> str:
        return self.database_url


settings = Settings()
