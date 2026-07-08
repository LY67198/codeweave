from langchain.chat_models import init_chat_model

from codeweave.config.settings import Settings, get_settings


def get_chat_model(
    *,
    temperature: float | None = None,
    settings: Settings | None = None,
):
    """Get a configured chat model instance using LangChain's init_chat_model.

    Supports any OpenAI-compatible provider (DeepSeek, Qwen, GLM, OpenAI).
    """
    s = settings or get_settings()
    return init_chat_model(
        model=s.model_name,
        model_provider="openai",
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
        temperature=temperature if temperature is not None else s.model_temperature,
    )
