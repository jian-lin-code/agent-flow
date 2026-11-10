import asyncio

from app.agent_graph.nodes.classify_intent import classify_intent


async def main():
    test_cases = [
        {
            "current_message": "帮我提交一笔差旅报销",
            "history": [],
        },
        {
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
            "current_message": "确认提交",
            "history": [
                {
                    "role": "assistant",
                    "content": "信息已收集完成，是否确认提交？",
                },
            ],
        },
        {
            "current_message": "公司的差旅报销标准是什么？",
            "history": [],
        },
    ]

    for case in test_cases:
        result = await classify_intent(case)

        print("=" * 50)
        print("当前消息：", case["current_message"])
        print("识别结果：", result)


if __name__ == "__main__":
    asyncio.run(main())