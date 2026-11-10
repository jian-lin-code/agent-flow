"""LLM Token 使用量统计。"""

from langchain_core.callbacks import UsageMetadataCallbackHandler


def create_usage_callback() -> UsageMetadataCallbackHandler:
    """创建 Token 使用量回调。"""
    return UsageMetadataCallbackHandler()


def get_token_usage(
    callback: UsageMetadataCallbackHandler,
) -> dict[str, int]:
    """获取本次 LLM 调用的 Token 使用量。"""

    usage_records = callback.usage_metadata.values()

    input_tokens = sum(
        item.get("input_tokens", 0)
        for item in usage_records
    )

    output_tokens = sum(
        item.get("output_tokens", 0)
        for item in usage_records
    )

    total_tokens = sum(
        item.get("total_tokens", 0)
        for item in usage_records
    )

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def accumulate_token_usage(
    state: dict,
    usage: dict[str, int],
) -> dict[str, int]:
    """将本次调用的 Token 用量累加到状态。"""

    return {
        "input_tokens": (
            state.get("input_tokens", 0)
            + usage["input_tokens"]
        ),
        "output_tokens": (
            state.get("output_tokens", 0)
            + usage["output_tokens"]
        ),
        "total_tokens": (
            state.get("total_tokens", 0)
            + usage["total_tokens"]
        ),
        # 每累加一次用量即代表发生了一次真实的模型调用，
        # 供右侧执行面板展示「LLM 调用次数」。
        "llm_calls": (
            state.get("llm_calls", 0)
            + 1
        ),
    }