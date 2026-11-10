
import asyncio
from pprint import pprint

from app.agent_graph.nodes.extract_expense_info import (
    extract_expense_info,
)


async def main():
    state = {
        "current_message": (
            "帮我提交一笔上海出差报销，"
            "高铁票500元，餐饮费360元，"
            "出差事由是参加客户项目会议。"
        ),
        "history": [],
    }

    result = await extract_expense_info(state)

    pprint(result)


if __name__ == "__main__":
    asyncio.run(main())
