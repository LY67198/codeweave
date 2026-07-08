from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CodeWeave 全局配置,使用 pydantic-settings 从环境变量加载。

    配置项包括 LLM、数据库、Redis、上下文、限制和服务端口。

    Attributes:
        openai_api_key: OpenAI 兼容 API Key。
        openai_base_url: API 基础 URL(支持 DeepSeek/Qwen/GLM 等)。
        model_name: 模型名称(如 deepseek-chat)。
        model_temperature: 模型温度参数,0.0 表示确定性输出。
        database_url: PostgreSQL 连接 URL。
        redis_url: Redis 连接 URL。
        compact_threshold: 触发自动压缩的 token 阈值,默认 32000。
        compact_enabled: 是否启用自动压缩。
        plan_mode_default: 是否默认进入 Plan Mode。
        max_react_iterations: ReAct 循环最大迭代次数。
        max_review_iterations: Coder ↔ Reviewer 循环最大迭代次数。
        max_recursion_limit: LangGraph 递归限制。
        api_host: API 服务监听地址。
        api_port: API 服务监听端口。
    """
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
    """获取全局缓存的 Settings 实例。

    使用 ``functools.lru_cache`` 实现单例模式,进程内只会构造一次。

    Returns:
        全局共享的 Settings 实例(单例)。
    """
    return Settings()