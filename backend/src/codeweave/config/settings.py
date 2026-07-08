from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === LLM 配置 ===
    openai_api_key: str = Field(default="sk-placeholder")
    openai_base_url: str = Field(default="https://api.deepseek.com/v1")
    model_name: str = Field(default="deepseek-chat")
    model_temperature: float = Field(default=0.0)

    # === 数据库 ===
    database_url: str = Field(default="postgresql://codeweave:codeweave_dev@localhost:5432/codeweave")

    # === Redis ===
    redis_url: str = Field(default="redis://localhost:6379/0")

    # === 上下文管理 ===
    compact_threshold: int = Field(default=32000)
    compact_enabled: bool = Field(default=True)
    plan_mode_default: bool = Field(default=True)

    # === 限制 ===
    max_react_iterations: int = Field(default=8)
    max_review_iterations: int = Field(default=3)
    max_recursion_limit: int = Field(default=50)

    # === 服务端 ===
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)


@lru_cache
def get_settings() -> Settings:
    """缓存的 Settings 实例。"""
    return Settings()
