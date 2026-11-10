from functools import lru_cache
from langchain_openai import ChatOpenAI
from app.core.config import settings


@lru_cache(maxsize=10)
def get_llm_model(*,temp:float| None = None, model_name: str | None = None) -> ChatOpenAI:
    """
    工厂函数：根据传入的模型名称获取 ChatOpenAI 实例。
    :param model_name: 模型名称。如果不传，则使用 .env 中的默认配置。
    :param is_vision: 是否用于视觉多模态（如果是，默认使用视觉模型并降低 temperature）
    """
    # 确定使用的模型名
    if model_name:
        target_model = model_name
    else:
        target_model = settings.LLM_DEFAULT_MODEL
    temp = temp if temp is not None else settings.LLM_DEFAULT_TEMPERATURE
    # 直接返回 LangChain 的 ChatOpenAI 实例
    return ChatOpenAI(
        model=target_model,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE,
        temperature=temp,
        max_retries=settings.LLM_MAX_RETRIES,
        timeout=45,
    )