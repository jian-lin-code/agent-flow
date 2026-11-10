import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from app.utils.llm import get_llm_model

async def test():
    llm = get_llm_model(
        model_name="tongyi-intent-detect-v3",
        temp=0,
    )

    response = await llm.ainvoke([
        SystemMessage(
            content="""
    你是一个意图分类器。

    你只能从以下标签中选择一个：
    business_action
    business_query
    knowledge_query
    provide_information
    confirm_action
    cancel_action
    resume_action
    confirm_resume
    reject_resume
    small_talk
    unknown

    用户消息：重新发一笔报销，去年3月1号给公司交话费23423元。

    只输出一个标签，不允许复述用户消息。
    """
        ),
        HumanMessage(content="重新发一笔报销，去年3月1号给公司交话费23423元"),
    ])

    print(repr(response.content))


if __name__ == '__main__':
    asyncio.run(test())