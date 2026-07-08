from langchain.chat_models import init_chat_model

from codeweave.config.settings import Settings, get_settings


def get_chat_model(
    *,
    temperature: float | None = None,
    settings: Settings | None = None,
):
    """使用 LangChain 的 init_chat_model 获取配置好的聊天模型实例。

    支持任意兼容 OpenAI 的服务提供商(DeepSeek、Qwen、GLM、OpenAI)。
    若未显式传入 ``settings``,则使用由 ``get_settings()`` 缓存的全局实例。

    Args:
        temperature: 可选的温度参数,用于覆盖全局默认温度。
        settings: 可选的 Settings 实例,主要用于测试时注入。

    Returns:
        LangChain BaseChatModel 实例,可直接调用 ``.invoke()`` /
        ``.with_structured_output()`` 等方法。
    """
    s = settings or get_settings()
    return init_chat_model(
        model=s.model_name,
        model_provider="openai",
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
        temperature=temperature if temperature is not None else s.model_temperature,
    )