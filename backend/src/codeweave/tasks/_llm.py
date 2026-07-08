"""LLM 摘要调用薄包装。便于测试 mock。"""
from __future__ import annotations

from codeweave.config.model import get_chat_model
from codeweave.config.settings import Settings
from codeweave.services.compact_logic import _ENC


def llm_summarize(prompt: str, settings: Settings) -> tuple[str, int]:
    """调模型摘要。返回 ``(summary_text, 估算 output tokens)``。

    Args:
        prompt: 完整的摘要 prompt(由 :func:`render_compact_prompt` 生成)。
        settings: 全局 :class:`Settings`,目前未直接使用,保留以便后续扩展
            (例如:模型选择、温度覆盖)。

    Returns:
        ``(summary_text, summary_tokens)`` 二元组,``summary_tokens`` 通过
        ``tiktoken`` ``cl100k_base`` 编码器估算。
    """
    del settings  # 当前实现不直接读 settings,保留参数便于未来切换模型
    llm = get_chat_model(temperature=0.0)
    response = llm.invoke(prompt)
    text = response.content if isinstance(response.content, str) else str(response.content)
    return text, len(_ENC.encode(text))