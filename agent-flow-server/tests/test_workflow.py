# 工作流相关测试
import asyncio

from app.agent_graph.workflow import build_agent_graph


async def main():
    graph = build_agent_graph()

    test_cases = [
        {
            "name": "发起报销",
            "current_message": "帮我提交一笔差旅报销",
            "history": [],
        },
        {
            "name": "补充报销金额",
            "current_message": "报销金额是860元",
            "history": [
                {
                    "role": "user",
                    "content": "帮我提交一笔差旅报销",
                },
                {
                    "role": "assistant",
                    "content": "好的，请告诉我报销金额。",
                },
            ],
        },
        {
            "name": "查询报销记录",
            "current_message": "查询我这个月的报销记录",
            "history": [],
        },
        {
            "name": "普通聊天",
            "current_message": "你好",
            "history": [],
        },
    ]

    for case in test_cases:
        print(f"\n{'=' * 60}")
        print(f"测试场景：{case['name']}")

        result = await graph.ainvoke(
            {
                "current_message": case["current_message"],
                "history": case["history"],
            }
        )

        intent = result["intent"]
        intent_value = getattr(intent, "value", intent)

        print("识别意图：", intent_value)
        print("置信度：", result["intent_confidence"])
        print("判断理由：", result["intent_reason"])
        print("AI 回复：", result["answer"])

        assert result["answer"]
        assert intent_value


if __name__ == "__main__":
    asyncio.run(main())